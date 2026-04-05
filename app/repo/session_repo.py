from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from app.browser_hook.step_extractor import TaskStep


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    steps: list[TaskStep]
    result: Any = None


class SessionRepo(ABC):
    @abstractmethod
    async def persist_task(self, task: TaskStatusResponse) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_task(self, session_id: str) -> TaskStatusResponse | None:
        raise NotImplementedError

    @abstractmethod
    async def list_tasks(self) -> list[TaskStatusResponse]:
        raise NotImplementedError

    @abstractmethod
    async def persist_step(self, session_id: str, step: TaskStep) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_steps(self, session_id: str) -> list[TaskStep]:
        raise NotImplementedError

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        raise NotImplementedError


class InMemorySessionRepo(SessionRepo):
    def __init__(self) -> None:
        self._tasks_by_session: dict[str, TaskStatusResponse] = {}
        self._steps_by_session: dict[str, list[TaskStep]] = defaultdict(list)

    async def persist_task(self, task: TaskStatusResponse) -> None:
        self._tasks_by_session[task.task_id] = task

    async def get_task(self, session_id: str) -> TaskStatusResponse | None:
        task = self._tasks_by_session.get(session_id)
        if task is None:
            return None
        return task.model_copy(deep=True)

    async def list_tasks(self) -> list[TaskStatusResponse]:
        return [task.model_copy(deep=True) for task in self._tasks_by_session.values()]

    async def persist_step(self, session_id: str, step: TaskStep) -> None:
        self._steps_by_session[session_id].append(step)

    async def get_steps(self, session_id: str) -> list[TaskStep]:
        return list(self._steps_by_session.get(session_id, []))

    async def clear_session(self, session_id: str) -> None:
        self._tasks_by_session.pop(session_id, None)
        self._steps_by_session.pop(session_id, None)


inMemoryRepo: SessionRepo = InMemorySessionRepo()
