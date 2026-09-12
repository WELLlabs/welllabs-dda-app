"""Concise EPA/ePRA appendix pages (clinton notebook pack, fallback content)."""

from __future__ import annotations

import textwrap

import matplotlib.pyplot as plt

from app.modules.diagnose.services.diagnosis_atlas.theme import (
    footer,
    page_setup,
    report_header,
    rounded_panel,
    theme,
    wrapped,
)

VALIDATED_HYPOTHESIS_COLUMN = "Validated hypothesis"

EPRA_WISER_GUIDE_PARAGRAPHS = [
    "Purpose: use the maps to test problem hypotheses with people and field observations.",
    "1. Start with the map clue: what does the desktop analysis suggest, and where is uncertainty highest?",
    "2. Walk one transect from ridge or source area to valley, tail-end, or problem area. Record GPS, photos, water signs, crop choices, and failed sources.",
    "3. Ask compound questions: what happens, when does it happen, who is affected first, and what changed in the last 5-10 years?",
    "4. Separate location from explanation: ePRA maps where the issue appears; FGD explains why it persists and who carries the burden.",
    "5. Close with a problem register: problem, likely root cause, map evidence, field evidence, people evidence, confidence, and next action.",
]

FIELD_SHEET_ROWS = [
    ["Field question", "What to ask in the field", "Record"],
    [
        "Where are we and who is present?",
        "Where are we, who is present, and which map clue are we checking?",
        "Village/hamlet, group, GPS/photo, map layer",
    ],
    [
        "How many are in agriculture?",
        "How many households or people are in farming, agricultural labour, sharecropping, or seasonal farm work?",
        "Households/share, farmer type, labour/sharecropper, season",
    ],
    [
        "What is the typical landholding size?",
        "What is the typical landholding size by group, and who has marginal, small, fragmented, or larger holdings?",
        "Typical size, range, farmer group, tenancy/sharecrop note",
    ],
    [
        "How many have access to irrigation?",
        "How many farmers have access to irrigation, what source do they use, who is excluded, and when does that source fail?",
        "Access count/share, source, excluded group, failure month",
    ],
    [
        "Where are their plots located?",
        "Where are their plots: upland or lowland, head or tail, near stream/canal, command or non-command, close or distant?",
        "Plot position, distance, slope/soil clue, head/tail/command status",
    ],
    [
        "What kind of crops do they grow?",
        "What crops do they grow in kharif, rabi, and summer, and which crops need assured water?",
        "Season, crop, water need, crop change",
    ],
    [
        "How does water availability shift choices?",
        "As water availability changes, which source lasts longest, which fails first, and how do crops, labour, or coping choices shift?",
        "Source, month, crop/livelihood shift, coping",
    ],
    [
        "What is the seasonality of water stress?",
        "Which months are water secure, stressed, dry, tanker-dependent, well-failure, or recovery months?",
        "Month calendar, source status, stress period, recovery",
    ],
    [
        "Where does rainwater move or recharge?",
        "When rain falls, where does water run, stand, soak, erode, or disappear?",
        "Place, sign, season, field photo",
    ],
    [
        "Where does drainage or canal water fail?",
        "Where does water stand or fail to reach, who is head/tail, and what blocks flow?",
        "Location, blockage, salinity/waterlogging",
    ],
    [
        "Who manages water decisions and repairs?",
        "Who repairs, decides turns or supply, and which past work helped or failed?",
        "Institution, asset, maintenance issue",
    ],
]

PROBLEM_REGISTER_ROWS = [
    ["Problem", "Likely cause", "Evidence", "Who affected", "Decision"],
    ["________________", "________________", "Map + field + people", "________________", "Confirm / Correct / Reject"],
    ["________________", "________________", "Map + field + people", "________________", "Confirm / Correct / Reject"],
    ["________________", "________________", "Map + field + people", "________________", "Confirm / Correct / Reject"],
]

HYPOTHESIS_SHEET_ROWS = [
    ["Hypothesis", "Map clue", "Observe", "Ask", VALIDATED_HYPOTHESIS_COLUMN],
    [
        "Ridge water scarcity",
        "High slope / ridge / dry upper area",
        "Dry sources, shallow soil, runoff marks, failed recharge works",
        "Which source dries first, and who loses crop or drinking water first?",
        "",
    ],
    [
        "Waterlogging or flooding",
        "Low area / nala / canal / command zone",
        "Standing water, salinity, blocked drain, crop stress",
        "Where does water stand, for how long, and who is affected?",
        "",
    ],
    [
        "Soil erosion",
        "Steep slope / dense drainage",
        "Rills, gullies, washed bunds, sediment",
        "Where does soil move during storms, and what protection exists?",
        "",
    ],
    [
        "High farm-water demand",
        "High cropping / second crop / extraction stress",
        "Pumps, wells, water-intensive crops, dry tail-end plots",
        "What enables the second crop, who misses it, and has pumping increased?",
        "",
    ],
]


def _draw_table(pdf, title: str, subtitle: str, rows: list[list[str]], footer_label: str, page_num: int, col_weights: list[float] | None = None):
    fig, ax = page_setup()
    report_header(ax, title, subtitle, section="Appendix")
    footer(ax, footer_label, page_num)

    col_count = max(len(r) for r in rows)
    rows = [list(r) + [""] * (col_count - len(r)) for r in rows]
    if not col_weights:
        if col_count == 3:
            col_weights = [0.24, 0.50, 0.26]
        elif col_count == 5:
            col_weights = [0.18, 0.20, 0.25, 0.28, 0.09]
        else:
            col_weights = [1.0 / col_count] * col_count

    table_left, table_right = 0.045, 0.955
    table_top, table_bottom = 0.845, 0.085
    table_width = table_right - table_left
    total_w = sum(col_weights)
    widths = [(w / total_w) * table_width for w in col_weights]

    # Adaptive row heights
    available = table_top - table_bottom
    heights = []
    for r_idx, row in enumerate(rows):
        max_lines = 1
        for c_idx, value in enumerate(row):
            wrap = max(8, int(col_weights[c_idx] * 105))
            lines = 0
            for raw in str(value or "").splitlines() or [""]:
                lines += max(1, len(textwrap.wrap(raw.strip(), width=wrap) or [""]))
            max_lines = max(max_lines, lines)
        heights.append(0.048 if r_idx == 0 else min(0.11, max(0.052, 0.018 + max_lines * 0.013)))
    scale = min(1.0, available / max(sum(heights), 0.001))
    heights = [h * scale for h in heights]

    y = table_top
    for r_idx, row in enumerate(rows):
        rh = heights[r_idx]
        x = table_left
        face = theme("green_dark") if r_idx == 0 else ("#ffffff" if r_idx % 2 == 0 else theme("panel"))
        for c_idx, value in enumerate(row):
            w = widths[c_idx]
            ax.add_patch(plt.Rectangle((x, y - rh), w, rh, facecolor=face, edgecolor=theme("line"), linewidth=0.65))
            wrap = max(8, int(col_weights[c_idx] * 105))
            text = "\n".join(textwrap.wrap(str(value or ""), width=wrap)[:6])
            ax.text(
                x + 0.006,
                y - rh / 2,
                text,
                fontsize=6.3,
                fontweight="bold" if r_idx == 0 else "normal",
                color="white" if r_idx == 0 else theme("ink"),
                ha="left",
                va="center",
                linespacing=1.05,
            )
            x += w
        y -= rh
    pdf.savefig(fig)
    plt.close(fig)


def save_appendix_divider(pdf, scale_name: str, page_num: int):
    fig, ax = page_setup()
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor=theme("green_dark"), edgecolor="none"))
    ax.text(0.09, 0.82, "APPENDIX", fontsize=12, color=theme("sky"), fontweight="bold", ha="left", va="top")
    ax.text(0.09, 0.75, "Concise EPA/ePRA Pack", fontsize=27, color="white", fontweight="bold", ha="left", va="top")
    body = (
        "Use these pages after the map-led diagnosis. They are separated from the main atlas so the report stays "
        "readable while the field team still gets the EPA/ePRA method and forms."
    )
    wrapped(ax, body, 0.09, 0.65, width=90, fontsize=11.0, color="cream", line_step=0.030)
    steps = [
        "1. Validate map clues",
        "2. Correct problem hypotheses",
        "3. Run focused ePRA questions",
        "4. Record confirmed root causes",
    ]
    x = 0.09
    for step in steps:
        num, rest = step.split(". ", 1)
        rounded_panel(ax, x, 0.28, 0.198, 0.12, face="green", edge="green", radius=0.012)
        ax.text(x + 0.012, 0.35, num + ".", fontsize=22, color=theme("sky"), fontweight="bold", ha="left", va="top")
        wrapped(ax, rest, x + 0.012, 0.31, width=17, fontsize=9.2, color="white", weight="bold", line_step=0.020)
        x += 0.218
    footer(ax, f"{scale_name} report appendix", page_num)
    # Force light footer text on dark page
    ax.texts[-1].set_color(theme("sky"))
    if len(ax.texts) >= 2:
        ax.texts[-2].set_color(theme("sky"))
    pdf.savefig(fig)
    plt.close(fig)


def save_field_validation_hypothesis_sheet(pdf, page_num: int):
    _draw_table(
        pdf,
        "Field Validation Hypothesis Sheet",
        "One-page starting sheet. Correct these hypotheses in the field and add new ones in the problem register.",
        HYPOTHESIS_SHEET_ROWS,
        "EPA/ePRA field validation pack",
        page_num,
        col_weights=[0.18, 0.20, 0.25, 0.28, 0.09],
    )


def save_epra_method_guide(pdf, page_num: int):
    fig, ax = page_setup()
    report_header(ax, "EPA/ePRA Method Guide", "Short method page for the field team.", section="Appendix")
    footer(ax, "EPA/ePRA method", page_num)
    y = 0.845
    for idx, para in enumerate(EPRA_WISER_GUIDE_PARAGRAPHS):
        if idx == 0:
            rounded_panel(ax, 0.055, y - 0.065, 0.890, 0.065, face="panel_alt")
            wrapped(ax, para, 0.075, y - 0.018, width=120, fontsize=9.4, weight="bold", line_step=0.022)
            y -= 0.095
            continue
        ax.plot(0.075, y - 0.008, "o", color=theme("green"), markersize=14)
        ax.text(0.075, y - 0.008, str(idx), fontsize=8, color="white", fontweight="bold", ha="center", va="center")
        body = para.split(". ", 1)[-1]
        y = wrapped(ax, body, 0.100, y, width=115, fontsize=9.0, line_step=0.024) - 0.020
    pdf.savefig(fig)
    plt.close(fig)


def save_epra_field_sheet(pdf, page_num: int):
    _draw_table(
        pdf,
        "Concise EPA/ePRA Field Sheet",
        "Use this as a fast field guide. The first column keeps the review inputs visible, but phrases them as natural field questions.",
        FIELD_SHEET_ROWS,
        "Concise EPA/ePRA Field Sheet",
        page_num,
        col_weights=[0.24, 0.50, 0.26],
    )


def save_problem_register(pdf, page_num: int):
    _draw_table(
        pdf,
        "Problem register output",
        "Record confirmed problems, likely causes, evidence, who is affected, and the decision.",
        PROBLEM_REGISTER_ROWS,
        "Problem register output",
        page_num,
        col_weights=[0.20, 0.20, 0.22, 0.18, 0.20],
    )


def append_epra_pack(pdf, scale_name: str, start_page: int) -> int:
    """Append full concise EPA/ePRA pack. Returns last page number used."""
    page = start_page
    page += 1
    save_appendix_divider(pdf, scale_name, page)
    page += 1
    save_field_validation_hypothesis_sheet(pdf, page)
    page += 1
    save_epra_method_guide(pdf, page)
    page += 1
    save_epra_field_sheet(pdf, page)
    page += 1
    save_problem_register(pdf, page)
    return page
