from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.browser_hook.models import DoneState, TaskStep
from app.models.api import BeginTask
from app.sessions_manager import session_manager

SessionStreamState = TaskStep | DoneState


async def start_session_and_create_stream(
    task_prompt: str,
    session_id: str | None = None,
    max_steps: int = 50,
) -> StreamingResponse:
    """Start a session and create an NDJSON stream for its updates."""
    task_id = await session_manager.start_session(
        task_prompt=task_prompt,
        max_steps=max_steps,
        session_id=session_id,
    )

    hook = session_manager.get_session(task_id)
    if hook is None:
        raise RuntimeError(f"Missing hook for active session {task_id}")

    async def _step_iterator() -> AsyncIterator[SessionStreamState]:
        async for update in hook.iter_events():
            yield update

    async def _ndjson_generator() -> AsyncIterator[str]:
        yield BeginTask(task_id=task_id).model_dump_json() + "\n"
        async for update in _step_iterator():
            yield update.model_dump_json() + "\n"

    return StreamingResponse(
        _ndjson_generator(),
        media_type="application/x-ndjson",
    )
