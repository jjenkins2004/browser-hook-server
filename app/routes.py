from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.repo import TaskStatusResponse, inMemoryRepo
from app.sessions_manager import session_manager

router = APIRouter()
_device_tokens: set[str] = set()


class RegisterDeviceTokenRequest(BaseModel):
    device_token: str


class StartTaskRequest(BaseModel):
    task: str


class StartTaskResponse(BaseModel):
    task_id: str


class InteractRequest(BaseModel):
    task_id: str
    message: str


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


@router.get("/update/{task_id}", response_model=TaskStatusResponse)
async def get_task_update(task_id: str) -> TaskStatusResponse:
    task = await inMemoryRepo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_copy(update={"steps": await inMemoryRepo.get_steps(task.task_id)})


@router.post("/task", status_code=202)
async def start_task(body: StartTaskRequest) -> StartTaskResponse:
    task_id = await session_manager.create_session(task_prompt=body.task)
    return StartTaskResponse(task_id=task_id)


@router.post("/task/interact", status_code=204)
async def interact_with_task(body: InteractRequest) -> None:
    pass
