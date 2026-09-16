from decimal import Decimal
from pathlib import Path
import subprocess
import sys

from sqlalchemy import inspect

from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.master_records import Customer, Product
from app.models.user import User, UserBranchAssignment


def test_user_branch_assignment_links_user_to_branch():
    assert User.__tablename__ == "users"
    assert UserBranchAssignment.__tablename__ == "user_branch_assignments"
    assert UserRole.ADMIN.value == "admin"
    assert "branch_id" in UserBranchAssignment.__table__.columns


def test_user_role_enum_persists_lowercase_values_in_model_and_migration():
    assert User.__table__.c.role.type.enums == ["admin", "manager", "staff"]

    backend_directory = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=backend_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CHECK (role IN ('admin', 'manager', 'staff'))" in result.stdout


def test_product_rates_use_decimal_numeric_columns():
    mapper = inspect(Product)
    column_names = {column.key for column in mapper.columns}

    assert {"base_rate", "gst_rate", "cess_rate"}.issubset(column_names)
    assert Product.__table__.c.base_rate.type.precision == 14
    assert Product.__table__.c.base_rate.type.scale == 4
    assert Product.__table__.c.gst_rate.type.precision == 5
    assert Product.__table__.c.gst_rate.type.scale == 2
    assert (
        Product(
            base_rate=Decimal("10.2500"),
            gst_rate=Decimal("18.00"),
            cess_rate=Decimal("0.00"),
        ).base_rate
        == Decimal("10.2500")
    )


def test_customer_has_separate_billing_and_shipping_address_columns():
    column_names = set(Customer.__table__.columns.keys())

    assert "billing_address_line1" in column_names
    assert "shipping_address_line1" in column_names
    assert "billing_state_code" in column_names
    assert "shipping_state_code" in column_names


def test_company_and_branch_gstin_context_is_explicit():
    assert Company.__tablename__ == "companies"
    assert Branch.__tablename__ == "branches"
    assert "gstin" in Branch.__table__.columns
    assert "company_id" in Branch.__table__.columns
