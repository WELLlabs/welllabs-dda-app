from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.modules.diagnose.services.package_progress import PackageProgress
from app.modules.diagnose.services.qfield_media_sync import sync_from_cloud
from app.modules.diagnose.services.qfield_sync import package_and_upload
from app.modules.diagnose.services.s3_cleanup import cleanup_orphan_projects, cleanup_project_s3
from app.shared.access import assert_diagnosis_access
from app.shared.auth import get_current_user

router = APIRouter()


class ProjectRequest(BaseModel):
    project_id: UUID


@router.post("/package")
def package_to_qfield(body: ProjectRequest, user: dict = Depends(get_current_user)):
    """Build QGIS project for the given app project, upload to QField Cloud, and trigger packaging."""
    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)
    try:
        result = package_and_upload(project_id, user["id"])
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Packaging failed: {e}") from e


@router.post("/package/stream")
async def package_to_qfield_stream(body: ProjectRequest, user: dict = Depends(get_current_user)):
    """Stream packaging progress as Server-Sent Events."""
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(percent: int, message: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "type": "progress",
                "percent": percent,
                "message": message,
                "time": datetime.now(UTC).isoformat(),
            },
        )

    async def run_package() -> None:
        progress = PackageProgress(on_event=on_progress)
        try:
            result = await loop.run_in_executor(
                None,
                lambda: package_and_upload(project_id, user["id"], progress=progress),
            )
            await queue.put({"type": "done", "percent": 100, "result": result})
        except ValueError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:
            await queue.put({"type": "error", "message": f"Packaging failed: {exc}"})

    async def event_stream():
        task = asyncio.create_task(run_package())
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sync")
def sync_from_qfield(body: ProjectRequest, user: dict = Depends(get_current_user)):
    """Pull QField Cloud project files and migrate field media to S3."""
    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)
    try:
        return sync_from_cloud(project_id, user["id"])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Sync failed: {e}") from e


@router.post("/sync/stream")
async def sync_from_qfield_stream(body: ProjectRequest, user: dict = Depends(get_current_user)):
    """Stream sync progress as Server-Sent Events."""
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(percent: int, message: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "type": "progress",
                "percent": percent,
                "message": message,
                "time": datetime.now(UTC).isoformat(),
            },
        )

    async def run_sync() -> None:
        progress = PackageProgress(on_event=on_progress)
        try:
            result = await loop.run_in_executor(
                None,
                lambda: sync_from_cloud(project_id, user["id"], progress=progress),
            )
            await queue.put({"type": "done", "percent": 100, "result": result})
        except ValueError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:
            await queue.put({"type": "error", "message": f"Sync failed: {exc}"})

    async def event_stream():
        task = asyncio.create_task(run_sync())
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CleanupRequest(BaseModel):
    project_id: UUID
    dry_run: bool = False


class OrphanCleanupRequest(BaseModel):
    dry_run: bool = False


@router.post("/cleanup-orphans")
def cleanup_orphan_s3(body: OrphanCleanupRequest, user: dict = Depends(get_current_user)):
    """Remove S3 prefixes for diagnosis projects that were deleted from the database."""
    try:
        return cleanup_orphan_projects(dry_run=body.dry_run)
    except Exception as e:
        raise HTTPException(500, f"Orphan cleanup failed: {e}") from e


@router.post("/cleanup")
def cleanup_s3(body: CleanupRequest, user: dict = Depends(get_current_user)):
    """Remove orphaned field-note media from S3 for a project."""
    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)
    try:
        return cleanup_project_s3(project_id, dry_run=body.dry_run)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Cleanup failed: {e}") from e
