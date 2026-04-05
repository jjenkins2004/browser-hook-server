from aioapns import APNs, NotificationRequest
from pydantic import BaseModel

from app.browser_hook.models import TaskStep


class LiveActivityContentState(BaseModel):
    session_id: str
    step: TaskStep


class LiveActivityPusher:
    def __init__(self):
        # Initialize the connection to Apple
        self.apns = APNs(
            key="path/to/AuthKey_YOURKEYID.p8",
            key_id="N96AD57HA8",
            team_id="3S6NT5MUQZ",
            topic="com.yourcompany.yourapp.push-type.liveactivity",  # Must append .push-type.liveactivity
            use_sandbox=True,  # Use True for development, False for production TestFlight/AppStore
        )

    async def update_activity(
        self,
        activity_push_token: str,
        session_id: str,
        step: TaskStep,
    ):
        # 1. Construct the EXACT JSON payload Apple expects
        import time

        content_state = LiveActivityContentState(session_id=session_id, step=step)

        payload = {
            "aps": {
                "timestamp": int(time.time()),
                "event": "update",  # Use "end" if the task is finished!
                "content-state": content_state.model_dump(mode="json"),
            }
        }

        # 2. Fire the push notification to Apple
        request = NotificationRequest(device_token=activity_push_token, message=payload)

        response = await self.apns.send_notification(request)
        if response.is_successful:
            print("Live Activity updated successfully!")
        else:
            print(f"Failed to update activity: {response.description}")


# Create a global instance
activity_pusher = LiveActivityPusher()
