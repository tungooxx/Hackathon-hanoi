"""Category-independent parsing for customer budget language."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class BudgetConstraint:
    kind: str  # max | min | range | target | ambiguous
    low: float | None = None
    high: float | None = None
    target: float | None = None


def _normal(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


_NUMBER_TOKEN = r"(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
_UNIT_TOKEN = r"tr\b|trieu\b|million\b|ngan\b|nghin\b|k\b|vnd\b|d\b|đ\b"
_AMOUNT_RE = re.compile(
    rf"(?<![\w.,])(?P<raw>{_NUMBER_TOKEN})\s*(?P<unit>{_UNIT_TOKEN})?",
)
_UNIT_MULTIPLIERS = {
    "tr": 1_000_000,
    "trieu": 1_000_000,
    "million": 1_000_000,
    "ngan": 1_000,
    "nghin": 1_000,
    "k": 1_000,
    "vnd": 1,
    "d": 1,
    "đ": 1,
}


def _number_value(raw: str) -> float:
    """Parse grouped thousands before treating a separator as a decimal mark."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def _amount_value(raw: str, unit: str | None) -> float:
    return _number_value(raw) * _UNIT_MULTIPLIERS.get(unit or "", 1)


def _amounts_vnd(text: str) -> list[float]:
    amounts: list[float] = []
    for match in _AMOUNT_RE.finditer(text):
        raw, unit = match.group("raw"), match.group("unit")
        if not unit and len(raw.replace(".", "").replace(",", "")) < 5:
            continue
        amounts.append(_amount_value(raw, unit))
    return amounts


def parse_budget_constraint(text: str, *, pending_amount: float | None = None) -> BudgetConstraint | None:
    """Parse customer price bounds without assuming a bare number is a maximum."""
    wording = _normal(text)
    if re.search(r"\b(tu|between)\b.*\b(den|toi|to|and)\b", wording):
        endpoints = list(_AMOUNT_RE.finditer(wording))[-2:]
        if len(endpoints) == 2:
            shared_unit = endpoints[-1].group("unit")
            values = [
                _amount_value(endpoint.group("raw"), endpoint.group("unit") or shared_unit)
                for endpoint in endpoints
            ]
            low, high = sorted(values)
            return BudgetConstraint("range", low=low, high=high)

    amounts = _amounts_vnd(wording)
    comparators = {
        "max": ("duoi", "toi da", "khong qua", "khong hon", "it hon", "less than", "under", "<="),
        "min": ("tren", "tro len", "it nhat", "hon ", "more than", "above", ">="),
        "target": ("khoang", "tam ", "quanh", "gan "),
    }
    kind = next((name for name, terms in comparators.items() if any(term in wording for term in terms)), None)
    amount = amounts[-1] if amounts else (pending_amount if kind else None)
    if amount is None:
        return None
    if kind == "max":
        return BudgetConstraint("max", high=amount)
    if kind == "min":
        return BudgetConstraint("min", low=amount)
    if kind == "target":
        return BudgetConstraint("target", target=amount)
    return BudgetConstraint("ambiguous", target=amount)
