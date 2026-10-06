import os
os.environ["DATABASE_URL"] = "sqlite:///test_smartrx.db"
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine

Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
c = TestClient(app)
d = lambda n: (date.today() + timedelta(days=n)).isoformat()


def setup_module():
    mid = c.post("/medicines", json={"name": "Insulin", "unit_weight_g": 50, "reorder_min": 20,
                                     "temp_min_c": 2, "temp_max_c": 8}).json()["id"]
    c.post("/batches", json={"medicine_id": mid, "batch_no": "B-LATE", "expiry_date": d(200), "qty": 10, "shelf_id": "S1"})
    c.post("/batches", json={"medicine_id": mid, "batch_no": "B-SOON", "expiry_date": d(10), "qty": 5, "shelf_id": "S1"})
    c.post("/batches", json={"medicine_id": mid, "batch_no": "B-OLD", "expiry_date": d(-3), "qty": 4})


def test_fefo_takes_earliest_valid_batch_first_and_skips_expired():
    r = c.post("/medicines/1/dispense", json={"qty": 7}).json()["taken"]
    assert [t["batch_no"] for t in r] == ["B-SOON", "B-LATE"]
    assert [t["qty"] for t in r] == [5, 2]


def test_cannot_dispense_more_than_valid_stock():
    assert c.post("/medicines/1/dispense", json={"qty": 999}).status_code == 409


def test_alerts():
    a = c.get("/alerts").json()
    assert [x["batch_no"] for x in a["expired"]] == ["B-OLD"]
    assert a["low_stock"][0]["stock"] == 8  # 10-2 left, expired excluded


def test_sensor_reading_counts_units_and_flags_excursion():
    ok = c.post("/readings", json={"shelf_id": "S1", "weight_g": 400, "temp_c": 5}).json()
    assert ok["estimated_units"] == 8 and ok["excursion"] is False
    bad = c.post("/readings", json={"shelf_id": "S1", "weight_g": 400, "temp_c": 14}).json()
    assert bad["excursion"] is True
    assert c.get("/alerts").json()["temp_excursion"]
