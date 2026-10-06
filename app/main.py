from datetime import date
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import Batch, Medicine, Supplier
from . import services

Base.metadata.create_all(engine)
app = FastAPI(title="SmartRx")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SupplierIn(BaseModel):
    name: str
    email: str | None = None
    lead_time_days: int = 2


class MedicineIn(BaseModel):
    name: str
    strength: str = ""
    unit_weight_g: float = 1.0
    unit_price: float = 0.0
    reorder_min: int = 10
    temp_min_c: float = 2.0
    temp_max_c: float = 25.0
    supplier_id: int | None = None


class BatchIn(BaseModel):
    medicine_id: int
    batch_no: str
    expiry_date: date
    qty: int
    shelf_id: str | None = None
    rfid_tag: str | None = None


class DispenseIn(BaseModel):
    qty: int


class ReadingIn(BaseModel):
    shelf_id: str
    weight_g: float | None = None
    temp_c: float | None = None
    humidity: float | None = None
    door_open: bool | None = None


@app.post("/suppliers")
def add_supplier(body: SupplierIn, db: Session = Depends(get_db)):
    s = Supplier(**body.model_dump()); db.add(s); db.commit()
    return {"id": s.id}


@app.post("/medicines")
def add_medicine(body: MedicineIn, db: Session = Depends(get_db)):
    m = Medicine(**body.model_dump()); db.add(m); db.commit()
    return {"id": m.id}


@app.post("/batches")
def add_batch(body: BatchIn, db: Session = Depends(get_db)):
    if not db.get(Medicine, body.medicine_id):
        raise HTTPException(404, "medicine not found")
    b = Batch(**body.model_dump()); db.add(b); db.commit()
    return {"id": b.id}


@app.post("/medicines/{medicine_id}/dispense")
def dispense(medicine_id: int, body: DispenseIn, db: Session = Depends(get_db)):
    try:
        return {"taken": services.dispense_fefo(db, medicine_id, body.qty)}
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    out = []
    for m in db.scalars(select(Medicine)):
        out.append({"medicine_id": m.id, "name": m.name, "stock": services.total_stock(db, m.id),
                    "batches": [{"batch_no": b.batch_no, "qty": b.qty, "expiry": b.expiry_date.isoformat()}
                                for b in sorted(m.batches, key=lambda x: x.expiry_date)]})
    return out


@app.get("/alerts")
def alerts(near_days: int = 30, db: Session = Depends(get_db)):
    return services.get_alerts(db, near_days)


@app.post("/readings")
def readings(body: ReadingIn, db: Session = Depends(get_db)):
    """Endpoint the ESP32 will post to (later replaced/augmented by MQTT)."""
    return services.ingest_reading(db, **body.model_dump())


from .api_extra import router  # noqa: E402
app.include_router(router)
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")
