from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.dependencies.providers import get_strava_import_manager
from app.integrations.strava.activity_import import (
    ActiveStravaConnectionRequiredError,
    ImportJobNotFoundError,
    StravaSummaryImportManager,
)


router = APIRouter(prefix="/integrations/strava/imports", tags=["integrations"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_strava_summary_import(
    current_user: AuthenticatedUser = Depends(get_current_user),
    manager: StravaSummaryImportManager = Depends(get_strava_import_manager),
) -> JSONResponse:
    """Queue or resume the current athlete's summary-only historical import."""

    try:
        job = await run_in_threadpool(manager.create_or_resume_job, current_user.id)
    except ActiveStravaConnectionRequiredError:
        raise _safe_error(
            status.HTTP_409_CONFLICT, "strava_connection_required"
        ) from None
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_import_start_failed"
        ) from None
    manager.schedule(job.job_id)
    return JSONResponse(
        {"job_id": str(job.job_id), "status": job.status},
        status_code=status.HTTP_202_ACCEPTED,
        headers=NO_STORE_HEADERS,
    )


@router.get("/{job_id}")
async def strava_summary_import_status(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    manager: StravaSummaryImportManager = Depends(get_strava_import_manager),
) -> JSONResponse:
    """Return an allow-listed import checkpoint owned by the current athlete."""

    try:
        job = await run_in_threadpool(
            manager.job_for_user, current_user.id, job_id
        )
    except ImportJobNotFoundError:
        raise _safe_error(status.HTTP_404_NOT_FOUND, "strava_import_not_found") from None
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_import_status_unavailable"
        ) from None
    return JSONResponse(
        jsonable_encoder(asdict(job)),
        status_code=status.HTTP_200_OK,
        headers=NO_STORE_HEADERS,
    )


def _safe_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code},
        headers=NO_STORE_HEADERS,
    )
