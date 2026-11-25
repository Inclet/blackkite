"""``custom`` collector type (spec 4.2): a named collector class from an allowlist.

Config (``CustomConfig``)::

    {"collector": "jsonld_events", "options": {...}}

``collector`` must be a key of ``CUSTOM_COLLECTORS`` below. The config never
holds an import path, module or class reference: the name is looked up in this
dict and nothing else, so an admin can only choose among classes shipped in
code. ``options`` are validated by the chosen class's own ``Options`` model.

A custom collector class has:

- ``name`` (its key in the allowlist) and ``help`` (one line for the admin form);
- ``Options``: a Pydantic model with help text on every field;
- ``__init__(client, options, *, preview)`` and ``fetch(source) -> list[RawItem]``,
  fetching only through the guarded ``FetchClient``.

Shipped: ``jsonld_events``, schema.org Event objects from a listing page's
JSON-LD (spec 4.5: Eventbrite and 10times listing pages carry them); and
``demo_fictional``, a no-op for the fictional sources of ``bk demo-seed`` (no
fetch, no items), so a run of a demo source succeeds instead of failing.

``demo_fictional`` exists only when BK_ENV=dev (``DEV_ONLY``): with BK_ENV=prod it
is left out of the admin form and refused as an unknown custom collector, so no
real source can be configured with it and a stray demo row fails its run.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from selectolax.lexbor import LexborHTMLParser

from blackkite.collectors.base import CollectorError, RawItem
from blackkite.collectors.common import (
    MAX_SNIPPET,
    clean,
    html_text,
    http_link,
    parse_model,
    safe_url,
    utc_now,
)
from blackkite.collectors.http import FetchClient

# --- JSON-LD events ---------------------------------------------------------------------

MAX_JSONLD_SCRIPTS = 50
MAX_JSONLD_NODES = 5000
MAX_DEPTH = 6
# schema.org Event subtypes that do not end in "Event".
EVENT_TYPES_EXTRA = frozenset({"Festival", "Hackathon", "CourseInstance"})


class JsonLdEventsOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_url: str = Field(description="Address of the event listing page (page 1).")
    pagination_pattern: str | None = Field(
        default=None,
        description="Address of later pages with {page} where the number goes.",
    )
    first_page: Annotated[int, Field(ge=0, le=1000)] = Field(
        default=2, description="Page number of the first pattern page."
    )
    max_pages: Annotated[int, Field(ge=1, le=20)] = Field(
        default=1, description="Pages to read per run, counting list_url as 1."
    )
    max_items: Annotated[int, Field(ge=1, le=500)] = Field(
        default=100, description="Keep at most this many events per run."
    )

    @field_validator("list_url")
    @classmethod
    def _list_url(cls, v: str) -> str:
        return safe_url(v)

    @field_validator("pagination_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "{page}" not in v:
            raise ValueError("pagination_pattern must contain {page}")
        safe_url(v.replace("{page}", "1"))
        return v

    def page_urls(self) -> list[str]:
        urls = [self.list_url]
        if self.pagination_pattern:
            for i in range(self.max_pages - 1):
                urls.append(
                    self.pagination_pattern.replace("{page}", str(self.first_page + i))
                )
        return urls


def _types(node: dict[str, Any]) -> list[str]:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    out = []
    for x in types:
        if isinstance(x, str):
            out.append(x.rsplit("/", 1)[-1].rsplit(":", 1)[-1])
    return out


def _is_event(node: dict[str, Any]) -> bool:
    return any(t.endswith("Event") or t in EVENT_TYPES_EXTRA for t in _types(node))


def jsonld_nodes(html: str) -> list[Any]:
    """Parsed JSON-LD blocks of a page; unparseable blocks are skipped."""
    tree = LexborHTMLParser(html)
    out = []
    for script in tree.css("script")[:500]:
        stype = (script.attributes.get("type") or "").split(";")[0].strip().lower()
        if stype != "application/ld+json":
            continue
        text = script.text(deep=True) or ""
        try:
            out.append(json.loads(text))
        except (ValueError, RecursionError):
            continue
        if len(out) >= MAX_JSONLD_SCRIPTS:
            break
    return out


def find_events(blocks: list[Any]) -> list[dict[str, Any]]:
    """Event objects found at the top level, in @graph, and in ItemList entries
    (ListItem.item), up to MAX_DEPTH deep and MAX_JSONLD_NODES nodes."""
    events: list[dict[str, Any]] = []
    budget = [MAX_JSONLD_NODES]

    def walk(node: Any, depth: int) -> None:
        if depth > MAX_DEPTH or budget[0] <= 0:
            return
        budget[0] -= 1
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
            return
        if not isinstance(node, dict):
            return
        if _is_event(node):
            events.append(node)
            return
        for key in ("@graph", "itemListElement", "item", "mainEntity", "subEvent"):
            if key in node:
                walk(node[key], depth + 1)

    walk(blocks, 0)
    return events


def _name(v: Any) -> str | None:
    if isinstance(v, list):
        names = [n for n in (_name(x) for x in v) if n]
        return clean(", ".join(dict.fromkeys(names)), 300)
    if isinstance(v, dict):
        return html_text(_str(v.get("name")), 300)
    return html_text(_str(v), 300)


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def _address(v: Any) -> str | None:
    if isinstance(v, str):
        return clean(v, 300)
    if not isinstance(v, dict):
        return None
    parts = [
        _str(v.get("streetAddress")),
        _str(v.get("addressLocality")),
        _str(v.get("addressRegion")),
        _name(v.get("addressCountry")),
    ]
    return clean(", ".join(p for p in parts if p), 300)


def _location(v: Any) -> str | None:
    if isinstance(v, list):
        locs = [x for x in (_location(i) for i in v) if x]
        return clean("; ".join(dict.fromkeys(locs)), 300)
    if isinstance(v, str):
        return clean(v, 300)
    if not isinstance(v, dict):
        return None
    if "VirtualLocation" in _types(v):
        return "Online"
    parts = [_name(v), _address(v.get("address"))]
    return clean(", ".join(dict.fromkeys(p for p in parts if p)), 300)


def _offers(v: Any) -> dict[str, str]:
    offer = v[0] if isinstance(v, list) and v else v
    if not isinstance(offer, dict):
        return {}
    out: dict[str, str] = {}
    price = offer.get("price", offer.get("lowPrice"))
    if isinstance(price, int | float | str) and not isinstance(price, bool):
        currency = _str(offer.get("priceCurrency")) or ""
        out["price"] = clean(f"{price} {currency}", 100) or ""
    if valid := clean(_str(offer.get("validThrough")), 100):
        out["offers_valid_through"] = valid
    return {k: v for k, v in out.items() if v}


def _enum_name(v: Any) -> str | None:
    s = _str(v)
    return clean(s.rsplit("/", 1)[-1], 100) if s else None


def event_item(node: dict[str, Any], page_url: str, source_id, fetched_at):
    title = _name(node.get("name"))
    url = http_link(page_url, node.get("url")) or http_link(page_url, node.get("@id"))
    if not title or not url:
        return None
    extra: dict[str, str] = {}
    for key, label in (("startDate", "event_start"), ("endDate", "event_end")):
        if value := clean(_str(node.get(key)), 100):
            extra[label] = value
    if loc := _location(node.get("location")):
        extra["location"] = loc
    if status := _enum_name(node.get("eventStatus")):
        extra["event_status"] = status
    if mode := _enum_name(node.get("eventAttendanceMode")):
        extra["attendance_mode"] = mode
    extra.update(_offers(node.get("offers")))
    extra["jsonld_type"] = ", ".join(_types(node))[:100]
    return RawItem(
        source_id=source_id,
        url=url,
        title=title,
        fetched_at=fetched_at,
        organisation=_name(node.get("organizer")),
        snippet=html_text(_str(node.get("description")), MAX_SNIPPET),
        extra=extra,
    )


class JsonLdEventsCollector:
    name: ClassVar[str] = "jsonld_events"
    help: ClassVar[str] = (
        "schema.org Event objects from the JSON-LD on an event listing page "
        "(Eventbrite, 10times and similar)."
    )
    Options: ClassVar[type[BaseModel]] = JsonLdEventsOptions

    def __init__(
        self,
        client: FetchClient,
        options: JsonLdEventsOptions,
        *,
        preview: bool = False,
        now=utc_now,
    ) -> None:
        self.client = client
        self.options = options
        self.preview = preview
        self.now = now

    def fetch(self, source) -> list[RawItem]:
        opts = self.options
        pages = opts.page_urls()[:1] if self.preview else opts.page_urls()
        items: list[RawItem] = []
        seen: set[str] = set()
        for page_url in pages:
            resp = self.client.get(page_url, delay=source.rate_limit)
            events = find_events(jsonld_nodes(resp.text))
            if not events and page_url != pages[0]:
                break
            fetched_at = self.now()
            for node in events:
                item = event_item(node, resp.url, source.id, fetched_at)
                if item is None or item.url in seen:
                    continue
                seen.add(item.url)
                items.append(item)
                if len(items) >= opts.max_items:
                    return items
        return items


# --- demo no-op -------------------------------------------------------------------------


class NoOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoFictionalCollector:
    """FICTIONAL demo sources only (``bk demo-seed``). Makes no request and
    returns no items: the demo catalogue is written by the seed, never collected."""

    name: ClassVar[str] = "demo_fictional"
    help: ClassVar[str] = (
        "Demo only: the fictional sources from bk demo-seed. Fetches nothing and "
        "finds no items."
    )
    Options: ClassVar[type[BaseModel]] = NoOptions

    def __init__(
        self, client: FetchClient, options: NoOptions, *, preview: bool = False
    ) -> None:
        self.preview = preview

    def fetch(self, source) -> list[RawItem]:
        return []


# --- the allowlist ----------------------------------------------------------------------

CUSTOM_COLLECTORS: dict[str, type] = {
    JsonLdEventsCollector.name: JsonLdEventsCollector,
    DemoFictionalCollector.name: DemoFictionalCollector,
}
# Collectors that exist only when BK_ENV=dev.
DEV_ONLY = frozenset({DemoFictionalCollector.name})


def available_collectors(env: str | None = None) -> dict[str, type]:
    """The allowlist for this environment (``env`` defaults to BK_ENV): every
    collector in dev, none of ``DEV_ONLY`` anywhere else."""
    if env is None:
        from blackkite.config import get_settings

        env = get_settings().env
    return {
        name: cls
        for name, cls in CUSTOM_COLLECTORS.items()
        if env == "dev" or name not in DEV_ONLY
    }


COLLECTOR_HELP = "Which built-in custom collector to run"


class CustomConfig(BaseModel):
    # The choices depend on BK_ENV, so the form and JSON schema get them from
    # ``patch_form`` at request time, not from this static model.
    model_config = ConfigDict(extra="forbid")
    collector: str = Field(description=COLLECTOR_HELP + ".")
    options: dict[str, Any] = Field(
        default={}, description="Settings for the chosen collector (see its form)."
    )

    @field_validator("collector")
    @classmethod
    def _known(cls, v: str) -> str:
        allowed = available_collectors()
        if v not in allowed:
            raise ValueError(
                f"unknown custom collector {v!r}; choose one of "
                + ", ".join(sorted(allowed))
            )
        return v


def parse_config(config: dict[str, Any]) -> CustomConfig:
    """Validate the config and the chosen class's options. The returned config
    holds the options as that class normalised them."""
    cfg = parse_model(CustomConfig, config, "custom")
    options_model = CUSTOM_COLLECTORS[cfg.collector].Options
    try:
        options = options_model.model_validate(cfg.options)
    except ValidationError as e:
        raise CollectorError(f"invalid options for {cfg.collector}: {e}") from None
    return CustomConfig(
        collector=cfg.collector,
        options=options.model_dump(mode="json", exclude_none=True),
    )


def build(client: FetchClient, config: dict[str, Any], *, preview: bool = False):
    cfg = parse_config(config)
    cls = CUSTOM_COLLECTORS[cfg.collector]
    return cls(client, cls.Options.model_validate(cfg.options), preview=preview)


class CustomCollector:
    """What the registry hands out: resolves the allowlisted class per source at
    fetch time (the config is per source)."""

    def __init__(self, client: FetchClient, *, preview: bool = False) -> None:
        self.client = client
        self.preview = preview

    def fetch(self, source) -> list[RawItem]:
        return build(self.client, source.config or {}, preview=self.preview).fetch(
            source
        )


def option_forms(env: str | None = None) -> dict[str, dict[str, Any]]:
    from blackkite.collectors.forms import describe

    return {
        name: {"help": cls.help, "fields": describe(cls.Options)}
        for name, cls in available_collectors(env).items()
    }


def patch_form(form: dict[str, Any], env: str | None = None) -> None:
    """Fill the env-dependent parts of the ``custom`` config form in place: the
    ``collector`` choices (field and JSON schema) and the per-collector forms."""
    names = sorted(available_collectors(env))
    help_text = f"{COLLECTOR_HELP}: {', '.join(names)}"
    for f in form["fields"]:
        if f["name"] == "collector":
            f.update(type="enum", choices=names, help=help_text)
    prop = form["json_schema"]["properties"]["collector"]
    prop.update(enum=names, description=help_text)
    form["collectors"] = option_forms(env)
