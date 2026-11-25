"""The caller's profiles (spec 7, contract section 2): list, create, edit, delete.
Editing bumps the version and requests a backfill (spec 5), run by the worker."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from blackkite.auth.deps import CurrentUser, DbDep, require_user
from blackkite.member import profiles as P

router = APIRouter(prefix="/profiles", dependencies=[Depends(require_user)])

NOT_FOUND = "Profile not found"


def _invalid(e: ValidationError) -> HTTPException:
    errors = e.errors(include_url=False, include_context=False, include_input=False)
    for err in errors:
        err["loc"] = ("body", "data", *err["loc"])
    return HTTPException(422, jsonable_encoder(errors))


def _taken(name: str) -> HTTPException:
    return HTTPException(409, f"You already have a profile called {name!r}")


@router.get("", response_model=list[P.ProfileOut])
def list_profiles(user: CurrentUser, db: DbDep) -> list[P.ProfileOut]:
    return [P.profile_out(p) for p in P.list_profiles(db, user)]


@router.post("", status_code=201, response_model=P.ProfileOut)
def create_profile(body: P.ProfileIn, user: CurrentUser, db: DbDep) -> P.ProfileOut:
    try:
        p = P.create_profile(db, user, body)
    except ValidationError as e:
        raise _invalid(e) from None
    except P.NameTaken as e:
        raise _taken(str(e)) from None
    return P.profile_out(p)


@router.get("/{profile_id}", response_model=P.ProfileOut)
def get_profile(profile_id: uuid.UUID, user: CurrentUser, db: DbDep) -> P.ProfileOut:
    p = P.get_profile(db, user, profile_id)
    if p is None:
        raise HTTPException(404, NOT_FOUND)
    return P.profile_out(p)


@router.patch("/{profile_id}", response_model=P.ProfileOut)
def edit_profile(
    profile_id: uuid.UUID, body: P.ProfilePatch, user: CurrentUser, db: DbDep
) -> P.ProfileOut:
    p = P.get_profile(db, user, profile_id)
    if p is None:
        raise HTTPException(404, NOT_FOUND)
    try:
        p = P.update_profile(db, user, p, body)
    except ValidationError as e:
        raise _invalid(e) from None
    except P.NameTaken as e:
        raise _taken(str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return P.profile_out(p)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    p = P.get_profile(db, user, profile_id)
    if p is None:
        raise HTTPException(404, NOT_FOUND)
    P.delete_profile(db, p)
    return Response(status_code=204)
