from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import HTTPException

from app.models.api import (
    FollowUpTaskRequest,
    InteractRequest,
    RegisterDeviceTokenRequest,
    StartTaskRequest,
)
from app.models.session_event import SessionEventLog
from app.repo import inMemoryRepo
from app.sessions_manager import SessionNotFoundError, FollowUpNotSupportedError
from app.utils import start_session_and_create_stream

router = APIRouter()
_device_tokens: set[str] = set()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/device_token", status_code=204)
async def register_device_token(body: RegisterDeviceTokenRequest) -> None:
    _device_tokens.add(body.device_token)


@router.get("/task_history", response_model=list[SessionEventLog])
async def task_history() -> list[SessionEventLog]:
    logs = await inMemoryRepo.get_history()
    for log in logs:
        log.events = sorted(log.events, key=lambda e: e.created_at)
    return logs


@router.get("/task_history/{session_id}", response_model=SessionEventLog)
async def task_history_by_session(session_id: str) -> SessionEventLog:
    event_log = await inMemoryRepo.get_event_log(session_id)
    event_log.events = sorted(event_log.events, key=lambda e: e.created_at)
    return event_log


@router.post(
    "/task",
    status_code=202,
    summary="Start task stream",
    description=(
        "Returns an NDJSON stream. The first line contains the session id, "
        "followed by step updates and a final completion update."
    ),
)
async def start_task(body: StartTaskRequest) -> StreamingResponse:
    return await start_session_and_create_stream(task_prompt=body.task)


@router.post(
    "/task/follow_up",
    status_code=202,
    summary="Start follow-up task stream",
    description=(
        "Returns an NDJSON stream for an existing session. The first line "
        "contains the session id, followed by step updates and a final "
        "completion update."
    ),
)
async def follow_up_task(body: FollowUpTaskRequest) -> StreamingResponse:
    try:
        return await start_session_and_create_stream(
            task_prompt=body.task, session_id=body.session_id
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Session {body.session_id!r} is not active or does not exist.",
        )
    except FollowUpNotSupportedError:
        raise HTTPException(
            status_code=409,
            detail="Live follow-up is not supported by the running agent.",
        )


@router.post("/task/interact", status_code=204)
async def interact_with_task(body: InteractRequest) -> None:
    pass
