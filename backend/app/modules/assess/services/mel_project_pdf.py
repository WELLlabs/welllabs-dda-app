"""Project-level MEL PDF: shared prose once, per-intervention log frames + methodology."""

from __future__ import annotations

import io
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.assess.services.mel_logframe import build_logframe_plan
from app.modules.assess.services.mel_playbooks import playbooks_as_reportlab_xml

_NAVY = colors.HexColor("#0d2c4c")
_BLUE = colors.HexColor("#1b75e0")
_INK = colors.HexColor("#1a2530")
_MUTED = colors.HexColor("#3b4a58")
_HAIR = colors.HexColor("#d5dde6")
_GOAL = colors.HexColor("#fff6e8")
_OUTPUT = colors.HexColor("#e8f7f2")
_WHITE = colors.white
_AMBER = colors.HexColor("#fff8ef")
_TITLE_MUTED = colors.HexColor("#b8d8f8")
_TITLE_RULE = colors.HexColor("#7dc3ff")


def _esc(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "MelProjH1",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=_NAVY,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "MelProjH2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=_NAVY,
            spaceBefore=10,
            spaceAfter=3,
        ),
        "h3": ParagraphStyle(
            "MelProjH3",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=_NAVY,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "MelProjBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=_MUTED,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "meta": ParagraphStyle(
            "MelProjMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=_MUTED,
            spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "MelProjCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=_INK,
        ),
        "cell_bold": ParagraphStyle(
            "MelProjCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=_INK,
        ),
        "th": ParagraphStyle(
            "MelProjTh",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=_WHITE,
        ),
        "section_title": ParagraphStyle(
            "MelProjSectionTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=_WHITE,
        ),
        "note": ParagraphStyle(
            "MelProjNote",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#5c4630"),
        ),
    }


def _draw_title_page(canvas, doc_, *, project_name: str, plan_count: int) -> None:
    """Full-bleed blue first page with vertically centered title hierarchy."""
    canvas.saveState()
    page_w, page_h = landscape(A4)
    canvas.setFillColor(_BLUE)
    canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    cx = page_w / 2
    cy = page_h / 2

    canvas.setFillColor(_TITLE_MUTED)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(cx, cy + 52, "ASSESS  ·  MEL PLAN")

    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 28)
    canvas.drawCentredString(cx, cy + 18, "Project level MEL plan")

    canvas.setStrokeColor(_TITLE_RULE)
    canvas.setLineWidth(1)
    canvas.line(cx - 90, cy - 4, cx + 90, cy - 4)

    canvas.setFillColor(_TITLE_MUTED)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(cx, cy - 28, "PROJECT")
    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(cx, cy - 46, project_name or "—")

    canvas.setFillColor(_TITLE_MUTED)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(cx, cy - 72, "PLANS INCLUDED")
    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(cx, cy - 90, str(plan_count))

    canvas.restoreState()


def _note_block(styles: dict, note: str) -> Table | None:
    note = (note or "").strip()
    if not note:
        return None
    body = re.sub(r"^Please note:\s*", "", note, flags=re.I)
    t = Table(
        [[Paragraph(f"<b>NOTE</b>  {_esc(body)}", styles["note"])]],
        colWidths=["*"],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _AMBER),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e8c9a0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _chain_cell(row: dict[str, Any], styles: dict) -> Paragraph:
    label = (row.get("label") or "").strip()
    title = (row.get("title") or "").strip()
    kind = (row.get("kind") or "").lower()
    is_cta = bool(row.get("cta")) or kind == "goal"
    if is_cta and title.startswith("["):
        color = "#b45309" if kind == "goal" else "#0f766e"
        html = f"<b>{_esc(label)}</b><br/><font color='{color}'><i>{_esc(title)}</i></font>"
    else:
        html = f"<b>{_esc(label)}</b><br/>{_esc(title)}" if label else _esc(title)
    return Paragraph(html, styles["cell"])


def _logframe_table(frame: dict[str, Any], styles: dict, usable_w: float) -> Table:
    """Section title is row 0 so it cannot orphan from the table."""
    has_type = bool(frame.get("has_outcome_type"))
    if has_type:
        headers = ["Outcome type", "Results Chain", "Indicators", "Assumptions"]
        widths = [28 * mm, usable_w * 0.28, usable_w * 0.32, usable_w * 0.28]
        scale = usable_w / sum(widths)
        widths = [w * scale for w in widths]
    else:
        headers = ["Results Chain", "Indicators", "Assumptions"]
        widths = [usable_w * 0.34, usable_w * 0.33, usable_w * 0.33]

    ncols = len(headers)
    title_row = [Paragraph("Log frame", styles["section_title"])] + [""] * (ncols - 1)
    data = [title_row, [Paragraph(h, styles["th"]) for h in headers]]
    for row in frame.get("outcomes") or []:
        inds = row.get("indicators") or []
        ind_html = "<br/>".join(
            f"{i}. {_esc(name)}" if len(inds) > 1 else _esc(name)
            for i, name in enumerate(inds, 1)
        )
        assumptions = _esc(row.get("assumptions") or "")
        if has_type:
            cells = [
                Paragraph(_esc(row.get("outcome_type") or ""), styles["cell"]),
                _chain_cell(row, styles),
                Paragraph(ind_html or "", styles["cell"]),
                Paragraph(assumptions, styles["cell"]),
            ]
        else:
            cells = [
                _chain_cell(row, styles),
                Paragraph(ind_html or "", styles["cell"]),
                Paragraph(assumptions, styles["cell"]),
            ]
        data.append(cells)

    table = Table(data, colWidths=widths, repeatRows=2)
    style_cmds = [
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), _BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 1), _WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, _HAIR),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
    ]
    for i, row in enumerate(frame.get("outcomes") or [], start=2):
        kind = (row.get("kind") or "").lower()
        if kind == "goal":
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), _GOAL))
        elif kind == "output":
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), _OUTPUT))
    table.setStyle(TableStyle(style_cmds))
    return table


def _methodology_table(frame: dict[str, Any], styles: dict, usable_w: float) -> Table:
    headers = [
        "Indicator",
        "Type",
        "Data",
        "Method",
        "Frequency",
        "Playbooks",
    ]
    widths = [
        usable_w * 0.20,
        usable_w * 0.08,
        usable_w * 0.18,
        usable_w * 0.22,
        usable_w * 0.14,
        usable_w * 0.18,
    ]
    m_title = frame.get("methodology_heading") or "Data and methodology for indicators"
    title_row = [Paragraph(_esc(m_title), styles["section_title"])] + [""] * 5
    data = [title_row, [Paragraph(h, styles["th"]) for h in headers]]
    for row in frame.get("methodology") or []:
        data.append(
            [
                Paragraph(_esc(row.get("indicator") or ""), styles["cell_bold"]),
                Paragraph(_esc(row.get("monitoring_type") or ""), styles["cell"]),
                Paragraph(_esc(row.get("data") or ""), styles["cell"]),
                Paragraph(_esc(row.get("method") or ""), styles["cell"]),
                Paragraph(_esc(row.get("frequency") or ""), styles["cell"]),
                Paragraph(playbooks_as_reportlab_xml(row.get("playbooks") or ""), styles["cell"]),
            ]
        )
    if len(data) == 2:
        data.append([Paragraph("—", styles["cell"]) for _ in headers])

    table = Table(data, colWidths=widths, repeatRows=2)
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                ("BACKGROUND", (0, 1), (-1, 1), _BLUE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, _HAIR),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ]
        )
    )
    return table


def _append_shared_field_setup(story: list, styles: dict, outro: list[str]) -> None:
    """Render Frequency + Field setup from outro, once."""
    items = list(outro or [])
    if not items:
        return

    def norm(t: str) -> str:
        return re.sub(r"\.$", "", (t or "").strip().lower())

    freq_idx = next((i for i, p in enumerate(items) if norm(p) == "frequency"), -1)
    after = next(
        (
            i
            for i, p in enumerate(items)
            if i > freq_idx and (norm(p).startswith("what do you do") or norm(p) == "sampling")
        ),
        -1,
    )
    if freq_idx >= 0 and after > freq_idx:
        frequency, field = items[freq_idx:after], items[after:]
    elif freq_idx == 0:
        frequency, field = items[:2], items[2:]
    else:
        frequency, field = [], items

    if frequency:
        story.append(Paragraph("Frequency", styles["h1"]))
        for para in frequency:
            if norm(para) == "frequency":
                continue
            story.append(Paragraph(_esc(para), styles["body"]))

    story.append(Paragraph("Field setup", styles["h1"]))
    i = 0
    while i < len(field):
        para = field[i]
        n = norm(para)
        if n in {
            "sampling",
            "field setup for data collections",
            "what do you do with the mel plan?",
            "what do you do with the mel plan",
        }:
            story.append(Paragraph(_esc(para.rstrip(".")), styles["h3"]))
            i += 1
            continue
        if para.startswith(
            ("For watershed", "Within each watershed", "Zones that are distinct")
        ):
            bullets = []
            while i < len(field) and field[i].startswith(
                ("For watershed", "Within each watershed", "Zones that are distinct")
            ):
                bullets.append(field[i])
                i += 1
            for n_i, b in enumerate(bullets, 1):
                story.append(Paragraph(f"<b>{n_i}.</b> {_esc(b)}", styles["body"]))
            continue
        if para.startswith(
            ("Select control assets:", "Asset allocation:", "Deploy Instruments:", "Train community")
        ):
            steps = []
            while i < len(field) and field[i].startswith(
                (
                    "Select control assets:",
                    "Asset allocation:",
                    "Deploy Instruments:",
                    "Train community",
                )
            ):
                steps.append(field[i])
                i += 1
            for n_i, step in enumerate(steps, 1):
                colon = step.find(":")
                title = step[: colon + 1] if colon >= 0 else step
                body = step[colon + 1 :] if colon >= 0 else ""
                story.append(
                    Paragraph(
                        f"<b>{n_i}. {_esc(title)}</b>{_esc(body)}",
                        styles["body"],
                    )
                )
            continue
        story.append(Paragraph(_esc(para), styles["body"]))
        i += 1


def build_mel_project_pdf(
    *,
    project_name: str,
    plans: list[dict[str, Any]],
) -> bytes:
    """Build one landscape PDF for all MEL plans in a project.

    Shared overview / frequency / field-setup prose appears once. Each plan
    contributes its log frame + methodology (+ note).
    """
    styles = _styles()
    page_w, _page_h = landscape(A4)
    margin = 12 * mm
    usable_w = page_w - 2 * margin

    frames: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for plan in plans:
        slug = plan.get("intervention_slug") or ""
        outcome_ids = (plan.get("plan_json") or {}).get("outcome_ids") or []
        try:
            from app.modules.assess.services.mel_logframe import resolve_selectable_outcomes

            outcomes = resolve_selectable_outcomes(slug, outcome_ids)
            frame = build_logframe_plan(
                intervention_slug=slug,
                selected_outcomes=outcomes,
                selected_outcome_ids=outcome_ids,
            )
        except KeyError:
            continue
        frames.append((plan, frame))

    if not frames:
        raise ValueError("No exportable MEL plans with log-frame templates in this project")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"{project_name} — Intervention MEL plans",
    )

    story: list = []
    # Blank first page — title is drawn by onFirstPage; content starts after break.
    story.append(PageBreak())

    shared_intro = frames[0][1].get("intro") or []
    story.append(Paragraph("Overview", styles["h1"]))
    for para in shared_intro:
        story.append(Paragraph(_esc(para), styles["body"]))

    for plan, frame in frames:
        name = frame.get("name") or plan.get("name") or plan.get("intervention_slug")
        plan_label = plan.get("name") or name
        # Keep only the intervention labels together — Log frame title lives in the table.
        story.append(
            KeepTogether(
                [
                    Paragraph(f"{_esc(name)}", styles["h2"]),
                    Paragraph(f"Plan: {_esc(plan_label)}", styles["meta"]),
                ]
            )
        )
        story.append(_logframe_table(frame, styles, usable_w))
        note = _note_block(styles, frame.get("note") or "")
        if note:
            story.append(Spacer(1, 4))
            story.append(note)
        story.append(Spacer(1, 6))
        story.append(_methodology_table(frame, styles, usable_w))
        story.append(Spacer(1, 10))

    _append_shared_field_setup(story, styles, frames[0][1].get("outro") or [])

    def _on_first(canvas, doc_):
        _draw_title_page(canvas, doc_, project_name=project_name, plan_count=len(frames))

    doc.build(story, onFirstPage=_on_first, onLaterPages=lambda c, d: None)
    return buf.getvalue()
