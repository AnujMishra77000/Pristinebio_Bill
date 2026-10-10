"""Capture bill addresses independently of mutable supplier/company masters."""
from app.models.company import Branch, Company


def postal_address_lines(source, *, prefix: str = "") -> tuple[str, ...]:
    def value(field: str) -> str:
        return (getattr(source, f"{prefix}{field}", None) or "").strip()

    locality = ", ".join(part for part in (value("city"), value("state")) if part)
    postal_code = value("postal_code")
    if postal_code:
        locality = f"{locality} - {postal_code}" if locality else postal_code
    return tuple(part for part in (value("address_line1"), value("address_line2"), locality) if part)


def company_address_snapshot(company: Company | None, branch: Branch) -> str:
    registered = company.registered_address if company else None
    if registered and registered.strip():
        return "\n".join(line.strip() for line in registered.splitlines() if line.strip())
    # Existing profiles may lack a separate registered address. Capture their
    # GST address once rather than sourcing the company header from a supplier.
    return "\n".join(postal_address_lines(branch))
