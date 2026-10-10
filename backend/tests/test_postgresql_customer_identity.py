"""Opt-in race on a disposable PostgreSQL schema, never the client database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import Response
from sqlalchemy import func, select, text

from app.api.v1.customers import create_customer
from app.api.v1.invoices import _get_or_create_customer_from_inline
from app.models.master_records import Customer
from app.models.user import User
from app.schemas.invoice import InvoiceCustomerInput
from app.schemas.master_records import CustomerCreate
from tests.test_master_records import customer_payload
from tests.test_postgresql_security import pg_sessions, seed  # noqa: F401


def test_concurrent_master_and_inline_saves_share_one_gstin_identity(pg_sessions):
    users, branch_id = seed(pg_sessions)
    barrier = Barrier(4)

    def save(index):
        with pg_sessions() as db:
            db.execute(text("SET LOCAL statement_timeout = '10s'"))
            payload = customer_payload(branch_id, f"Concurrent buyer {index}")
            payload["gstin"] = " 29abcde1234f1z5 " if index % 2 else "29ABCDE1234F1Z5"
            barrier.wait(timeout=10)
            if index % 2:
                payload.pop("branch_id")
                customer = _get_or_create_customer_from_inline(db, branch_id, InvoiceCustomerInput(**payload))
                db.commit()
                return customer.id
            return create_customer(CustomerCreate(**payload), Response(), db, db.get(User, users[0][0])).id

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(save, range(4)))
    assert len(set(ids)) == 1
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(Customer)) == 1
