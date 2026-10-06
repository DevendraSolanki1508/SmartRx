from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Batch, Medicine, Movement, Reading


def total_stock(db: Session, medicine_id: int, today: date | None = None) -> int:
    """Sellable stock: excludes expired batches."""
    today = today or date.today()
    rows = db.scalars(select(Batch).where(Batch.medicine_id == medicine_id, Batch.expiry_date >= today))
    return sum(b.qty for b in rows)


def dispense_fefo(db: Session, medicine_id: int, qty: int, today: date | None = None) -> list[dict]:
    """First-expiry-first-out: take from the earliest-expiring non-expired batches."""
    today = today or date.today()
    batches = db.scalars(
        select(Batch)
        .where(Batch.medicine_id == medicine_id, Batch.expiry_date >= today, Batch.qty > 0)
        .order_by(Batch.expiry_date)
    ).all()
    if sum(b.qty for b in batches) < qty:
        raise ValueError("insufficient non-expired stock")
    taken, need = [], qty
    for b in batches:
        take = min(b.qty, need)
        b.qty -= take
        db.add(Movement(batch_id=b.id, delta=-take, reason="dispense"))
        taken.append({"batch_id": b.id, "batch_no": b.batch_no, "qty": take})
        need -= take
        if need == 0:
            break
    db.commit()
    return taken


def get_alerts(db: Session, near_days: int = 30, today: date | None = None) -> dict:
    today = today or date.today()
    soon = today + timedelta(days=near_days)
    expired, near, low, spoiled = [], [], [], []
    for b in db.scalars(select(Batch).where(Batch.qty > 0)):
        item = {"batch_id": b.id, "medicine": b.medicine.name, "batch_no": b.batch_no,
                "qty": b.qty, "expiry_date": b.expiry_date.isoformat()}
        if b.expiry_date < today:
            expired.append(item)
        elif b.expiry_date <= soon:
            near.append({**item, "days_left": (b.expiry_date - today).days})
        if b.excursion_count > 0:
            spoiled.append({**item, "excursions": b.excursion_count})
    for m in db.scalars(select(Medicine)):
        stock = total_stock(db, m.id, today)
        if stock < m.reorder_min:
            low.append({"medicine_id": m.id, "medicine": m.name, "stock": stock, "reorder_min": m.reorder_min})
    return {"expired": expired, "near_expiry": near, "low_stock": low, "temp_excursion": spoiled}


def ingest_reading(db: Session, shelf_id: str, weight_g=None, temp_c=None, humidity=None, door_open=None) -> dict:
    """Store a sensor reading, convert weight to unit count, flag temperature excursions."""
    db.add(Reading(shelf_id=shelf_id, weight_g=weight_g, temp_c=temp_c, humidity=humidity, door_open=door_open))
    result = {"shelf_id": shelf_id, "estimated_units": None, "excursion": False}
    batches = db.scalars(select(Batch).where(Batch.shelf_id == shelf_id, Batch.qty > 0)).all()
    if batches:
        med = batches[0].medicine
        if weight_g is not None and med.unit_weight_g > 0:
            result["estimated_units"] = round(weight_g / med.unit_weight_g)
        if temp_c is not None and not (med.temp_min_c <= temp_c <= med.temp_max_c):
            result["excursion"] = True
            for b in batches:
                b.excursion_count += 1
    db.commit()
    return result
