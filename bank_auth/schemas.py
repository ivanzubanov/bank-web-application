import re
from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

PHONE_REGEX = re.compile(r"^\+\d{11,15}$")

class UserRegisterSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    email: EmailStr
    phone: str
    birth_date: date

    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    patronymic: Optional[str] = Field(None, max_length=50)

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, value: str) -> str:
        cleaned = value.replace(" ", "")
        if not PHONE_REGEX.match(cleaned):
            raise ValueError("Номер телефона должен быть в международном формате (например, +79991234567)")
        return cleaned

    @field_validator("birth_date")
    @classmethod
    def validate_age(cls, value: date) -> date:
        today = date.today()
        try:
            max_birth_date = today.replace(year=today.year - 14)
        except ValueError:
            # if today is February 29 of a leap year,
            # and 14 years ago February had 28 days
            max_birth_date = today.replace(year=today.year - 14, day=28)
        if value > max_birth_date:
            raise ValueError("Регистрация доступна только с 14 лет")
        return value

class UserVerifySchema(BaseModel):
    user_id: int
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

class OTPResendSchema(BaseModel):
    user_id: int

class UserLoginSchema(BaseModel):
    username_or_email: str
    password: str

class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

    model_config = ConfigDict(from_attributes=True)