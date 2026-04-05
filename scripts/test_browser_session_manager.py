import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.session_event import AgentDoneEvent, AgentStepEvent, SessionEventLog
from app.models.task import TaskStatus
from app.repo.session_repo import InMemorySessionRepo, SessionRepo
from app.sessions_manager import BrowserSessionManager


async def wait_for_session(repo: SessionRepo, session_id: str) -> SessionEventLog:
    """Poll until a session exits RUNNING and return its event log."""
    while True:
        event_log = await repo.get_event_log(session_id)
        if event_log.status != TaskStatus.RUNNING:
            return event_log
        await asyncio.sleep(0.5)


def extract_report(event_log: SessionEventLog) -> str:
    """Prefer final done result, fallback to latest step memory."""
    for event in reversed(event_log.events):
        if isinstance(event, AgentDoneEvent):
            return event.done.result or "<done with no result>"
    for event in reversed(event_log.events):
        if isinstance(event, AgentStepEvent):
            return event.step.memory or "<no step memory>"
    return "<no agent output captured>"


async def run_prompt(
    manager: BrowserSessionManager,
    repo: SessionRepo,
    prompt: str,
    max_steps: int = 25,
    session_id: str | None = None,
) -> tuple[str, str, TaskStatus]:
    resolved_session_id = await manager.start_session(
        task_prompt=prompt,
        max_steps=max_steps,
        session_id=session_id,
    )
    event_log = await wait_for_session(repo, resolved_session_id)
    report = extract_report(event_log)
    return resolved_session_id, report, event_log.status


async def main() -> None:
    repo = InMemorySessionRepo()
    manager = BrowserSessionManager(repo=repo)

    prompt_1 = "Go to https://example.com and report the page header."
    prompt_2 = "Now report any content you can read on the page."

    session_1, report_1, status_1 = await run_prompt(manager, repo, prompt_1)
    print(f"Session 1: {session_1}")
    print(f"Status: {status_1}")
    print(f"Report: {report_1}\n")

    session_2, report_2, status_2 = await run_prompt(
        manager,
        repo,
        prompt_2,
        session_id=session_1,
    )
    print(f"Session 2: {session_2}")
    print(f"Status: {status_2}")
    print(f"Report: {report_2}")


if __name__ == "__main__":
    asyncio.run(main())
