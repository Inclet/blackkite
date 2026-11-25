"""Magic links, invites and sessions. Callers commit."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import sqlalchemy as sa
from sqlalchemy.orm import Session as DB

from blackkite.auth.tokens import hash_token, new_token
from blackkite.config import Settings
from blackkite.db.models import Invite, LoginToken, Session, User
from blackkite.delivery.mail import Mail


def now() -> datetime:
    return datetime.now(UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def confirm_url(settings: Settings, token: str) -> str:
    """The emailed link: a web page that asks the person to continue (decision 17).

    Opening it spends nothing, so mail scanners that fetch links cannot use the
    token up. Only the page's POST /auth/verify spends it.

    The token rides in the URL fragment, which browsers never send to a server,
    so it stays out of access logs and Referer headers.
    """
    return f"{settings.web_base_url.rstrip('/')}/auth/confirm#{urlencode({'token': token})}"


def find_user_by_email(db: DB, email: str) -> User | None:
    return db.scalar(
        sa.select(User).where(sa.func.lower(User.email) == normalise_email(email))
    )


def find_pending_invite(db: DB, email: str) -> Invite | None:
    return db.scalar(
        sa.select(Invite)
        .where(
            sa.func.lower(Invite.email) == normalise_email(email),
            Invite.accepted_at.is_(None),
            Invite.expires_at > now(),
        )
        .order_by(Invite.created_at.desc())
        .limit(1)
    )


# --- Magic links ------------------------------------------------------------------


def issue_login_link(db: DB, settings: Settings, email: str) -> Mail | None:
    """Create a login token if this address may sign in; return the mail to send.

    Returns None for unknown or deactivated addresses. The HTTP response must not
    differ between the two outcomes.
    """
    email = normalise_email(email)
    user = find_user_by_email(db, email)
    token = new_token()
    expires = now() + timedelta(minutes=settings.login_token_minutes)
    if user is not None:
        if user.status != "active":
            return None
        db.add(
            LoginToken(
                token_hash=hash_token(token), user_id=user.id, expires_at=expires
            )
        )
    else:
        invite = find_pending_invite(db, email)
        if invite is None:
            return None
        db.add(
            LoginToken(
                token_hash=hash_token(token), invite_id=invite.id, expires_at=expires
            )
        )
    db.flush()
    return Mail(
        to=email,
        subject="Your Blackkite sign-in link",
        text=(
            "Use this link to sign in to Blackkite. It works once and expires in "
            f"{settings.login_token_minutes} minutes.\n\n{confirm_url(settings, token)}\n\n"
            "If you did not ask for it, ignore this email."
        ),
    )


def _accept_invite(db: DB, invite_id: uuid.UUID, via_login_token: bool) -> User | None:
    """Mark the invite accepted (atomically, once) and return the member it creates.

    via_login_token: the invite is being redeemed through a magic link the invitee
    requested (already single use and checked for expiry when issued). Otherwise the
    caller is spending the invite's own token, which must be unexpired and unused.
    """
    conds = [Invite.id == invite_id, Invite.accepted_at.is_(None)]
    if not via_login_token:
        conds.append(Invite.expires_at > now())
    email = db.scalar(
        sa.update(Invite)
        .where(*conds)
        .values(accepted_at=now())
        .returning(Invite.email)
    )
    if email is None:
        if not via_login_token:
            return None  # invite token already spent, or expired
        # A second requested link for an invite accepted meanwhile: sign in the user it made.
        invite = db.get(Invite, invite_id)
        if invite is None or invite.accepted_user_id is None:
            return None
        user = db.get(User, invite.accepted_user_id)
        return user if user is not None and user.status == "active" else None
    user = find_user_by_email(db, email)
    if user is None:
        user = User(email=normalise_email(email), role="member", status="active")
        db.add(user)
        db.flush()
    elif user.status != "active":
        return None
    db.execute(
        sa.update(Invite).where(Invite.id == invite_id).values(accepted_user_id=user.id)
    )
    return user


def consume_token(db: DB, token: str) -> User | None:
    """Spend a login or invite token. Returns the user to sign in, or None."""
    h = hash_token(token)
    row = db.execute(
        sa.update(LoginToken)
        .where(
            LoginToken.token_hash == h,
            LoginToken.used_at.is_(None),
            LoginToken.expires_at > now(),
        )
        .values(used_at=now())
        .returning(LoginToken.user_id, LoginToken.invite_id)
    ).first()
    if row is not None:
        if row.user_id is not None:
            user = db.get(User, row.user_id)
            return user if user is not None and user.status == "active" else None
        return _accept_invite(db, row.invite_id, via_login_token=True)
    # Not a login token: maybe the token from an invite email.
    invite_id = db.scalar(sa.select(Invite.id).where(Invite.token_hash == h))
    if invite_id is None:
        return None
    return _accept_invite(db, invite_id, via_login_token=False)


# --- Invites --------------------------------------------------------------------


@dataclass
class NewInvite:
    invite: Invite
    mail: Mail


class AlreadyUser(Exception):
    pass


def create_invite(
    db: DB, settings: Settings, email: str, invited_by: User
) -> NewInvite:
    email = normalise_email(email)
    if find_user_by_email(db, email) is not None:
        raise AlreadyUser(email)
    # Re-inviting replaces any earlier unaccepted invite for the address.
    db.execute(
        sa.delete(Invite).where(
            sa.func.lower(Invite.email) == email, Invite.accepted_at.is_(None)
        )
    )
    token = new_token()
    invite = Invite(
        email=email,
        invited_by=invited_by.id,
        token_hash=hash_token(token),
        expires_at=now() + timedelta(days=settings.invite_days),
    )
    db.add(invite)
    db.flush()
    mail = Mail(
        to=email,
        subject="You are invited to Blackkite",
        text=(
            "You have been invited to Blackkite, a tool that finds opportunities in Rwanda.\n\n"
            f"Accept the invitation and sign in (link works once, expires in "
            f"{settings.invite_days} days):\n\n{confirm_url(settings, token)}\n\n"
            "If the link has expired, request a sign-in link with this address while "
            "the invitation is still open, or ask for a new invitation."
        ),
    )
    return NewInvite(invite=invite, mail=mail)


def invite_status(invite: Invite) -> str:
    if invite.accepted_at is not None:
        return "accepted"
    if invite.expires_at <= now():
        return "expired"
    return "pending"


# --- Sessions -------------------------------------------------------------------


def create_session(db: DB, settings: Settings, user: User) -> str:
    """Store a new session for `user`; return the raw id for the cookie."""
    raw = new_token()
    db.add(
        Session(
            token_hash=hash_token(raw),
            user_id=user.id,
            expires_at=now() + timedelta(days=settings.session_days),
        )
    )
    db.flush()
    return raw


def session_user(db: DB, raw: str) -> tuple[Session, User] | None:
    row = db.execute(
        sa.select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(
            Session.token_hash == hash_token(raw),
            Session.expires_at > now(),
            User.status == "active",
        )
    ).first()
    return (row[0], row[1]) if row else None


def deactivate_user(db: DB, user: User) -> None:
    user.status = "deactivated"
    db.execute(sa.delete(Session).where(Session.user_id == user.id))
    db.execute(
        sa.delete(LoginToken).where(
            LoginToken.user_id == user.id, LoginToken.used_at.is_(None)
        )
    )
