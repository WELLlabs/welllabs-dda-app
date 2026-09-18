"""QField Cloud project names: letters, numbers, hyphen, underscore, and dots only."""

from __future__ import annotations

import re

from app.shared.config import settings

_INVALID = re.compile(r"[^A-Za-z0-9._-]+")
_REPEAT = re.compile(r"[-_.]{2,}")
_MAX_LEN = 80


def qfield_cloud_project_name(diagnosis_name: str | None) -> str:
    prefix = (settings.qfield_project_name or "diagnose").strip() or "diagnose"
    combined = f"{prefix}-{diagnosis_name or 'project'}"
    slug = _INVALID.sub("-", combined)
    slug = _REPEAT.sub("-", slug).strip("-._")
    if slug and slug[0].isdigit():
        slug = f"p-{slug}"
    return (slug or "diagnose-project")[:_MAX_LEN]


def qfield_cloud_name_aliases(diagnosis_name: str | None) -> list[str]:
    """Sanitized name plus the older space-to-hyphen form, so re-packages still match."""
    names: list[str] = []
    for candidate in (
        qfield_cloud_project_name(diagnosis_name),
        f"{settings.qfield_project_name}-{diagnosis_name or 'project'}".replace(" ", "-")[:80],
    ):
        if candidate and candidate not in names:
            names.append(candidate)
    return names
