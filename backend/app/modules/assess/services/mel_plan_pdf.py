"""Generate a portrait MEL plan PDF matching the Assess website visual language."""

from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.assess.services.mel_measurement_catalog import build_schedule_packages

# Website @theme brand tokens (frontend/src/app.css)
_BRAND_NAVY = colors.HexColor("#0a3d2a")
_BRAND_BLUE = colors.HexColor("#0d983b")
_BRAND_STEEL = colors.HexColor("#15803d")
_BRAND_SKY_SOFT = colors.HexColor("#f0fdf4")
_BRAND_SKY_MID = colors.HexColor("#dcfce7")
_BRAND_FOREST = colors.HexColor("#186d13")
_HAIRLINE = colors.HexColor("#e1e7ef")
_PANEL_RAISED = colors.HexColor("#f9fafc")
_WHITE = colors.white
_AMBER_SOFT = colors.HexColor("#fff7ed")
_AMBER = colors.HexColor("#c2410c")

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_CATEGORY_SHORT = {
    "Biophysical (plot / structure level)": "Biophysical",
    "Socio-economic": "Socio-economic",
    "Watershed-level": "Watershed",
}

_PACKAGE_LABELS = {
    "continuous_everyday": "Continuous · Everyday",
    "continuous_weekly": "Continuous · Weekly",
    "continuous_monthly": "Continuous · Monthly",
    "one_time": "One-time",
    "bme": "BME survey",
}

_TOC = (
    ("1", "Assess overview & contents"),
    ("2", "Selected intervention"),
    ("3", "Outcomes (selected & not selected)"),
    ("4", "Indicators & details"),
    ("5", "Indicator checking methods"),
    ("6", "ODK form guide"),
)


@lru_cache(maxsize=1)
def _register_brand_fonts() -> dict[str, str]:
    mapping = {
        "headline": "Helvetica-Bold",
        "headline_semi": "Helvetica-Bold",
        "body": "Helvetica",
        "body_medium": "Helvetica",
        "body_semi": "Helvetica-Bold",
    }
    files = {
        "MelJosefinBold": _FONTS_DIR / "JosefinSans-Bold.ttf",
        "MelJosefinSemi": _FONTS_DIR / "JosefinSans-SemiBold.ttf",
        "MelMontserrat": _FONTS_DIR / "Montserrat-Regular.ttf",
        "MelMontserratMedium": _FONTS_DIR / "Montserrat-Medium.ttf",
        "MelMontserratSemi": _FONTS_DIR / "Montserrat-SemiBold.ttf",
    }
    if not all(path.is_file() for path in files.values()):
        return mapping
    for name, path in files.items():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return {
        "headline": "MelJosefinBold",
        "headline_semi": "MelJosefinSemi",
        "body": "MelMontserrat",
        "body_medium": "MelMontserratMedium",
        "body_semi": "MelMontserratSemi",
    }


def _clean(text: str | None, *, limit: int | None = None) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _short_category(label: str | None) -> str:
    raw = (label or "").strip()
    return _CATEGORY_SHORT.get(raw, raw or "Other")


def _package_label(package_id: str) -> str:
    return _PACKAGE_LABELS.get(package_id, package_id.replace("_", " "))


def _kv_table(rows: list[tuple[str, str]], *, usable_w: float, label_w: float, styles: dict) -> Table:
    data = [
        [
            Paragraph(f"<b>{_clean(k)}</b>", styles["cell_label"]),
            Paragraph(_clean(v) or "—", styles["cell"]),
        ]
        for k, v in rows
    ]
    table = Table(data, colWidths=[label_w, usable_w - label_w])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), _BRAND_SKY_SOFT),
                ("BACKGROUND", (1, 0), (1, -1), _WHITE),
                ("BOX", (0, 0), (-1, -1), 0.6, _HAIRLINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, _HAIRLINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    return table


def _section_title(number: str, title: str, styles: dict) -> list:
    bar = Table([[""]], colWidths=[3], rowHeights=[14])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _BRAND_BLUE)]))
    heading = Table(
        [[bar, Paragraph(f"{number}. {title}", styles["h1"])]],
        colWidths=[6, None],
    )
    heading.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    return [Spacer(1, 6), heading, Spacer(1, 6)]


def _card(content_flowables: list, *, usable_w: float, selected: bool = True) -> Table:
    """Bordered panel as a multi-row table so ReportLab can split across pages.

    A 1×1 wrapper around all content cannot split; tall packages (e.g. BME
    field checklists) then raise LayoutError when taller than the frame.
    """
    rows = content_flowables or [Spacer(1, 1)]
    table = Table([[f] for f in rows], colWidths=[usable_w])
    border = _BRAND_BLUE if selected else _HAIRLINE
    bg = _BRAND_SKY_SOFT if selected else _PANEL_RAISED
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.7, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (0, 0), 6),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 1),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _append_card(
    story: list,
    content_flowables: list,
    *,
    usable_w: float,
    selected: bool = True,
    gap: float = 6,
    keep: bool = False,
) -> None:
    """Append a card; only KeepTogether when content is expected to fit one page."""
    card = _card(content_flowables, usable_w=usable_w, selected=selected)
    spacer = Spacer(1, gap)
    if keep:
        story.append(KeepTogether([card, spacer]))
    else:
        story.append(card)
        story.append(spacer)


def _tag_chip(text: str, styles: dict, *, tone: str = "green") -> Table:
    bg = _BRAND_SKY_MID if tone == "green" else _AMBER_SOFT
    border = _BRAND_BLUE if tone == "green" else _AMBER
    fg = "#15803d" if tone == "green" else "#c2410c"
    chip = Table(
        [[Paragraph(f"<font color='{fg}'><b>{_clean(text, limit=48)}</b></font>", styles["chip"])]],
        colWidths=[None],
    )
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    return chip


def _data_table(header: list, rows: list[list], col_widths: list[float]) -> Table:
    table = Table([header, *rows], colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BACKGROUND", (0, 0), (-1, 0), _BRAND_SKY_MID),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, _BRAND_BLUE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _BRAND_SKY_SOFT]),
                ("BOX", (0, 0), (-1, -1), 0.6, _HAIRLINE),
                ("INNERGRID", (0, 1), (-1, -1), 0.35, _HAIRLINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_mel_plan_pdf(
    *,
    intervention: dict,
    outcomes: list[dict],
    indicators: list[dict],
    all_outcomes: list[dict] | None = None,
) -> bytes:
    """Build a multi-page portrait MEL plan PDF.

    ``outcomes`` = selected outcomes. ``all_outcomes`` = full catalog for the
    intervention (used to list outcomes that were not selected).
    """
    fonts = _register_brand_fonts()
    packages_payload = build_schedule_packages(indicators)
    matched = {item["id"]: item for item in packages_payload["matched_indicators"]}
    unmatched = packages_payload["unmatched_indicators"]

    selected_ids = {o.get("id") for o in outcomes}
    catalog_outcomes = all_outcomes if all_outcomes is not None else outcomes
    not_selected = [o for o in catalog_outcomes if o.get("id") not in selected_ids]

    page_w, page_h = A4
    left = 16 * mm
    right = 16 * mm
    top = 14 * mm
    bottom = 14 * mm
    usable_w = page_w - left - right

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=f"MEL Plan · {intervention.get('name') or 'Plan'}",
    )

    base = getSampleStyleSheet()
    styles = {
        "eyebrow": ParagraphStyle(
            "MelEyebrow",
            parent=base["Normal"],
            fontName=fonts["body_semi"],
            fontSize=8,
            leading=10,
            textColor=_BRAND_BLUE,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "title": ParagraphStyle(
            "MelTitle",
            parent=base["Heading1"],
            fontName=fonts["headline"],
            fontSize=18,
            leading=22,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "MelH1",
            parent=base["Heading1"],
            fontName=fonts["headline_semi"],
            fontSize=13,
            leading=16,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "h2": ParagraphStyle(
            "MelH2",
            parent=base["Heading2"],
            fontName=fonts["body_semi"],
            fontSize=10,
            leading=13,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "MelBody",
            parent=base["BodyText"],
            fontName=fonts["body"],
            fontSize=9,
            leading=12,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
        ),
        "muted": ParagraphStyle(
            "MelMuted",
            parent=base["BodyText"],
            fontName=fonts["body"],
            fontSize=8,
            leading=11,
            textColor=_BRAND_STEEL,
            alignment=TA_LEFT,
        ),
        "cell": ParagraphStyle(
            "MelCell",
            parent=base["BodyText"],
            fontName=fonts["body"],
            fontSize=8,
            leading=10.5,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
        ),
        "cell_label": ParagraphStyle(
            "MelCellLabel",
            parent=base["BodyText"],
            fontName=fonts["body_semi"],
            fontSize=8,
            leading=10.5,
            textColor=_BRAND_NAVY,
            alignment=TA_LEFT,
        ),
        "chip": ParagraphStyle(
            "MelChip",
            parent=base["BodyText"],
            fontName=fonts["body_semi"],
            fontSize=7.5,
            leading=9,
            textColor=_BRAND_FOREST,
            alignment=TA_LEFT,
        ),
    }

    story: list = []

    # ── 1. Assess & TOC ──────────────────────────────────────────────
    header = Table(
        [
            [Paragraph("ASSESS · MEL PLAN", styles["eyebrow"])],
            [Paragraph("Monitoring, Evaluation & Learning plan", styles["title"])],
            [
                Paragraph(
                    "Export from the Water Security Tool Assess module. "
                    "This document records the selected intervention, outcomes, "
                    "indicators, checking methods, and ODK form packages.",
                    styles["muted"],
                )
            ],
        ],
        colWidths=[usable_w],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BRAND_SKY_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, _HAIRLINE),
                ("LINEBELOW", (0, -1), (-1, -1), 2.5, _BRAND_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(header)
    story.extend(_section_title("1", "Assess overview & contents", styles))
    story.append(
        Paragraph(
            f"<b>Plan for:</b> {_clean(intervention.get('name'))}",
            styles["body"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("Table of contents", styles["h2"]))
    toc_rows = [
        [
            Paragraph(f"<b>{num}</b>", styles["cell_label"]),
            Paragraph(label, styles["cell"]),
        ]
        for num, label in _TOC
    ]
    toc = Table(toc_rows, colWidths=[12 * mm, usable_w - 12 * mm])
    toc.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BACKGROUND", (0, 0), (0, -1), _BRAND_SKY_MID),
                ("BOX", (0, 0), (-1, -1), 0.6, _HAIRLINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, _HAIRLINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(toc)

    # ── 2. Selected intervention ─────────────────────────────────────
    story.append(PageBreak())
    story.extend(_section_title("2", "Selected intervention", styles))
    story.append(
        _kv_table(
            [
                ("Name", intervention.get("name") or "—"),
                ("Slug", intervention.get("slug") or "—"),
                ("Requirement", intervention.get("requirement") or "—"),
                ("Outcomes in catalog", str(len(catalog_outcomes))),
                ("Outcomes selected", str(len(outcomes))),
                ("Outcomes not selected", str(len(not_selected))),
                ("Indicators in this plan", str(len(indicators))),
                ("ODK packages derived", str(len(packages_payload["packages"]))),
            ],
            usable_w=usable_w,
            label_w=48 * mm,
            styles=styles,
        )
    )

    # ── 3. Outcomes selected & not selected ──────────────────────────
    story.append(PageBreak())
    story.extend(_section_title("3", "Outcomes (selected & not selected)", styles))

    story.append(Paragraph("Selected outcomes", styles["h2"]))
    if not outcomes:
        story.append(Paragraph("No outcomes selected.", styles["muted"]))
    else:
        for outcome in outcomes:
            title = outcome.get("title") or outcome.get("outcome") or "Outcome"
            chips = []
            chip_row = [
                _tag_chip(_short_category(outcome.get("category_label")), styles),
            ]
            if outcome.get("must_measure"):
                chip_row.append(_tag_chip("Must measure", styles))
            chip_row.append(_tag_chip("Selected", styles, tone="green"))
            chips_table = Table([chip_row], colWidths=None)
            chips_table.setStyle(
                TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ]
                )
            )
            block = [
                Paragraph(f"<b>{_clean(title)}</b>", styles["body"]),
                Spacer(1, 4),
                chips_table,
            ]
            if outcome.get("assumptions"):
                block.append(Spacer(1, 4))
                block.append(Paragraph("<b>Assumptions</b>", styles["muted"]))
                block.append(Paragraph(_clean(outcome.get("assumptions"), limit=900), styles["cell"]))
            inds = outcome.get("indicators") or []
            if inds:
                block.append(Spacer(1, 4))
                block.append(Paragraph(f"<b>Indicators ({len(inds)})</b>", styles["muted"]))
                for ind in inds:
                    block.append(Paragraph(f"• {_clean(ind)}", styles["cell"]))
            else:
                block.append(Spacer(1, 4))
                block.append(Paragraph("No indicators listed for this outcome.", styles["muted"]))
            # Outcomes can list many indicators; allow the card to split.
            _append_card(story, block, usable_w=usable_w, selected=True, gap=6, keep=False)

    story.append(Paragraph("Not selected", styles["h2"]))
    if not not_selected:
        story.append(Paragraph("All catalog outcomes for this intervention are included.", styles["muted"]))
    else:
        story.append(
            Paragraph(
                f"{len(not_selected)} outcome(s) in the catalog were not included in this plan.",
                styles["muted"],
            )
        )
        story.append(Spacer(1, 4))
        for outcome in not_selected:
            title = outcome.get("title") or outcome.get("outcome") or "Outcome"
            cat = _short_category(outcome.get("category_label"))
            n_ind = len(outcome.get("indicators") or [])
            block = [
                Paragraph(f"<b>{_clean(title)}</b>", styles["body"]),
                Spacer(1, 3),
                Paragraph(
                    f"{_clean(cat)} · {n_ind} indicator(s)"
                    + (" · Must measure (always on)" if outcome.get("must_measure") else ""),
                    styles["muted"],
                ),
            ]
            _append_card(story, block, usable_w=usable_w, selected=False, gap=4, keep=True)

    # ── 4. Indicators & details ──────────────────────────────────────
    story.append(PageBreak())
    story.extend(_section_title("4", "Indicators & details", styles))
    story.append(
        Paragraph(
            "All indicators from selected outcomes, with category and parent outcome.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4))
    if not indicators:
        story.append(Paragraph("No indicators to collect.", styles["muted"]))
    else:
        header = [
            Paragraph("<b>#</b>", styles["cell_label"]),
            Paragraph("<b>Indicator</b>", styles["cell_label"]),
            Paragraph("<b>Outcome</b>", styles["cell_label"]),
            Paragraph("<b>Category</b>", styles["cell_label"]),
            Paragraph("<b>Must measure</b>", styles["cell_label"]),
        ]
        fracs = (0.06, 0.36, 0.30, 0.16, 0.12)
        widths = [usable_w * f for f in fracs]
        rows = []
        for idx, item in enumerate(indicators, start=1):
            rows.append(
                [
                    Paragraph(str(idx), styles["cell"]),
                    Paragraph(_clean(item.get("indicator"), limit=120), styles["cell"]),
                    Paragraph(_clean(item.get("outcome"), limit=80), styles["cell"]),
                    Paragraph(_short_category(item.get("category_label")), styles["cell"]),
                    Paragraph("Yes" if item.get("must_measure") else "No", styles["cell"]),
                ]
            )
        story.append(_data_table(header, rows, widths))

    # ── 5. Indicator checking methods ────────────────────────────────
    story.append(PageBreak())
    story.extend(_section_title("5", "Indicator checking methods", styles))
    story.append(
        Paragraph(
            "How each indicator is measured: unit, data to collect, method, frequency, and analysis. "
            "Matched to the indicators MEL catalog where available.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4))

    if not indicators:
        story.append(Paragraph("No indicators to check.", styles["muted"]))
    else:
        for item in indicators:
            label = item.get("indicator") or item.get("label") or "Indicator"
            measurement = matched.get(item.get("id"), {}).get("measurement")
            block = [Paragraph(f"<b>{_clean(label)}</b>", styles["body"])]
            block.append(
                Paragraph(
                    f"Outcome: {_clean(item.get('outcome'))} · {_short_category(item.get('category_label'))}",
                    styles["muted"],
                )
            )
            if not measurement:
                block.append(Spacer(1, 4))
                block.append(
                    Paragraph(
                        "<i>No measurement recipe matched in the indicators MEL catalog.</i>",
                        styles["muted"],
                    )
                )
                _append_card(story, block, usable_w=usable_w, selected=False, gap=6, keep=True)
                continue

            # Title card stays short; kv table is a separate splitable flowable
            # so long measurement recipes cannot overflow a single page frame.
            _append_card(story, block, usable_w=usable_w, selected=True, gap=2, keep=True)
            story.append(
                _kv_table(
                    [
                        ("Unit", measurement.get("unit") or "—"),
                        ("Data to collect", measurement.get("data") or "—"),
                        ("Method of collection", measurement.get("method") or "—"),
                        ("When / frequency", measurement.get("frequency") or "—"),
                        ("Method of analysis", measurement.get("analysis") or "—"),
                        ("Playbooks", measurement.get("playbooks") or "—"),
                        (
                            "ODK packages",
                            ", ".join(_package_label(p) for p in (measurement.get("package_ids") or []))
                            or "—",
                        ),
                    ],
                    usable_w=usable_w,
                    label_w=42 * mm,
                    styles=styles,
                )
            )
            story.append(Spacer(1, 8))

    if unmatched:
        story.append(Paragraph("Unmatched indicators", styles["h2"]))
        story.append(
            Paragraph(
                "These indicators are in the plan but have no recipe in the measurement catalog:",
                styles["muted"],
            )
        )
        story.append(Spacer(1, 4))
        for item in unmatched:
            _append_card(
                story,
                [Paragraph(f"• {_clean(item.get('indicator'))}", styles["cell"])],
                usable_w=usable_w,
                selected=False,
                gap=3,
                keep=True,
            )

    # ── 6. ODK table guide ───────────────────────────────────────────
    story.append(PageBreak())
    story.extend(_section_title("6", "ODK form guide", styles))
    story.append(
        Paragraph(
            "Schedule packages derived from matched indicators. Use these as the guide for "
            "which ODK forms to publish (Continuous / One-time / BME).",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4))

    packages = packages_payload["packages"]
    if not packages:
        story.append(
            Paragraph(
                "No schedule packages could be derived from matched indicators.",
                styles["muted"],
            )
        )
    else:
        header = [
            Paragraph("<b>Package</b>", styles["cell_label"]),
            Paragraph("<b>Description</b>", styles["cell_label"]),
            Paragraph("<b>When</b>", styles["cell_label"]),
            Paragraph("<b>Indicators</b>", styles["cell_label"]),
            Paragraph("<b>Fields</b>", styles["cell_label"]),
        ]
        fracs = (0.18, 0.26, 0.18, 0.28, 0.10)
        widths = [usable_w * f for f in fracs]
        rows = []
        for package in packages:
            ind_names = "; ".join(
                _clean(i.get("indicator"), limit=40)
                for i in (package.get("indicators") or [])
                if i.get("indicator")
            )
            rows.append(
                [
                    Paragraph(f"<b>{_clean(package.get('title'), limit=40)}</b>", styles["cell"]),
                    Paragraph(_clean(package.get("description"), limit=120) or "—", styles["muted"]),
                    Paragraph(_clean(package.get("frequency_label"), limit=80) or "—", styles["cell"]),
                    Paragraph(
                        f"{len(package.get('indicators') or [])}: {_clean(ind_names, limit=140) or '—'}",
                        styles["cell"],
                    ),
                    Paragraph(str(len(package.get("suggested_fields") or [])), styles["cell"]),
                ]
            )
        story.append(_data_table(header, rows, widths))

        story.append(Spacer(1, 10))
        story.append(Paragraph("Field checklist by package", styles["h2"]))
        for package in packages:
            fields = package.get("suggested_fields") or []
            block = [
                Paragraph(f"<b>{_clean(package.get('title'))}</b>", styles["body"]),
                Paragraph(_clean(package.get("description")) or "", styles["muted"]),
                Spacer(1, 4),
            ]
            if not fields:
                block.append(Paragraph("No suggested fields.", styles["muted"]))
            else:
                for field in fields:
                    itype = field.get("input_type") or "decimal"
                    block.append(
                        Paragraph(
                            f"• <b>{_clean(field.get('label'), limit=80)}</b> "
                            f"<font color='#15803d'>({_clean(itype)})</font>",
                            styles["cell"],
                        )
                    )
            # BME / continuous packages can list dozens of fields — must split.
            _append_card(story, block, usable_w=usable_w, selected=True, gap=6, keep=False)

    doc.build(story)
    return buffer.getvalue()
