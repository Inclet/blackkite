"""Helpers for scoring tests. Synthetic notices only; the profiles are the spec 7.1
seed, loaded through ``bk bootstrap``'s loader for an example.com admin."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa

from blackkite.config import EMBEDDING_DIM
from blackkite.db.models import (
    Document,
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    UserOpportunityScore,
)
from blackkite.llm.client import LLMError
from blackkite.scoring.service import ScoringDeps
from blackkite.scoring.settings import ScoringSettings
from blackkite.seed.loader import bootstrap

ADMIN = "owner@example.com"


def now() -> datetime:
    return datetime.now(UTC)


def days(n: float) -> datetime:
    return now() + timedelta(days=n)


class FakeScoreLLM:
    """Returns ``reply`` (dict, or callable of the user message) and records calls."""

    model = "fake-score-1"

    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def structured(self, *, system, user, schema, tool_name, tool_description):
        self.calls.append({"system": system, "user": user, "tool": tool_name})
        if self.error:
            raise self.error
        reply = self.reply(user) if callable(self.reply) else self.reply
        if reply is None:
            raise LLMError("no reply configured")
        return schema.model_validate(reply)


def judgement(fit=0.85, elig=0.8, quote=None, reason=None, flags=()):
    """A reply builder whose quote is taken from the notice it is shown."""

    def build(user: str) -> dict[str, Any]:
        notice = user.split("<notice>\n", 1)[1]
        q = quote or notice.splitlines()[0][:80]
        return {
            "fit_confidence": fit,
            "eligibility_confidence": elig,
            "reason": reason or f'It asks for "{q}", which you offer.',
            "quote": q,
            "flags": list(flags),
        }

    return build


class BowEmbedder:
    """Deterministic bag-of-words vectors: similar words, similar vectors."""

    model = "fake-bow-1"

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        out = []
        for t in texts:
            v = [0.0] * EMBEDDING_DIM
            for tok in re.findall(r"[a-z]+", t.lower()):
                h = int(hashlib.sha1(tok.encode()).hexdigest(), 16)
                v[h % EMBEDDING_DIM] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


def settings(**kw) -> ScoringSettings:
    return ScoringSettings(_env_file=None, **kw)


def deps(llm=None, embedder=None, **kw) -> ScoringDeps:
    return ScoringDeps(llm=llm, embedder=embedder, settings=settings(**kw))


@pytest.fixture
def owner(db):
    r = bootstrap(db, ADMIN)
    db.commit()
    return r.user


@pytest.fixture
def profiles(db, owner) -> dict[str, Profile]:
    return {
        p.name: p
        for p in db.scalars(sa.select(Profile).where(Profile.user_id == owner.id))
    }


@pytest.fixture
def make_source(db):
    def make(
        kind="original",
        streams=("tender",),
        status="active",
        home_url="https://notices.example.org",
        name=None,
    ) -> Source:
        s = Source(
            name=name or f"{kind}-{uuid.uuid4().hex[:6]}",
            home_url=home_url,
            streams=list(streams),
            kind=kind,
            collector_type="html_list",
            status=status,
        )
        db.add(s)
        db.flush()
        return s

    return make


@pytest.fixture
def make_opp(db, make_source):
    def make(
        title: str,
        *,
        stream="tender",
        source: Source | None | bool = None,
        url: str | None = None,
        document: str | None = None,
        **fields,
    ) -> Opportunity:
        fields.setdefault("status", "open")
        fields.setdefault("verification", "verified_original")
        fields.setdefault("visibility", "public")
        fields.setdefault("evidence", {"_trust": "confirmed"})
        fields.setdefault("tags", [])
        fields.setdefault("deadline_at", days(30) if stream != "event" else None)
        if "value_amount" in fields and fields["value_amount"] is not None:
            fields["value_amount"] = Decimal(str(fields["value_amount"]))
        opp = Opportunity(stream=stream, title=title, needs_review=False, **fields)
        db.add(opp)
        db.flush()
        if source is not False and fields["visibility"] == "public":
            src = source or make_source(streams=(stream,))
            db.add(
                OpportunitySource(
                    opportunity_id=opp.id,
                    source_id=src.id,
                    url=url or f"{src.home_url}/n/{opp.id.hex[:8]}",
                    is_original=src.kind == "original",
                )
            )
        if document:
            db.add(
                Document(
                    opportunity_id=opp.id,
                    url=f"https://x.example/{opp.id}",
                    extracted_text=document,
                )
            )
        db.commit()
        return opp

    return make


def row(db, profile: Profile, opp: Opportunity) -> UserOpportunityScore:
    db.expire_all()
    return db.scalar(
        sa.select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == profile.user_id,
            UserOpportunityScore.profile_id == profile.id,
            UserOpportunityScore.opportunity_id == opp.id,
        )
    )


def flag_codes(r: UserOpportunityScore) -> list[str]:
    return [f["code"] for f in r.score_breakdown["flags"]]
