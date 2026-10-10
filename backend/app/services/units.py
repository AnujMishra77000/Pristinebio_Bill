"""Canonical unit symbols used by the reagent product catalog."""

from __future__ import annotations


UNIT_LABELS = {
    "g": "Gram (g)",
    "kg": "Kilogram (kg)",
    "mg": "Milligram (mg)",
    "µg": "Microgram (µg)",
    "mL": "Millilitre (mL)",
    "L": "Litre (L)",
    "t": "Tonne (t)",
}

_UNIT_ALIASES = {
    "g": "g",
    "gm": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "µg": "µg",
    "μg": "µg",
    "ug": "µg",
    "microgram": "µg",
    "micrograms": "µg",
    "ml": "mL",
    "milliliter": "mL",
    "millilitre": "mL",
    "milliliters": "mL",
    "millilitres": "mL",
    "l": "L",
    "liter": "L",
    "litre": "L",
    "liters": "L",
    "litres": "L",
    "t": "t",
    "ton": "t",
    "tons": "t",
    "tonne": "t",
    "tonnes": "t",
}


def canonical_unit(value: str) -> str | None:
    """Return a canonical symbol for a supported unit or None if unsupported."""
    return _UNIT_ALIASES.get(value.strip().casefold())


def normalize_catalog_unit(value: str) -> str:
    """Normalize accepted legacy/business aliases and reject unsupported units."""
    normalized = canonical_unit(value)
    if normalized is None:
        allowed = ", ".join(UNIT_LABELS)
        raise ValueError(f"Unit must be one of: {allowed}")
    return normalized
