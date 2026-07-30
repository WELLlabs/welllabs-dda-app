"""Accounts module: password hashing and auth request models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.accounts.routers.auth import LoginRequest, RegisterRequest
from app.shared.auth import hash_password, verify_password


class TestPasswordHashing:
    def test_hash_and_verify_round_trip(self):
        password = "secure-password-123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_verify_rejects_wrong_password(self):
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_verify_rejects_invalid_hash(self):
        assert not verify_password("password", "not-a-bcrypt-hash")


class TestRegisterRequest:
    def test_valid_register_payload(self):
        body = RegisterRequest(email="user@example.com", name="Test User", password="password123")
        assert body.email == "user@example.com"
        assert body.name == "Test User"

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", name="Test User", password="short")

    def test_rejects_invalid_email(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", name="Test User", password="password123")


class TestLoginRequest:
    def test_valid_login_payload(self):
        body = LoginRequest(email="user@example.com", password="secret")
        assert body.email == "user@example.com"

    def test_rejects_empty_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password="")
