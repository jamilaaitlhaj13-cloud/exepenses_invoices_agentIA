import sys
import json
import tempfile
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from PIL import ImageFilter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.document_verifier_tool import DocumentVerifierTool
from tools.ocr_extraction_tool import OCRExtractionTool
from tools.ai_classifier_tool import AIClassifierTool
from tools.image_enhancer_tool import ImageEnhancerTool
from models.invoice import Invoice

# ── Paths ──────────────────────────────────────────────────────────────────────
BATCH_DIR   = Path("C:/Users/LENOVO/Downloads/batch_1/batch_1")
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BATCHES = [
    {"images": BATCH_DIR / "batch1_1", "csv": BATCH_DIR / "batch1_1.csv"},
    {"images": BATCH_DIR / "batch1_2", "csv": BATCH_DIR / "batch1_2.csv"},
    {"images": BATCH_DIR / "batch1_3", "csv": BATCH_DIR / "batch1_3.csv"},
]

MAX_WORKERS       = 5       # Parallel API calls (OCR + LLM)
OPTIMAL_THRESHOLD = 0.3725  # Optimal threshold found after DiT fine-tuning

# ── Cache helpers ──────────────────────────────────────────────────────────────
def load_cache(name: str) -> pd.DataFrame | None:
    """Load cached results if they exist."""
    path = RESULTS_DIR / f"cache_{name}.csv"
    if path.exists():
        print(f"  [cache] Loading {name} from cache...")
        return pd.read_csv(path)
    return None

def save_cache(df: pd.DataFrame, name: str):
    """Save results to cache."""
    df.to_csv(RESULTS_DIR / f"cache_{name}.csv", index=False)

# ── Step 1: Load dataset (200 images balanced across 3 batches) ───────────────
def load_dataset(n_per_batch: int = 67) -> pd.DataFrame:
    """Load n_per_batch images from each batch -> ~200 total."""
    dfs = []
    for batch in BATCHES:
        df = pd.read_csv(batch["csv"])
        df["image_path"] = df["File Name"].apply(
            lambda f: str(batch["images"] / f)
        )
        df["batch"] = batch["csv"].stem
        dfs.append(df.head(n_per_batch))
    result = pd.concat(dfs, ignore_index=True)
    print(f"  batch1_1 : {(result['batch']=='batch1_1').sum()} images")
    print(f"  batch1_2 : {(result['batch']=='batch1_2').sum()} images")
    print(f"  batch1_3 : {(result['batch']=='batch1_3').sum()} images")
    return result

# ── Step 2: DiT Classifier (parallel) ────────────────────────────────────────
def _dit_single(row: dict, verifier: DocumentVerifierTool) -> dict:
    """Classify one image with DiT."""
    try:
        is_invoice, confidence, confidence_level = verifier.verify(Path(row["image_path"]))
        status = "correct" if is_invoice else "false_negative"
    except Exception as e:
        is_invoice, confidence, confidence_level = False, 0.0, "error"
        status = f"error: {str(e)}"

    print(f"[DiT] {row['File Name']} -> {status} (conf={confidence:.2f})")
    return {
        "file_name":        row["File Name"],
        "image_path":       row["image_path"],
        "batch":            row["batch"],
        "is_invoice":       is_invoice,
        "confidence":       confidence,
        "confidence_level": confidence_level,
        "dit_status":       status,
    }

def evaluate_dit_classifier(df: pd.DataFrame) -> pd.DataFrame:
    """Evaluate DiT classifier in parallel (DiT is local so thread-safe)."""
    cached = load_cache("dit")
    if cached is not None:
        return cached

    verifier = DocumentVerifierTool()
    verifier.set_threshold(OPTIMAL_THRESHOLD)
    rows     = df.to_dict("records")
    results  = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_dit_single, row, verifier): row for row in rows}
        for future in as_completed(futures):
            results.append(future.result())

    result_df = pd.DataFrame(results)
    save_cache(result_df, "dit")
    return result_df

# ── Step 3: OCR Evaluation (parallel) ────────────────────────────────────────
def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER)."""
    ref = list(str(reference))
    hyp = list(str(hypothesis))
    r, h = len(ref), len(hyp)
    dp = [[0] * (h + 1) for _ in range(r + 1)]
    for i in range(r + 1): dp[i][0] = i
    for j in range(h + 1): dp[0][j] = j
    for i in range(1, r + 1):
        for j in range(1, h + 1):
            dp[i][j] = dp[i-1][j-1] if ref[i-1] == hyp[j-1] else \
                       1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[r][h] / max(r, 1)

def invoice_to_text(invoice: Invoice) -> str:
    """Convert Invoice fields to flat string for CER comparison."""
    parts = [invoice.vendor_name or "", invoice.customer_name or "",
             invoice.invoice_id or "", str(invoice.invoice_date or ""),
             str(invoice.total_amount or ""), invoice.currency or ""]
    return " ".join(p for p in parts if p)

def _ocr_single(row: dict, df: pd.DataFrame) -> dict:
    """Run OCR on one image."""
    ocr_tool     = OCRExtractionTool()
    ground_truth = df.loc[df["File Name"] == row["file_name"], "OCRed Text"].values
    ground_truth = ground_truth[0] if len(ground_truth) > 0 else ""
    try:
        invoice  = Invoice(source_file=Path(row["image_path"]))
        invoice  = ocr_tool.extract(invoice)
        ocr_text = invoice_to_text(invoice)
        cer      = compute_cer(str(ground_truth), ocr_text)
        status   = "success"
    except Exception as e:
        cer, status = 1.0, f"error: {str(e)}"

    print(f"[OCR] {row['file_name']} -> CER={cer:.4f} | {status}")
    return {"file_name": row["file_name"], "cer": round(cer, 4), "ocr_status": status}

def evaluate_ocr(df: pd.DataFrame, dit_results: pd.DataFrame) -> pd.DataFrame:
    """Evaluate OCR in parallel on images accepted by DiT."""
    cached = load_cache("ocr")
    if cached is not None:
        return cached

    accepted = dit_results[dit_results["dit_status"] == "correct"].to_dict("records")
    if not accepted:
        return pd.DataFrame(columns=["file_name", "cer", "ocr_status"])

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_ocr_single, row, df): row for row in accepted}
        for future in as_completed(futures):
            results.append(future.result())

    result_df = pd.DataFrame(results)
    save_cache(result_df, "ocr")
    return result_df

# ── Step 4: LLM Extraction Evaluation (parallel) ─────────────────────────────
FIELDS_TO_CHECK  = ["client_name", "seller_name", "invoice_number",
                    "invoice_date", "total_amount", "currency"]
INVOICE_FIELD_MAP = {
    "client_name":    "customer_name",
    "seller_name":    "vendor_name",
    "invoice_number": "invoice_id",
    "invoice_date":   "invoice_date",
    "total_amount":   "total_amount",
    "currency":       "currency",
}

def _llm_single(row: dict, df: pd.DataFrame) -> dict:
    """Run OCR + LLM extraction on one image."""
    ocr_tool = OCRExtractionTool()
    ai_tool  = AIClassifierTool()

    gt_raw = df.loc[df["File Name"] == row["file_name"], "Json Data"].values
    gt_raw = gt_raw[0] if len(gt_raw) > 0 else "{}"
    try:
        ground_truth = json.loads(gt_raw).get("invoice", {})
    except json.JSONDecodeError:
        ground_truth = {}

    try:
        invoice = Invoice(source_file=Path(row["image_path"]))
        invoice = ocr_tool.extract(invoice)
        invoice = ai_tool.classify(invoice)
        status  = "success"
    except Exception as e:
        invoice, status = None, f"error: {str(e)}"

    field_scores = {}
    for field in FIELDS_TO_CHECK:
        pred_val = str(getattr(invoice, INVOICE_FIELD_MAP.get(field, field), "") or "").strip().lower() if invoice else ""
        gt_val   = str(ground_truth.get(field, "")).strip().lower()
        field_scores[field] = (pred_val == gt_val)

    precision = sum(field_scores.values()) / len(FIELDS_TO_CHECK)
    print(f"[LLM] {row['file_name']} -> precision={precision:.2f} | {status}")

    record = {"file_name": row["file_name"], "llm_status": status, "precision": round(precision, 4)}
    record.update({f"field_{f}": v for f, v in field_scores.items()})
    return record

def evaluate_llm_extraction(df: pd.DataFrame, dit_results: pd.DataFrame) -> pd.DataFrame:
    """Evaluate LLM extraction in parallel."""
    cached = load_cache("llm")
    if cached is not None:
        return cached

    accepted = dit_results[dit_results["dit_status"] == "correct"].to_dict("records")
    if not accepted:
        return pd.DataFrame(columns=["file_name", "llm_status", "precision"])

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_llm_single, row, df): row for row in accepted}
        for future in as_completed(futures):
            results.append(future.result())

    result_df = pd.DataFrame(results)
    save_cache(result_df, "llm")
    return result_df

# ── Step 5: End-to-end (reuse DiT results, parallel OCR+LLM) ─────────────────
def _e2e_single(row: dict, dit_status: str) -> dict:
    """Run one image through full pipeline."""
    ocr_tool = OCRExtractionTool()
    ai_tool  = AIClassifierTool()
    step     = "dit"
    status   = "failed"

    try:
        if dit_status != "correct":
            status = "rejected_by_dit"
            raise StopIteration
        step    = "ocr"
        invoice = Invoice(source_file=Path(row["image_path"]))
        invoice = ocr_tool.extract(invoice)
        step    = "llm"
        invoice = ai_tool.classify(invoice)
        status  = "success"
    except StopIteration:
        pass
    except Exception as e:
        status = f"error_at_{step}: {str(e)}"

    print(f"[E2E] {row['File Name']} -> {status}")
    return {"file_name": row["File Name"], "e2e_status": status}

def evaluate_end_to_end(df: pd.DataFrame, dit_results: pd.DataFrame) -> pd.DataFrame:
    """Run full pipeline in parallel, reusing DiT results."""
    cached = load_cache("e2e")
    if cached is not None:
        return cached

    dit_map = dict(zip(dit_results["file_name"], dit_results["dit_status"]))
    rows    = df.to_dict("records")
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_e2e_single, row, dit_map.get(row["File Name"], "error")): row
            for row in rows
        }
        for future in as_completed(futures):
            results.append(future.result())

    result_df = pd.DataFrame(results)
    save_cache(result_df, "e2e")
    return result_df

# ── Step 6: Robustness test (50 degraded images, parallel) ───────────────────
def _rob_single(row: dict, verifier: DocumentVerifierTool,
                enhancer: ImageEnhancerTool) -> dict:
    """Degrade one image and compare DiT with/without enhancement."""
    original_path = Path(row["image_path"])
    img = enhancer.load_image(original_path)
    if img is None:
        return None

    img_degraded = img.filter(ImageFilter.GaussianBlur(radius=2))
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        img_degraded.save(tmp.name, "JPEG", quality=20)
        degraded_path = Path(tmp.name)

    try:
        detected_no_enhance, conf_no, _ = verifier.verify(degraded_path)
    except Exception:
        detected_no_enhance, conf_no = False, 0.0

    try:
        enhanced_path, _             = enhancer.enhance_for_attempt(degraded_path, attempt=2)
        detected_enhanced, conf_e, _ = verifier.verify(enhanced_path)
        enhancer.cleanup(enhanced_path)
    except Exception:
        detected_enhanced, conf_e = False, 0.0

    enhancer.cleanup(degraded_path)

    print(f"[ROB] {row['File Name']} -> no_enhance={detected_no_enhance}({conf_no:.2f}) | enhanced={detected_enhanced}({conf_e:.2f})")
    return {
        "file_name":           row["File Name"],
        "batch":               row["batch"],
        "detected_no_enhance": detected_no_enhance,
        "conf_no_enhance":     round(conf_no, 4),
        "detected_enhanced":   detected_enhanced,
        "conf_enhanced":       round(conf_e, 4),
        "improvement":         detected_enhanced and not detected_no_enhance,
    }

def evaluate_robustness(df: pd.DataFrame, n_degraded: int = 50) -> pd.DataFrame:
    """Degrade n_degraded images (~17 per batch) and test ImageEnhancer."""
    cached = load_cache("rob")
    if cached is not None:
        return cached

    sample = (df.groupby("batch", group_keys=False)
                .apply(lambda x: x.head(n_degraded // 3))
                .reset_index(drop=True))

    verifier = DocumentVerifierTool()
    verifier.set_threshold(OPTIMAL_THRESHOLD)
    enhancer = ImageEnhancerTool()
    rows     = sample.to_dict("records")
    results  = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_rob_single, row, verifier, enhancer): row for row in rows}
        for future in as_completed(futures):
            r = future.result()
            if r is not None:
                results.append(r)

    result_df = pd.DataFrame(results)
    save_cache(result_df, "rob")
    return result_df

# ── Step 7: Save report ───────────────────────────────────────────────────────
def save_report(dit_df, ocr_df, llm_df, e2e_df, rob_df):
    """Merge all results and save to CSV."""
    report = dit_df[["file_name", "dit_status", "confidence"]].copy()
    if not ocr_df.empty and "file_name" in ocr_df.columns:
        report = report.merge(ocr_df[["file_name", "cer", "ocr_status"]], on="file_name", how="left")
    if not llm_df.empty and "file_name" in llm_df.columns:
        report = report.merge(llm_df[["file_name", "precision", "llm_status"]], on="file_name", how="left")
    if not e2e_df.empty and "file_name" in e2e_df.columns:
        report = report.merge(e2e_df[["file_name", "e2e_status"]], on="file_name", how="left")
    report.to_csv(RESULTS_DIR / "evaluation_report.csv", index=False)
    print(f"\nReport saved -> {RESULTS_DIR / 'evaluation_report.csv'}")

# ── Step 8: Generate evaluation dashboard ────────────────────────────────────
def generate_charts(dit_df, ocr_df, llm_df, e2e_df, rob_df):
    """Generate and save evaluation dashboard as PNG."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("SmartExpenseAgent — Pipeline Evaluation Dashboard (200 images)",
                 fontsize=16, fontweight="bold", y=0.98)
    C = {"ok": "#2ecc71", "err": "#e74c3c", "warn": "#e67e22", "blue": "#3498db"}

    # Chart 1: DiT Results (pie)
    ax = axes[0, 0]
    counts = dit_df["dit_status"].value_counts()
    colors = [C["ok"] if s == "correct" else C["err"] for s in counts.index]
    ax.pie(counts.values, labels=counts.index, autopct="%1.1f%%",
           colors=colors, startangle=90, textprops={"fontsize": 10})
    ax.set_title("DiT Classifier Results", fontweight="bold")

    # Chart 2: DiT Confidence Distribution
    ax = axes[0, 1]
    ax.hist(dit_df["confidence"], bins=20, color=C["blue"], edgecolor="white", alpha=0.85)
    mean_conf = dit_df["confidence"].mean()
    ax.axvline(mean_conf, color="red", linestyle="--", label=f"Mean={mean_conf:.2f}")
    ax.axvline(OPTIMAL_THRESHOLD, color="orange", linestyle="-",
               linewidth=2, label=f"Threshold={OPTIMAL_THRESHOLD}")
    ax.set_xlabel("Confidence Score")
    ax.set_ylabel("Number of Images")
    ax.set_title("DiT Confidence Distribution", fontweight="bold")
    ax.legend()

    # Chart 3: OCR CER Distribution
    ax = axes[0, 2]
    if not ocr_df.empty and "cer" in ocr_df.columns:
        cer_ok = ocr_df[ocr_df["ocr_status"] == "success"]["cer"]
        ax.hist(cer_ok, bins=20, color=C["blue"], edgecolor="white", alpha=0.85)
        ax.axvline(cer_ok.mean(), color="red", linestyle="--", label=f"Mean CER={cer_ok.mean():.3f}")
        ax.set_xlabel("Character Error Rate (CER)")
        ax.set_ylabel("Number of Images")
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No OCR data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
    ax.set_title("OCR — Character Error Rate", fontweight="bold")

    # Chart 4: LLM Field Precision
    ax = axes[1, 0]
    if not llm_df.empty and "precision" in llm_df.columns:
        field_cols  = [c for c in llm_df.columns if c.startswith("field_")]
        field_names = [c.replace("field_", "") for c in field_cols]
        field_means = [llm_df[c].mean() * 100 for c in field_cols]
        bars = ax.bar(field_names, field_means,
                      color=[C["ok"] if v >= 70 else C["err"] for v in field_means],
                      edgecolor="white", alpha=0.85)
        ax.set_ylim(0, 115)
        ax.set_ylabel("Precision (%)")
        ax.set_xticklabels(field_names, rotation=30, ha="right", fontsize=9)
        for bar, val in zip(bars, field_means):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=8)
    else:
        ax.text(0.5, 0.5, "No LLM data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
    ax.set_title("LLM Extraction Precision (per field)", fontweight="bold")

    # Chart 5: E2E Pipeline Status
    ax = axes[1, 1]
    if not e2e_df.empty:
        e2e_counts = e2e_df["e2e_status"].value_counts()
        bar_colors = [C["ok"] if "success" in s else C["err"] for s in e2e_counts.index]
        bars = ax.bar(e2e_counts.index, e2e_counts.values,
                      color=bar_colors, edgecolor="white", alpha=0.85)
        ax.set_ylabel("Number of Images")
        ax.set_xticklabels(e2e_counts.index, rotation=20, ha="right", fontsize=9)
        for bar, val in zip(bars, e2e_counts.values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    str(val), ha="center", va="bottom", fontsize=9)
    ax.set_title("End-to-End Pipeline Status", fontweight="bold")

    # Chart 6: Robustness — confidence before/after
    ax = axes[1, 2]
    if not rob_df.empty and "conf_no_enhance" in rob_df.columns:
        x     = np.arange(len(rob_df))
        w     = 0.35
        ax.bar(x - w/2, rob_df["conf_no_enhance"], w, label="Degraded", color=C["err"], alpha=0.8)
        ax.bar(x + w/2, rob_df["conf_enhanced"],   w, label="Enhanced", color=C["ok"],  alpha=0.8)
        ax.set_ylabel("DiT Confidence Score")
        ax.set_xlabel("Image Index")
        ax.legend(fontsize=9)
        ax.set_xticks([])
        improved = rob_df["improvement"].sum()
        ax.text(0.5, 0.95, f"Improvement: {improved}/{len(rob_df)} images",
                transform=ax.transAxes, ha="center", va="top",
                fontsize=10, color="darkgreen", fontweight="bold")
    else:
        ax.text(0.5, 0.5, "No robustness data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
    ax.set_title("Robustness — ImageEnhancer Impact\n(50 degraded images)", fontweight="bold")

    plt.tight_layout()
    out = RESULTS_DIR / "evaluation_dashboard.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Dashboard saved -> {out}")

    print("\n========== EVALUATION SUMMARY ==========")
    print(f"Total images tested  : {len(dit_df)}")
    print(f"DiT accuracy         : {(dit_df['dit_status']=='correct').mean()*100:.2f}%")
    if not ocr_df.empty and "cer" in ocr_df.columns:
        print(f"Mean CER (OCR)       : {ocr_df['cer'].mean():.4f}")
    if not llm_df.empty and "precision" in llm_df.columns:
        print(f"Mean field precision : {llm_df['precision'].mean()*100:.2f}%")
    if not e2e_df.empty:
        print(f"E2E success rate     : {(e2e_df['e2e_status']=='success').mean()*100:.2f}%")
    if not rob_df.empty and "improvement" in rob_df.columns:
        print(f"Enhancer improvement : {rob_df['improvement'].sum()} / {len(rob_df)} images")
    print("=========================================")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading dataset (200 images — ~67 per batch)...")
    df = load_dataset(n_per_batch=67)
    print(f"Dataset loaded: {len(df)} images\n")

    print("--- Step 2: DiT Classifier Evaluation ---")
    dit_results = evaluate_dit_classifier(df)

    print("\n--- Step 3: OCR Evaluation ---")
    ocr_results = evaluate_ocr(df, dit_results)

    print("\n--- Step 4: LLM Extraction Evaluation ---")
    llm_results = evaluate_llm_extraction(df, dit_results)

    print("\n--- Step 5: End-to-End Pipeline ---")
    e2e_results = evaluate_end_to_end(df, dit_results)

    print("\n--- Step 6: Robustness Test (50 degraded images) ---")
    rob_results = evaluate_robustness(df, n_degraded=50)

    print("\n--- Step 7: Saving Report ---")
    save_report(dit_results, ocr_results, llm_results, e2e_results, rob_results)

    print("\n--- Step 8: Generating Dashboard ---")
    generate_charts(dit_results, ocr_results, llm_results, e2e_results, rob_results)