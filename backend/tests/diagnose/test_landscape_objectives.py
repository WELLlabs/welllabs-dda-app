from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_pdf import PdfPages

from app.modules.diagnose.services.diagnosis_atlas.build import _save_landscape_objective_pages
from app.modules.diagnose.services.landscape_objectives import (
    get_landscape_objective,
    load_landscape_objectives,
    load_specific_objectives,
    specific_objectives_for_landscape,
)


def test_load_landscape_objectives_from_csv():
    objs = load_landscape_objectives()
    assert len(objs) == 8
    assert [o["landscape_id"] for o in objs] == [f"L-0{i}" for i in range(1, 9)]
    first = objs[0]
    assert first["objective_id"] == "L-01"
    assert first["landscape_objective"]


def test_specific_objectives_exclude_purpose():
    specs = specific_objectives_for_landscape("L-01")
    assert len(specs) >= 3
    assert all(s["landscape_id"] == "L-01" for s in specs)
    assert "purpose" not in specs[0]
    assert specs[0]["objective_id"].startswith("L-01-")
    assert specs[0]["specific_objective"]
    assert specs[0]["wiser_dimension"]
    assert len(load_specific_objectives()) > 8


def test_landscape_objective_pdf_page(tmp_path: Path):
    obj = get_landscape_objective("L-02")
    assert obj is not None
    hyps = [
        {
            "hypothesis": "Drinking water fails in summer",
            "status": "validated",
            "landscape_objective": obj,
        }
    ]
    out = tmp_path / "objective.pdf"
    with PdfPages(out) as pdf:
        last = _save_landscape_objective_pages(pdf, hyps, 1)
    assert last >= 1
    raw = out.read_bytes()
    assert raw[:4] == b"%PDF"
