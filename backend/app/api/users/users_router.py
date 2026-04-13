from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import create_access_token, get_current_admin
from app.db.deps import get_db
import app.api.users.users_dto as dto
import app.api.users.users_crud as crud

router = APIRouter()


@router.post("/login", response_model=dto.TokenResponseDTO, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    if form.username != settings.admin_username or form.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": form.username})
    return dto.TokenResponseDTO(access_token=token)


@router.get("/", response_model=list[dto.UserResponseDTO], tags=["users"])
def get_all_users(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    return crud.get_all_users(db)


@router.get("/pending", response_model=list[dto.UserResponseDTO], tags=["users"])
def get_pending_users(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    return crud.get_users_by_status("pending", db)


@router.get("/approved", response_model=list[dto.UserResponseDTO], tags=["users"])
def get_approved_users(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    return crud.get_users_by_status("approved", db)


@router.get("/{user_id}", response_model=dto.UserResponseDTO, tags=["users"])
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    user = crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=dto.UserResponseDTO, tags=["users"])
def update_user_status(
    user_id: int,
    body: dto.StatusUpdateDTO,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    user = crud.update_user_status(user_id, body.status, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{user_id}", tags=["users"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    if not crud.delete_user(user_id, db):
        raise HTTPException(status_code=404, detail="User not found")
    return {"detail": "User deleted"}
