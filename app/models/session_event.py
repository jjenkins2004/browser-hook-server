from datetime import datetime, timezone
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.browser_hook.models import DoneState, TaskStep
from app.models.task import TaskStatus


class UserEvent(BaseModel):
    event_type: Literal["user_prompt"] = "user_prompt"
    prompt: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Backwards-compatible alias for older imports.
UserPromptEvent = UserEvent


class AgentStepEvent(BaseModel):
    event_type: Literal["agent_step"] = "agent_step"
    step: TaskStep
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentDoneEvent(BaseModel):
    event_type: Literal["agent_done"] = "agent_done"
    done: DoneState
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentCancelledEvent(BaseModel):
    event_type: Literal["agent_cancelled"] = "agent_cancelled"
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


SessionEvent = UserEvent | AgentStepEvent | AgentDoneEvent | AgentCancelledEvent


class SessionEventLog(BaseModel):
    session_id: str
    status: TaskStatus = TaskStatus.RUNNING
    events: list[SessionEvent] = Field(default_factory=list)
