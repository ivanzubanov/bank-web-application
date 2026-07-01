from pydantic import BaseModel, EmailStr, Field, AliasChoices

class BaseNotificationEvent(BaseModel):
    event_id: str = Field(validation_alias=AliasChoices("event_id", "transaction_id"))

class EmailVerificationEvent(BaseNotificationEvent):
    email: EmailStr
    otp_code: str
    username: str

class UserActivatedEvent(BaseNotificationEvent):
    user_id: int
    username: str
    email: EmailStr

class UserStatusChangedEvent(BaseNotificationEvent):
    event_type: str = "UserStatusChanged"
    user_id: int
    action: str
    old_role: str
    new_role: str
    is_banned: bool
    updated_at: str

class AdminMassMailEvent(BaseNotificationEvent):
    email: EmailStr
    username: str
    subject: str
    body: str
    dispatched_at: str