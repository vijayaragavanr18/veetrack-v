"""Data transfer objects for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    workspace_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    workspace_id: str


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    workspace_id: str
