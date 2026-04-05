from abc import ABC, abstractmethod

from app.browser_hook.models import TaskStep
from app.models.session_event import AgentStepEvent, SessionEvent, SessionEventLog
from app.models.task import TaskStatus, TaskStatusResponse
from app.repo.mock_session_data import build_mock_session_store


class SessionRepo(ABC):

    @abstractmethod
    async def persist_event(self, session_id: str, event: SessionEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_session_state(
        self,
        session_id: str,
        status: TaskStatus,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        raise NotImplementedError
    
    @abstractmethod
    async def get_event_log(self, session_id: str) -> SessionEventLog:
        raise NotImplementedError

    @abstractmethod
    async def get_history(self) -> list[SessionEventLog]:
        raise NotImplementedError

class InMemorySessionRepo(SessionRepo):
    def __init__(self) -> None:
        self._event_logs_by_session: dict[str, SessionEventLog] = {}
        self._load_mock_data()

    def _load_mock_data(self) -> None:
        _, event_logs_by_session = build_mock_session_store()
        self._event_logs_by_session.update(event_logs_by_session)

    def _get_or_create_event_log(self, session_id: str) -> SessionEventLog:
        event_log = self._event_logs_by_session.get(session_id)
        if event_log is None:
            event_log = SessionEventLog(session_id=session_id)
            self._event_logs_by_session[session_id] = event_log
        return event_log

    async def persist_event(self, session_id: str, event: SessionEvent) -> None:
        event_log = self._get_or_create_event_log(session_id)
        event_log.events.append(event)

    async def set_session_state(
        self,
        session_id: str,
        status: TaskStatus,
    ) -> None:
        event_log = self._get_or_create_event_log(session_id)
        event_log.status = status

    async def get_event_log(self, session_id: str) -> SessionEventLog:
        event_log = self._event_logs_by_session.get(session_id)
        if event_log is None:
            return SessionEventLog(session_id=session_id)
        return event_log.model_copy(deep=True)

    async def clear_session(self, session_id: str) -> None:
        self._event_logs_by_session.pop(session_id, None)

    async def get_history(self) -> list[SessionEventLog]:
        return [log.model_copy(deep=True) for log in self._event_logs_by_session.values()]


inMemoryRepo: SessionRepo = InMemorySessionRepo()
