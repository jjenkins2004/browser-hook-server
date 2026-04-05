from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.api import (
    FollowUpTaskRequest,
    InteractRequest,
    RegisterDeviceTokenRequest,
    StartTaskRequest,
)
from app.models.session_event import SessionEventLog
from app.repo import inMemoryRepo
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
    return await inMemoryRepo.get_history()


@router.get("/task_history/{session_id}", response_model=SessionEventLog)
async def task_history_by_session(session_id: str) -> SessionEventLog:
    return await inMemoryRepo.get_event_log(session_id)


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
    return await start_session_and_create_stream(
        task_prompt=body.task, session_id=body.session_id
    )


@router.post("/task/interact", status_code=204)
async def interact_with_task(body: InteractRequest) -> None:
    pass
