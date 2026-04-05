import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.browser_hook.hook_client import BrowserHook


@dataclass
class ActiveSession:
    hook: "BrowserHook"
    runner_task: asyncio.Task[Any] | None = None
