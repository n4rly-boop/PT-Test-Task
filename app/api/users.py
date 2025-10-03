from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import models as db_models
from app.schemas.users import UserCreate, UserUpdate, UserResponse


router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(db_models.User).filter(db_models.User.external_id == payload.external_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this external_id already exists")
    user = db_models.User(external_id=payload.external_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.get("/", response_model=List[UserResponse])
def list_users(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    users = (
        db.query(db_models.User)
        .order_by(db_models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [UserResponse(id=u.id, external_id=u.external_id, created_at=u.created_at, updated_at=u.updated_at) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Check unique constraint on external_id
    conflict = db.query(db_models.User).filter(
        db_models.User.external_id == payload.external_id,
        db_models.User.id != user_id,
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="external_id already in use")
    user.external_id = payload.external_id
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, external_id=user.external_id, created_at=user.created_at, updated_at=user.updated_at)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(db_models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


