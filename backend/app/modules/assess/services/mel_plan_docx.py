"""Build a MEL plan .docx from mapping-derived outcomes and indicators."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from docx import Document
from docx.shared import Pt


def _append_question_list(doc: Document, title: str, questions: list[dict[str, Any]]) -> None:
    doc.add_heading(title, level=1)
    if not questions:
        doc.add_paragraph("None listed.")
        return
    for q in questions:
        text = (q.get("question") or "").strip()
        if not text:
            continue
        bits = []
        if q.get("input_type"):
            bits.append(str(q["input_type"]))
        if q.get("metric"):
            bits.append(str(q["metric"]))
        label = text if not bits else f"{text} ({', '.join(bits)})"
        doc.add_paragraph(label, style="List Number")
        skip = (q.get("skip_logic") or "").strip()
        if skip:
            doc.add_paragraph(f"Skip logic: {skip}", style="List Bullet")


def _apply_question_overrides(
    questions: list[dict[str, Any]],
    overrides: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge catalog questions with plan_json card edits (labels / include / order)."""
    if not questions:
        return []
    by_id = {str(o.get("id")): o for o in (overrides or []) if o.get("id")}
    if not by_id:
        return list(questions)

    enriched: list[dict[str, Any]] = []
    for q in questions:
        qid = str(q.get("variable_name") or q.get("id") or "")
        prev = by_id.get(qid)
        if prev is not None and prev.get("included") is False:
            continue
        item = dict(q)
        if prev and prev.get("label"):
            item["question"] = prev["label"]
        if prev and prev.get("input_type"):
            item["input_type"] = prev["input_type"]
        if prev and (prev.get("options") is not None or prev.get("selectors") is not None):
            opts = prev.get("options")
            if opts is None:
                opts = prev.get("selectors")
            item["selectors"] = list(opts or [])
        if prev and prev.get("metric") is not None:
            item["metric"] = prev.get("metric") or ""
        if prev and prev.get("hint"):
            item["skip_logic"] = prev.get("hint") or item.get("skip_logic")
        order = prev.get("order") if prev else None
        enriched.append({**item, "_order": order if order is not None else 10_000})

    enriched.sort(key=lambda x: (x.get("_order", 10_000), x.get("question") or ""))
    for item in enriched:
        item.pop("_order", None)
    return enriched


def build_mel_plan_docx(
    *,
    project_name: str,
    plan_name: str,
    intervention_name: str,
    outcomes: list[dict[str, Any]],
    one_time_questions: list[dict[str, Any]] | None = None,
    cm_questions: list[dict[str, Any]] | None = None,
) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    doc.add_heading("MEL Plan", level=0)
    doc.add_paragraph(f"Project: {project_name}")
    doc.add_paragraph(f"Plan: {plan_name}")
    doc.add_paragraph(f"Intervention: {intervention_name}")

    if not outcomes:
        doc.add_paragraph("No outcomes selected.")
    for outcome in outcomes:
        doc.add_heading(outcome.get("title") or "Outcome", level=1)
        assumptions = (outcome.get("assumptions") or "").strip()
        if assumptions:
            doc.add_heading("Assumptions", level=2)
            doc.add_paragraph(assumptions)

        indicators = outcome.get("indicators") or []
        if indicators:
            doc.add_heading("Indicators", level=2)
            for ind in indicators:
                doc.add_paragraph(ind.get("title") or "", style="List Bullet")

        data_points = outcome.get("data_points") or []
        if data_points:
            doc.add_heading("Data points to be collected", level=2)
            # de-dupe by question text
            seen = set()
            for dp in data_points:
                q = (dp.get("question") or "").strip()
                if not q or q in seen:
                    continue
                seen.add(q)
                cat = dp.get("category") or ""
                metric = dp.get("metric") or ""
                suffix = []
                if cat:
                    suffix.append(cat)
                if metric:
                    suffix.append(metric)
                label = q if not suffix else f"{q} ({', '.join(suffix)})"
                doc.add_paragraph(label, style="List Bullet")

    _append_question_list(
        doc, "Asset allocation (one-time) questions", one_time_questions or []
    )
    _append_question_list(
        doc, "Continuous monitoring questions", cm_questions or []
    )

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
