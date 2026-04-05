import asyncio
import hashlib
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
            topic="tech.themobilebrowser.wingman.push-type.liveactivity",  # Must append .push-type.liveactivity
            use_sandbox=True,  # Use the APNS sandbox environment for development
        )
        self._tokens_by_session: dict[str, str] = {}
        self._in_flight: set[asyncio.Task[None]] = set()

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        # Log a short, non-reversible token fingerprint for troubleshooting.
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    def register_activity_token(self, session_id: str, push_token: str) -> None:
        self._tokens_by_session[session_id] = push_token
        self.logger.info(
            "Registered live activity token for session %s (token_fp=%s)",
            session_id,
            self._token_fingerprint(push_token),
        )

    def unregister_activity_token(self, session_id: str) -> None:
        token = self._tokens_by_session.pop(session_id, None)
        if token is not None:
            self.logger.info(
                "Unregistered live activity token for session %s (token_fp=%s)",
                session_id,
                self._token_fingerprint(token),
            )

    def reset_state(self) -> None:
        for task in list(self._in_flight):
            if not task.done():
                task.cancel()
        self._in_flight.clear()
        self._tokens_by_session.clear()

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

        timestamp = int(time.time())
        aps_payload = {
            "timestamp": timestamp,
            "event": "end" if is_done else "update",
            "content-state": content_state.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
        }

        payload = {"aps": aps_payload}

        request = NotificationRequest(
            device_token=activity_push_token,
            message=payload,
            push_type=PushType.LIVEACTIVITY,
            priority=10,
        )

        event_name = "end" if is_done else "update"
        token_fp = self._token_fingerprint(activity_push_token)
        self.logger.debug(
            "Sending Live Activity APNS push (session=%s, event=%s, token_fp=%s)",
            session_id,
            event_name,
            token_fp,
        )

        response = await self.apns.send_notification(request)
        apns_status = getattr(response, "status", None)
        apns_id = getattr(response, "notification_id", None)
        if response.is_successful:
            self.logger.info(
                "Live Activity push succeeded (session=%s, event=%s, token_fp=%s, status=%s, notification_id=%s)",
                session_id,
                event_name,
                token_fp,
                apns_status,
                apns_id,
            )
        else:
            self.logger.error(
                "Live Activity push failed (session=%s, event=%s, token_fp=%s, status=%s, notification_id=%s, reason=%s)",
                session_id,
                event_name,
                token_fp,
                apns_status,
                apns_id,
                response.description,
            )
            if response.description == "BadDeviceToken":
                self.logger.warning(
                    "BadDeviceToken diagnostic: token likely invalid/stale or environment/topic mismatch. "
                    "Check iOS-provided live activity token freshness, APNS sandbox vs production, and topic suffix '.push-type.liveactivity'."
                )

    async def publish_session_update(
        self,
        session_id: str,
        state: TaskStep | DoneState,
    ) -> None:
        token = self._tokens_by_session.get(session_id)
        if token is None:
            self.logger.debug(
                "No live activity token registered for session %s; skipping push",
                session_id,
            )
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
                    "Unexpected error publishing Live Activity update for session %s (token_fp=%s)",
                    session_id,
                    self._token_fingerprint(token),
                )
            finally:
                if isinstance(state, DoneState):
                    self.unregister_activity_token(session_id)

        task: asyncio.Task[None] = asyncio.create_task(_send_update_safely())
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)


# Create a global instance
activity_pusher = LiveActivityPusher()
