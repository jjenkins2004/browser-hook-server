from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.browser_hook.models import DoneState, TaskStep
from app.models.api import BeginTask
from app.sessions_manager import session_manager

SessionStreamState = TaskStep | DoneState


async def orchestrate_streaming_task(
    task_prompt: str,
    session_id: str | None = None,
    max_steps: int = 50,
) -> StreamingResponse:
    """Orchestrate task execution and stream session updates as NDJSON."""
    session_id_value = await session_manager.start_session(
        task_prompt=task_prompt,
        max_steps=max_steps,
        session_id=session_id,
    )

    hook = session_manager.get_session(session_id_value)
    if hook is None:
        raise RuntimeError(f"Missing hook for active session {session_id_value}")

    async def _step_iterator() -> AsyncIterator[SessionStreamState]:
        async for update in hook.iter_events():
            yield update

    async def _ndjson_generator() -> AsyncIterator[str]:
        yield BeginTask(session_id=session_id_value).model_dump_json() + "\n"
        async for update in _step_iterator():
            yield update.model_dump_json() + "\n"

    return StreamingResponse(
        _ndjson_generator(),
        media_type="application/x-ndjson",
    )


# Backwards-compatible alias for callers still importing the old name.
start_session_and_create_stream = orchestrate_streaming_task
