import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatBrowserUse
from browser_use.agent.views import ActionResult, AgentHistoryList, AgentOutput

try:
    from app.config import keys
    from app.browser_hook.get_tools import extract_ui_tools
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.config import keys
    from app.browser_hook.get_tools import extract_ui_tools


class StepActions(BaseModel):
    step: int
    hook: str
    actions: list[Any]
    results: list[ActionResult]

    model_config = {"arbitrary_types_allowed": True}


AgentType = Agent[object, BaseModel]
AgentHistoryType = AgentHistoryList[BaseModel]


def _extract_step_actions(agent: AgentType, hook: str) -> StepActions:
    output: AgentOutput | None = agent.state.last_model_output
    results: list[ActionResult] = agent.state.last_result or []
    actions: list[Any] = output.action if output else []
    return StepActions(
        step=agent.state.n_steps,
        hook=hook,
        actions=actions,
        results=results,
    )


async def main() -> None:
    os.environ.setdefault("BROWSER_USE_API_KEY", keys.BROWSER_USE_KEY)

    step_events: list[StepActions] = []

    async def on_step_start(agent: AgentType) -> None:
        step = _extract_step_actions(agent, hook="start")
        step_events.append(step)

    async def on_step_end(agent: AgentType) -> None:
        step = _extract_step_actions(agent, hook="end")
        step_events.append(step)

    llm = ChatBrowserUse(api_key=keys.BROWSER_USE_KEY)
    cloud_browser = Browser(use_cloud=True)
    agent: AgentType = Agent(
        task="Use every single tool available to you once..",
        llm=llm,
        browser=cloud_browser,
    )
    history: AgentHistoryType = await agent.run(
        max_steps=100,
        on_step_start=on_step_start,
        on_step_end=on_step_end,
    )

    print("\n=== Run Complete ===")
    print(f"final_result: {history.final_result()}")
    end_steps = [e for e in step_events if e.hook == "end"]
    print(f"total_steps: {len(end_steps)}")

    print(f"\n=== All Tool Calls And Results ===")
    for event in end_steps:
        print(f"\nStep {event.step}")
        ui_tools = extract_ui_tools(event.actions, event.results)
        print(f"tools: {ui_tools or 'no tools'}")


if __name__ == "__main__":
    asyncio.run(main())
