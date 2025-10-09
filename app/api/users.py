from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db_models
from app.db.database import get_db
from app.schemas.users import UserCreate, UserUpdate, UserResponse


router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(db_models.User).where(db_models.User.external_id == payload.external_id)
    )
    existing_user = existing.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=409, detail="User with this external_id already exists")
    user = db_models.User(external_id=payload.external_id)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(db_models.User)
        .order_by(db_models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    users = result.scalars().all()
    return [
        UserResponse(id=u.id, external_id=u.external_id, created_at=u.created_at, updated_at=u.updated_at) for u in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Check unique constraint on external_id
    conflict = await db.execute(
        select(db_models.User).where(
            db_models.User.external_id == payload.external_id,
            db_models.User.id != user_id,
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="external_id already in use")
    user.external_id = payload.external_id
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"ok": True}
