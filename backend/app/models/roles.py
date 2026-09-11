from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class Role(StrEnum):
    """Shared Owner/Admin/Member role, used at both workspace and project scope."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# Role rank for "minimum role" permission checks — higher number = more privilege.
ROLE_RANK: dict[Role, int] = {
    Role.MEMBER: 0,
    Role.ADMIN: 1,
    Role.OWNER: 2,
}


def member_role_column() -> SAEnum:
    """
    A workspace_memberships/project_memberships `role` column backed by the single
    shared `member_role` Postgres enum type (same three values at both scopes).
    Returns a fresh SAEnum instance per call — safe to use in multiple mapped_column()
    calls since SQLAlchemy resolves the underlying Postgres type by name.
    """
    return SAEnum(
        Role,
        name="member_role",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )
