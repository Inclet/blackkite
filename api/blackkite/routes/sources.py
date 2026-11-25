"""Source routes. Members (mounted under /api): sources page, mute, suggest (spec 3,
4.4). Admins (/api/admin): the registry, status changes, run history, test runs,
suggestion review (spec 4.3)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError

from blackkite.auth.deps import (
    AdminUser,
    CurrentUser,
    DbDep,
    SettingsDep,
    require_admin,
)
from blackkite.collectors.http import FetchClient, make_fetch_client
from blackkite.collectors.registry import validate_config
from blackkite.db.models import Source, SourceRun, SourceSuggestion, User
from blackkite.pipeline.visibility import refresh_verification_for_source
from blackkite.routes.source_schemas import (
    ORIGINAL_SEARCH_QUERY,
    AdminSuggestionOut,
    CollectorTypeOut,
    MemberSourceOut,
    PreviewIn,
    PreviewItemOut,
    PreviewOut,
    PromotionGateOut,
    RunOut,
    RunPage,
    SourceDetailOut,
    SourceIn,
    SourceOut,
    SourcePatch,
    StatusChangeOut,
    StatusIn,
    SuggestionIn,
    SuggestionOut,
)
from blackkite.scoring.backfill import request_user_rescore
from blackkite.sources import service
from blackkite.sources.collector_types import collector_type_schemas
from blackkite.sources.testrun import (
    PreviewResult,
    TestRunBusy,
    TestRunGate,
    preview_source,
    transient_source,
)

log = logging.getLogger("blackkite.sources")

member_router = APIRouter()
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def get_preview_client_factory(settings: SettingsDep) -> Callable[[], FetchClient]:
    """A fresh client per test run, with an in-memory cache (writes nothing)."""
    return lambda: make_fetch_client(settings)


PreviewClients = Annotated[
    Callable[[], FetchClient], Depends(get_preview_client_factory)
]


def get_test_run_gate(request: Request) -> TestRunGate:
    return request.app.state.test_run_gate


TestRunGateDep = Annotated[TestRunGate, Depends(get_test_run_gate)]


def _too_many_suggestions(limit: int) -> str:
    return f"You can suggest up to {limit} sources a day. Please try again tomorrow."


# --- members -------------------------------------------------------------------------


@member_router.get("/sources", response_model=list[MemberSourceOut])
def list_sources(user: CurrentUser, db: DbDep) -> list[MemberSourceOut]:
    """Active sources only; testing/paused/retired ones are not shown to members."""
    sources = service.member_sources(db)
    stats = service.source_stats(db, [s.id for s in sources])
    muted = service.muted_ids(db, user)
    return [
        MemberSourceOut(
            id=s.id,
            name=s.name,
            home_url=s.home_url,
            publisher=s.publisher,
            kind=s.kind,
            streams=s.streams,
            last_success_at=stats[s.id].last_success_at,
            items_30d=stats[s.id].items_30d,
            health=stats[s.id].health,
            muted=s.id in muted,
        )
        for s in sources
    ]


@member_router.post("/sources/{source_id}/mute", status_code=204)
def mute_source(source_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    source = db.get(Source, source_id)
    if source is None or source.status != "active":
        raise HTTPException(404, "Source not found")
    service.mute(db, user, source)
    request_user_rescore(db, user.id, datetime.now(UTC))
    db.commit()
    return Response(status_code=204)


@member_router.delete("/sources/{source_id}/mute", status_code=204)
def unmute_source(source_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    # Works whatever the source's status now, so a mute is never stuck.
    service.unmute(db, user, source_id)
    # Rows stay (created_at kept); the feed shows them unscored until the worker's
    # next tick rescores them.
    request_user_rescore(db, user.id, datetime.now(UTC), immediate=True)
    db.commit()
    return Response(status_code=204)


@member_router.post(
    "/source-suggestions", status_code=201, response_model=SuggestionOut
)
def suggest_source(
    body: SuggestionIn, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> SuggestionOut:
    # Per user, any 24 hours. The user's row is locked so two requests at once
    # cannot both take the last place.
    db.execute(sa.select(User.id).where(User.id == user.id).with_for_update())
    recent = db.scalar(
        sa.select(sa.func.count())
        .select_from(SourceSuggestion)
        .where(
            SourceSuggestion.user_id == user.id,
            SourceSuggestion.created_at > sa.func.now() - sa.text("interval '1 day'"),
        )
    )
    limit = settings.suggestions_per_user_per_day
    if recent >= limit:
        db.rollback()
        raise HTTPException(429, _too_many_suggestions(limit))
    s = SourceSuggestion(user_id=user.id, url=body.url, note=body.note)
    db.add(s)
    db.commit()
    db.refresh(s)
    return SuggestionOut.model_validate(s)


@member_router.get("/source-suggestions", response_model=list[SuggestionOut])
def my_suggestions(user: CurrentUser, db: DbDep) -> list[SuggestionOut]:
    rows = db.scalars(
        sa.select(SourceSuggestion)
        .where(SourceSuggestion.user_id == user.id)
        .order_by(SourceSuggestion.created_at.desc())
    )
    return [SuggestionOut.model_validate(r) for r in rows]


# --- admin: registry -------------------------------------------------------------------


def _source_out(db, settings, sources: list[Source]) -> list[SourceOut]:
    stats = service.source_stats(db, [s.id for s in sources])
    return [
        SourceOut(
            id=s.id,
            name=s.name,
            home_url=s.home_url,
            publisher=s.publisher,
            streams=s.streams,
            kind=s.kind,
            collector_type=s.collector_type,
            config=s.config,
            schedule=s.schedule,
            effective_schedule=s.schedule or settings.default_source_schedule,
            rate_limit=s.rate_limit,
            access_note=s.access_note,
            status=s.status,
            added_by=s.added_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
            config_changed_at=s.config_changed_at,
            health=stats[s.id].health,
            last_success_at=stats[s.id].last_success_at,
            last_run_at=stats[s.id].last_run_at,
            items_30d=stats[s.id].items_30d,
            promotion_runs=service.qualifying_runs(db, s),
        )
        for s in sources
    ]


def _get_source(db, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    return source


@admin_router.get("/sources", response_model=list[SourceOut])
def admin_list_sources(
    db: DbDep,
    settings: SettingsDep,
    status: Annotated[
        Literal["suggested", "testing", "active", "paused", "retired"] | None, Query()
    ] = None,
) -> list[SourceOut]:
    q = sa.select(Source).order_by(Source.name)
    if status:
        q = q.where(Source.status == status)
    return _source_out(db, settings, list(db.scalars(q)))


@admin_router.post("/sources", status_code=201, response_model=SourceDetailOut)
def create_source(
    body: SourceIn, admin: AdminUser, db: DbDep, settings: SettingsDep
) -> SourceDetailOut:
    suggestion = None
    if body.suggestion_id is not None:
        suggestion = db.get(SourceSuggestion, body.suggestion_id)
        if suggestion is None:
            raise HTTPException(404, "Suggestion not found")
        if suggestion.status != "accepted" or suggestion.source_id is not None:
            raise HTTPException(409, "Suggestion must be accepted and not yet used")
    # Spec 4.3 step 3: a new source is saved as testing.
    source = Source(
        **body.model_dump(exclude={"suggestion_id"}),
        status="testing",
        added_by=admin.id,
    )
    db.add(source)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A source with that name already exists") from None
    service.record_status(db, source, None, admin, "created")
    if suggestion is not None:
        suggestion.source_id = source.id
    db.commit()
    db.refresh(source)
    return _detail_out(db, settings, source)


def _detail_out(db, settings, source: Source) -> SourceDetailOut:
    base = _source_out(db, settings, [source])[0]
    return SourceDetailOut(
        **dict(base),
        promotion_gate=PromotionGateOut(**asdict(service.promotion_gate(db, source))),
        status_history=[
            StatusChangeOut.model_validate(c)
            for c in service.status_history(db, source)
        ],
    )


@admin_router.get("/sources/{source_id}", response_model=SourceDetailOut)
def get_source(
    source_id: uuid.UUID, db: DbDep, settings: SettingsDep
) -> SourceDetailOut:
    """The full record for the admin source screen (spec 4.4): config,
    access_note, run stats, promotion-gate progress and status history."""
    return _detail_out(db, settings, _get_source(db, source_id))


def _normalised_config(source: Source) -> dict | None:
    """The stored config as validation would store it (seeded or older rows may
    hold it unnormalised), or None when it no longer validates."""
    try:
        return validate_config(source.collector_type, source.config)
    except (ValueError, TypeError):
        return None


@admin_router.patch("/sources/{source_id}", response_model=SourceDetailOut)
def edit_source(
    source_id: uuid.UUID,
    body: SourcePatch,
    admin: AdminUser,
    db: DbDep,
    settings: SettingsDep,
) -> SourceDetailOut:
    """Edit a source. Changing ``collector_type`` or ``config`` of an ``active``
    source sends it back to ``testing`` in the same request (owner's ruling,
    2026-11-25): promotion then needs two good runs of the new config again, and
    its items stay visible to members only through other active/paused sources.
    Other fields never change the status."""
    source = _get_source(db, source_id)
    changes = body.model_dump(exclude_unset=True)
    config_changed = False
    required = {"name", "home_url", "streams", "kind", "collector_type", "config"}
    if nulls := sorted(k for k in required if k in changes and changes[k] is None):
        raise HTTPException(422, f"cannot clear {', '.join(nulls)}")
    if "collector_type" in changes or "config" in changes:
        ctype = changes.get("collector_type", source.collector_type)
        config = changes.get("config", source.config)
        try:
            validated = validate_config(ctype, config)
        except (ValueError, TypeError) as e:
            raise HTTPException(422, f"config: {e}") from None
        if ctype != source.collector_type or validated != _normalised_config(source):
            source.config_changed_at = service.now_utc()
            config_changed = True
        changes["config"] = validated
    kind = changes.get("kind", source.kind)
    ctype = changes.get("collector_type", source.collector_type)
    if kind == "original" and ctype == "search_query":
        raise HTTPException(422, ORIGINAL_SEARCH_QUERY)
    kind_changed = "kind" in changes and changes["kind"] != source.kind
    for k, v in changes.items():
        setattr(source, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A source with that name already exists") from None
    if config_changed and source.status == "active":
        # Also recomputes verification for the source's items.
        service.change_status(db, source, "testing", admin, "config changed")
    elif kind_changed:
        refresh_verification_for_source(db, source.id)
    db.commit()
    db.refresh(source)
    return _detail_out(db, settings, source)


@admin_router.post("/sources/{source_id}/status", response_model=SourceDetailOut)
def set_status(
    source_id: uuid.UUID,
    body: StatusIn,
    admin: AdminUser,
    db: DbDep,
    settings: SettingsDep,
) -> SourceDetailOut:
    """Promote (active), pause, retire, or send back to testing. See the graph in
    sources/service.py."""
    source = _get_source(db, source_id)
    try:
        service.change_status(db, source, body.status, admin)
    except service.TransitionError as e:
        raise HTTPException(409, str(e)) from None
    db.commit()
    db.refresh(source)
    return _detail_out(db, settings, source)


@admin_router.get("/sources/{source_id}/runs", response_model=RunPage)
def source_runs(
    source_id: uuid.UUID,
    db: DbDep,
    status: Annotated[Literal["running", "succeeded", "failed"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunPage:
    """Run history, newest first, with each failed run's error text (the error
    log is ``status=failed``)."""
    _get_source(db, source_id)
    where = [SourceRun.source_id == source_id]
    if status:
        where.append(SourceRun.status == status)
    total = db.scalar(sa.select(sa.func.count()).select_from(SourceRun).where(*where))
    rows = db.scalars(
        sa.select(SourceRun)
        .where(*where)
        .order_by(SourceRun.started_at.desc(), SourceRun.id)
        .limit(limit)
        .offset(offset)
    )
    return RunPage(total=total or 0, items=[RunOut.model_validate(r) for r in rows])


@admin_router.get("/collector-types", response_model=list[CollectorTypeOut])
def collector_types() -> list[CollectorTypeOut]:
    """Config fields per collector type, from the collectors' own config models,
    so the web editor renders forms without hard-coding them."""
    return [CollectorTypeOut.model_validate(t) for t in collector_type_schemas()]


# --- admin: test runs ------------------------------------------------------------------


def _preview_out(r: PreviewResult) -> PreviewOut:
    return PreviewOut(
        ok=r.ok,
        error=r.error,
        items=[
            PreviewItemOut(
                **{
                    k: v
                    for k, v in asdict(i).items()
                    if k not in ("source_id", "fetched_at")
                }
            )
            for i in r.items
        ],
        total_parsed=r.total_parsed,
        requests_made=r.requests_made,
        elapsed_seconds=r.elapsed_seconds,
    )


@admin_router.post("/sources/test-run", response_model=PreviewOut)
def test_run_unsaved(
    body: PreviewIn,
    settings: SettingsDep,
    clients: PreviewClients,
    gate: TestRunGateDep,
) -> PreviewOut:
    """Fetch once with an unsaved config; nothing is written anywhere."""
    src = transient_source(
        home_url=body.home_url or "",
        streams=body.streams,
        kind="publisher",
        collector_type=body.collector_type,
        config=body.config,
        rate_limit=body.rate_limit,
        status="testing",
    )
    try:
        with gate.slot():
            result = preview_source(
                src, clients(), brave_api_key=settings.brave_api_key
            )
    except TestRunBusy as e:
        raise HTTPException(429, str(e)) from None
    return _preview_out(result)


@admin_router.post("/sources/{source_id}/test-run", response_model=PreviewOut)
def test_run_saved(
    source_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    clients: PreviewClients,
    gate: TestRunGateDep,
) -> PreviewOut:
    """Fetch once with the saved config; no source_run row, no catalogue writes."""
    source = _get_source(db, source_id)
    db.expunge(source)  # nothing the collector does can be flushed back
    db.rollback()  # no transaction held open while the fetch runs
    try:
        with gate.slot():
            result = preview_source(
                source, clients(), brave_api_key=settings.brave_api_key
            )
    except TestRunBusy as e:
        raise HTTPException(429, str(e)) from None
    return _preview_out(result)


# --- admin: suggestions ----------------------------------------------------------------


@admin_router.get("/source-suggestions", response_model=list[AdminSuggestionOut])
def list_suggestions(
    db: DbDep,
    status: Annotated[
        Literal["suggested", "accepted", "rejected"] | None, Query()
    ] = "suggested",
) -> list[AdminSuggestionOut]:
    q = sa.select(SourceSuggestion).order_by(SourceSuggestion.created_at)
    if status:
        q = q.where(SourceSuggestion.status == status)
    return [AdminSuggestionOut.model_validate(r) for r in db.scalars(q)]


def _review(suggestion_id: uuid.UUID, admin, db, decision: str) -> AdminSuggestionOut:
    s = db.get(SourceSuggestion, suggestion_id)
    if s is None:
        raise HTTPException(404, "Suggestion not found")
    try:
        service.review_suggestion(db, s, admin, decision)
    except service.TransitionError as e:
        raise HTTPException(409, str(e)) from None
    db.commit()
    db.refresh(s)
    return AdminSuggestionOut.model_validate(s)


@admin_router.post(
    "/source-suggestions/{suggestion_id}/accept", response_model=AdminSuggestionOut
)
def accept_suggestion(
    suggestion_id: uuid.UUID, admin: AdminUser, db: DbDep
) -> AdminSuggestionOut:
    """Marks it accepted. The admin then creates the source (POST /api/admin/sources
    with suggestion_id), which links the two."""
    return _review(suggestion_id, admin, db, "accepted")


@admin_router.post(
    "/source-suggestions/{suggestion_id}/reject", response_model=AdminSuggestionOut
)
def reject_suggestion(
    suggestion_id: uuid.UUID, admin: AdminUser, db: DbDep
) -> AdminSuggestionOut:
    return _review(suggestion_id, admin, db, "rejected")
