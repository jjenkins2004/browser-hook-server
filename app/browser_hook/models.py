from enum import Enum

from pydantic import BaseModel


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


class ToolResult(BaseModel):
    tool: str
    title: str
    description: str | None = None
    status: ToolStatus


class TaskStep(BaseModel):
    step: int
    memory: str | None = None
    tools: list[ToolResult]
