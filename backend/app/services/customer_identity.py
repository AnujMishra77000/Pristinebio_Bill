"""GSTIN identity without deleting/relinking historical customer records."""
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.master_records import Customer


def normalize_gstin(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().upper() or None


def lock_customer_gstin(db: Session, branch_id: int, gstin: str | None) -> None:
    """Serialize all application writers until commit/rollback on PostgreSQL.

    Legacy duplicates prohibit adding a unique index without a historical-data
    decision. SQLite does not provide this PostgreSQL concurrency guarantee.
    """
    gstin = normalize_gstin(gstin)
    if gstin and db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(sha256(f"customer-gstin:{branch_id}:{gstin}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def find_customer_by_gstin(db: Session, branch_id: int, gstin: str | None, *, exclude_id: int | None = None) -> Customer | None:
    gstin = normalize_gstin(gstin)
    if not gstin:
        return None
    statement = select(Customer).where(Customer.branch_id == branch_id, func.upper(func.trim(Customer.gstin)) == gstin)
    if exclude_id is not None:
        statement = statement.where(Customer.id != exclude_id)
    return db.scalar(statement.order_by(Customer.is_active.desc(), Customer.id).limit(1))


def require_active_customer(customer: Customer) -> Customer:
    if not customer.is_active:
        raise HTTPException(status_code=422, detail="A customer with this GSTIN is inactive. Reactivate the saved customer before using it for new bills.")
    return customer
