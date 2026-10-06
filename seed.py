"""Populate demo data: python seed.py  (delete smartrx.db first for a clean start)"""
import math, random
from datetime import date, timedelta
from app.db import Base, SessionLocal, engine
from app.models import Batch, Medicine, Movement, Supplier
from app import orders, services

random.seed(7)
Base.metadata.create_all(engine)
db = SessionLocal()
ml = Supplier(name="MedLine Distributors", lead_time_days=2)
cc = Supplier(name="CoolChain Pharma", lead_time_days=3)
db.add_all([ml, cc]); db.flush()
# name, strength, shelf, unit_g, price, min, tmin, tmax, supplier, daily demand, batches[(no, days_to_expiry, qty)]
MEDS = [
 ("Insulin glargine", "100 IU/mL", "C1", 50, 615, 20, 2, 8, cc, 4, [("IG-2407", 14, 6), ("IG-2501", 200, 18)]),
 ("Hepatitis B vaccine", "20 mcg", "C1", 40, 310, 10, 2, 8, cc, 1, [("HB-0311", 60, 9)]),
 ("Amoxicillin", "500 mg", "R1", 12, 6, 60, 15, 25, ml, 12, [("AX-118", -4, 12), ("AX-205", 120, 140)]),
 ("Paracetamol", "650 mg", "R1", 9, 2, 100, 15, 30, ml, 15, [("PC-077", 25, 80), ("PC-091", 300, 400)]),
 ("Cetirizine", "10 mg", "R2", 6, 3, 40, 15, 30, ml, 9, [("CT-044", 22, 95)]),
 ("Metformin", "500 mg", "R2", 8, 2, 50, 15, 30, ml, 10, [("MF-031", 180, 35)]),
 ("Pantoprazole", "40 mg", "R2", 7, 4, 30, 15, 30, ml, 8, [("PN-012", 90, 22)]),
]
today = date.today()
for n, st, sh, g, pr, mn, t0, t1, sup, d, bs in MEDS:
    m = Medicine(name=n, strength=st, unit_weight_g=g, unit_price=pr, reorder_min=mn, temp_min_c=t0, temp_max_c=t1, supplier_id=sup.id)
    db.add(m); db.flush()
    for no, days, q in bs:
        b = Batch(medicine_id=m.id, batch_no=no, expiry_date=today + timedelta(days=days), qty=q, shelf_id=sh)
        db.add(b); db.flush()
    last = b
    for k in range(60, 0, -1):  # 60 days of dispensing with a weekly pattern
        day = today - timedelta(days=k)
        qty = max(0, round(d * (1 + 0.3 * math.sin(day.weekday() * 0.9)) + random.gauss(0, d * 0.15)))
        if qty:
            db.add(Movement(batch_id=last.id, delta=-qty, reason="dispense",
                            ts=orders.now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=k)))
db.commit()
for i in range(48):  # last 24h of readings, cold store with a breach near the end
    t = 4.6 + math.sin(i / 5) * 0.9 + ([3.6, 4.5, 3.9, 2.4][i - 36] if 36 <= i <= 39 else 0)
    services.ingest_reading(db, "C1", weight_g=1240, temp_c=round(t, 1), humidity=52, door_open=False)
services.ingest_reading(db, "R1", weight_g=8420, temp_c=24.6, humidity=48, door_open=False)
services.ingest_reading(db, "R2", weight_g=3110, temp_c=25.2, humidity=50, door_open=True)
print("POs drafted:", [p.po_no for p in orders.generate_pos(db)])
