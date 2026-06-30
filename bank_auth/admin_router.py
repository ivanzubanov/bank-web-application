from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bank_auth.database import get_db
from bank_auth.dependencies import RoleChecker
from bank_auth.schemas import UserRole, UserRoleUpdateSchema
from bank_auth.services import update_user_role

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