from pydantic import BaseModel


class RegisterDeviceTokenRequest(BaseModel):
    device_token: str


class StartTaskRequest(BaseModel):
    task: str


class FollowUpTaskRequest(BaseModel):
    session_id: str
    task: str


class StartTaskResponse(BaseModel):
    session_id: str


class BeginTask(BaseModel):
    session_id: str


class InteractRequest(BaseModel):
    session_id: str
    message: str


class TokenRegisterRequest(BaseModel):
    session_id: str
    push_token: str
