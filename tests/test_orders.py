import os
os.environ["DATABASE_URL"] = "sqlite:///test_smartrx.db"
from datetime import timedelta, date
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import Movement
from app import orders

c = TestClient(app)


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    sid = c.post("/suppliers", json={"name": "S1", "lead_time_days": 2}).json()["id"]
    mid = c.post("/medicines", json={"name": "Drug", "reorder_min": 5, "unit_price": 10, "supplier_id": sid}).json()["id"]
    bid = c.post("/batches", json={"medicine_id": mid, "batch_no": "X1", "qty": 3,
                                   "expiry_date": (date.today() + timedelta(days=90)).isoformat()}).json()["id"]
    db = SessionLocal()
    for k in range(1, 29):
        db.add(Movement(batch_id=bid, delta=-4, reason="dispense", ts=orders.now() - timedelta(days=k)))
    db.commit(); db.close()


def test_forecast_shape():
    f = c.get("/forecast/1").json()
    assert len(f["history"]) == 14 and len(f["forecast"]) == 14 and f["forecast"][0] > 0


def test_generate_approve_flow_and_audit():
    pos = c.post("/purchase-orders/generate").json()
    assert len(pos) == 1 and pos[0]["items"][0]["qty"] > 0 and pos[0]["status"] == "pending"
    assert c.post("/purchase-orders/generate").json() == []  # no duplicate while one is pending
    pid = pos[0]["id"]
    assert c.post(f"/purchase-orders/{pid}/approve").json()["status"] == "approved"
    assert c.post(f"/purchase-orders/{pid}/approve").status_code == 409
    assert any("Approved" in a["message"] for a in c.get("/audit").json())


def test_simulation_runs_and_reports_both_policies():
    import simulate
    out = simulate.main(runs=2)
    for pol in ("threshold", "smartrx"):
        assert {"wastage_pct", "stockout_day_pct", "fill_rate_pct", "avg_inventory_units"} <= set(out[pol])
    assert out["smartrx"]["avg_inventory_units"]["mean"] < out["threshold"]["avg_inventory_units"]["mean"]
