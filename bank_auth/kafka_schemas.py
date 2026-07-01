from pydantic import BaseModel, EmailStr

class EmailVerificationEvent(BaseModel):
    event_id: str
    email: EmailStr
    otp_code: str
    username: str

class UserActivatedEvent(BaseModel):
    event_id: str
    user_id: int
    username: str
    email: EmailStr

class UserStatusChangedEvent(BaseModel):
    event_type: str = "UserStatusChanged"
    event_id: str
    user_id: int
    action: str
    old_role: str
    new_role: str
    is_banned: bool
    updated_at: str

class AdminMassMailEvent(BaseModel):
    event_id: str
    email: EmailStr
    username: str
    subject: str
    body: str
    dispatched_at: str