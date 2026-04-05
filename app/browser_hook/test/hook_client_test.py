import asyncio
import os

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatBrowserUse

from app.config import keys
from app.browser_hook.hook_client import BrowserHook
from app.browser_hook.models import TaskStep

AgentType = Agent[object, BaseModel]


async def main() -> None:
    os.environ["BROWSER_USE_API_KEY"] = keys.BROWSER_USE_KEY

    llm = ChatBrowserUse()
    cloud_browser = Browser(use_cloud=True)
    agent: AgentType = Agent(
        task="Go to example.com. Record the page title and all headings.",
        llm=llm,
        browser=cloud_browser,
    )

    hook = BrowserHook(agent=agent)

    async def observe_events() -> None:
        async for event in hook.iter_events():
            if isinstance(event, TaskStep):
                print(f"\n=== Step {event.step} received ===")
                print(f"  memory: {event.memory}")
                print(f"  tools:  {[t.tool for t in event.tools]}")

                # Pause after every step so we can inspect before continuing.
                hook.pause()

                print("  [paused] - resuming in 2 seconds...")
                await asyncio.sleep(2)

                hook.resume()
                print("  [resumed]")

    observer_task = asyncio.create_task(observe_events())
    history = await hook.run(max_steps=5)
    await observer_task

    print(f"\n=== Run complete ===")
    print(f"final_result: {history.final_result()}")
    print(f"total_steps:  {len(hook.steps)}")
    for ts in hook.steps:
        print(f"  Step {ts.step}: {[t.tool for t in ts.tools]}")


if __name__ == "__main__":
    asyncio.run(main())
