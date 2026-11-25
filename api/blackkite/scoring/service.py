"""Match and score (spec 5 stages 7-8, spec 7) and the triggers that run them.

Entry points (none commits; the caller owns the transaction):

* ``score_new_opportunities(session, since)``: the worker, after ingest. Every
  active user's active profiles against the items created or updated since
  ``since`` (open, closing soon or expired; expired ones become
  ``deadline_passed`` rows).
* ``backfill_profile(session, profile_id)``: a new or edited profile, over the
  currently open (open / closing_soon) items its owner can see.
* ``score_user(session, user_id)``: every active profile of one user (``bk score``).

Per pair: hard filters (rules.py) -> match (match.py) -> for shortlisted tender and
funding pairs one model judgement (judge.py) -> components -> fit word -> upsert of
one ``user_opportunity_score`` row per (user, opportunity, profile), breakdown
version 1 exactly as docs/api-contract.md section 1. ``user_opportunity`` (state)
is never read or written here.

Cost guard: at most ``max_llm_calls_per_run`` model calls per entry-point call. A
stored model judgement is reused, with the rule components recomputed, while the
profile has not changed since (``profile.updated_at``), the item's text has not
changed since (its creation, its last extraction, its newest document; for private
items its ``updated_at``), and the model and prompt version are the same. A row
whose content would not change is not rewritten.

No model key, a failed call, or the cap reached: a rules-only score, fit word
capped at "possible", reason "Scored without the model", ``model`` null in the
breakdown. The pair is judged on a later run.

Privacy (spec 6, 10): every query on a per-user table filters by the profile
owner's ``user_id``; candidates are limited by ``visibility.visible_to`` for that
user, so another user's private items are never scored for anyone else.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from blackkite.db.models import (
    Document,
    Opportunity,
    OpportunitySource,
    Profile,
    Source,
    User,
    UserOpportunityScore,
    UserSourceMute,
)
from blackkite.llm.client import LLMClient, LLMError
from blackkite.llm.embeddings import Embedder
from blackkite.pipeline.dates import kigali_date
from blackkite.pipeline.visibility import MEMBER_VISIBLE_SOURCE_STATUSES, visible_to
from blackkite.scoring import judge as judge_mod
from blackkite.scoring.fitword import fit_word
from blackkite.scoring.match import Match, match, profile_embedding
from blackkite.scoring.rules import (
    RULE_FLAG_ORDER,
    RULE_FLAGS,
    CarryingSource,
    Flag,
    check_rules,
    source_score,
    time_score,
    value_score,
)
from blackkite.scoring.settings import COMPONENTS, ScoringSettings, get_scoring_settings
from blackkite.scoring.text import notice_text

log = logging.getLogger("blackkite.scoring")

BREAKDOWN_VERSION = 1
NO_MODEL_REASON = "Scored without the model"
LLM_STREAMS = ("tender", "funding")
OPEN_STATUSES = ("open", "closing_soon")
NEW_STATUSES = ("open", "closing_soon", "expired")
# Statuses of carrying sources counted for an admin (admins also see testing items).
ADMIN_SOURCE_STATUSES = ("testing", "active", "paused")
_CHUNK = 500


# --- dependencies and run state --------------------------------------------------


@dataclass
class ScoringDeps:
    llm: LLMClient | None = None
    embedder: Embedder | None = None
    settings: ScoringSettings = field(default_factory=get_scoring_settings)


def scoring_llm(settings=None) -> LLMClient | None:
    """Real scoring client from ANTHROPIC_API_KEY and BK_MODEL_SCORE, or None."""
    from blackkite.config import get_settings

    settings = settings or get_settings()
    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value():
        return None
    from blackkite.llm.anthropic_client import AnthropicLLM
    from blackkite.pipeline.settings import get_pipeline_settings

    return AnthropicLLM(
        api_key=key.get_secret_value(),
        model=settings.model_score,
        max_tokens=1024,
        timeout_seconds=get_pipeline_settings().llm_timeout_seconds,
    )


def default_deps() -> ScoringDeps:
    """Real clients from the environment (either may be None). Tests replace this."""
    from blackkite.config import get_settings
    from blackkite.llm.factory import embedder
    from blackkite.pipeline.settings import get_pipeline_settings

    settings = get_settings()
    return ScoringDeps(
        llm=scoring_llm(settings),
        embedder=embedder(settings, get_pipeline_settings()),
        settings=get_scoring_settings(),
    )


@dataclass
class RunStats:
    pairs: int = 0
    written: int = 0
    unchanged: int = 0
    hard_filtered: int = 0
    shortlisted: int = 0
    llm_calls: int = 0
    llm_reused: int = 0
    llm_failed: int = 0
    rules_only: int = 0  # shortlisted model pairs scored without the model
    capped: int = 0  # of which because the per-run cap was reached
    profiles: int = 0

    def summary(self) -> str:
        return (
            f"profiles {self.profiles}, pairs {self.pairs}, written {self.written}, "
            f"unchanged {self.unchanged}, filtered {self.hard_filtered}, "
            f"shortlisted {self.shortlisted}, model calls {self.llm_calls}, "
            f"reused {self.llm_reused}, failed {self.llm_failed}, "
            f"rules-only {self.rules_only} (capped {self.capped})"
        )


@dataclass
class _Run:
    deps: ScoringDeps
    now: datetime
    stats: RunStats = field(default_factory=RunStats)
    llm_left: int = 0


# --- loading -------------------------------------------------------------------------


def _chunks(ids: Sequence[uuid.UUID]) -> Iterable[Sequence[uuid.UUID]]:
    for i in range(0, len(ids), _CHUNK):
        yield ids[i : i + _CHUNK]


def _carrying_sources(
    session: Session, user: User, opp_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[CarryingSource]]:
    statuses = (
        ADMIN_SOURCE_STATUSES if user.is_admin else MEMBER_VISIBLE_SOURCE_STATUSES
    )
    muted = sa.exists(
        sa.select(sa.literal(1)).where(
            UserSourceMute.user_id == user.id, UserSourceMute.source_id == Source.id
        )
    )
    out: dict[uuid.UUID, list[CarryingSource]] = defaultdict(list)
    for chunk in _chunks(opp_ids):
        rows = session.execute(
            sa.select(
                OpportunitySource.opportunity_id,
                Source.name,
                Source.kind,
                Source.home_url,
                OpportunitySource.url,
                OpportunitySource.is_original,
                muted.label("muted"),
            )
            .join(Source, Source.id == OpportunitySource.source_id)
            .where(
                OpportunitySource.opportunity_id.in_(chunk),
                Source.status.in_(statuses),
            )
        ).all()
        for oid, name, kind, home, url, orig, is_muted in rows:
            out[oid].append(
                CarryingSource(name, kind, home, url, bool(orig), bool(is_muted))
            )
    return out


def _documents(
    session: Session, opp_ids: Sequence[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[str]], dict[uuid.UUID, datetime]]:
    texts: dict[uuid.UUID, list[str]] = defaultdict(list)
    newest: dict[uuid.UUID, datetime] = {}
    for chunk in _chunks(opp_ids):
        rows = session.execute(
            sa.select(
                Document.opportunity_id, Document.extracted_text, Document.created_at
            )
            .where(Document.opportunity_id.in_(chunk))
            .order_by(Document.created_at)
        ).all()
        for oid, text, created in rows:
            if text:
                texts[oid].append(text)
            if oid not in newest or created > newest[oid]:
                newest[oid] = created
    return texts, newest


def _existing(
    session: Session, profile: Profile, opp_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, UserOpportunityScore]:
    out: dict[uuid.UUID, UserOpportunityScore] = {}
    for chunk in _chunks(opp_ids):
        for row in session.scalars(
            sa.select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == profile.user_id,
                UserOpportunityScore.profile_id == profile.id,
                UserOpportunityScore.opportunity_id.in_(chunk),
            )
        ):
            out[row.opportunity_id] = row
    return out


def _candidates(
    session: Session,
    user: User,
    vector: list[float] | None,
    *,
    statuses: Sequence[str],
    opportunity_ids: Sequence[uuid.UUID] | None,
) -> list[tuple[Opportunity, float | None]]:
    if vector is not None:
        sim = (1 - Opportunity.embedding.cosine_distance(vector)).label("sim")
    else:
        sim = sa.literal(None).label("sim")
    q = (
        sa.select(Opportunity, sim)
        .where(
            visible_to(user.id, is_admin=user.is_admin),
            Opportunity.status.in_(statuses),
        )
        .order_by(
            Opportunity.deadline_at.asc().nulls_last(),
            Opportunity.event_start.asc().nulls_last(),
            Opportunity.created_at,
        )
    )
    if opportunity_ids is not None:
        out: list[tuple[Opportunity, float | None]] = []
        for chunk in _chunks(list(opportunity_ids)):
            out.extend(
                (o, None if s is None else float(s))
                for o, s in session.execute(q.where(Opportunity.id.in_(chunk))).all()
            )
        return out
    return [(o, None if s is None else float(s)) for o, s in session.execute(q).all()]


# --- reuse -----------------------------------------------------------------------


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _content_time(opp: Opportunity, newest_doc: datetime | None) -> datetime:
    if opp.visibility == "private":
        return opp.updated_at
    times = [opp.created_at]
    ext = _parse_ts(((opp.evidence or {}).get("_extraction") or {}).get("at"))
    if ext:
        times.append(ext)
    if newest_doc:
        times.append(newest_doc)
    return max(times)


def _reusable(
    row: UserOpportunityScore | None,
    profile: Profile,
    opp: Opportunity,
    newest_doc: datetime | None,
    llm: LLMClient | None,
) -> dict[str, Any] | None:
    """The stored breakdown when its model judgement still holds, else None."""
    if row is None or not row.score_breakdown:
        return None
    b = row.score_breakdown
    if b.get("version") != BREAKDOWN_VERSION or not b.get("model"):
        return None
    if b.get("prompt_version") != judge_mod.PROMPT_VERSION:
        return None
    if llm is not None and b["model"] != llm.model:
        return None
    scored = _parse_ts(b.get("scored_at"))
    if scored is None or scored < profile.updated_at:
        return None
    if scored < _content_time(opp, newest_doc):
        return None
    return b


# --- per pair --------------------------------------------------------------------


def _full_date(dt: datetime) -> str:
    d = kigali_date(dt)
    return f"{d.day} {d.strftime('%B %Y')}"


def _rules_reason(opp: Opportunity, m: Match) -> str:
    if opp.stream == "event":
        what = (opp.subtype or "Event").capitalize()
        when = opp.event_start or opp.deadline_at
        text = what + (f" on {_full_date(when)}" if when else ", date not stated")
        if m.matched:
            text += f", on {', '.join(m.matched[:2])}"
        return text + "."
    if opp.stream == "investment":
        what = (opp.subtype or "Investment listing").capitalize()
        org = opp.organisation_short or opp.organisation
        text = what + (f" from {org}" if org else "")
        if opp.deadline_at:
            text += f", closing {_full_date(opp.deadline_at)}"
        return text + "."
    if m.excluded:
        return f"It matches this profile's exclusion “{m.excluded}”."
    if not m.shortlisted:
        return "Little in it matches what this profile lists."
    if m.matched:
        return f"It mentions {', '.join(m.matched[:3])}, which this profile lists."
    if m.similarity is not None:
        return "Its description is close to what this profile lists."
    return "Not enough detail to judge the fit."


def _sorted_flags(flags: list[Flag]) -> list[Flag]:
    def key(f: Flag) -> int:
        return (
            RULE_FLAG_ORDER.index(f.code)
            if f.code in RULE_FLAGS
            else len(RULE_FLAG_ORDER)
        )

    seen: set[str] = set()
    out = []
    for f in sorted(flags, key=key):  # stable: model flags keep their order
        if f.code not in seen:
            out.append(f)
            seen.add(f.code)
    return out


def _model_flags(b: dict[str, Any]) -> list[Flag]:
    out = []
    for f in b.get("flags") or []:
        if f.get("code") in judge_mod.MODEL_FLAG_CODES.values():
            out.append(
                Flag(f["code"], f["label"], f.get("quote"), f.get("to_check", ""))
            )
    return out


def _breakdown(
    *,
    components: dict[str, float],
    fit_conf: float,
    elig_conf: float,
    word: str | None,
    reasons: list[str],
    flags: list[Flag],
    provisional: bool,
    hard_filtered: str | None,
    model: str | None,
    prompt_version: str | None,
    now: datetime,
) -> dict[str, Any]:
    return {
        "version": BREAKDOWN_VERSION,
        "components": {c: round(components[c], 1) for c in COMPONENTS},
        "fit_confidence": round(fit_conf, 2),
        "eligibility_confidence": round(elig_conf, 2),
        "fit_word": word,
        "reasons": reasons,
        "flags": [f.as_dict() for f in flags],
        "provisional": provisional,
        "hard_filtered": hard_filtered,
        "model": model,
        "prompt_version": prompt_version,
        "scored_at": now.isoformat(),
    }


@dataclass
class _Scored:
    score: int
    reason: str
    breakdown: dict[str, Any]
    called_model: bool


def score_pair(
    opp: Opportunity,
    profile: Profile,
    *,
    sources: list[CarryingSource],
    documents: list[str],
    similarity: float | None,
    existing: UserOpportunityScore | None,
    newest_doc: datetime | None,
    run: _Run,
) -> _Scored:
    s = run.deps.settings
    w = s.weights
    now = run.now
    provisional = bool((profile.data or {}).get("provisional"))
    rules = check_rules(opp, profile, sources, documents, now)
    if rules.hard_filtered:
        run.stats.hard_filtered += 1
        reason = rules.filter_reason or rules.hard_filtered
        return _Scored(
            0,
            reason,
            _breakdown(
                components=dict.fromkeys(COMPONENTS, 0.0),
                fit_conf=0.0,
                elig_conf=0.0,
                word=None,
                reasons=[reason],
                flags=[],
                provisional=provisional,
                hard_filtered=rules.hard_filtered,
                model=None,
                prompt_version=None,
                now=now,
            ),
            False,
        )

    m = match(opp, profile, similarity, s)
    rule_flags = rules.flags
    penalised = [f for f in rule_flags if f.code != "value_unknown"]
    rules_elig = max(
        0.0, s.rules_eligibility - s.flag_eligibility_penalty * len(penalised)
    )
    reasons: list[str]
    model = prompt_version = None
    cap: str | None = None
    called = False
    flags = list(rule_flags)

    if opp.stream not in LLM_STREAMS:
        # Spec 7.1: events and investments rank on time, verification and source.
        fit_conf = 0.0 if m.excluded else (0.5 if m.matched else 0.4)
        elig_conf = rules_elig
        reason = _rules_reason(opp, m)
        reasons = [reason]
    elif not m.shortlisted:
        fit_conf = min(m.strength, 0.3)
        elig_conf = rules_elig
        reason = _rules_reason(opp, m)
        reasons = [reason]
    else:
        run.stats.shortlisted += 1
        reused = _reusable(existing, profile, opp, newest_doc, run.deps.llm)
        judgement: judge_mod.Judgement | None = None
        if reused is not None:
            run.stats.llm_reused += 1
            fit_conf = float(reused["fit_confidence"])
            elig_conf = float(reused["eligibility_confidence"])
            reason = existing.score_reason or _rules_reason(opp, m)
            flags += _model_flags(reused)
            model, prompt_version = reused["model"], reused["prompt_version"]
            reasons = [reason]
        else:
            if run.deps.llm is not None and run.llm_left > 0:
                run.llm_left -= 1
                run.stats.llm_calls += 1
                called = True
                notice = notice_text(opp, documents, s.text_max_chars)
                try:
                    judgement = judge_mod.judge(
                        run.deps.llm, opp, profile, notice, rule_flags
                    )
                except LLMError as exc:
                    run.stats.llm_failed += 1
                    log.warning(
                        "scoring call failed for %s/%s: %s", profile.id, opp.id, exc
                    )
            elif run.deps.llm is not None:
                run.stats.capped += 1
            if judgement is not None:
                fit_conf = judgement.fit_confidence
                elig_conf = judgement.eligibility_confidence
                reason = judgement.reason or _rules_reason(opp, m)
                flags += judgement.flags
                model, prompt_version = judgement.model, judgement.prompt_version
                reasons = [reason]
            else:
                run.stats.rules_only += 1
                fit_conf = m.strength
                elig_conf = rules_elig
                reason = NO_MODEL_REASON
                reasons = [NO_MODEL_REASON, _rules_reason(opp, m)]
                cap = "possible"

    flags = _sorted_flags(flags)
    components = {
        "fit": w["fit"] * fit_conf,
        "eligibility": w["eligibility"] * elig_conf,
        "value": w["value"] * value_score(opp, profile),
        "time": w["time"] * time_score(opp, now, s),
        "source": w["source"] * source_score(opp, sources, s),
    }
    word = fit_word(
        s.fit_word,
        fit=fit_conf,
        eligibility=elig_conf,
        n_flags=len(flags),
        stream=opp.stream,
        cap=cap,  # type: ignore[arg-type]
    )
    score = max(0, min(100, round(sum(components.values()))))
    return _Scored(
        score,
        reason,
        _breakdown(
            components=components,
            fit_conf=fit_conf,
            elig_conf=elig_conf,
            word=word,
            reasons=reasons,
            flags=flags,
            provisional=provisional,
            hard_filtered=None,
            model=model,
            prompt_version=prompt_version,
            now=now,
        ),
        called,
    )


def _same(row: UserOpportunityScore, scored: _Scored) -> bool:
    if row.score != scored.score or row.score_reason != scored.reason:
        return False
    old = dict(row.score_breakdown or {})
    new = dict(scored.breakdown)
    old.pop("scored_at", None)
    new.pop("scored_at", None)
    return old == new


def _upsert(
    session: Session, profile: Profile, opp_id: uuid.UUID, scored: _Scored
) -> None:
    stmt = pg_insert(UserOpportunityScore).values(
        user_id=profile.user_id,
        opportunity_id=opp_id,
        profile_id=profile.id,
        score=scored.score,
        score_reason=scored.reason,
        score_breakdown=scored.breakdown,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "opportunity_id", "profile_id"],
        set_={
            "score": stmt.excluded.score,
            "score_reason": stmt.excluded.score_reason,
            "score_breakdown": stmt.excluded.score_breakdown,
            "updated_at": sa.func.now(),
        },
    )
    session.execute(stmt)


# --- per profile -----------------------------------------------------------------


def _score_profile(
    session: Session,
    user: User,
    profile: Profile,
    run: _Run,
    *,
    statuses: Sequence[str],
    opportunity_ids: Sequence[uuid.UUID] | None,
) -> None:
    if profile.user_id != user.id:  # defensive: never mix users
        raise ValueError("profile does not belong to user")
    run.stats.profiles += 1
    vector = profile_embedding(profile, run.deps.embedder)
    cands = _candidates(
        session, user, vector, statuses=statuses, opportunity_ids=opportunity_ids
    )
    if not cands:
        return
    ids = [o.id for o, _ in cands]
    sources = _carrying_sources(session, user, ids)
    docs, newest = _documents(session, ids)
    existing = _existing(session, profile, ids)
    for opp, sim in cands:
        run.stats.pairs += 1
        row = existing.get(opp.id)
        scored = score_pair(
            opp,
            profile,
            sources=sources.get(opp.id, []),
            documents=docs.get(opp.id, []),
            similarity=sim,
            existing=row,
            newest_doc=newest.get(opp.id),
            run=run,
        )
        if row is not None and not scored.called_model and _same(row, scored):
            run.stats.unchanged += 1
            continue
        _upsert(session, profile, opp.id, scored)
        run.stats.written += 1
    session.flush()


def _active_profiles(session: Session, user_id: uuid.UUID) -> list[Profile]:
    return list(
        session.scalars(
            sa.select(Profile)
            .where(Profile.user_id == user_id, Profile.active.is_(True))
            .order_by(Profile.created_at, Profile.name)
        )
    )


def _new_run(deps: ScoringDeps | None, now: datetime | None) -> _Run:
    deps = deps or default_deps()
    return _Run(
        deps=deps,
        now=now or datetime.now(UTC),
        llm_left=deps.settings.max_llm_calls_per_run,
    )


# --- entry points --------------------------------------------------------------------


def score_user(
    session: Session,
    user_id: uuid.UUID,
    *,
    deps: ScoringDeps | None = None,
    now: datetime | None = None,
) -> RunStats:
    """Every active profile of one active user over the open items they can see."""
    run = _new_run(deps, now)
    user = session.get(User, user_id)
    if user is None or user.status != "active":
        return run.stats
    for profile in _active_profiles(session, user.id):
        _score_profile(
            session, user, profile, run, statuses=OPEN_STATUSES, opportunity_ids=None
        )
    return run.stats


def backfill_profile(
    session: Session,
    profile_id: uuid.UUID,
    *,
    deps: ScoringDeps | None = None,
    now: datetime | None = None,
) -> RunStats:
    """Spec 5: a new or edited profile is matched and scored over currently open
    items. An inactive profile, or one whose owner is deactivated, is skipped."""
    run = _new_run(deps, now)
    profile = session.get(Profile, profile_id)
    if profile is None or not profile.active:
        return run.stats
    user = session.get(User, profile.user_id)
    if user is None or user.status != "active":
        return run.stats
    _score_profile(
        session, user, profile, run, statuses=OPEN_STATUSES, opportunity_ids=None
    )
    return run.stats


def score_new_opportunities(
    session: Session,
    since: datetime,
    *,
    deps: ScoringDeps | None = None,
    now: datetime | None = None,
) -> RunStats:
    """The worker's hook after ingest: items created or updated since ``since``,
    for every active user's active profiles."""
    run = _new_run(deps, now)
    ids = list(
        session.scalars(
            sa.select(Opportunity.id).where(
                sa.or_(
                    Opportunity.created_at >= since, Opportunity.updated_at >= since
                ),
                Opportunity.status.in_(NEW_STATUSES),
            )
        )
    )
    if not ids:
        return run.stats
    users = session.scalars(
        sa.select(User).where(User.status == "active").order_by(User.created_at)
    ).all()
    for user in users:
        for profile in _active_profiles(session, user.id):
            _score_profile(
                session, user, profile, run, statuses=NEW_STATUSES, opportunity_ids=ids
            )
    return run.stats
