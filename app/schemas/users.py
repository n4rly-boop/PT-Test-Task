from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)


class UserUpdate(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: int
    external_id: str
    created_at: datetime
    updated_at: datetime