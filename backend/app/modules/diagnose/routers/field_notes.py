import asyncio
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from geojson_pydantic import Feature, FeatureCollection
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.shared.access import assert_diagnosis_access
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage

router = APIRouter()
logger = logging.getLogger(__name__)

LEGACY_PHOTOS_DIR = Path(settings.packages_dir) / "photos"
MAX_MEDIA_BYTES = 50 * 1024 * 1024
_TEXT_MAX = 10_000
_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_ALLOWED_AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".webm"}


def _ensure_legacy_photos_dir() -> None:
    LEGACY_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


class FieldNoteUpdate(BaseModel):
    geometry: dict | None = None
    title: str | None = Field(default=None, max_length=_TEXT_MAX)
    text: str | None = Field(default=None, max_length=_TEXT_MAX)
    hypothesis_id: UUID | None = None


def _parse_geojson(value) -> dict:
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _validate_hypothesis_link(cur, project_id: str, hypothesis_id: str | None) -> None:
    if not hypothesis_id:
        return
    cur.execute(
        "SELECT 1 FROM hypotheses WHERE id = %(id)s AND project_id = %(project_id)s",
        {"id": hypothesis_id, "project_id": project_id},
    )
    if not cur.fetchone():
        raise HTTPException(400, "Hypothesis not found in this project")


def _row_to_feature(row: dict) -> Feature:
    return Feature(
        type="Feature",
        id=str(row["id"]),
        geometry=_parse_geojson(row["geojson"]),
        properties={
            "project_id": str(row["project_id"]),
            "title": row.get("title") or "",
            "text": row["text"],
            "photo_path": row["photo_path"],
            "audio_path": row.get("audio_path"),
            "hypothesis_id": str(row["hypothesis_id"]) if row.get("hypothesis_id") else None,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "created_by": row["created_by"],
        },
    )


def _guess_content_type(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
    }.get(ext)


def _validate_image_upload(content: bytes, filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            400,
            f"Unsupported image type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_IMAGE_EXTS))}",
        )
    try:
        with Image.open(BytesIO(content)) as img:
            img.verify()
        # verify() leaves the image in an unusable state; reopen to confirm decode
        with Image.open(BytesIO(content)) as img:
            img.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(400, "Uploaded file is not a valid image") from exc
    except OSError as exc:
        raise HTTPException(400, f"Invalid or truncated image: {exc}") from exc


def _validate_audio_upload(content: bytes, filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            400,
            f"Unsupported audio type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_AUDIO_EXTS))}",
        )
    if len(content) < 16:
        raise HTTPException(400, "Audio file is empty or too small")


def _store_media_local(filename: str, content: bytes) -> str:
    _ensure_legacy_photos_dir()
    dest = LEGACY_PHOTOS_DIR / filename
    dest.write_bytes(content)
    return f"photos/{filename}"


async def _store_media(project_id: str, content: bytes, original_filename: str) -> str:
    ext = Path(original_filename).suffix or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    content_type = _guess_content_type(filename)

    if s3_storage.is_s3_enabled():
        key = s3_storage.media_key(project_id, filename)
        try:
            await s3_storage.upload_bytes_async(key, content, content_type=content_type)
            return key
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "S3Error")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            logger.error("S3 media upload failed (%s) for %s: %s", code, key, message)
            raise HTTPException(
                503,
                f"S3 media upload failed ({code}): {message}",
            ) from exc

    return await asyncio.to_thread(_store_media_local, filename, content)


def _delete_media(photo_path: str | None) -> None:
    if not photo_path:
        return
    if s3_storage.is_s3_enabled() and not photo_path.startswith("photos/"):
        s3_storage.delete_object(photo_path)
        return
    if photo_path.startswith("photos/"):
        local = LEGACY_PHOTOS_DIR / Path(photo_path).name
        if local.is_file():
            local.unlink()


def _note_project_id(cur, note_id: str) -> str:
    cur.execute("SELECT project_id FROM field_notes WHERE id = %(id)s", {"id": note_id})
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Field note not found")
    return str(row["project_id"])


def _project_id_for_media(key: str) -> str | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT project_id FROM field_notes WHERE photo_path = %(key)s OR audio_path = %(key)s LIMIT 1",
            {"key": key},
        )
        row = cur.fetchone()
    return str(row["project_id"]) if row else None


def _insert_field_note(
    project_id: str,
    geometry: str,
    title: str,
    text: str,
    photo_path: str | None,
    audio_path: str | None,
    created_by: str,
    hypothesis_id: str | None,
) -> dict:
    with db_cursor() as cur:
        _validate_hypothesis_link(cur, project_id, hypothesis_id)
        cur.execute(
            """
            INSERT INTO field_notes (
                project_id, geom, title, text, photo_path, audio_path, created_by, hypothesis_id
            )
            VALUES (
                %(project_id)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326),
                %(title)s,
                %(text)s,
                %(photo_path)s,
                %(audio_path)s,
                %(created_by)s,
                %(hypothesis_id)s
            )
            RETURNING id, project_id, title, text, photo_path, audio_path, hypothesis_id,
                      created_at, updated_at, created_by,
                      ST_AsGeoJSON(geom)::json AS geojson
            """,
            {
                "project_id": project_id,
                "geojson": geometry,
                "title": title,
                "text": text,
                "photo_path": photo_path,
                "audio_path": audio_path,
                "created_by": created_by,
                "hypothesis_id": hypothesis_id,
            },
        )
        return cur.fetchone()


@router.get("", response_model=FeatureCollection)
def list_field_notes(project_id: str = Query(...), user: dict = Depends(get_current_user)):
    assert_diagnosis_access(user["id"], project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, title, text, photo_path, audio_path, hypothesis_id,
                   created_at, updated_at, created_by,
                   ST_AsGeoJSON(geom)::json AS geojson
            FROM field_notes
            WHERE project_id = %(project_id)s
            ORDER BY created_at DESC
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()
    return FeatureCollection(type="FeatureCollection", features=[_row_to_feature(r) for r in rows])


@router.post("", response_model=Feature, status_code=201)
async def create_field_note(
    project_id: str = Form(...),
    geometry: str = Form(...),
    title: str = Form("", max_length=_TEXT_MAX),
    text: str = Form("", max_length=_TEXT_MAX),
    hypothesis_id: str | None = Form(None),
    photo: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
):
    await asyncio.to_thread(assert_diagnosis_access, user["id"], project_id)

    photo_path = None
    audio_path = None
    hyp_id = hypothesis_id or None

    for upload, kind in ((photo, "photo"), (audio, "audio")):
        if not upload or not upload.filename:
            continue
        content = await upload.read()
        if len(content) > MAX_MEDIA_BYTES:
            raise HTTPException(413, f"{kind.capitalize()} file exceeds 50MB limit")
        if kind == "photo":
            _validate_image_upload(content, upload.filename)
        else:
            _validate_audio_upload(content, upload.filename)
        try:
            stored = await _store_media(project_id, content, upload.filename)
        except OSError as exc:
            raise HTTPException(500, f"Failed to store {kind}: {exc}") from exc
        if kind == "photo":
            photo_path = stored
        else:
            audio_path = stored

    row = await asyncio.to_thread(
        _insert_field_note,
        project_id,
        geometry,
        title,
        text,
        photo_path,
        audio_path,
        str(user["id"]),
        hyp_id,
    )
    return _row_to_feature(row)


@router.patch("/{note_id}", response_model=Feature)
def update_field_note(note_id: str, body: FieldNoteUpdate, user: dict = Depends(get_current_user)):
    sets = []
    params: dict = {"id": note_id}
    if body.title is not None:
        sets.append("title = %(title)s")
        params["title"] = body.title
    if body.text is not None:
        sets.append("text = %(text)s")
        params["text"] = body.text
    if body.geometry is not None:
        sets.append("geom = ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)")
        params["geojson"] = json.dumps(body.geometry)
    if "hypothesis_id" in body.model_fields_set:
        sets.append("hypothesis_id = %(hypothesis_id)s")
        params["hypothesis_id"] = str(body.hypothesis_id) if body.hypothesis_id else None
    if not sets:
        raise HTTPException(400, "No fields to update")

    with db_cursor() as cur:
        project_id = _note_project_id(cur, note_id)
        assert_diagnosis_access(user["id"], project_id)
        if "hypothesis_id" in body.model_fields_set:
            _validate_hypothesis_link(cur, project_id, params.get("hypothesis_id"))
        cur.execute(
            f"""
            UPDATE field_notes SET {", ".join(sets)}
            WHERE id = %(id)s
            RETURNING id, project_id, title, text, photo_path, audio_path, hypothesis_id,
                      created_at, updated_at, created_by,
                      ST_AsGeoJSON(geom)::json AS geojson
            """,
            params,
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Field note not found")
    return _row_to_feature(row)


@router.get("/media")
def serve_field_note_media(key: str = Query(..., min_length=1), user: dict = Depends(get_current_user)):
    if ".." in key or key.startswith("/"):
        raise HTTPException(400, "Invalid media key")

    project_id = _project_id_for_media(key)
    if project_id:
        assert_diagnosis_access(user["id"], project_id)

    if s3_storage.is_s3_enabled() and not key.startswith("photos/"):
        return RedirectResponse(s3_storage.presigned_get_url(key), status_code=302)

    filename = Path(key).name
    path = LEGACY_PHOTOS_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "Media not found")
    return FileResponse(path)


def _load_media_bytes(key: str) -> bytes:
    if s3_storage.is_s3_enabled() and not key.startswith("photos/"):
        try:
            return s3_storage.get_object_bytes(key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise HTTPException(404, "Media not found") from exc
            raise HTTPException(502, f"Failed to fetch media from S3 ({code})") from exc

    path = LEGACY_PHOTOS_DIR / Path(key).name
    if not path.is_file():
        raise HTTPException(404, "Media not found")
    return path.read_bytes()


def _make_square_thumbnail(data: bytes, size: int) -> bytes:
    with Image.open(BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        thumb = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)
        out = BytesIO()
        thumb.save(out, format="JPEG", quality=72, optimize=True)
        return out.getvalue()


@router.get("/media/thumbnail")
def serve_field_note_thumbnail(
    key: str = Query(..., min_length=1),
    size: int = Query(128, ge=48, le=256),
    user: dict = Depends(get_current_user),
):
    """Return a small square JPEG thumbnail for quick card previews."""
    if ".." in key or key.startswith("/"):
        raise HTTPException(400, "Invalid media key")
    if not key.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        raise HTTPException(400, "Thumbnails are only available for images")

    project_id = _project_id_for_media(key)
    if project_id:
        assert_diagnosis_access(user["id"], project_id)

    try:
        jpeg = _make_square_thumbnail(_load_media_bytes(key), size)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Thumbnail generation failed for %s: %s", key, exc)
        raise HTTPException(422, "Could not generate thumbnail") from exc

    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/media/{filename}")
def serve_field_note_media_legacy(filename: str, user: dict = Depends(get_current_user)):
    return serve_field_note_media(key=f"photos/{filename}", user=user)


@router.delete("/{note_id}", status_code=204)
def delete_field_note(note_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        assert_diagnosis_access(user["id"], _note_project_id(cur, note_id))
        cur.execute(
            "DELETE FROM field_notes WHERE id = %(id)s RETURNING photo_path, audio_path",
            {"id": note_id},
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Field note not found")
    _delete_media(row.get("photo_path"))
    _delete_media(row.get("audio_path"))
