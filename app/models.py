from datetime import date, datetime
from sqlalchemy import ForeignKey, String, Float, Integer, Date, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(120), default=None)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=2)


class Medicine(Base):
    __tablename__ = "medicines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    strength: Mapped[str] = mapped_column(String(40), default="")
    unit_weight_g: Mapped[float] = mapped_column(Float, default=1.0)  # one pack, for weight -> count
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    reorder_min: Mapped[int] = mapped_column(Integer, default=10)     # baseline threshold rule
    temp_min_c: Mapped[float] = mapped_column(Float, default=2.0)
    temp_max_c: Mapped[float] = mapped_column(Float, default=25.0)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), default=None)
    batches: Mapped[list["Batch"]] = relationship(back_populates="medicine")


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id"))
    batch_no: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date] = mapped_column(Date)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    shelf_id: Mapped[str | None] = mapped_column(String(20), default=None)
    rfid_tag: Mapped[str | None] = mapped_column(String(40), default=None)
    excursion_count: Mapped[int] = mapped_column(Integer, default=0)  # readings out of temp range
    medicine: Mapped[Medicine] = relationship(back_populates="batches")


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(30))
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Reading(Base):
    __tablename__ = "readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    shelf_id: Mapped[str] = mapped_column(String(20))
    weight_g: Mapped[float | None] = mapped_column(Float, default=None)
    temp_c: Mapped[float | None] = mapped_column(Float, default=None)
    humidity: Mapped[float | None] = mapped_column(Float, default=None)
    door_open: Mapped[bool | None] = mapped_column(Boolean, default=None)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_no: Mapped[str] = mapped_column(String(20))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), default=None)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | approved | rejected
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["POItem"]] = relationship(cascade="all, delete-orphan")


class POItem(Base):
    __tablename__ = "po_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id"))
    qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    medicine: Mapped[Medicine] = relationship()


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actor: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(200))
