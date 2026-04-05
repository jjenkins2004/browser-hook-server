import asyncio
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.browser_hook.models import TaskStep
from app.models.api import BeginTask
from app.models.task import TaskStatus
from app.repo import inMemoryRepo
from app.sessions_manager import session_manager


async def start_session_and_yield_steps(
    task_prompt: str,
    session_id: str | None = None,
    max_steps: int = 50,
) -> tuple[str, AsyncIterator[TaskStep]]:
    """Start a session and stream emitted steps through an async iterator."""
    step_queue: asyncio.Queue[TaskStep] = asyncio.Queue()

    async def _on_step_callback(step: TaskStep) -> None:
        await step_queue.put(step)

    task_id = await session_manager.start_session(
        task_prompt=task_prompt,
        max_steps=max_steps,
        session_id=session_id,
        on_step_callback=_on_step_callback,
    )

    async def _step_iterator() -> AsyncIterator[TaskStep]:
        while True:
            if step_queue.empty():
                task = await inMemoryRepo.get_task(task_id)
                if task is not None and task.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                }:
                    break

            try:
                step = await asyncio.wait_for(step_queue.get(), timeout=0.2)
            except TimeoutError:
                continue

            yield step

    return task_id, _step_iterator()


def build_session_ndjson_stream(
    task_id: str,
    step_iterator: AsyncIterator[TaskStep],
) -> StreamingResponse:
    """Wrap a step iterator in the shared NDJSON response format for sessions."""

    async def _ndjson_generator() -> AsyncIterator[str]:
        yield BeginTask(task_id=task_id).model_dump_json() + "\n"
        async for step in step_iterator:
            yield step.model_dump_json() + "\n"

    return StreamingResponse(
        _ndjson_generator(),
        media_type="application/x-ndjson",
    )
