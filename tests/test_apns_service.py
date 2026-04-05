import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.apns_service import LiveActivityPusher
from app.browser_hook.models import DoneState, TaskStep, ToolResult, ToolStatus


def _response(
    *,
    success: bool,
    description: str | None = None,
    status: int = 200,
    notification_id: str = "notif-1",
):
    return SimpleNamespace(
        is_successful=success,
        description=description,
        status=status,
        notification_id=notification_id,
    )


class TestLiveActivityPusher(unittest.IsolatedAsyncioTestCase):
    async def test_done_state_sends_update_then_delayed_end_then_cleans_up(self) -> None:
        apns = MagicMock()
        apns.send_notification = AsyncMock(
            side_effect=[
                _response(success=True, notification_id="update-id"),
                _response(success=True, notification_id="end-id"),
            ]
        )
        pusher = LiveActivityPusher(apns_client=apns, end_delay_seconds=0.01)
        pusher.register_activity_token("session-1", "token-1")

        done = DoneState(result="Finished", status=ToolStatus.SUCCESS)

        await pusher.publish_session_update("session-1", done)
        await asyncio.sleep(0)

        self.assertEqual(apns.send_notification.await_count, 1)
        first_request = apns.send_notification.await_args_list[0].args[0]
        self.assertEqual(first_request.message["aps"]["event"], "update")
        self.assertEqual(
            first_request.message["aps"]["content-state"],
            {
                "session_id": "session-1",
                "done": {"result": "Finished", "status": "success"},
            },
        )
        self.assertIn("session-1", pusher._tokens_by_session)

        await asyncio.sleep(0.05)

        self.assertEqual(apns.send_notification.await_count, 2)
        second_request = apns.send_notification.await_args_list[1].args[0]
        self.assertEqual(second_request.message["aps"]["event"], "end")
        self.assertEqual(
            second_request.message["aps"]["content-state"],
            {
                "session_id": "session-1",
                "done": {"result": "Finished", "status": "success"},
            },
        )
        self.assertNotIn("session-1", pusher._tokens_by_session)
        self.assertNotIn("session-1", pusher._pending_end_tasks)

    async def test_invalid_done_token_cleans_up_without_scheduling_end(self) -> None:
        apns = MagicMock()
        apns.send_notification = AsyncMock(
            return_value=_response(
                success=False,
                description="BadDeviceToken",
                status=400,
                notification_id="bad-token-id",
            )
        )
        pusher = LiveActivityPusher(apns_client=apns, end_delay_seconds=0.01)
        pusher.register_activity_token("session-2", "token-2")

        done = DoneState(result="Finished", status=ToolStatus.SUCCESS)

        await pusher.publish_session_update("session-2", done)
        await asyncio.sleep(0.02)

        self.assertEqual(apns.send_notification.await_count, 1)
        request = apns.send_notification.await_args_list[0].args[0]
        self.assertEqual(request.message["aps"]["event"], "update")
        self.assertNotIn("session-2", pusher._tokens_by_session)
        self.assertNotIn("session-2", pusher._pending_end_tasks)

    async def test_intermediate_update_payload_is_unchanged(self) -> None:
        apns = MagicMock()
        apns.send_notification = AsyncMock(
            return_value=_response(success=True, notification_id="step-id")
        )
        pusher = LiveActivityPusher(apns_client=apns, end_delay_seconds=0.01)
        pusher.register_activity_token("session-3", "token-3")

        step = TaskStep(
            step=3,
            memory="Working",
            tools=[
                ToolResult(
                    tool="navigate",
                    title="Navigate",
                    status=ToolStatus.SUCCESS,
                )
            ],
        )

        await pusher.publish_session_update("session-3", step)
        await asyncio.sleep(0)

        self.assertEqual(apns.send_notification.await_count, 1)
        request = apns.send_notification.await_args_list[0].args[0]
        self.assertEqual(request.message["aps"]["event"], "update")
        self.assertEqual(
            request.message["aps"]["content-state"],
            {
                "session_id": "session-3",
                "step": {
                    "step": 3,
                    "memory": "Working",
                    "tools": [
                        {
                            "tool": "navigate",
                            "title": "Navigate",
                            "status": "success",
                        }
                    ],
                },
            },
        )
        self.assertIn("session-3", pusher._tokens_by_session)


if __name__ == "__main__":
    unittest.main()
