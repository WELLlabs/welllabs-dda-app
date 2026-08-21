"""Boilerplate router for the Design module.

Design owns its own data model (kept separate from Diagnose's `diagnosis`
table per the module split) — fill in schema and endpoints as the Design
flow is built out.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def design_status():
    return {"module": "design", "status": "not_implemented"}
