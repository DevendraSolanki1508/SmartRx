import json
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Audit, Batch, Medicine, PurchaseOrder, Reading
from . import orders, services

router = APIRouter()


@router.get("/medicines")
def list_medicines(db: Session = Depends(get_db)):
    out = []
    for m in db.scalars(select(Medicine)):
        shelf = next((b.shelf_id for b in m.batches if b.shelf_id), None)
        out.append({"id": m.id, "name": m.name, "strength": m.strength, "shelf": shelf, "reorder_min": m.reorder_min})
    return out


@router.get("/batches")
def list_batches(db: Session = Depends(get_db)):
    today = date.today()
    return [{"id": b.id, "medicine_id": b.medicine_id, "batch_no": b.batch_no, "qty": b.qty, "shelf_id": b.shelf_id,
             "days_left": (b.expiry_date - today).days, "excursion_count": b.excursion_count}
            for b in db.scalars(select(Batch).where(Batch.qty > 0))]


@router.get("/shelves")
def shelves(db: Session = Depends(get_db)):
    out = []
    ids = sorted({b.shelf_id for b in db.scalars(select(Batch)) if b.shelf_id})
    for sid in ids:
        r = db.scalars(select(Reading).where(Reading.shelf_id == sid).order_by(Reading.id.desc())).first()
        b = db.scalars(select(Batch).where(Batch.shelf_id == sid, Batch.qty > 0)).first()
        row = {"shelf_id": sid, "weight_g": None, "estimated_units": None, "temp_c": None, "humidity": None,
               "door_open": None, "excursion": False}
        if r:
            row.update(weight_g=r.weight_g, temp_c=r.temp_c, humidity=r.humidity, door_open=r.door_open)
            if b and r.weight_g is not None and b.medicine.unit_weight_g > 0:
                row["estimated_units"] = round(r.weight_g / b.medicine.unit_weight_g)
            if b and r.temp_c is not None:
                row["excursion"] = not (b.medicine.temp_min_c <= r.temp_c <= b.medicine.temp_max_c)
        out.append(row)
    return out


@router.get("/readings")
def readings(shelf_id: str, limit: int = 48, db: Session = Depends(get_db)):
    rows = db.scalars(select(Reading).where(Reading.shelf_id == shelf_id, Reading.temp_c.is_not(None))
                      .order_by(Reading.id.desc()).limit(limit)).all()
    return [r.temp_c for r in reversed(rows)]


@router.get("/forecast/{medicine_id}")
def get_forecast(medicine_id: int, db: Session = Depends(get_db)):
    if not db.get(Medicine, medicine_id):
        raise HTTPException(404, "medicine not found")
    return orders.forecast(db, medicine_id)


@router.post("/purchase-orders/generate")
def generate(db: Session = Depends(get_db)):
    return [orders.po_dict(db, po) for po in orders.generate_pos(db)]


@router.get("/purchase-orders")
def list_pos(db: Session = Depends(get_db)):
    return [orders.po_dict(db, po) for po in db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id.desc()))]


def _decide(db: Session, po_id: int, status: str):
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(404, "purchase order not found")
    if po.status != "pending":
        raise HTTPException(409, f"already {po.status}")
    po.status = status
    orders.log(db, "Pharmacist", f"{status.capitalize()} {po.po_no}")  # sending to supplier is a stub for now
    db.commit()
    return orders.po_dict(db, po)


@router.post("/purchase-orders/{po_id}/approve")
def approve(po_id: int, db: Session = Depends(get_db)):
    return _decide(db, po_id, "approved")


@router.post("/purchase-orders/{po_id}/reject")
def reject(po_id: int, db: Session = Depends(get_db)):
    return _decide(db, po_id, "rejected")


@router.get("/audit")
def audit(limit: int = 30, db: Session = Depends(get_db)):
    return [{"ts": a.ts.isoformat(), "actor": a.actor, "message": a.message}
            for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limit))]


@router.get("/evaluation")
def evaluation():
    f = Path(__file__).resolve().parent.parent / "results.json"
    if not f.exists():
        raise HTTPException(404, "run simulate.py first")
    return json.loads(f.read_text())
