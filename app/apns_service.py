import asyncio
import logging

from aioapns import APNs, NotificationRequest, PushType
from pydantic import BaseModel

from app.config import keys
from app.browser_hook.models import DoneState, TaskStep


class LiveActivityContentState(BaseModel):
    session_id: str
    step: TaskStep | None = None
    done: DoneState | None = None


class LiveActivityPusher:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Initialize the connection to Apple
        self.apns = APNs(
            key=keys.p8_key(),
            key_id="N96AD57HA8",
            team_id="3S6NT5MUQZ",
            topic="com.yourcompany.yourapp.push-type.liveactivity",  # Must append .push-type.liveactivity
        )
        self._tokens_by_session: dict[str, str] = {}
        self._in_flight: set[asyncio.Task[None]] = set()

    def register_activity_token(self, session_id: str, push_token: str) -> None:
        self._tokens_by_session[session_id] = push_token

    def unregister_activity_token(self, session_id: str) -> None:
        self._tokens_by_session.pop(session_id, None)

    async def update_activity(
        self,
        activity_push_token: str,
        session_id: str,
        state: TaskStep | DoneState,
    ):
        import time

        is_done = isinstance(state, DoneState)
        content_state = LiveActivityContentState(
            session_id=session_id,
            step=state if isinstance(state, TaskStep) else None,
            done=state if is_done else None,
        )

        payload = {
            "aps": {
                "timestamp": int(time.time()),
                "event": "end" if is_done else "update",
                "content-state": content_state.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            }
        }

        request = NotificationRequest(
            device_token=activity_push_token,
            message=payload,
            push_type=PushType.LIVEACTIVITY,
            priority=10,
        )

        response = await self.apns.send_notification(request)
        if response.is_successful:
            self.logger.info(
                "Live Activity updated successfully for session %s", session_id
            )
        else:
            self.logger.error(
                "Failed to update activity for session %s: %s",
                session_id,
                response.description,
            )

    async def publish_session_update(
        self,
        session_id: str,
        state: TaskStep | DoneState,
    ) -> None:
        token = self._tokens_by_session.get(session_id)
        if token is None:
            return

        async def _send_update_safely() -> None:
            try:
                await self.update_activity(
                    activity_push_token=token,
                    session_id=session_id,
                    state=state,
                )
            except Exception:
                self.logger.exception(
                    "Unexpected error publishing Live Activity update for session %s",
                    session_id,
                )
            finally:
                if isinstance(state, DoneState):
                    self.unregister_activity_token(session_id)

        task: asyncio.Task[None] = asyncio.create_task(_send_update_safely())
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)


# Create a global instance
activity_pusher = LiveActivityPusher()
