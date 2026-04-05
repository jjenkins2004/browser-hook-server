import asyncio
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatBrowserUse

from app.browser_hook.hook_client import BrowserHook
from app.browser_hook.step_extractor import TaskStep
from app.config import keys
from app.repo.session_repo import SessionRepo, TaskStatusResponse, inMemoryRepo

AgentType = Agent[object, BaseModel]


@dataclass
class ActiveSession:
    hook: BrowserHook
    runner_task: asyncio.Task[Any]


class BrowserSessionManager:
    """In-memory manager for currently active BrowserHook sessions."""

    def __init__(self, repo: SessionRepo) -> None:
        self._repo = repo
        self._active_sessions: dict[str, ActiveSession] = {}

    async def create_session(
        self,
        task_prompt: str,
        max_steps: int = 50,
    ) -> str:
        """Create and start a BrowserHook-backed session. Returns session_id."""
        os.environ.setdefault("BROWSER_USE_API_KEY", keys.BROWSER_USE_KEY)

        llm = ChatBrowserUse(api_key=keys.BROWSER_USE_KEY)
        browser = Browser(use_cloud=True)
        agent: AgentType = Agent(task=task_prompt, llm=llm, browser=browser)

        session_id = str(uuid4())
        await self._repo.persist_task(
            TaskStatusResponse(
                task_id=session_id, status="running", steps=[], result=None
            )
        )

        async def _on_step_callback(_hook: BrowserHook, step: TaskStep) -> None:
            await self.handle_step(session_id, step)

        hook = BrowserHook(agent=agent, on_step_callback=_on_step_callback)

        # Runner that sets task to complete at the end and removes task from active ones
        async def _runner() -> None:
            try:
                history = await hook.run(max_steps=max_steps)
                task = await self._repo.get_task(session_id)
                if task is not None:
                    task.status = "completed"
                    task.result = str(history.final_result())
                    await self._repo.persist_task(task)
            except Exception as exc:
                task = await self._repo.get_task(session_id)
                if task is not None:
                    task.status = "error"
                    task.result = str(exc)
                    await self._repo.persist_task(task)
            finally:
                self._active_sessions.pop(session_id, None)

        # Save active session (hook + runner task) in one dictionary
        runner_task = asyncio.create_task(_runner())
        self._active_sessions[session_id] = ActiveSession(
            hook=hook,
            runner_task=runner_task,
        )
        return session_id

    async def handle_step(self, session_id: str, step: TaskStep) -> None:
        """Handle a step callback."""

        # Persist step to repository for that session
        await self._repo.persist_step(session_id=session_id, step=step)

    def get_session(self, session_id: str) -> BrowserHook | None:
        active_session = self._active_sessions.get(session_id)
        return active_session.hook if active_session else None

    def get_active_session_ids(self) -> list[str]:
        return list(self._active_sessions.keys())


session_manager = BrowserSessionManager(repo=inMemoryRepo)
