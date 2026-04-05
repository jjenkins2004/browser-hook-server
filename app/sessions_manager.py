import asyncio
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatBrowserUse

from app.browser_hook.hook_client import BrowserHook
from app.browser_hook.models import DoneState, TaskStep
from app.models.session import ActiveSession
from app.models.session_event import AgentDoneEvent, AgentStepEvent, UserEvent
from app.config import keys
from app.models.task import TaskStatus
from app.repo.session_repo import SessionRepo, inMemoryRepo
from app.ssl_config import configure_ca_bundle

AgentType = Agent[object, BaseModel]


class FollowUpSessionError(Exception):
    """Base error for follow-up session problems."""


class SessionNotFoundError(FollowUpSessionError):
    """Raised when a follow-up references a session_id not active in memory."""


class FollowUpNotSupportedError(FollowUpSessionError):
    """Raised when a live agent does not support add_new_task."""


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
    ) -> str:
        """Start a new session or reuse an existing one when session_id is provided."""
        os.environ.setdefault("BROWSER_USE_API_KEY", keys.BROWSER_USE_KEY)
        configure_ca_bundle()

        if session_id is None:
            # Brand-new task
            session_key = str(uuid4())
            active_session = self._create_new_session(
                session_key=session_key,
                task_prompt=task_prompt,
            )
            self._sessions[session_key] = active_session
        else:
            # Follow-up: session_id must reference an active in-memory session
            session_key = session_id
            active_session = self._sessions.get(session_key)
            if active_session is None:
                raise SessionNotFoundError(
                    f"Session {session_key!r} is not active in memory. "
                    "It may have expired or never existed."
                )
            self._prepare_follow_up(
                active_session=active_session, task_prompt=task_prompt
            )

        await self._persist_user_input_event(
            session_id=session_key,
            task_prompt=task_prompt,
        )
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
    ) -> ActiveSession:
        llm = ChatBrowserUse(api_key=keys.BROWSER_USE_KEY)
        browser = Browser(use_cloud=True, keep_alive=True)
        agent: AgentType = Agent(task=task_prompt, llm=llm, browser=browser)

        hook = BrowserHook(agent=agent)
        return ActiveSession(hook=hook)

    def _prepare_follow_up(
        self, active_session: ActiveSession, task_prompt: str
    ) -> None:
        """Route to live or completed follow-up path."""
        runner = active_session.runner_task
        if runner is not None and not runner.done():
            # Still running – try live follow-up
            self._append_live_follow_up(active_session, task_prompt)
        else:
            # Completed – rebuild agent on existing browser session
            self._prepare_completed_session_for_follow_up(active_session, task_prompt)

    def _append_live_follow_up(
        self, active_session: ActiveSession, task_prompt: str
    ) -> None:
        agent = active_session.hook.agent
        follow_up_task = self.format_follow_up_prompt(task_prompt)

        if not hasattr(agent, "add_new_task"):
            raise FollowUpNotSupportedError(
                "The running agent does not support live follow-up "
                "(no add_new_task method)."
            )
        agent.add_new_task(follow_up_task)

    def _prepare_completed_session_for_follow_up(
        self, active_session: ActiveSession, task_prompt: str
    ) -> None:
        """Replace the hook's agent with a fresh one bound to the same browser."""
        new_agent = self._build_follow_up_agent(active_session, task_prompt)
        new_hook = BrowserHook(agent=new_agent)
        active_session.hook = new_hook

    def _build_follow_up_agent(
        self, active_session: ActiveSession, task_prompt: str
    ) -> AgentType:
        old_agent = active_session.hook.agent
        follow_up_task = self.format_follow_up_prompt(task_prompt)

        agent: AgentType = Agent(
            task=f"FOLLOW-UP TASK: {follow_up_task}",
            llm=old_agent.llm,
            browser_session=old_agent.browser_session,
            directly_open_url=False,
        )
        return agent

    async def _persist_user_input_event(
        self, session_id: str, task_prompt: str
    ) -> None:
        await self._repo.persist_event(
            session_id=session_id,
            event=UserEvent(prompt=task_prompt),
        )

    async def _set_task_running(self, session_key: str) -> None:
        await self._repo.set_session_state(
            session_id=session_key,
            status=TaskStatus.RUNNING,
        )

    async def _set_task_completed(self, session_key: str) -> None:
        await self._repo.set_session_state(
            session_id=session_key,
            status=TaskStatus.COMPLETED,
        )

    async def _set_task_failed(self, session_key: str) -> None:
        await self._repo.set_session_state(
            session_id=session_key,
            status=TaskStatus.FAILED,
        )

    async def _run_session(
        self,
        session_key: str,
        active_session: ActiveSession,
        max_steps: int,
    ) -> None:
        events_task = asyncio.create_task(
            self._persist_session_events(session_key, active_session.hook)
        )
        try:
            history = await active_session.hook.run(max_steps=max_steps)
            await events_task
            await self._set_task_completed(session_key)
        except Exception as exc:
            await events_task
            await self._set_task_failed(session_key)

    async def _persist_session_events(
        self,
        session_id: str,
        hook: BrowserHook,
    ) -> None:
        async for update in hook.iter_events():
            if isinstance(update, TaskStep):
                await self._repo.persist_event(
                    session_id=session_id,
                    event=AgentStepEvent(step=update),
                )
            elif isinstance(update, DoneState):
                await self._repo.persist_event(
                    session_id=session_id,
                    event=AgentDoneEvent(done=update),
                )

    def get_session(self, session_id: str) -> BrowserHook | None:
        active_session = self._sessions.get(session_id)
        return active_session.hook if active_session else None

    def get_active_session_ids(self) -> list[str]:
        return [
            session_id
            for session_id, session in self._sessions.items()
            if session.runner_task is not None and not session.runner_task.done()
        ]

    @staticmethod
    def format_follow_up_prompt(user_text: str) -> str:
        return "Follow-up request for the current session:\n\n" f"{user_text}"


session_manager = BrowserSessionManager(repo=inMemoryRepo)
