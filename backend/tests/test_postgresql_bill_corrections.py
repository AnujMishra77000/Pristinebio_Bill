"""Opt-in row-lock race; never connect to a non-disposable client database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select, text

from app.db.session import Base
from app.models.bill_correction import BillCorrection
from app.models.user import User
from app.schemas.bill_correction import InvoiceCorrectionUpdate, PurchaseOrderCorrectionUpdate
from app.services.bill_corrections import save
from tests.test_confirmed_bill_corrections import confirmed, correction_update
from tests.test_postgresql_security import pg_sessions  # noqa: F401


@pytest.mark.parametrize("kind", ("sales", "domestic_oils"))
def test_concurrent_correction_saves_publish_one_working_revision_not_two(
    kind, pg_sessions, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    _, original, payload, model, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    # Copy only this test's isolated fixtures into the disposable per-test schema.
    with pg_sessions() as target:
        for table in Base.metadata.sorted_tables:
            rows = [dict(row) for row in db_session.execute(select(table)).mappings()]
            if rows:
                target.execute(table.insert(), rows)
                if "id" in table.c and table.c.id.primary_key:
                    sequence = target.scalar(text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table.name})
                    if sequence:
                        target.execute(text(f"SELECT setval(CAST(:sequence AS regclass), (SELECT MAX(id) FROM {table.name}), true)"), {"sequence": sequence})
        target.commit()
    collection = "invoices" if kind == "sales" else "purchase-orders"
    request_cls = InvoiceCorrectionUpdate if kind == "sales" else PurchaseOrderCorrectionUpdate
    request = request_cls(**correction_update(kind, payload, original["version"]))
    barrier = Barrier(2)

    def attempt(_):
        with pg_sessions() as db:
            db.execute(text("SET LOCAL statement_timeout = '10s'"))
            user = db.get(User, admin_user.id)
            barrier.wait(timeout=10)
            try:
                save(db, user, collection, original["id"], request)
                return "saved"
            except HTTPException as exc:
                db.rollback()
                assert exc.status_code == 409
                return exc.detail["code"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == ["saved", "version_conflict"]
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(BillCorrection)) == 1
        assert db.scalar(select(func.count()).select_from(model)) == 1
        assert db.get(model, original["id"]).version == original["version"]

