import asyncio
from typing import Awaitable, Callable
from pydantic import BaseModel
from browser_use import Agent
from browser_use.agent.views import AgentHistoryList

from .step_extractor import extract_step, TaskStep

AgentType = Agent[object, BaseModel]
AgentHistoryType = AgentHistoryList[BaseModel]

# Update the signature to accept the hook instance AND the step
StepCallback = Callable[["BrowserHook", TaskStep], Awaitable[None] | None]


class BrowserHook:
    def __init__(
        self,
        agent: AgentType,
        on_step_callback: StepCallback | None = None,
    ):
        self.agent = agent
        self.on_step_callback = on_step_callback
        self.steps: list[TaskStep] = []
        
    async def run(self, max_steps: int = 500) -> AgentHistoryType:
        """Runs the agent and stores extracted TaskStep entries in self.steps."""

        async def on_step_end(agent: AgentType) -> None:
            # Extract the step data
            step: TaskStep = extract_step(agent)
            
            self.steps.append(step)

            # Execute the callback, passing `self` so the user can control the hook
            if self.on_step_callback is not None:
                action = self.on_step_callback(self, step)
                if asyncio.iscoroutine(action):
                    await action

        return await self.agent.run(
            max_steps=max_steps,
            on_step_end=on_step_end,
        )

    def pause(self) -> None:
        """
        Call this INSIDE callback to freeze the agent at the end of the current step.
        """
        self.agent.pause()

    def resume(self) -> None:
        """
        Call this to unfreeze the agent.
        """
        self.agent.resume()
