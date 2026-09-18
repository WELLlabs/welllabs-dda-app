"""Paginated field tables so atlas PDFs keep full observe/ask/hypothesis text."""

from __future__ import annotations

import textwrap


def wrap_field(text: str, width: int) -> list[str]:
    """Wrap every paragraph. Never truncate."""
    raw = str(text or "").replace("\r\n", "\n").strip() or "—"
    width = max(8, int(width))
    lines: list[str] = []
    for para in raw.split("\n"):
        chunk = para.strip() or "—"
        lines.extend(textwrap.wrap(chunk, width=width) or [chunk])
    return lines or ["—"]


def row_height(cells: list[list[str]], *, line_h: float, pad: float, min_h: float) -> float:
    lines = max((len(c) for c in cells), default=1)
    return max(min_h, pad + lines * line_h)


def _split_cells(cells: list[list[str]], max_lines: int) -> tuple[list[list[str]], list[list[str]]]:
    max_lines = max(1, int(max_lines))
    head = [c[:max_lines] or ["—"] for c in cells]
    tail = [c[max_lines:] for c in cells]
    return head, tail


def paginate_rows(
    rows: list[dict],
    *,
    available: float,
    line_h: float = 0.014,
    pad: float = 0.016,
    min_h: float = 0.048,
) -> list[list[dict]]:
    """Pack rows onto pages. Oversized rows split across pages (text continues)."""
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = 0.0

    def flush() -> None:
        nonlocal current, used
        if current:
            pages.append(current)
        current = []
        used = 0.0

    for row in rows:
        remaining_cells = [list(c) for c in row["cells"]]
        first_chunk = True
        while remaining_cells and any(remaining_cells):
            room = available - used
            if current and room < min_h:
                flush()
                room = available
            max_lines = max(1, int((room - pad) / line_h))
            needed = max(len(c) for c in remaining_cells)
            if needed > max_lines:
                head, tail = _split_cells(remaining_cells, max_lines)
                chunk = {
                    **row,
                    "cells": head,
                    "continued": not first_chunk,
                    "height": row_height(head, line_h=line_h, pad=pad, min_h=min_h),
                }
                current.append(chunk)
                flush()
                remaining_cells = tail
                first_chunk = False
                continue
            height = row_height(remaining_cells, line_h=line_h, pad=pad, min_h=min_h)
            if current and used + height > available + 1e-9:
                flush()
                continue
            current.append(
                {
                    **row,
                    "cells": remaining_cells,
                    "continued": not first_chunk,
                    "height": height,
                }
            )
            used += height
            remaining_cells = []
            first_chunk = False
    flush()
    return pages or [[]]
