from pydantic import BaseModel
from browser_use import Agent
from browser_use.agent.views import ActionResult

from app.browser_hook.get_tools import extract_ui_tools
from app.browser_hook.models import TaskStep

AgentType = Agent[object, BaseModel]


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
