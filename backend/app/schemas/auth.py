from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=128)
    invite_code: str = Field(min_length=16, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    is_disabled: bool
    file_limit: int
    storage_limit_bytes: int
    created_at: datetime.datetime


class SessionResponse(BaseModel):
    user: UserResponse
    access_expires_at: datetime.datetime
    refresh_expires_at: datetime.datetime


class CreateInviteRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_at: datetime.datetime | None = None


class InviteResponse(BaseModel):
    id: int
    code: str
    max_uses: int
    use_count: int
    expires_at: datetime.datetime
    disabled_at: datetime.datetime | None


class InviteUpdateRequest(BaseModel):
    disabled: bool


class UserUpdateRequest(BaseModel):
    disabled: bool | None = None
    file_limit: int | None = Field(default=None, ge=0)
    storage_limit_bytes: int | None = Field(default=None, ge=0)
