import asyncio
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatBrowserUse

from app.browser_hook.hook_client import BrowserHook
from app.browser_hook.models import TaskStep
from app.models.session import ActiveSession, StepCallback
from app.config import keys
from app.models.task import TaskStatus, TaskStatusResponse
from app.repo.session_repo import SessionRepo, inMemoryRepo
from app.ssl_config import configure_ca_bundle

AgentType = Agent[object, BaseModel]


class BrowserSessionManager:
    """In-memory manager for all BrowserHook sessions."""

    def __init__(self, repo: SessionRepo) -> None:
        self._repo = repo
        self._sessions: dict[str, ActiveSession] = {}

    async def start_session(
        self,
        task_prompt: str,
        max_steps: int = 50,
        session_id: str | None = None,
        on_step_callback: StepCallback | None = None,
    ) -> str:
        """Start a new session or reuse an existing one when session_id is provided."""
        os.environ.setdefault("BROWSER_USE_API_KEY", keys.BROWSER_USE_KEY)
        configure_ca_bundle()

        session_key = session_id or str(uuid4())
        active_session = self._sessions.get(session_key)

        if active_session is None:
            active_session = self._create_new_session(
                session_key=session_key,
                task_prompt=task_prompt,
                step_callback=on_step_callback,
            )
            self._sessions[session_key] = active_session
            await self._set_task_running(session_key)
        else:
            self._append_follow_up_task(
                active_session=active_session, task_prompt=task_prompt
            )
            if on_step_callback is not None:
                active_session.step_callback = on_step_callback
            await self._set_task_running(session_key)

        # If this session is already running, do not start a second runner.
        if (
            active_session.runner_task is not None
            and not active_session.runner_task.done()
        ):
            return session_key

        # Keep session in memory even when run completes.
        active_session.runner_task = asyncio.create_task(
            self._run_session(
                session_key=session_key,
                active_session=active_session,
                max_steps=max_steps,
            )
        )
        return session_key

    def _create_new_session(
        self,
        session_key: str,
        task_prompt: str,
        step_callback: StepCallback | None,
    ) -> ActiveSession:
        llm = ChatBrowserUse(api_key=keys.BROWSER_USE_KEY)
        browser = Browser(use_cloud=True)
        agent: AgentType = Agent(task=task_prompt, llm=llm, browser=browser)

        async def _on_step_callback(_hook: BrowserHook, step: TaskStep) -> None:
            await self.handle_step(session_key, step)

        hook = BrowserHook(agent=agent, on_step_callback=_on_step_callback)
        return ActiveSession(hook=hook, step_callback=step_callback)

    def _append_follow_up_task(
        self, active_session: ActiveSession, task_prompt: str
    ) -> None:
        agent = active_session.hook.agent
        follow_up_task = f"FOLLOW-UP TASK: {task_prompt}"

        if hasattr(agent, "add_new_task"):
            agent.add_new_task(follow_up_task)
            return

        # Fallback for older Agent versions.
        agent.task += f"\n\n{follow_up_task}"

    async def _set_task_running(self, session_key: str) -> None:
        task = await self._repo.get_task(session_key)
        if task is None:
            task = TaskStatusResponse(
                task_id=session_key,
                status=TaskStatus.RUNNING,
                steps=[],
                result=None,
            )
        else:
            task.status = TaskStatus.RUNNING
            task.result = None
        await self._repo.persist_task(task)

    async def _set_task_completed(self, session_key: str, result: str) -> None:
        task = await self._repo.get_task(session_key)
        if task is None:
            return
        task.status = TaskStatus.COMPLETED
        task.result = result
        await self._repo.persist_task(task)

    async def _set_task_failed(self, session_key: str, error: str) -> None:
        task = await self._repo.get_task(session_key)
        if task is None:
            return
        task.status = TaskStatus.FAILED
        task.result = error
        await self._repo.persist_task(task)

    async def _run_session(
        self,
        session_key: str,
        active_session: ActiveSession,
        max_steps: int,
    ) -> None:
        try:
            history = await active_session.hook.run(max_steps=max_steps)
            await self._set_task_completed(session_key, str(history.final_result()))
        except Exception as exc:
            await self._set_task_failed(session_key, str(exc))

    async def handle_step(self, session_id: str, step: TaskStep) -> None:
        """Handle a step callback."""

        # Persist step to repository for that session
        await self._repo.persist_step(session_id=session_id, step=step)

        active_session = self._sessions.get(session_id)
        if active_session is None or active_session.step_callback is None:
            return

        callback_result = active_session.step_callback(step)
        if asyncio.iscoroutine(callback_result):
            await callback_result

    def get_session(self, session_id: str) -> BrowserHook | None:
        active_session = self._sessions.get(session_id)
        return active_session.hook if active_session else None

    def get_active_session_ids(self) -> list[str]:
        return [
            session_id
            for session_id, session in self._sessions.items()
            if session.runner_task is not None and not session.runner_task.done()
        ]


session_manager = BrowserSessionManager(repo=inMemoryRepo)
