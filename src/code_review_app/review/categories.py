from __future__ import annotations


CATEGORY_LABELS = {
    "significant_concerns": "Significant Concerns",
    "correctness": "Correctness",
    "security": "Security",
    "performance": "Performance",
    "maintainability": "Maintainability",
}
CATEGORY_ORDER = tuple(CATEGORY_LABELS)
DEFAULT_CATEGORY = "correctness"


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS[DEFAULT_CATEGORY])
