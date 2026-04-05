import asyncio
import hashlib
import logging
from dataclasses import dataclass

from aioapns import APNs, NotificationRequest, PushType
from aioapns.exceptions import MaxAttemptsExceeded
from pydantic import BaseModel

from app.config import keys
from app.browser_hook.models import DoneState, TaskStep
from app.ssl_config import build_ssl_context


class LiveActivityContentState(BaseModel):
    session_id: str
    step: TaskStep | None = None
    done: DoneState | None = None


@dataclass(slots=True)
class PushDeliveryResult:
    success: bool
    invalid_token: bool
    status: int | None
    notification_id: str | None
    description: str | None


class LiveActivityPusher:
    def __init__(self, apns_client: APNs | None = None, end_delay_seconds: float = 90.0):
        self.logger = logging.getLogger(__name__)
        # Initialize the connection to Apple
        self.apns = apns_client or APNs(
            key=keys.p8_key(),
            key_id="N96AD57HA8",
            team_id="3S6NT5MUQZ",
            topic="tech.themobilebrowser.wingman.push-type.liveactivity",  # Must append .push-type.liveactivity
            use_sandbox=True,  # Use the APNS sandbox environment for development
            ssl_context=build_ssl_context(),
        )
        self._end_delay_seconds = end_delay_seconds
        self._tokens_by_session: dict[str, str] = {}
        self._in_flight: set[asyncio.Task[None]] = set()
        self._pending_end_tasks: dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        # Log a short, non-reversible token fingerprint for troubleshooting.
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _is_invalid_token_response(description: str | None) -> bool:
        return description in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}

    def register_activity_token(self, session_id: str, push_token: str) -> None:
        self._cancel_pending_end(session_id, reason="token_registered")
        self._tokens_by_session[session_id] = push_token
        self.logger.info(
            "Registered live activity token for session %s (token_fp=%s)",
            session_id,
            self._token_fingerprint(push_token),
        )

    def unregister_activity_token(self, session_id: str) -> None:
        self._cancel_pending_end(session_id, reason="token_unregistered")
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
        for task in list(self._pending_end_tasks.values()):
            if not task.done():
                task.cancel()
        self._in_flight.clear()
        self._pending_end_tasks.clear()
        self._tokens_by_session.clear()

    def _cleanup_session_token(self, session_id: str, *, when: str) -> None:
        token = self._tokens_by_session.pop(session_id, None)
        if token is None:
            self.logger.info(
                "Live Activity token cleanup skipped for session %s; token already absent (cleanup=%s)",
                session_id,
                when,
            )
            return
        self.logger.info(
            "Cleaned up Live Activity token for session %s (token_fp=%s, cleanup=%s)",
            session_id,
            self._token_fingerprint(token),
            when,
        )

    def _cancel_pending_end(self, session_id: str, *, reason: str) -> None:
        task = self._pending_end_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            self.logger.info(
                "Cancelled delayed Live Activity end for session %s (reason=%s)",
                session_id,
                reason,
            )

    async def _send_activity_event(
        self,
        activity_push_token: str,
        session_id: str,
        state: TaskStep | DoneState,
        *,
        event_name: str,
    ) -> PushDeliveryResult:
        import time

        content_state = LiveActivityContentState(
            session_id=session_id,
            step=state if isinstance(state, TaskStep) else None,
            done=state if isinstance(state, DoneState) else None,
        )

        timestamp = int(time.time())
        aps_payload = {
            "timestamp": timestamp,
            "event": event_name,
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
            return PushDeliveryResult(
                success=True,
                invalid_token=False,
                status=apns_status,
                notification_id=apns_id,
                description=getattr(response, "description", None),
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
            return PushDeliveryResult(
                success=False,
                invalid_token=self._is_invalid_token_response(response.description),
                status=apns_status,
                notification_id=apns_id,
                description=response.description,
            )

    def _schedule_delayed_end(self, session_id: str, state: DoneState) -> None:
        self._cancel_pending_end(session_id, reason="rescheduled")
        self.logger.info(
            "Scheduled delayed Live Activity end for session %s (delay_seconds=%s)",
            session_id,
            self._end_delay_seconds,
        )

        async def _delayed_end() -> None:
            try:
                await asyncio.sleep(self._end_delay_seconds)
                token = self._tokens_by_session.get(session_id)
                if token is None:
                    self.logger.info(
                        "Delayed Live Activity end found no token for session %s; cleanup happened before APNS success",
                        session_id,
                    )
                    return

                self.logger.info(
                    "Sending delayed Live Activity end for session %s",
                    session_id,
                )
                result = await self._send_activity_event(
                    activity_push_token=token,
                    session_id=session_id,
                    state=state,
                    event_name="end",
                )
                if result.success:
                    self._cleanup_session_token(session_id, when="after_apns_success")
                elif result.invalid_token:
                    self.logger.warning(
                        "Delayed Live Activity end found invalid token for session %s; cleaning up before APNS success",
                        session_id,
                    )
                    self._cleanup_session_token(session_id, when="before_apns_success")
            except asyncio.CancelledError:
                self.logger.debug(
                    "Delayed Live Activity end task cancelled for session %s",
                    session_id,
                )
                raise
            except MaxAttemptsExceeded:
                token = self._tokens_by_session.get(session_id)
                self.logger.error(
                    "Delayed Live Activity end failed after APNS connection retries (session=%s, token_fp=%s).",
                    session_id,
                    self._token_fingerprint(token) if token is not None else "missing",
                )
            except Exception:
                token = self._tokens_by_session.get(session_id)
                self.logger.exception(
                    "Unexpected error sending delayed Live Activity end for session %s (token_fp=%s)",
                    session_id,
                    self._token_fingerprint(token) if token is not None else "missing",
                )
            finally:
                current_task = asyncio.current_task()
                if self._pending_end_tasks.get(session_id) is current_task:
                    self._pending_end_tasks.pop(session_id, None)

        task: asyncio.Task[None] = asyncio.create_task(_delayed_end())
        self._pending_end_tasks[session_id] = task
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)

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
                if isinstance(state, DoneState):
                    self.logger.info(
                        "Sending final Live Activity completion update for session %s",
                        session_id,
                    )
                    result = await self._send_activity_event(
                        activity_push_token=token,
                        session_id=session_id,
                        state=state,
                        event_name="update",
                    )
                    if result.invalid_token:
                        self.logger.warning(
                            "Final Live Activity completion update found invalid token for session %s; cleaning up before APNS success",
                            session_id,
                        )
                        self._cleanup_session_token(
                            session_id, when="before_apns_success"
                        )
                        return
                    self._schedule_delayed_end(session_id, state)
                else:
                    self._cancel_pending_end(session_id, reason="intermediate_update")
                    await self._send_activity_event(
                        activity_push_token=token,
                        session_id=session_id,
                        state=state,
                        event_name="update",
                    )
            except MaxAttemptsExceeded:
                self.logger.error(
                    "Live Activity push failed after APNS connection retries (session=%s, token_fp=%s). "
                    "This usually indicates a transport/TLS issue before APNS returned a response.",
                    session_id,
                    self._token_fingerprint(token),
                )
            except Exception:
                self.logger.exception(
                    "Unexpected error publishing Live Activity update for session %s (token_fp=%s)",
                    session_id,
                    self._token_fingerprint(token),
                )

        task: asyncio.Task[None] = asyncio.create_task(_send_update_safely())
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)


# Create a global instance
activity_pusher = LiveActivityPusher()
