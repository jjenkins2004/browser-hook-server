import asyncio
from collections.abc import AsyncIterator

from pydantic import BaseModel
from browser_use import Agent
from browser_use.agent.views import AgentHistoryList

from app.browser_hook.models import DoneState, TaskStep
from .step_extractor import extract_step

AgentType = Agent[object, BaseModel]
AgentHistoryType = AgentHistoryList[BaseModel]

HookEvent = TaskStep | DoneState


class BrowserHook:
    def __init__(self, agent: AgentType):
        self.agent = agent
        self.steps: list[TaskStep] = []
        self._event_subscribers: list[asyncio.Queue[HookEvent | None]] = []

    async def _publish_event(self, event: HookEvent) -> None:
        for subscriber in list(self._event_subscribers):
            await subscriber.put(event)

    async def _close_event_streams(self) -> None:
        for subscriber in list(self._event_subscribers):
            await subscriber.put(None)

    async def iter_events(self) -> AsyncIterator[HookEvent]:
        """Yield hook events (TaskStep and DoneState) for the current run."""
        subscriber: asyncio.Queue[HookEvent | None] = asyncio.Queue()
        self._event_subscribers.append(subscriber)
        try:
            while True:
                event = await subscriber.get()
                if event is None:
                    break
                yield event
        finally:
            if subscriber in self._event_subscribers:
                self._event_subscribers.remove(subscriber)

    async def run(self, max_steps: int = 500) -> AgentHistoryType:
        """Runs the agent and streams extracted TaskStep entries."""

        async def on_step_end(agent: AgentType) -> None:
            # Extract the step data
            step: TaskStep = extract_step(agent)

            # Check if this is a final "done" step
            done_tools = [tool for tool in step.tools if tool.tool == "done"]
            if done_tools:
                # Remove the "done" tool from the normal step tools
                step.tools = [tool for tool in step.tools if tool.tool != "done"]

            self.steps.append(step)
            
            # Fire the step event
            await self._publish_event(step)

            # Fire the done event if we hit it
            if done_tools:
                done_state = DoneState(
                    result=done_tools[0].description,
                    status=done_tools[0].status,
                )
                await self._publish_event(done_state)

        try:
            return await self.agent.run(
                max_steps=max_steps,
                on_step_end=on_step_end,
            )
        finally:
            # When the agent finishes, tell the iterators to pack it up
            await self._close_event_streams()

    def pause(self) -> None:
        """Freeze the agent at the end of the current step."""
        self.agent.pause()

    def resume(self) -> None:
        """Unfreeze the agent."""
        self.agent.resume()
    
    def stop(self) -> None:
        """Stop the agent immediately."""
        self.agent.stop()