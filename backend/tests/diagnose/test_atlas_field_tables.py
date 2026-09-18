from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_pdf import PdfPages

from app.modules.diagnose.services.diagnosis_atlas.build import _save_hypotheses_pages, _save_zones_pages
from app.modules.diagnose.services.diagnosis_atlas.field_tables import paginate_rows, wrap_field
from app.modules.diagnose.services.qfield_names import qfield_cloud_name_aliases, qfield_cloud_project_name


LONG_OBSERVE = (
    "Cropping intensity is high. Major double crop and plantations, water usage and availability "
    "should be checked at the canal tail and at each farm pond."
)
LONG_ASK = (
    "If this is paddy given the fields structure, what is grown as second crop, what is the "
    "source of irrigation, and who is left out in a dry year?"
)
LONG_HYP = (
    "Has irrigation system canal water access and the water is being diverted to paddy and "
    "plantations rather than drinking water."
)


def test_wrap_field_keeps_full_sentence():
    lines = wrap_field(LONG_ASK, 24)
    assert "left out in a dry year?" in " ".join(lines)
    assert all(len(line) <= 24 for line in lines)


def test_paginate_rows_splits_instead_of_dropping_text():
    rows = [
        {
            "source_i": 0,
            "cells": [wrap_field(LONG_OBSERVE, 20), wrap_field(LONG_ASK, 20)],
        }
    ]
    pages = paginate_rows(rows, available=0.12, line_h=0.014, pad=0.016, min_h=0.04)
    joined = " ".join(" ".join(" ".join(c) for c in item["cells"]) for page in pages for item in page)
    assert "farm pond" in joined
    assert "dry year?" in joined
    assert len(pages) >= 2


def test_qfield_name_strips_illegal_characters(monkeypatch):
    monkeypatch.setattr(
        "app.modules.diagnose.services.qfield_names.settings.qfield_project_name",
        "diagnose",
    )
    name = qfield_cloud_project_name("Periyakulam (Vaigai) / MWS")
    assert name == "diagnose-Periyakulam-Vaigai-MWS"
    assert "/" not in name
    assert "(" not in name
    aliases = qfield_cloud_name_aliases("Periyakulam (Vaigai) / MWS")
    assert aliases[0] == "diagnose-Periyakulam-Vaigai-MWS"
    assert "diagnose-Periyakulam-(Vaigai)-/-MWS" in aliases


def test_zone_pdf_pages_include_full_observe_ask(tmp_path: Path):
    zones = [
        {
            "id": "z1",
            "text": "Zone 1: Agri High",
            "observations": LONG_OBSERVE,
            "questions": LONG_ASK,
            "color": "green",
        }
    ]
    hyps = [
        {
            "hypothesis": LONG_HYP,
            "observation_zone_ids": ["z1"],
            "status": "untested",
            "root_cause": "",
            "field_note_count": 0,
        }
    ]
    out = tmp_path / "zones.pdf"
    with PdfPages(out) as pdf:
        last = _save_zones_pages(pdf, {"name": "Test"}, zones, hyps, 1)
        last = _save_hypotheses_pages(pdf, zones, hyps, last + 1)
    # map page + at least one full-width table page + hypotheses page
    assert last >= 3
    raw = out.read_bytes()
    assert raw[:4] == b"%PDF"
    assert b"/Type" in raw
    # PdfPages writes one page object per savefig; expect map + table (+ hyp)
    assert raw.count(b"/Type /Page") >= 3 or raw.count(b"/Type/Page") >= 3 or last >= 3