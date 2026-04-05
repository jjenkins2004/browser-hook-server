import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch, call

from app.models.session import ActiveSession
from app.sessions_manager import (
    BrowserSessionManager,
    FollowUpNotSupportedError,
    FollowUpSessionError,
    SessionNotFoundError,
)


def _make_mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.persist_event = AsyncMock()
    repo.set_session_state = AsyncMock()
    repo.clear_session = AsyncMock()
    repo.get_event_log = AsyncMock()
    repo.get_history = AsyncMock(return_value=[])
    return repo


def _make_mock_agent(*, has_add_new_task: bool = True) -> MagicMock:
    agent = MagicMock()
    agent.browser = MagicMock()
    agent.llm = MagicMock()
    if has_add_new_task:
        agent.add_new_task = MagicMock()
    else:
        # Remove the attribute entirely so hasattr returns False
        if hasattr(agent, "add_new_task"):
            del agent.add_new_task
    return agent


def _make_mock_hook(agent: MagicMock | None = None) -> MagicMock:
    hook = MagicMock()
    hook.agent = agent or _make_mock_agent()
    hook.run = AsyncMock()
    hook.iter_events = MagicMock(return_value=AsyncIteratorMock([]))
    hook.steps = []
    return hook


class AsyncIteratorMock:
    """Helper that acts as an async iterator yielding given items."""

    def __init__(self, items: list) -> None:
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _make_active_session(
    *,
    hook: MagicMock | None = None,
    runner_done: bool = True,
) -> ActiveSession:
    hook = hook or _make_mock_hook()
    session = ActiveSession(hook=hook)
    if runner_done:
        # Simulate a completed runner task
        task = MagicMock()
        task.done.return_value = True
        session.runner_task = task
    else:
        # Simulate a still-running runner task
        task = MagicMock()
        task.done.return_value = False
        session.runner_task = task
    return session


class TestRejectUnknownSession(unittest.TestCase):
    """start_session must raise SessionNotFoundError for unknown session_ids."""

    def test_unknown_session_id_raises(self) -> None:
        repo = _make_mock_repo()
        mgr = BrowserSessionManager(repo=repo)

        with self.assertRaises(SessionNotFoundError):
            asyncio.get_event_loop().run_until_complete(
                mgr.start_session(
                    task_prompt="click the button",
                    session_id="nonexistent-session-id",
                )
            )

    def test_stale_session_only_in_history_raises(self) -> None:
        """A session_id that exists in task history but not in _sessions must fail."""
        repo = _make_mock_repo()
        mgr = BrowserSessionManager(repo=repo)
        # Do NOT insert it into mgr._sessions; it only "exists" in the repo.

        with self.assertRaises(SessionNotFoundError):
            asyncio.get_event_loop().run_until_complete(
                mgr.start_session(
                    task_prompt="do something else",
                    session_id="stale-history-only-id",
                )
            )


class TestLiveFollowUp(unittest.TestCase):
    """Follow-up on a still-running session should use add_new_task."""

    @patch("app.sessions_manager.configure_ca_bundle")
    @patch("app.sessions_manager.keys")
    def test_live_follow_up_calls_add_new_task(
        self, mock_keys: MagicMock, mock_ca: MagicMock
    ) -> None:
        mock_keys.BROWSER_USE_KEY = "fake-key"
        repo = _make_mock_repo()
        mgr = BrowserSessionManager(repo=repo)

        agent = _make_mock_agent(has_add_new_task=True)
        hook = _make_mock_hook(agent=agent)
        session = _make_active_session(hook=hook, runner_done=False)
        mgr._sessions["live-session"] = session

        asyncio.get_event_loop().run_until_complete(
            mgr.start_session(
                task_prompt="now scroll down",
                session_id="live-session",
            )
        )

        agent.add_new_task.assert_called_once()
        call_args = agent.add_new_task.call_args[0][0]
        self.assertIn("now scroll down", call_args)

    @patch("app.sessions_manager.configure_ca_bundle")
    @patch("app.sessions_manager.keys")
    def test_live_follow_up_without_add_new_task_raises(
        self, mock_keys: MagicMock, mock_ca: MagicMock
    ) -> None:
        mock_keys.BROWSER_USE_KEY = "fake-key"
        repo = _make_mock_repo()
        mgr = BrowserSessionManager(repo=repo)

        agent = _make_mock_agent(has_add_new_task=False)
        hook = _make_mock_hook(agent=agent)
        session = _make_active_session(hook=hook, runner_done=False)
        mgr._sessions["live-no-support"] = session

        with self.assertRaises(FollowUpNotSupportedError):
            asyncio.get_event_loop().run_until_complete(
                mgr.start_session(
                    task_prompt="scroll down",
                    session_id="live-no-support",
                )
            )


class TestCompletedSessionFollowUp(unittest.TestCase):
    """Follow-up on a completed session should rebuild the agent."""

    @patch("app.sessions_manager.Agent")
    @patch("app.sessions_manager.configure_ca_bundle")
    @patch("app.sessions_manager.keys")
    def test_completed_follow_up_rebuilds_agent(
        self, mock_keys: MagicMock, mock_ca: MagicMock, mock_agent_cls: MagicMock
    ) -> None:
        mock_keys.BROWSER_USE_KEY = "fake-key"
        repo = _make_mock_repo()
        mgr = BrowserSessionManager(repo=repo)

        old_agent = _make_mock_agent()
        old_hook = _make_mock_hook(agent=old_agent)
        session = _make_active_session(hook=old_hook, runner_done=True)
        mgr._sessions["completed-session"] = session

        # The Agent constructor should return a mock new agent
        new_agent_instance = MagicMock()
        new_agent_instance.run = AsyncMock()
        mock_agent_cls.return_value = new_agent_instance

        asyncio.get_event_loop().run_until_complete(
            mgr.start_session(
                task_prompt="now do step 2",
                session_id="completed-session",
            )
        )

        # Agent was called to build a fresh instance
        mock_agent_cls.assert_called_once()
        kwargs = mock_agent_cls.call_args
        # The new agent should reuse the old *live* browser_session
        self.assertIs(kwargs.kwargs.get("browser_session"), old_agent.browser_session)
        # The new agent should reuse the old llm
        self.assertIs(kwargs.kwargs.get("llm"), old_agent.llm)
        # directly_open_url should be False
        self.assertFalse(kwargs.kwargs.get("directly_open_url"))
        # The task should include FOLLOW-UP TASK prefix
        self.assertIn("FOLLOW-UP TASK", kwargs.kwargs.get("task", ""))

        # The session's hook should have been replaced (not the old one)
        self.assertIsNot(session.hook, old_hook)


class TestExceptionHierarchy(unittest.TestCase):
    """Verify exception types inherit correctly."""

    def test_session_not_found_is_follow_up_error(self) -> None:
        self.assertTrue(issubclass(SessionNotFoundError, FollowUpSessionError))

    def test_follow_up_not_supported_is_follow_up_error(self) -> None:
        self.assertTrue(issubclass(FollowUpNotSupportedError, FollowUpSessionError))


class TestRouteWiring(unittest.TestCase):
    """The follow_up route should still be registered."""

    def test_follow_up_route_exists(self) -> None:
        from app.routes import router

        paths = [route.path for route in router.routes]
        self.assertIn("/task/follow_up", paths)

    def test_task_route_exists(self) -> None:
        from app.routes import router

        paths = [route.path for route in router.routes]
        self.assertIn("/task", paths)


if __name__ == "__main__":
    unittest.main()
