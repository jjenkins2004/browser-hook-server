from pydantic import BaseModel
from browser_use import Agent
from browser_use.agent.views import ActionResult
from typing import Optional

from app.browser_hook.get_tools import ToolResult, extract_ui_tools

AgentType = Agent[object, BaseModel]

class TaskStep(BaseModel):
    step: int
    memory: Optional[str] = None
    tools: list[ToolResult]


def extract_step(agent: AgentType) -> TaskStep:
    output = agent.state.last_model_output
    raw_actions = output.action if output else []
    raw_results: list[ActionResult] = agent.state.last_result or []
    memory: str | None = getattr(
        output.current_state if output else None, "memory", None
    )

    return TaskStep(
        step=agent.state.n_steps,
        memory=memory,
        tools=extract_ui_tools(raw_actions, raw_results),
    )
