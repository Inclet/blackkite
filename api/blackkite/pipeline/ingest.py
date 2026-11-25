"""Shared pipeline entry point: RawItems from one source run -> catalogue records.

``ingest_items(session, source, items)`` runs normalise -> dedupe -> enrich ->
extract -> validate for each item inside its own SAVEPOINT, so one bad item is
rolled back and counted in ``items_failed`` without touching the others. It never
commits: the caller (the source runner) owns the transaction.

Counts:

* ``items_found``: items handed in;
* ``items_new``: items that created a new opportunity (not seen before at any
  source, by URL or similarity);
* ``items_failed``: items rolled back because of an error.

An item the extraction model says is not an opportunity (a news story, a results
list) is not stored and counts in neither ``items_new`` nor ``items_failed``.

Cost: enrichment and the extraction call run only for items that create a record,
for the first item an ``original`` source contributes to a record (its dates and
fields take precedence, spec 2.3), and for records never extracted (for example
while ANTHROPIC_API_KEY was unset). A re-seen URL only refreshes ``last_seen`` and
the deadline that source lists (a changed deadline is not re-extracted; the newer
listed value is used, unless it moved into the past or to before publication, which
is flagged and not believed).

Evidence layout (``opportunity.evidence``):

* ``<field>``: ``{"snippet": ..., "source_id": ...}`` for every extracted field
  (dates that failed validation also keep ``"raw"`` and ``"status"``);
* ``requirements`` / ``tags``: ``{"snippets": [...]}`` / ``{"snippets": {tag: ...}}``;
* ``_sources``: per source id, what that source listed (title, organisation,
  listed and extracted deadline, ``deadline_history`` of superseded values) - the
  record of each source's deadline used for conflict checks. When a source's
  dated listed deadline changes between runs, the newer listed value wins over an
  older extracted one (see ``_record_listed_deadline``);
* ``_deadline_conflict``, ``_trust`` (see validate.py), ``_extraction`` (model,
  prompt version, source, time, dropped fields), ``_embedding`` (model, time),
  ``_enrich`` (fetch errors), ``_review`` (list of ``{"code", "detail"}``: why
  ``needs_review`` was set).

``needs_review`` is set whenever a new review reason is added and is never cleared
by the pipeline, except when the only reasons were a skipped or failed
extraction/embedding and that step has since succeeded.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from blackkite.collectors.base import RawItem
from blackkite.db.models import (
    ChangeEvent,
    Document,
    Opportunity,
    OpportunitySource,
    Source,
)
from blackkite.llm.client import LLMClient, LLMError
from blackkite.llm.embeddings import Embedder, EmbeddingError
from blackkite.pipeline.dates import (
    kigali_date,
    parse_date,
    parse_extracted_date,
)
from blackkite.pipeline.dedupe import find_by_url, find_similar
from blackkite.pipeline.enrich import Enrichment, Fetcher, enrich
from blackkite.pipeline.extract import (
    Extracted,
    embedding_text,
    extract,
    strip_advice,
)
from blackkite.pipeline.normalise import NormalisedItem, normalise
from blackkite.pipeline.settings import PipelineSettings, get_pipeline_settings
from blackkite.pipeline.validate import (
    DateCheck,
    SourceDeadline,
    check_date,
    resolve_deadline,
    review_reason,
    status_for,
    trust_state,
)
from blackkite.pipeline.visibility import verification_of

log = logging.getLogger("blackkite.pipeline")

TRACKED_FIELDS = ("deadline_at", "status", "value_amount", "value_currency")
# Plain extracted columns (dates, requirements, tags handled separately).
SIMPLE_FIELDS = (
    "subtype",
    "title",
    "organisation",
    "organisation_short",
    "summary",
    "value_amount",
    "value_currency",
    "value_note",
    "location",
    "eligibility",
    "submission_method",
    "fees",
)
OTHER_DATES = {"published_at": "start", "event_start": "start", "event_end": "end"}
# Review codes that a later successful step makes stale.
TRANSIENT = {
    "extraction": ("extraction_skipped", "extraction_failed"),
    "embedding": ("embedding_skipped", "embedding_failed"),
}
# Extraction drops that are worth a human look (spec 10: deadline and amount
# always need a supporting snippet).
KEY_FIELDS = {"deadline_at", "value_amount"}


@dataclass
class IngestResult:
    items_found: int
    items_new: int
    items_failed: int = 0


@dataclass
class PipelineDeps:
    fetcher: Fetcher | None = None
    llm: LLMClient | None = None
    embedder: Embedder | None = None
    settings: PipelineSettings = field(default_factory=get_pipeline_settings)


def default_deps(fetcher: Fetcher | None = None) -> PipelineDeps:
    """Real clients from settings; a client whose key is unset is ``None``."""
    from blackkite.config import get_settings
    from blackkite.llm.factory import embedder, extraction_llm

    s, ps = get_settings(), get_pipeline_settings()
    return PipelineDeps(
        fetcher=fetcher,
        llm=extraction_llm(s, ps),
        embedder=embedder(s, ps),
        settings=ps,
    )


def ingest_items(
    session: Session,
    source: Source,
    items: list[RawItem],
    *,
    deps: PipelineDeps | None = None,
    now: datetime | None = None,
) -> IngestResult:
    deps = deps or default_deps()
    now = now or datetime.now(UTC)
    new = failed = 0
    for raw in items:
        try:
            with session.begin_nested():
                if _ingest_one(session, source, raw, deps, now):
                    new += 1
        except Exception:  # one bad item must not sink the batch
            failed += 1
            log.exception("ingest failed for %s from source %s", raw.url, source.id)
    session.flush()
    return IngestResult(items_found=len(items), items_new=new, items_failed=failed)


# --- helpers --------------------------------------------------------------------------


class _Review:
    def __init__(self) -> None:
        self.add: list[dict[str, str]] = []
        self.clear: set[str] = set()

    def __call__(self, code: str, detail: str) -> None:
        self.add.append({"code": code, "detail": detail})


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _snapshot(opp: Opportunity) -> dict[str, Any]:
    return {f: getattr(opp, f) for f in TRACKED_FIELDS}


def _has_original(session: Session, opp_id) -> bool:
    return bool(
        session.scalar(
            sa.select(
                sa.exists().where(
                    OpportunitySource.opportunity_id == opp_id,
                    OpportunitySource.is_original,
                )
            )
        )
    )


def _link(
    session: Session, opp: Opportunity, source: Source, url: str, now: datetime
) -> OpportunitySource:
    link = session.scalars(
        sa.select(OpportunitySource).where(
            OpportunitySource.opportunity_id == opp.id,
            OpportunitySource.source_id == source.id,
            OpportunitySource.url == url,
        )
    ).first()
    if link is not None:
        link.last_seen = now
        return link
    # At most one original per opportunity (schema); a second original-kind source
    # is recorded as carrying it, and still counts as original for verification.
    is_original = source.kind == "original" and not _has_original(session, opp.id)
    link = OpportunitySource(
        opportunity_id=opp.id,
        source_id=source.id,
        url=url,
        is_original=is_original,
        first_seen=now,
        last_seen=now,
    )
    session.add(link)
    session.flush()
    return link


def _date_value(entry: dict[str, Any] | None) -> datetime | None:
    if entry and entry.get("status") == "ok" and entry.get("value"):
        return datetime.fromisoformat(entry["value"])
    return None


def _date_entry(check: DateCheck, snippet: str | None = None) -> dict[str, Any]:
    return {
        "status": check.status,
        "value": _iso(check.value),
        "raw": check.raw,
        "snippet": snippet if snippet is not None else check.raw,
    }


def _source_text(item: NormalisedItem, enrichment: Enrichment, max_chars: int) -> str:
    return (item.raw_text + "\n\n" + enrichment.text()).strip()[:max_chars]


# --- per item ------------------------------------------------------------------------


def _ingest_one(
    session: Session, source: Source, raw: RawItem, deps: PipelineDeps, now: datetime
) -> bool:
    if raw.source_id != source.id:
        raise ValueError("RawItem.source_id does not match the source being ingested")
    item = normalise(raw)
    if not item.title:
        raise ValueError("item has no title")
    sid = str(source.id)
    streams = list(source.streams)
    review = _Review()

    listed_deadline = check_date(
        "deadline_at", parse_date(item.listed_deadline, "end"), now
    )
    listed_published = check_date(
        "published_at", parse_date(item.listed_published, "start"), now
    )

    # Dedupe, before spending anything on enrichment or the model.
    match = find_by_url(session, [item.url, item.detail_url], streams)
    if match is None and len(streams) == 1:
        match = find_similar(
            session,
            title=item.title,
            organisation=item.organisation,
            deadline=listed_deadline.value,
            streams=streams,
            now=now,
        )
    opp = match.opportunity if match else None

    want_extract = (
        opp is None
        or (source.kind == "original" and not _has_original(session, opp.id))
        or ("_extraction" not in (opp.evidence or {}) and deps.llm is not None)
    )
    enrichment: Enrichment | None = None
    extracted: Extracted | None = None
    if want_extract:
        ps = deps.settings
        enrichment = enrich(
            deps.fetcher,
            item.detail_url or item.url,
            data_dir=ps.data_dir,
            max_bytes=ps.document_max_bytes,
            max_attachments=ps.documents_per_item,
            pdf_timeout=ps.pdf_text_timeout_seconds,
        )
        if deps.llm is None:
            review(
                "extraction_skipped", "extraction skipped: ANTHROPIC_API_KEY is not set"
            )
        else:
            try:
                extracted = extract(
                    deps.llm,
                    _source_text(item, enrichment, ps.extract_max_chars),
                    source_name=source.name,
                    source_kind=source.kind,
                    streams=streams,
                )
                review.clear.update(TRANSIENT["extraction"])
            except LLMError as exc:
                review("extraction_failed", f"extraction failed: {exc}"[:500])
        if extracted is not None and not extracted.is_opportunity:
            if opp is None:
                log.info(
                    "not an opportunity, skipped: %s (%s)",
                    item.url,
                    extracted.not_opportunity_reason,
                )
                return False
            extracted = None
        # Multi-stream sources: similarity matching waits until the stream is known.
        stream = extracted.values.get("stream") if extracted else None
        if opp is None and len(streams) > 1 and stream:
            match = find_similar(
                session,
                title=extracted.values.get("title") or item.title,
                organisation=extracted.values.get("organisation") or item.organisation,
                deadline=listed_deadline.value,
                streams=[stream],
                now=now,
            )
            opp = match.opportunity if match else None

    created = opp is None
    if opp is None:
        stream = extracted.values.get("stream") if extracted else None
        if stream is None:
            stream = streams[0]
            if len(streams) > 1:
                review(
                    "stream_unknown",
                    f"stream not determined; filed under {stream!r} (source feeds "
                    f"{', '.join(streams)})",
                )
        opp = Opportunity(
            stream=stream,
            title=item.title,
            organisation=item.organisation,
            evidence={},
            tags=[],
            status="open",
            verification="unverified",
            needs_review=False,
            visibility="public",
        )
        session.add(opp)
        session.flush()
    before = None if created else _snapshot(opp)
    ev: dict[str, Any] = copy.deepcopy(opp.evidence or {})

    link = _link(session, opp, source, item.url, now)
    entry = ev.setdefault("_sources", {}).setdefault(sid, {})
    entry.update(
        {
            "kind": source.kind,
            "is_original": bool(entry.get("is_original"))
            or link.is_original
            or source.kind == "original",
            "url": item.url,
            "title": item.title,
            "organisation": item.organisation,
            "seen_at": now.isoformat(),
        }
    )
    _record_listed_deadline(session, opp, entry, listed_deadline, source, now, review)
    if listed_deadline.reviewable:
        review(
            "date", review_reason("deadline_at", listed_deadline) + f" [{source.name}]"
        )

    authoritative = created or link.is_original
    if extracted is not None:
        if opp.stream == "investment":
            strip_advice(extracted)  # also when the model named another stream
        _apply_extraction(opp, ev, entry, extracted, sid, authoritative, now, review)

    if opp.published_at is None and listed_published.value is not None:
        opp.published_at = listed_published.value
        ev["published_at"] = {"snippet": item.listed_published, "source_id": sid}
    elif listed_published.reviewable and created:
        review("date", review_reason("published_at", listed_published))
        ev.setdefault(
            "published_at", {**_date_entry(listed_published), "source_id": sid}
        )

    if enrichment is not None:
        _store_documents(session, opp, enrichment)
        if enrichment.errors:
            ev["_enrich"] = {"errors": enrichment.errors[:10], "at": now.isoformat()}

    if created or extracted is not None or opp.embedding is None:
        _embed(opp, ev, deps.embedder, now, review)

    _finalise(session, opp, ev, now, review)
    opp.evidence = ev

    if before is not None:
        after = _snapshot(opp)
        for f in TRACKED_FIELDS:
            if before[f] != after[f]:
                session.add(
                    ChangeEvent(
                        opportunity_id=opp.id,
                        field=f,
                        old=_jsonable(before[f]),
                        new=_jsonable(after[f]),
                        at=now,
                    )
                )
    session.flush()
    return created


def _source_current_deadline(entry: dict[str, Any]) -> datetime | None:
    """The deadline this source currently counts for: its extracted value, else the
    value it listed (same order as ``_finalise``)."""
    for key in ("deadline_extracted", "deadline_listed"):
        value = _date_value(entry.get(key))
        if value is not None:
            return value
    return None


def _suspect_reason(opp: Opportunity, listed: DateCheck, now: datetime) -> str | None:
    """Why a changed listed deadline is not believed, or None.

    A deadline that moves into the past, or to before the item was published, is
    far more often a mis-mapped selector or a portal reset than a real change; a
    real cancellation is a status. Such a value must not expire a live item.
    """
    assert listed.value is not None
    if listed.value < now:
        return "a past date"
    if opp.published_at is not None and listed.value < opp.published_at:
        return "a date before publication"
    return None


def _record_listed_deadline(
    session: Session,
    opp: Opportunity,
    entry: dict[str, Any],
    listed: DateCheck,
    source: Source,
    now: datetime,
    review: _Review,
) -> None:
    """Store what this source lists as the deadline now, and notice when it moved.

    * A sighting whose listed deadline has no usable value (no year, unparsed, out
      of window, absent) never replaces a dated value seen earlier.
    * A changed value that is before ``now`` or before the item's ``published_at``
      is suspect: the source keeps its current deadline, the suspicious value goes
      to ``deadline_history`` (kind ``listed_suspect``) and the item is flagged
      ``deadline_changed_suspect``. Nothing about the deadline changes.
    * Any other changed value becomes that source's deadline: an older extracted
      value is superseded (moved to ``deadline_history``), a ``change_event`` with
      field ``source_deadline`` is written and the item is flagged
      ``deadline_changed``. ``_finalise`` then resolves the deadline across sources
      again.
    """
    previous = _date_value(entry.get("deadline_listed"))
    if listed.value is None and previous is not None:
        return  # keep the last dated listing
    if previous is None or listed.value is None or previous == listed.value:
        entry["deadline_listed"] = _date_entry(listed)
        return
    history = entry.setdefault("deadline_history", [])
    old_current = _source_current_deadline(entry)
    old_day = kigali_date(old_current).isoformat() if old_current else "none"
    new_day = kigali_date(listed.value).isoformat()
    shown = f" (listed {listed.raw!r})" if listed.raw else ""

    suspect = _suspect_reason(opp, listed, now)
    if suspect is not None:
        last = history[-1] if history else {}
        if not (
            last.get("kind") == "listed_suspect"
            and last.get("value") == _iso(listed.value)
        ):
            history.append(
                {**_date_entry(listed), "kind": "listed_suspect", "at": now.isoformat()}
            )
            del history[:-20]
        review(
            "deadline_changed_suspect",
            f"listed deadline moved to {suspect} at {source.name}: "
            f"{old_day} -> {new_day}{shown}; kept {old_day}",
        )
        return

    history.append(
        {**entry["deadline_listed"], "kind": "listed", "until": now.isoformat()}
    )
    extracted_entry = entry.pop("deadline_extracted", None)
    if extracted_entry is not None:
        history.append(
            {**extracted_entry, "kind": "extracted", "until": now.isoformat()}
        )
    del history[:-20]
    review(
        "deadline_changed",
        f"deadline changed at {source.name}: {old_day} -> {new_day}{shown}",
    )
    session.add(
        ChangeEvent(
            opportunity_id=opp.id,
            field="source_deadline",
            old={"source_id": str(source.id), "value": _iso(old_current)},
            new={"source_id": str(source.id), "value": _iso(listed.value)},
            at=now,
        )
    )
    entry["deadline_listed"] = _date_entry(listed)


def _apply_extraction(
    opp: Opportunity,
    ev: dict[str, Any],
    entry: dict[str, Any],
    x: Extracted,
    sid: str,
    authoritative: bool,
    now: datetime,
    review: _Review,
) -> None:
    """Copy checked fields onto the record. A new record or the original source
    overwrites; any other source only fills fields that are still empty."""
    v = x.values
    for name in SIMPLE_FIELDS:
        if name in v and (authoritative or getattr(opp, name) is None):
            setattr(opp, name, v[name])
            ev[name] = {**x.evidence[name], "source_id": sid}
    for name in ("requirements", "tags"):
        if name in v and (authoritative or not getattr(opp, name)):
            setattr(opp, name, v[name])
            ev[name] = {**x.evidence[name], "source_id": sid}

    for name, edge in OTHER_DATES.items():
        snippet = x.evidence.get(name, {}).get("snippet")
        if name not in v and snippet is None:
            continue
        check = check_date(name, parse_extracted_date(v.get(name), snippet, edge), now)
        if check.value is not None:
            if authoritative or getattr(opp, name) is None:
                setattr(opp, name, check.value)
                ev[name] = {"snippet": snippet, "source_id": sid}
        elif check.reviewable or (check.status == "empty" and snippet):
            # A quoted date with no usable value: keep the raw text, never guess.
            check = DateCheck(
                None, "no_year" if check.status == "empty" else check.status, snippet
            )
            if getattr(opp, name) is None:
                ev[name] = {**_date_entry(check, snippet), "source_id": sid}
            review("date", review_reason(name, check))

    snippet = x.evidence.get("deadline_at", {}).get("snippet")
    if "deadline_at" in v or snippet is not None:
        check = check_date(
            "deadline_at",
            parse_extracted_date(v.get("deadline_at"), snippet, "end"),
            now,
        )
        if check.status == "empty" and snippet:
            check = DateCheck(None, "no_year", snippet)
        entry["deadline_extracted"] = _date_entry(check, snippet)
        if check.reviewable:
            review("date", review_reason("deadline_at", check))

    ev["_extraction"] = {
        "model": x.model,
        "prompt_version": x.prompt_version,
        "source_id": sid,
        "at": now.isoformat(),
        "dropped": sorted(set(x.dropped)),
    }
    for reason in x.reasons:
        if reason.startswith("dropped fields") and not (KEY_FIELDS & set(x.dropped)):
            continue
        review("extraction_check", reason)


def _store_documents(
    session: Session, opp: Opportunity, enrichment: Enrichment
) -> None:
    known = set(
        session.scalars(
            sa.select(Document.url).where(Document.opportunity_id == opp.id)
        )
    )
    for doc in enrichment.documents:
        if doc.url in known:
            continue
        session.add(
            Document(
                opportunity_id=opp.id,
                url=doc.url,
                file_path=doc.file_path,
                extracted_text=doc.text,
            )
        )
        known.add(doc.url)


def _embed(
    opp: Opportunity,
    ev: dict[str, Any],
    embedder: Embedder | None,
    now: datetime,
    review: _Review,
) -> None:
    if embedder is None:
        review("embedding_skipped", "embedding skipped: VOYAGE_API_KEY is not set")
        return
    try:
        [vector] = embedder.embed(
            [embedding_text(opp.title, opp.summary, opp.tags or [])]
        )
    except (EmbeddingError, ValueError) as exc:
        review("embedding_failed", f"embedding failed: {exc}"[:500])
        return
    opp.embedding = vector
    ev["_embedding"] = {"model": embedder.model, "at": now.isoformat()}
    review.clear.update(TRANSIENT["embedding"])


def _finalise(
    session: Session,
    opp: Opportunity,
    ev: dict[str, Any],
    now: datetime,
    review: _Review,
) -> None:
    # Deadline: one per source, then the original's, else the earliest.
    candidates: list[SourceDeadline] = []
    snippets: dict[str, str | None] = {}
    for sid, entry in ev.get("_sources", {}).items():
        for key in ("deadline_extracted", "deadline_listed"):
            value = _date_value(entry.get(key))
            if value is not None:
                candidates.append(
                    SourceDeadline(sid, bool(entry.get("is_original")), value)
                )
                snippets[sid] = entry[key].get("snippet")
                break
    chosen, conflict, rule = resolve_deadline(candidates)
    if chosen is not None:
        opp.deadline_at = chosen
        chosen_sid = next(c.source_id for c in candidates if c.value == chosen)
        ev["deadline_at"] = {
            "snippet": snippets[chosen_sid],
            "source_id": chosen_sid,
            "rule": rule,
        }
    else:
        for sid, entry in ev.get("_sources", {}).items():
            for key in ("deadline_extracted", "deadline_listed"):
                e = entry.get(key) or {}
                if e.get("status") in (
                    "no_year",
                    "unparsed",
                    "out_of_window",
                    "mismatch",
                ):
                    # Not guessed: keep the raw text so a reviewer can see it.
                    ev.setdefault(
                        "deadline_at",
                        {
                            "raw": e.get("raw"),
                            "snippet": e.get("snippet"),
                            "status": e["status"],
                            "source_id": sid,
                        },
                    )
    ev["_deadline_conflict"] = conflict
    if conflict:
        days = sorted({kigali_date(c.value).isoformat() for c in candidates})
        review(
            "deadline_conflict",
            f"sources disagree on the deadline ({', '.join(days)}); kept the {rule} one",
        )

    if opp.event_start and opp.event_end and opp.event_end < opp.event_start:
        review("date", "event_end is before event_start; event_end removed")
        opp.event_end = None

    opp.status = status_for(
        opp.status or "open",
        opp.stream,
        opp.deadline_at,
        opp.event_start,
        opp.event_end,
        now,
    )
    opp.verification = verification_of(session, opp.id)  # member-visible sources
    ev["_trust"] = trust_state(opp.verification, ev)

    reasons: list[dict[str, str]] = list(ev.get("_review", []))
    had = len(reasons)
    reasons = [r for r in reasons if r["code"] not in review.clear]
    cleared = len(reasons) < had
    added = False
    for r in review.add:
        if r["code"] in review.clear:
            continue
        if r not in reasons:
            reasons.append(r)
            added = True
    ev["_review"] = reasons
    if added:
        opp.needs_review = True
    elif cleared and not reasons:
        opp.needs_review = False


# --- periodic -------------------------------------------------------------------------


def refresh_statuses(session: Session, now: datetime | None = None) -> int:
    """Move open/closing_soon items on as time passes (call from the scheduler).
    Returns how many changed; each change is logged in change_event."""
    now = now or datetime.now(UTC)
    changed = 0
    rows = session.scalars(
        sa.select(Opportunity).where(Opportunity.status.in_(("open", "closing_soon")))
    ).all()
    for opp in rows:
        new = status_for(
            opp.status, opp.stream, opp.deadline_at, opp.event_start, opp.event_end, now
        )
        if new != opp.status:
            session.add(
                ChangeEvent(
                    opportunity_id=opp.id,
                    field="status",
                    old=opp.status,
                    new=new,
                    at=now,
                )
            )
            opp.status = new
            changed += 1
    session.flush()
    return changed
