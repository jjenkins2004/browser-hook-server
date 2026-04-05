from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.browser_hook.models import TaskStep


class TaskStatus(str, Enum):
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    steps: list[TaskStep]
    result: Any = None
