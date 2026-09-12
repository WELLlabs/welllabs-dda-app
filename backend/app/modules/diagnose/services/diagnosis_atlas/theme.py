"""WELL Labs report theme (matches clinton_code REPORT_THEME)."""

from __future__ import annotations

import textwrap

import matplotlib.patches as mpatches

WELL_COLORS = {
    "deep_blue": "#00306d",
    "bright_blue": "#1c75e9",
    "green": "#1c7a1a",
    "brown": "#6e3f2e",
    "rust": "#b5523a",
    "golden_ochre": "#fcb912",
    "sky_blue": "#a3d8f4",
    "light_grey": "#e6e9eb",
    "soft_cream": "#fff1e5",
    "white": "#ffffff",
    "black": "#000000",
}

REPORT_THEME = {
    "ink": WELL_COLORS["deep_blue"],
    "muted": WELL_COLORS["brown"],
    "line": WELL_COLORS["light_grey"],
    "panel": WELL_COLORS["white"],
    "panel_alt": WELL_COLORS["soft_cream"],
    "green": WELL_COLORS["green"],
    "green_dark": WELL_COLORS["deep_blue"],
    "blue": WELL_COLORS["bright_blue"],
    "amber": WELL_COLORS["golden_ochre"],
    "red": WELL_COLORS["rust"],
    "rust": WELL_COLORS["rust"],
    "brown": WELL_COLORS["brown"],
    "sky": WELL_COLORS["sky_blue"],
    "cream": WELL_COLORS["soft_cream"],
    "white": WELL_COLORS["white"],
    "black": WELL_COLORS["black"],
}

DEFAULT_PAGE_SIZE = (11.69, 8.27)  # A4 landscape inches

FIELD_HANDOFF_ROWS = [
    ["Map clue", "Observe", "Ask"],
    [
        "Ridge / steep slope / dense drainage",
        "Runoff marks, gullies, soil depth, dry sources, failed structures",
        "Where does water run fastest, where does soil move, and which source dries first?",
    ],
    [
        "Declining, lost, or strongly seasonal JRC water",
        "Hydroperiod, siltation, breached structures, encroachment, pumping, channel movement",
        "When did it fill and dry earlier versus now, what changed, and who lost access?",
    ],
    [
        "High cropping or groundwater stress",
        "Crop choice, pumps, well depth, second-crop source, dry tail-end plots",
        "What enables the second crop, who misses it, and has pumping increased?",
    ],
    [
        "Low WISER access or crop resilience",
        "Fields left uncropped, failed rabi plots, protective irrigation points, storage, soil moisture",
        "Why does crop area fall in dry years, who can still irrigate, and what makes that possible?",
    ],
    [
        "Low / canal / nala / command area",
        "Standing water, salinity, blocked drains, broken outlets, crop stress",
        "Where does water stand, who gets canal water first or last, and what blocks flow?",
    ],
    [
        "Social stress overlap",
        "Remote hamlets, weak sources, time burden, women-led coping",
        "Who pays more, walks farther, gets water last, or was missing from the discussion?",
    ],
]

# Matches reference atlas map-guide (four categories; JRC shown only if paired elsewhere).
MAP_GUIDE = [
    (
        "Context Maps",
        "Location, selected boundary, state context, access routes, built environment, and satellite reference.",
    ),
    (
        "Hydrology & Landscape Controls",
        "Elevation, drainage clues, land use / land cover, cropping intensity, WISER groundwater stress, aquifer setting, and climate trend.",
    ),
    (
        "WISER Outcome Layers",
        "Outcome-style layers for irrigation access, crop resilience in dry years, and groundwater stress.",
    ),
    (
        "Social & Demographic Profile",
        "Population and marginalized-community patterns used to plan inclusive field verification.",
    ),
]


def theme(key: str) -> str:
    return REPORT_THEME.get(key, key)


def page_setup(figsize=None, face: str = "cream"):
    import matplotlib.pyplot as plt

    if figsize is None:
        figsize = DEFAULT_PAGE_SIZE
    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(theme(face))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(theme(face))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def report_header(ax, title: str, subtitle: str = "", section: str = "Problem Diagnosis", right_label: str = ""):
    ax.add_patch(
        mpatches.Rectangle((0, 0.890), 1, 0.110, facecolor=theme("green_dark"), edgecolor="none")
    )
    ax.add_patch(
        mpatches.Rectangle((0, 0.887), 1, 0.006, facecolor=theme("amber"), edgecolor="none")
    )
    ax.text(
        0.045,
        0.975,
        section.upper(),
        fontsize=7.4,
        color=theme("sky"),
        ha="left",
        va="top",
        fontweight="bold",
    )
    ax.text(
        0.045,
        0.946,
        title,
        fontsize=14.0,
        color=theme("white"),
        ha="left",
        va="top",
        fontweight="bold",
    )
    if subtitle:
        ax.text(
            0.045,
            0.908,
            subtitle,
            fontsize=7.8,
            color=theme("cream"),
            ha="left",
            va="top",
        )
    if right_label:
        ax.text(
            0.955,
            0.946,
            right_label,
            fontsize=8.0,
            color=theme("cream"),
            ha="right",
            va="top",
            fontweight="bold",
        )


def footer(ax, label: str = "", page_num: int | None = None):
    ax.plot([0.045, 0.955], [0.052, 0.052], color=theme("line"), linewidth=0.8)
    if label:
        text = "\n".join(textwrap.wrap(str(label), width=118)[:2])
        ax.text(
            0.045,
            0.018,
            text,
            fontsize=6.6,
            color=theme("muted"),
            ha="left",
            va="bottom",
            linespacing=1.05,
        )
    if page_num is not None:
        ax.text(
            0.955,
            0.018,
            str(page_num),
            fontsize=6.6,
            color=theme("muted"),
            ha="right",
            va="bottom",
        )


def wrapped(ax, text, x, y, width=80, fontsize=8.5, color="ink", weight="normal", line_step=0.020):
    lines = textwrap.wrap(str(text or ""), width=max(1, int(width))) or [""]
    for line in lines:
        ax.text(
            x,
            y,
            line,
            fontsize=fontsize,
            color=theme(color),
            fontweight=weight,
            ha="left",
            va="top",
        )
        y -= line_step
    return y


def rounded_panel(ax, x, y, w, h, face="panel", edge="line", radius=0.014):
    patch = mpatches.FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=mpatches.BoxStyle("Round", pad=0.008, rounding_size=radius),
        facecolor=theme(face),
        edgecolor=theme(edge),
        linewidth=0.8,
    )
    ax.add_patch(patch)
    return patch


def metric_card(ax, x, y, w, h, label: str, value: str, accent: str = "green"):
    """Cover KPI card with left accent bar (matches clinton/reference)."""
    rounded_panel(ax, x, y, w, h, face="panel", edge="line", radius=0.010)
    ax.add_patch(
        mpatches.Rectangle((x, y), 0.008, h, facecolor=theme(accent), edgecolor="none", zorder=3)
    )
    ax.text(
        x + w / 2,
        y + h * 0.72,
        str(label).upper(),
        fontsize=6.2,
        color=theme("muted"),
        ha="center",
        va="center",
        fontweight="bold",
    )
    ax.text(
        x + w / 2,
        y + h * 0.38,
        str(value)[:22],
        fontsize=10.5,
        color=theme("ink"),
        ha="center",
        va="center",
        fontweight="bold",
    )


def setup_map_page(
    title: str,
    subtitle: str = "",
    section: str = "Problem Diagnosis",
    footer_label: str = "",
    *,
    map_rect: tuple[float, float, float, float] | None = None,
):
    fig, ax_bg = page_setup()
    report_header(ax_bg, title, subtitle, section=section)
    footer(ax_bg, footer_label)
    # Default leaves room on the right for colorbar + stats (avoids legend/colorbar clash).
    rect = map_rect or (0.050, 0.145, 0.620, 0.700)
    ax_map = fig.add_axes(list(rect))
    ax_map.set_facecolor("#f7fafc")
    return fig, ax_bg, ax_map
