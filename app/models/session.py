import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.browser_hook.models import TaskStep

if TYPE_CHECKING:
    from app.browser_hook.hook_client import BrowserHook


StepCallback = Callable[[TaskStep], Awaitable[None] | None]


@dataclass
class ActiveSession:
    hook: "BrowserHook"
    runner_task: asyncio.Task[Any] | None = None
    step_callback: StepCallback | None = None
