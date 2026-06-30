from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bank_auth.database import get_db
from bank_auth.dependencies import RoleChecker
from bank_auth.schemas import (
    UserRole, UserRoleUpdateSchema, MassMailSchema, UserBanSchema
)
from bank_auth.services import (
    update_user_role, mass_mail_users, ban_user
)

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)


@admin_router.patch(
    "/users/{user_id}/role",
    dependencies=[Depends(RoleChecker([UserRole.ADMIN]))]
)
async def change_user_role_endpoint(
    user_id: int,
    data: UserRoleUpdateSchema,
    db: AsyncSession = Depends(get_db)
):
    return await update_user_role(user_id, data, db)


@admin_router.post(
    "/mass-mail",
    dependencies=[Depends(RoleChecker([UserRole.ADMIN]))]
)
async def mass_mail_endpoint(
    data: MassMailSchema,
    db: AsyncSession = Depends(get_db)
):
    return await mass_mail_users(data, db)


@admin_router.patch(
    "/users/{user_id}/ban",
    dependencies=[Depends(RoleChecker([UserRole.ADMIN]))]
)
async def ban_user_endpoint(
    user_id: int,
    data: UserBanSchema,
    db: AsyncSession = Depends(get_db)
):
    return await ban_user(user_id, data, db)