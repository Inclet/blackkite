"""Benchmarks and procurement plans (spec 8 "Benchmarks", spec 2.6;
docs/api-contract.md section 6). Member routes under ``/api``; every one needs a
session. Benchmarks hold no per-user data; plans read only the caller's own
active profiles."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from blackkite.auth.deps import CurrentUser, DbDep, SettingsDep, require_user
from blackkite.llm.embeddings import Embedder
from blackkite.member import procurement as PR
from blackkite.pipeline import categories
from blackkite.routes.member import Now
from blackkite.scoring.settings import get_scoring_settings

router = APIRouter(dependencies=[Depends(require_user)])

BACKWARDS = "The end date must be on or after the start date."
UNKNOWN_CATEGORY = "There is no benchmark category with that name."
NO_PROFILE = "Profile not found"
Currency = Annotated[str, Query(pattern=r"^[A-Z]{3}$")]


def _window(first: date | None, last: date | None) -> None:
    if first is not None and last is not None and last < first:
        raise HTTPException(422, BACKWARDS)


@router.get("/benchmarks", response_model=PR.BenchmarksOut)
def get_benchmarks(
    db: DbDep,
    category: str | None = None,
    entity: Annotated[str | None, Query(max_length=300)] = None,
    first: Annotated[date | None, Query(alias="from")] = None,
    last: Annotated[date | None, Query(alias="to")] = None,
) -> PR.BenchmarksOut:
    _window(first, last)
    if category is not None and category not in categories.KEYS:
        raise HTTPException(422, UNKNOWN_CATEGORY)
    return PR.benchmarks(
        db, category=category, entity=entity, date_from=first, date_to=last
    )


@router.get("/benchmarks/{category}", response_model=PR.BenchmarkAwardsOut)
def get_benchmark_awards(
    category: str,
    db: DbDep,
    currency: Currency | None = None,
    entity: Annotated[str | None, Query(max_length=300)] = None,
    first: Annotated[date | None, Query(alias="from")] = None,
    last: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PR.BenchmarkAwardsOut:
    if category not in categories.KEYS:
        raise HTTPException(404, UNKNOWN_CATEGORY)
    _window(first, last)
    return PR.benchmark_awards(
        db,
        category,
        entity=entity,
        date_from=first,
        date_to=last,
        currency=currency,
        limit=limit,
        offset=offset,
    )


def get_plan_embedder(settings: SettingsDep) -> Embedder | None:
    """The embedder for the plan match, or None without VOYAGE_API_KEY. Called
    only when some plan has an embedding (one call per profile per process)."""
    from blackkite.llm.factory import embedder
    from blackkite.pipeline.settings import get_pipeline_settings

    return embedder(settings, get_pipeline_settings())


@router.get("/plans", response_model=PR.PlansOut)
def get_plans(
    user: CurrentUser,
    db: DbDep,
    now: Now,
    embedder: Annotated[Embedder | None, Depends(get_plan_embedder)],
    window: Literal["3", "6", "12"] = "12",
    profile: uuid.UUID | None = None,
) -> PR.PlansOut:
    out = PR.plans_for(
        db,
        user.id,
        now=now,
        window=int(window),
        profile_id=profile,
        settings=get_scoring_settings(),
        embedder=embedder,
    )
    if out is None:
        raise HTTPException(404, NO_PROFILE)
    return out
