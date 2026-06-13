# backend_fastapi/routers/invoices.py
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from database import get_db
from models import InvoiceRecord
from schemas import InvoiceCreate, InvoiceResponse
from auth_utils import get_current_company

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "backend_fastapi", "media")
os.makedirs(MEDIA_ROOT, exist_ok=True)


@router.get("/")
def list_invoices(
    status:   Optional[str] = None,
    category: Optional[str] = None,
    source:   Optional[str] = None,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    qs = db.query(InvoiceRecord).filter(InvoiceRecord.company_id == company.id)
    if status:
        qs = qs.filter(InvoiceRecord.status == status)
    if category:
        qs = qs.filter(InvoiceRecord.expense_category == category)
    if source:
        qs = qs.filter(InvoiceRecord.source == source)
    return [InvoiceResponse.model_validate(i) for i in qs.all()]


@router.post("/", status_code=201)
def create_invoice(
    data: InvoiceCreate,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    invoice = InvoiceRecord(**data.model_dump(), company_id=company.id)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)


@router.get("/stats/")
def get_stats(
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    qs = db.query(InvoiceRecord).filter(InvoiceRecord.company_id == company.id)
    total       = qs.count()
    validated   = qs.filter(InvoiceRecord.status == "validated").count()
    rejected    = qs.filter(InvoiceRecord.status == "rejected").count()
    need_review = qs.filter(InvoiceRecord.status == "need_review").count()
    total_amount = db.query(func.sum(InvoiceRecord.total_amount)).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.status == "validated"
    ).scalar() or 0

    # By category
    from sqlalchemy import case
    by_cat = db.query(
        InvoiceRecord.expense_category,
        func.count(InvoiceRecord.id).label("count"),
        func.sum(InvoiceRecord.total_amount).label("amount"),
    ).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.status == "validated"
    ).group_by(InvoiceRecord.expense_category).all()

    by_source = db.query(
        InvoiceRecord.source,
        func.count(InvoiceRecord.id).label("count"),
    ).filter(InvoiceRecord.company_id == company.id).group_by(InvoiceRecord.source).all()

    recent = [InvoiceResponse.model_validate(i)
              for i in qs.order_by(InvoiceRecord.created_at.desc()).limit(5).all()]

    return {
        "total":        total,
        "validated":    validated,
        "rejected":     rejected,
        "need_review":  need_review,
        "total_amount": float(total_amount),
        "by_category":  [{"expense_category": r[0], "count": r[1], "amount": r[2]} for r in by_cat],
        "by_source":    [{"source": r[0], "count": r[1]} for r in by_source],
        "recent":       recent,
    }


@router.get("/metrics/")
def get_metrics(
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    qs = db.query(InvoiceRecord).filter(InvoiceRecord.company_id == company.id)
    total       = qs.count()
    validated   = qs.filter(InvoiceRecord.status == "validated").count()
    rejected    = qs.filter(InvoiceRecord.status == "rejected").count()
    need_review = qs.filter(InvoiceRecord.status == "need_review").count()

    # Taux de filtrage DiT : % de docs rejetés visuellement
    dit_filter_rate = round(rejected / total * 100, 1) if total else 0.0

    # Taux de validation parmi les docs acceptés par DiT
    accepted_by_dit = validated + need_review
    validation_rate = round(validated / accepted_by_dit * 100, 1) if accepted_by_dit else 0.0

    # Taux de décision globale : docs traités sans ambiguïté
    decision_rate = round((validated + rejected) / total * 100, 1) if total else 0.0

    # Score DiT moyen par statut
    avg_dit_rejected = db.query(func.avg(InvoiceRecord.dit_confidence)).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.status == "rejected",
        InvoiceRecord.dit_confidence.isnot(None),
    ).scalar()

    avg_dit_validated = db.query(func.avg(InvoiceRecord.dit_confidence)).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.status == "validated",
        InvoiceRecord.dit_confidence.isnot(None),
    ).scalar()

    # Rejets haute confiance DiT (score < 0.3 → très loin du seuil)
    high_conf_rejections = db.query(InvoiceRecord).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.status == "rejected",
        InvoiceRecord.dit_confidence.isnot(None),
        InvoiceRecord.dit_confidence < 0.3,
    ).count()

    return {
        "total":                total,
        "validated":            validated,
        "rejected":             rejected,
        "need_review":          need_review,
        "dit_filter_rate":      dit_filter_rate,
        "validation_rate":      validation_rate,
        "decision_rate":        decision_rate,
        "avg_dit_score_rejected":  round(float(avg_dit_rejected), 3) if avg_dit_rejected else None,
        "avg_dit_score_validated": round(float(avg_dit_validated), 3) if avg_dit_validated else None,
        "high_confidence_rejections": high_conf_rejections,
    }


@router.get("/dit_scores/")
def get_dit_scores(
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Scores DiT individuels par statut — pour l'histogramme de distribution."""
    rows = db.query(
        InvoiceRecord.dit_confidence,
        InvoiceRecord.status,
    ).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.dit_confidence.isnot(None),
    ).all()
    return [{"score": round(float(r[0]), 4), "status": r[1]} for r in rows]


@router.get("/timeline/")
def get_timeline(
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Nombre de factures traitées par jour — pour le graphique d'évolution."""
    rows = db.query(
        cast(InvoiceRecord.created_at, Date).label("day"),
        InvoiceRecord.status,
        func.count(InvoiceRecord.id).label("count"),
    ).filter(
        InvoiceRecord.company_id == company.id,
    ).group_by(
        cast(InvoiceRecord.created_at, Date),
        InvoiceRecord.status,
    ).order_by(
        cast(InvoiceRecord.created_at, Date),
    ).all()
    return [{"day": str(r[0]), "status": r[1], "count": r[2]} for r in rows]


@router.get("/check_hash/")
def check_hash(
    hash: str,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    exists = db.query(InvoiceRecord).filter(
        InvoiceRecord.company_id == company.id,
        InvoiceRecord.content_hash == hash,
    ).first() is not None
    return {"exists": exists, "hash": hash}


@router.get("/{invoice_id}/")
def get_invoice(
    invoice_id: int,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    inv = db.query(InvoiceRecord).filter(
        InvoiceRecord.id == invoice_id,
        InvoiceRecord.company_id == company.id,
    ).first()
    if not inv:
        raise HTTPException(404)
    return InvoiceResponse.model_validate(inv)


@router.delete("/{invoice_id}/", status_code=204)
def delete_invoice(
    invoice_id: int,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    inv = db.query(InvoiceRecord).filter(
        InvoiceRecord.id == invoice_id,
        InvoiceRecord.company_id == company.id,
    ).first()
    if not inv:
        raise HTTPException(404)
    db.delete(inv)
    db.commit()


@router.post("/{invoice_id}/upload_excel/")
async def upload_excel(
    invoice_id: int,
    excel_file: UploadFile = File(...),
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    inv = db.query(InvoiceRecord).filter(
        InvoiceRecord.id == invoice_id,
        InvoiceRecord.company_id == company.id,
    ).first()
    if not inv:
        raise HTTPException(404)

    dest_dir = os.path.join(MEDIA_ROOT, "excel")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{invoice_id}_{excel_file.filename}")

    with open(dest, "wb") as f:
        f.write(await excel_file.read())

    inv.excel_file = dest
    db.commit()
    return {"excel_url": f"/api/invoices/{invoice_id}/excel/"}


@router.get("/{invoice_id}/excel/")
def download_excel(
    invoice_id: int,
    company=Depends(get_current_company),
    db: Session = Depends(get_db),
):
    inv = db.query(InvoiceRecord).filter(
        InvoiceRecord.id == invoice_id,
        InvoiceRecord.company_id == company.id,
    ).first()
    if not inv or not inv.excel_file or not os.path.exists(inv.excel_file):
        raise HTTPException(404)
    return FileResponse(inv.excel_file, media_type=
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(inv.excel_file))
