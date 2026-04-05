from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.api import (
    FollowUpTaskRequest,
    InteractRequest,
    RegisterDeviceTokenRequest,
    StartTaskRequest,
)
from app.models.task import TaskStatusResponse
from app.repo import inMemoryRepo
from app.utils import build_session_ndjson_stream, start_session_and_yield_steps

router = APIRouter()
_device_tokens: set[str] = set()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/device_token", status_code=204)
async def register_device_token(body: RegisterDeviceTokenRequest) -> None:
    _device_tokens.add(body.device_token)


@router.get("/task_history", response_model=list[TaskStatusResponse])
async def task_history() -> list[TaskStatusResponse]:
    tasks = await inMemoryRepo.list_tasks()
    return [
        task.model_copy(update={"steps": await inMemoryRepo.get_steps(task.task_id)})
        for task in tasks
    ]


@router.post(
    "/task",
    status_code=202,
    summary="Start task stream",
    description=(
        "Returns an NDJSON stream. The first line is a BeginTask object "
        "with task_id, followed by TaskStep objects for each emitted step."
    ),
)
async def start_task(body: StartTaskRequest) -> StreamingResponse:
    task_id, iterator = await start_session_and_yield_steps(task_prompt=body.task)
    return build_session_ndjson_stream(task_id=task_id, step_iterator=iterator)


@router.post(
    "/task/follow_up",
    status_code=202,
    summary="Start follow-up task stream",
    description=(
        "Returns an NDJSON stream for an existing session. The first line is "
        "a BeginTask object with task_id, followed by TaskStep objects for "
        "each emitted step."
    ),
)
async def follow_up_task(body: FollowUpTaskRequest) -> StreamingResponse:
    task_id, iterator = await start_session_and_yield_steps(
        task_prompt=body.task, session_id=body.session_id
    )
    return build_session_ndjson_stream(task_id=task_id, step_iterator=iterator)


@router.post("/task/interact", status_code=204)
async def interact_with_task(body: InteractRequest) -> None:
    pass
