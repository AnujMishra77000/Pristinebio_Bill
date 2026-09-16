from fastapi import APIRouter

from app.api.v1 import auth, bank_accounts, branches, companies, customers, invoices, products, purchase_orders, suppliers, terms, transporters, users


router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(branches.router, prefix="/branches", tags=["branches"])
router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
router.include_router(products.router, prefix="/products", tags=["products"])
router.include_router(bank_accounts.router, prefix="/bank-accounts", tags=["bank-accounts"])
router.include_router(transporters.router, prefix="/transporters", tags=["transporters"])
router.include_router(terms.router, prefix="/terms-and-conditions", tags=["terms-and-conditions"])
router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
router.include_router(purchase_orders.router, prefix="/purchase-orders", tags=["purchase-orders"])


@router.get("/status", tags=["system"])
def api_status() -> dict[str, str]:
    return {"status": "ok", "api_version": "v1"}
