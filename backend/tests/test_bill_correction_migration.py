"""Execute the forward migration on an isolated in-memory database."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_forward_correction_migration_preserves_parents_and_enforces_unique_working_copy(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261015_0025_confirmed_bill_corrections.py"
    spec = importlib.util.spec_from_file_location("correction_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        for name in ("invoices", "purchase_orders", "branches", "users"):
            connection.execute(text(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)"))
            connection.execute(text(f"INSERT INTO {name} (id) VALUES (1)"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert "bill_corrections" in inspect(connection).get_table_names()
        for name in ("invoices", "purchase_orders", "branches", "users"):
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {name}")) == 1
        statement = "INSERT INTO bill_corrections (invoice_id, branch_id, base_version, version, status, reason, created_by_id, original_snapshot, working_snapshot) VALUES (1, 1, 1, 2, 'draft', 'Correction', 1, '{}', '{}')"
        connection.execute(text(statement))
        with pytest.raises(IntegrityError):
            connection.execute(text(statement))
        with pytest.raises(IntegrityError):
            connection.execute(text("INSERT INTO bill_corrections (branch_id, base_version, version, status, reason, created_by_id, original_snapshot, working_snapshot) VALUES (1, 1, 1, 'draft', 'Correction', 1, '{}', '{}')"))
    engine.dispose()
