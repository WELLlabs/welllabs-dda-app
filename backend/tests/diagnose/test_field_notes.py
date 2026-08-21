"""Diagnose module: field note validation and models."""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from app.modules.diagnose.routers.field_notes import (
    FieldNoteUpdate,
    _guess_content_type,
    _parse_geojson,
    _validate_audio_upload,
    _validate_image_upload,
)


def _tiny_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
    return buf.getvalue()


class TestParseGeojson:
    def test_returns_dict_unchanged(self):
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        assert _parse_geojson(geom) == geom

    def test_parses_json_string(self):
        geom = _parse_geojson('{"type":"Point","coordinates":[1,2]}')
        assert geom["type"] == "Point"


class TestGuessContentType:
    def test_maps_jpeg_extension(self):
        assert _guess_content_type("photo.jpg") == "image/jpeg"

    def test_maps_mp3_extension(self):
        assert _guess_content_type("note.mp3") == "audio/mpeg"

    def test_unknown_extension_returns_none(self):
        assert _guess_content_type("file.xyz") is None


class TestValidateImageUpload:
    def test_accepts_valid_png(self):
        _validate_image_upload(_tiny_png(), "photo.png")

    def test_rejects_bad_extension(self):
        with pytest.raises(HTTPException) as exc:
            _validate_image_upload(_tiny_png(), "photo.bmp")
        assert exc.value.status_code == 400
        assert "Unsupported image type" in exc.value.detail

    def test_rejects_non_image_bytes(self):
        with pytest.raises(HTTPException) as exc:
            _validate_image_upload(b"not-an-image", "photo.png")
        assert exc.value.status_code == 400


class TestValidateAudioUpload:
    def test_accepts_mp3_extension(self):
        _validate_audio_upload(b"\x00" * 32, "clip.mp3")

    def test_rejects_unknown_extension(self):
        with pytest.raises(HTTPException) as exc:
            _validate_audio_upload(b"\x00" * 32, "clip.flac")
        assert exc.value.status_code == 400

    def test_rejects_too_small_file(self):
        with pytest.raises(HTTPException) as exc:
            _validate_audio_upload(b"tiny", "clip.mp3")
        assert exc.value.status_code == 400


class TestFieldNoteUpdate:
    def test_accepts_partial_update(self):
        body = FieldNoteUpdate(title="New title")
        assert body.title == "New title"
        assert body.text is None

    def test_rejects_title_over_max_length(self):
        with pytest.raises(ValidationError):
            FieldNoteUpdate(title="x" * 10_001)

    def test_accepts_uuid_hypothesis_id(self):
        hyp_id = uuid4()
        body = FieldNoteUpdate(hypothesis_id=hyp_id)
        assert body.hypothesis_id == hyp_id
