"""DocumentVerifierTool
Verifies visually if a downloaded document is an invoice
using the fine-tuned DiT (Document Image Transformer).

Input  : path to a PDF or image file
Output : (is_invoice: bool, score: float, confidence_level: str)
"""

import json
import logging
from pathlib import Path
from typing import Tuple
import torch
from PIL import Image
from transformers import (
    BeitImageProcessor,
    BeitForImageClassification,)

logger = logging.getLogger(__name__)
MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "dit_invoice_classifier"

class DocumentVerifierTool:
    """
    Visually verifies if a document is an invoice.
    Uses DiT (Document Image Transformer) fine-tuned on invoiceXpert.
    """

    def __init__(self):
        logger.info("Loading DiT Document Verifier...")
        
        if not MODEL_DIR.exists():
            raise FileNotFoundError(
                f"DiT model not found at {MODEL_DIR.absolute()}.\n"
                f"Download the model from Kaggle and extract it to {MODEL_DIR}"
            )
        self.processor = BeitImageProcessor.from_pretrained(str(MODEL_DIR))
        self.model = BeitForImageClassification.from_pretrained(str(MODEL_DIR))
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()
        self.threshold = self._load_threshold()
        
        logger.info(f"DiT Document Verifier ready")
        logger.info(f"   Model      : microsoft/dit-base (fine-tuned)")
        logger.info(f"   Dataset    : invoiceXpert (FATURA2 + RVL-CDIP)")
        logger.info(f"   Device     : {self.device}")
        logger.info(f"   Threshold  : {self.threshold:.4f}")
        logger.info(f"   Parameters : {self.model.num_parameters():,}")

    def _load_threshold(self) -> float:
        """Load the optimal threshold from model files."""
        threshold_file = MODEL_DIR / "optimal_threshold.json"
        if threshold_file.exists():
            try:
                with open(threshold_file, 'r') as f:
                    data = json.load(f)
                    threshold = data.get("optimal_threshold", 0.3725)
                    logger.info(f"   Loaded optimal threshold: {threshold:.4f}")
                    return threshold
            except Exception as e:
                logger.warning(f"Could not load threshold file: {e}")
        
        logger.info("   Using default threshold: 0.3725")
        return 0.3725

    def verify(self, file_path: Path) -> Tuple[bool, float, str]:
        """
        Verify if the document is visually an invoice.
        Args:
            file_path: Path to the file (PDF or image)
        Returns:
            (is_invoice, confidence_score, confidence_level)
        """
        try:
            image = self._load_document(file_path)
        except Exception as e:
            logger.error(f"Cannot load {file_path.name}: {e}")
            return False, 0.0, "error"
        try:
            score, is_invoice, confidence_level = self._classify(image)
            logger.info(
                f"DiT → '{file_path.name}' : "
                f"score={score:.4f} ({confidence_level} confidence) → "
                f"{'invoice' if is_invoice else 'non-invoice'}"
            )
            return is_invoice, score, confidence_level

        except Exception as e:
            logger.error(f"Classification error for {file_path.name}: {e}")
            return False, 0.0, "error"

    def _load_document(self, file_path: Path) -> Image.Image:
        """Load first page of PDF or image directly."""
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            return self._pdf_to_image(file_path)
        elif ext in {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}:
            return Image.open(file_path).convert("RGB")
        else:
            raise ValueError(f"Unsupported format: {ext}")

    def _pdf_to_image(self, pdf_path: Path) -> Image.Image:
        """Convert first page of PDF to PIL Image."""
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(
                str(pdf_path),
                dpi=200,
                first_page=1,
                last_page=1
            )
            if pages:
                return pages[0].convert("RGB")
            raise ValueError("PDF is empty or unreadable")
        except ImportError:
            raise RuntimeError(
                "pdf2image not installed. Run: pip install pdf2image"
            )

    def _classify(self, image: Image.Image) -> Tuple[float, bool, str]:
        """Classify image with DiT."""
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1)
            score = probs[0][0].item()
        is_invoice = score >= self.threshold
        
        confidence_gap = abs(score - 0.5) * 2
        if confidence_gap > 0.6:
            confidence_level = "high"
        elif confidence_gap > 0.2:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        return score, is_invoice, confidence_level

    def get_model_info(self) -> dict:
        """Return information about the loaded model."""
        return {
            "model_type": self.model.config.model_type,
            "model_path": str(MODEL_DIR.absolute()),
            "device": str(self.device),
            "threshold": self.threshold,
            "parameters": self.model.num_parameters(),
        }

    def set_threshold(self, new_threshold: float):
        """Update the classification threshold."""
        if not 0 <= new_threshold <= 1:
            raise ValueError(f"Threshold must be between 0 and 1, got {new_threshold}")
        
        old_threshold = self.threshold
        self.threshold = new_threshold
        logger.info(f"Threshold updated: {old_threshold:.4f} → {new_threshold:.4f}")