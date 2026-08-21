"""Pydantic schemas for FastAPI Users."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import Field


class UserRead(schemas.BaseUser[uuid.UUID]):
    name: str = ""
    created_at: datetime | None = None


class UserCreate(schemas.BaseUserCreate):
    name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=8)


class UserUpdate(schemas.BaseUserUpdate):
    name: str | None = Field(default=None, min_length=1, max_length=200)
