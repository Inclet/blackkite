"""Admin endpoints: invites and users (spec 3). Every route requires an admin."""

import uuid
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from blackkite.auth import service
from blackkite.auth.deps import AdminUser, DbDep, SettingsDep, require_admin
from blackkite.db.models import Invite, User
from blackkite.delivery.mail import MailTransport, get_mail_transport
from blackkite.routes.schemas import AdminUserOut, EmailIn, InviteOut, UserPatch

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _invite_out(i: Invite) -> InviteOut:
    return InviteOut(
        id=i.id,
        email=i.email,
        invited_by=i.invited_by,
        created_at=i.created_at,
        expires_at=i.expires_at,
        accepted_at=i.accepted_at,
        status=service.invite_status(i),
    )


@router.post("/invites", status_code=201, response_model=InviteOut)
def create_invite(
    body: EmailIn,
    admin: AdminUser,
    db: DbDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    mailer: Annotated[MailTransport, Depends(get_mail_transport)],
) -> InviteOut:
    try:
        new = service.create_invite(db, settings, body.email, admin)
    except service.AlreadyUser:
        raise HTTPException(409, "That address already has an account") from None
    db.commit()
    db.refresh(new.invite)
    background.add_task(mailer.send, new.mail)
    return _invite_out(new.invite)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    db: DbDep,
    status: Annotated[Literal["pending", "expired", "accepted"] | None, Query()] = None,
) -> list[InviteOut]:
    """Newest first, each with its status (pending, expired, accepted)."""
    rows = db.scalars(sa.select(Invite).order_by(Invite.created_at.desc())).all()
    out = [_invite_out(i) for i in rows]
    return [i for i in out if status is None or i.status == status]


@router.delete("/invites/{invite_id}", status_code=204)
def delete_invite(invite_id: uuid.UUID, db: DbDep) -> Response:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(409, "Invite already accepted; deactivate the user instead")
    db.delete(invite)
    db.commit()
    return Response(status_code=204)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: DbDep) -> list[AdminUserOut]:
    """Every account, oldest first: role, status, created, last sign-in."""
    rows = db.scalars(sa.select(User).order_by(User.created_at)).all()
    return [AdminUserOut.model_validate(u) for u in rows]


@router.post("/users/{user_id}/deactivate", response_model=AdminUserOut)
def deactivate(user_id: uuid.UUID, admin: AdminUser, db: DbDep) -> AdminUserOut:
    if user_id == admin.id:
        raise HTTPException(400, "You cannot deactivate yourself")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "admin" and user.status == "active":
        _keep_an_admin(db, admin, user)
    service.deactivate_user(db, user)
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user)


def _keep_an_admin(db, caller: User, losing: User) -> None:
    """``losing`` is about to stop being an active admin. Lock every active admin
    row so two admins acting on each other at once cannot leave none, then
    check the caller is still one of them and someone else remains."""
    admins = set(
        db.scalars(
            sa.select(User.id)
            .where(User.role == "admin", User.status == "active")
            .with_for_update()
        )
    )
    if caller.id not in admins:
        raise HTTPException(403, "Admins only")
    if not admins - {losing.id}:
        raise HTTPException(409, "There must be at least one active admin")


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def edit_user(
    user_id: uuid.UUID, body: UserPatch, admin: AdminUser, db: DbDep
) -> AdminUserOut:
    """Change a user's role (member <-> admin). Not your own, and never the last
    active admin. Spec 3 lists invite and deactivate only; a role change is
    what lets the first admin make a second one."""
    if user_id == admin.id:
        raise HTTPException(400, "You cannot change your own role")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.role is not None and body.role != user.role:
        if user.role == "admin" and user.status == "active":
            _keep_an_admin(db, admin, user)
        user.role = body.role
        db.commit()
        db.refresh(user)
    return AdminUserOut.model_validate(user)
