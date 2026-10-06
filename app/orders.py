from datetime import datetime, timedelta, timezone
from math import ceil
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import Audit, Batch, Medicine, Movement, POItem, PurchaseOrder, Supplier
from .services import total_stock


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log(db: Session, actor: str, message: str):
    db.add(Audit(ts=now(), actor=actor, message=message))


def daily_demand(db: Session, medicine_id: int, days: int = 28, today=None) -> list[float]:
    today = today or now().date()
    first = today - timedelta(days=days - 1)
    rows = db.execute(
        select(Movement.ts, Movement.delta).join(Batch, Batch.id == Movement.batch_id)
        .where(Batch.medicine_id == medicine_id, Movement.reason == "dispense",
               Movement.ts >= datetime.combine(first, datetime.min.time()))
    ).all()
    series = [0.0] * days
    for ts, delta in rows:
        i = (ts.date() - first).days
        if 0 <= i < days:
            series[i] += -delta
    return series


def forecast(db: Session, medicine_id: int, horizon: int = 14, today=None) -> dict:
    """Baseline model: recent mean x weekday factor. Replace with Prophet/LightGBM later."""
    today = today or now().date()
    s = daily_demand(db, medicine_id, 28, today)
    mean = sum(s) / 28
    recent = sum(s[-14:]) / 14
    f = [1.0] * 7
    if mean > 0:
        for w in range(7):
            v = [s[i] for i in range(28) if (today - timedelta(days=27 - i)).weekday() == w]
            f[w] = (sum(v) / len(v)) / mean
    out = [round(recent * f[(today + timedelta(days=k + 1)).weekday()], 1) for k in range(horizon)]
    return {"history": [round(x, 1) for x in s[-14:]], "forecast": out}


def suggest(db: Session, med: Medicine, today=None) -> dict | None:
    sup = db.get(Supplier, med.supplier_id) if med.supplier_id else None
    lead = sup.lead_time_days if sup else 2
    fc = forecast(db, med.id, 14, today)["forecast"]
    stock = total_stock(db, med.id, today)
    need = ceil(sum(fc[:lead + 7]))
    safety = ceil(0.25 * need)
    if need == 0:  # no demand history: fall back to the fixed threshold rule
        if stock >= med.reorder_min:
            return None
        qty = med.reorder_min * 2 - stock
        why = f"No demand history yet. Stock {stock} is below the minimum {med.reorder_min}."
    else:
        if stock - sum(fc[:lead]) >= safety:
            return None
        qty = max(0, need + safety - stock)
        why = (f"Forecast demand {round(sum(fc[:lead]))} over the {lead}-day lead time and "
               f"{round(sum(fc[:7]))} over 7 days. Stock {stock}. Order covers lead time plus 7 days with 25% safety stock.")
    return {"qty": qty, "why": why}


def generate_pos(db: Session, today=None) -> list[PurchaseOrder]:
    pending = set(db.scalars(select(POItem.medicine_id).join(PurchaseOrder).where(PurchaseOrder.status == "pending")))
    groups: dict = {}
    for med in db.scalars(select(Medicine)):
        if med.id in pending:
            continue
        r = suggest(db, med, today)
        if r and r["qty"] > 0:
            groups.setdefault(med.supplier_id, []).append((med, r))
    created = []
    for sid, items in groups.items():
        n = db.scalar(select(func.count(PurchaseOrder.id))) + 1
        po = PurchaseOrder(po_no=f"PO-{now().year}-{n:04d}", supplier_id=sid,
                           rationale=" ".join(f"{m.name}: {r['why']}" for m, r in items))
        po.items = [POItem(medicine_id=m.id, qty=r["qty"], unit_price=m.unit_price) for m, r in items]
        db.add(po)
        db.flush()
        log(db, "Reorder agent", f"Drafted {po.po_no} with {len(items)} item(s)")
        created.append(po)
    db.commit()
    return created


def po_dict(db: Session, po: PurchaseOrder) -> dict:
    sup = db.get(Supplier, po.supplier_id) if po.supplier_id else None
    return {"id": po.id, "po_no": po.po_no, "supplier": sup.name if sup else "Unassigned", "status": po.status,
            "rationale": po.rationale, "created_at": po.created_at.isoformat(),
            "items": [{"name": f"{i.medicine.name} {i.medicine.strength}".strip(), "qty": i.qty, "unit_price": i.unit_price}
                      for i in po.items]}
