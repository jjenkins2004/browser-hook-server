# Live Activities + APNs Helper

This note is for the server-side work around iOS Live Activities in this repo.

## Current server flow

The existing implementation already has the basic shape needed for Live Activity updates:

- `app/routes.py`
  - `POST /live-activity/register`
  - accepts `{ "session_id": "...", "push_token": "..." }`
  - stores the Live Activity push token for a session
- `app/utils.py`
  - every streamed `TaskStep` or `DoneState` update also triggers `activity_pusher.publish_session_update(...)`
- `app/apns_service.py`
  - builds the APNs payload
  - sends it with `PushType.LIVEACTIVITY`
  - uses topic `tech.themobilebrowser.wingman.push-type.liveactivity`

In other words:

1. iOS starts a Live Activity.
2. iOS sends the activity push token to this server through `/live-activity/register`.
3. The server associates that token with `session_id`.
4. As the task stream emits updates, the server forwards them to APNs.
5. When a `DoneState` arrives, the server sends an `end` event and unregisters the token.

## Files to know

- `app/apns_service.py`: APNs client setup, payload construction, sending logic
- `app/routes.py`: registration endpoint and debug push endpoint
- `app/utils.py`: task streaming + opportunistic Live Activity fan-out
- `app/browser_hook/models.py`: `TaskStep`, `DoneState`, `ToolResult`
- `app/models/api.py`: request models for token registration and debug push

## Payload shape used today

The server currently sends payloads like:

```json
{
  "aps": {
    "timestamp": 1712345678,
    "event": "update",
    "content-state": {
      "session_id": "abc123",
      "step": {
        "step": 1,
        "memory": "Test step from server",
        "tools": [
          {
            "tool": "navigate",
            "title": "Navigating to example.com",
            "status": "success"
          }
        ]
      }
    }
  }
}
```

When the task finishes, `event` becomes `"end"` and the payload carries:

```json
{
  "session_id": "abc123",
  "done": {
    "result": "Task complete",
    "status": "success"
  }
}
```

That means the iOS `ActivityAttributes.ContentState` needs to match this structure closely.

## Important APNs details

- The APNs topic for Live Activities must end with `.push-type.liveactivity`.
- The push token used here is the Live Activity push token, not the normal device token.
- The server is correctly using `PushType.LIVEACTIVITY`.
- `timestamp` should always be present and should move forward over time.
- `event` should be either `update` or `end` for the current flow.

## What the iOS side must agree on

The biggest integration risk is schema drift between server and app.

The iOS app should expect:

- `session_id: String`
- `step: TaskStep?`
- `done: DoneState?`

And the nested models should align with:

- `TaskStep.step: Int`
- `TaskStep.memory: String?`
- `TaskStep.tools: [ToolResult]`
- `ToolResult.tool: String`
- `ToolResult.title: String`
- `ToolResult.description: String?`
- `ToolResult.status: String`
- `DoneState.result: String?`
- `DoneState.status: String`

If the Swift models rename fields or change optionality, remote updates may decode incorrectly or be ignored by the app.

## Good implementation notes for this repo

### 1. Keep APNs failures non-fatal

`app/utils.py` already does the right thing: Live Activity push failures should not break the NDJSON task stream.

### 2. Token storage is currently in-memory

`LiveActivityPusher` stores tokens in:

```python
self._tokens_by_session: dict[str, str] = {}
```

This is fine for development, but production caveats are:

- tokens disappear on server restart
- multiple app instances will not share token state
- reconnect/retry flows may lose the association

If this feature matters in production, move the mapping to shared storage.

### 3. The APNs credentials are hardcoded right now

`app/apns_service.py` currently hardcodes:

- `key_id`
- `team_id`
- `topic`

Those should ideally come from config/env so the server is easier to move across environments.

### 4. One session currently maps to one Live Activity token

This line implies a 1:1 mapping:

```python
self._tokens_by_session: dict[str, str]
```

That is okay if each session can only have one active Live Activity. If multiple clients/devices can observe the same session, change this to `dict[str, set[str]]` and fan out to all tokens.

### 5. End behavior is basic but valid

On `DoneState`, the code:

- sends `event = "end"`
- unregisters the token afterward

That is a sensible default. If the iOS team wants better UX later, they can coordinate extra fields like a final alert, dismissal timing, or stale handling.

## Debugging path already available

There is already a dev endpoint:

- `POST /debug/live-activity/test-push`

It:

1. registers the provided push token under a mock session
2. sends one mock `TaskStep`
3. waits 5 seconds
4. sends one mock `DoneState`

This is the fastest way to validate:

- APNs auth is working
- the topic is correct
- the token is valid
- the app decodes the server payload correctly

## Recommended next improvements

If we want to harden this feature, the next best server changes are:

1. Move `key_id`, `team_id`, and `topic` into config.
2. Persist Live Activity tokens outside process memory.
3. Add better logging around `session_id`, APNs response status, and token lifecycle.
4. Support multiple activity tokens per session if multiple observers are expected.
5. Add a small integration test around payload serialization to prevent schema drift.

## Practical checklist for the dev

- Confirm the iOS Live Activity content state matches this JSON structure exactly.
- Confirm the app is sending the Live Activity push token, not the standard device token.
- Confirm the APNs topic matches the app bundle topic with `.push-type.liveactivity`.
- Use `/debug/live-activity/test-push` before wiring the full task flow.
- Treat token persistence as a production follow-up if this must survive restarts or horizontal scaling.

## Current code references

- `app/apns_service.py`
- `app/routes.py`
- `app/utils.py`
- `app/models/api.py`
- `app/browser_hook/models.py`
