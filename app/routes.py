import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import HTTPException

from app.models.api import (
    FollowUpTaskRequest,
    InteractRequest,
    RegisterDeviceTokenRequest,
    StopTaskRequest,
    StartTaskRequest,
    TestLiveActivityPushRequest,
    TokenRegisterRequest,
)
from app.browser_hook.models import DoneState, TaskStep
from app.models.session_event import SessionEventLog
from app.apns_service import activity_pusher
from app.repo import inMemoryRepo
from app.sessions_manager import (
    FollowUpNotSupportedError,
    SessionNotFoundError,
    SessionNotRunningError,
    session_manager,
)
from app.utils import orchestrate_streaming_task

router = APIRouter()
_device_tokens: set[str] = set()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/device_token", status_code=204)
async def register_device_token(body: RegisterDeviceTokenRequest) -> None:
    _device_tokens.add(body.device_token)


@router.post("/live-activity/register")
async def register_live_activity(req: TokenRegisterRequest) -> None:
    activity_pusher.register_activity_token(
        session_id=req.session_id,
        push_token=req.push_token,
    )


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
    return await orchestrate_streaming_task(task_prompt=body.task)


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
        return await orchestrate_streaming_task(
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


@router.post(
    "/task/stop",
    status_code=204,
    summary="Stop a running task session",
    description="Cancels an in-flight task run for the provided session id.",
)
async def stop_task(body: StopTaskRequest) -> None:
    try:
        await session_manager.stop_session(body.session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Session {body.session_id!r} is not active or does not exist.",
        )
    except SessionNotRunningError:
        raise HTTPException(
            status_code=409,
            detail=f"Session {body.session_id!r} is not currently running.",
        )


@router.post("/task/interact", status_code=204)
async def interact_with_task(body: InteractRequest) -> None:
    pass


@router.post(
    "/debug/live-activity/test-push",
    status_code=204,
    summary="Test Live Activity push",
    description=(
        "Sends a mock step update followed by a mock done update to the "
        "supplied push token. For development/debugging only."
    ),
)
async def debug_test_live_activity_push(body: TestLiveActivityPushRequest) -> None:
    from app.browser_hook.models import ToolResult, ToolStatus

    mock_session_id = "debug-test-session"
    activity_pusher.register_activity_token(mock_session_id, body.push_token)

    mock_step = TaskStep(
        step=1,
        memory="Test step from server",
        tools=[
            ToolResult(
                tool="navigate",
                title="Navigating to example.com",
                status=ToolStatus.SUCCESS,
            )
        ],
    )
    await activity_pusher.publish_session_update(mock_session_id, mock_step)

    await asyncio.sleep(5)

    mock_done = DoneState(result="Test task complete", status=ToolStatus.SUCCESS)
    await activity_pusher.publish_session_update(mock_session_id, mock_done)
