"""Config form schema per collector type (spec 4.2), for the admin source editor.

The web editor renders a form from this instead of hard-coding each type. Fields
come from the collector's own Pydantic config model when it has one, found by
convention in ``blackkite.collectors.<type>``:

1. a module attribute ``CONFIG_MODEL``, else
2. the return annotation of ``parse_config``, else
3. a class named ``<CamelType>Config`` (``rss`` -> ``RssConfig``).

A type with no module or model yet gets the fields spec 4.2 names for it
(``DECLARED`` below; docs/api-contract.md section 4), marked ``schemaSource:
"declared"``. Help text comes from the model field's ``description`` when set,
else from ``HELP`` here, so collectors/ need not change for the editor.

Field ``kind`` values: string, url, integer, number, boolean, choice (with
``options``), string_list, selector (a CSS string or ``{css, attr}``), object
(with ``fields``), object_list (with ``fields``), map (string to string), json.
"""

from __future__ import annotations

import importlib
import logging
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Literal, Union, get_args, get_origin

import annotated_types as at
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, to_jsonable_python

from blackkite.db.models import COLLECTOR_TYPES

log = logging.getLogger("blackkite.sources")

Kind = Literal[
    "string",
    "url",
    "integer",
    "number",
    "boolean",
    "choice",
    "string_list",
    "selector",
    "object",
    "object_list",
    "map",
    "json",
]

# Help text by (collector type, dotted path), then by field name for any type.
HELP: dict[tuple[str, str], str] = {
    ("html_list", "list_url"): "Listing page to fetch (page 1).",
    ("html_list", "pagination_pattern"): (
        "URL of further pages with {page} where the page number goes."
    ),
    ("html_list", "first_page"): "Page number of the first pattern page.",
    ("html_list", "max_pages"): "Pages to fetch in total, counting the list URL.",
    ("html_list", "selectors"): "Where each listing and its fields are on the page.",
    ("html_list", "selectors.item"): "CSS selector matching one node per listing.",
    ("html_list", "detail"): "Optional: follow each listing to its detail page.",
    ("html_list", "detail.selectors"): (
        "Fields read from the detail page; they win over the listing's."
    ),
    ("html_list", "detail.max_items"): "Detail pages to follow per run at most.",
    ("search_query", "queries"): "Search queries, one per line.",
    ("search_query", "domains"): (
        "Restrict results to these domains (adds site:); empty for any site."
    ),
    ("search_query", "recency_days"): "Only results from the last N days.",
    ("search_query", "count"): "Results per query (1-20).",
}
HELP_BY_NAME: dict[str, str] = {
    "title": "Selector for the listing's title.",
    "link": "Selector for the link (default: the <a> in or around the title).",
    "date": "Selector for the published date.",
    "deadline": "Selector for the closing date.",
    "organisation": "Selector for the issuing organisation.",
    "snippet": "Selector for a short description.",
    "css": "CSS selector.",
    "attr": "Attribute to read instead of the text (for example href).",
}
URL_NAMES = frozenset({"url", "endpoint", "feed_url", "list_url"})


@dataclass
class ConfigField:
    name: str
    kind: str
    required: bool
    help: str = ""
    default: Any = None
    options: list[str] | None = None
    min: float | None = None
    max: float | None = None
    fields: list[ConfigField] | None = None


@dataclass
class CollectorTypeSchema:
    type: str
    implemented: bool
    schema_source: str  # "model" | "declared"
    fields: list[ConfigField] = field(default_factory=list)


def _f(name: str, kind: str, required: bool, help: str, **kw: Any) -> ConfigField:
    return ConfigField(name=name, kind=kind, required=required, help=help, **kw)


# Spec 4.2 fields for types whose collector has no config model yet. Replaced
# automatically once the collector module defines one.
DECLARED: dict[str, list[ConfigField]] = {
    "rss": [_f("feed_url", "url", True, "RSS or Atom feed URL.")],
    "json_api": [
        _f("endpoint", "url", True, "JSON endpoint the site's front end calls."),
        _f("params", "map", False, "Query parameters sent with each request."),
        _f(
            "field_mapping",
            "map",
            True,
            "Item field (title, url, deadline, ...) to its path in the JSON.",
        ),
    ],
    "email_ingest": [
        _f(
            "sender",
            "string",
            True,
            "Sender address or pattern to pick from the shared inbox.",
        )
    ],
    "custom": [
        _f(
            "class_name",
            "string",
            True,
            "Name of a collector class from the allowlist in code.",
        )
    ],
}
# browser_list: "same as html_list, rendered with a headless browser" (spec 4.2).
SAME_AS = {"browser_list": "html_list"}


def config_model(collector_type: str) -> type[BaseModel] | None:
    try:
        mod = importlib.import_module(f"blackkite.collectors.{collector_type}")
    except ModuleNotFoundError as e:
        if e.name != f"blackkite.collectors.{collector_type}":
            log.warning("collector %s failed to import: %s", collector_type, e)
        return None
    except Exception as e:  # noqa: BLE001 - a broken collector must not break the editor
        log.warning("collector %s failed to import: %s", collector_type, e)
        return None
    candidates: list[Any] = [getattr(mod, "CONFIG_MODEL", None)]
    parse = getattr(mod, "parse_config", None)
    if parse is not None:
        try:
            candidates.append(typing.get_type_hints(parse).get("return"))
        except (NameError, TypeError) as e:
            log.warning(
                "collector %s: unreadable parse_config hints: %s", collector_type, e
            )
    camel = "".join(p.capitalize() for p in collector_type.split("_"))
    candidates.append(getattr(mod, f"{camel}Config", None))
    for c in candidates:
        if isinstance(c, type) and issubclass(c, BaseModel):
            return c
    return None


def _strip_optional(t: Any) -> tuple[Any, bool]:
    origin = get_origin(t)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return t, False


def _strip_annotated(t: Any) -> Any:
    while get_origin(t) is typing.Annotated:
        t = get_args(t)[0]
    return t


def _is_selector(model: type[BaseModel]) -> bool:
    return set(model.model_fields) == {"css", "attr"}


def _kind(name: str, t: Any) -> tuple[str, dict[str, Any]]:
    t, _ = _strip_optional(_strip_annotated(t))
    t = _strip_annotated(t)
    origin = get_origin(t)
    if isinstance(t, type) and issubclass(t, BaseModel):
        return ("selector", {}) if _is_selector(t) else ("object", {"model": t})
    if origin is Literal:
        return "choice", {"options": [str(a) for a in get_args(t)]}
    if origin in (list, tuple, set, frozenset):
        (inner,) = get_args(t)[:1] or (Any,)
        inner, _ = _strip_optional(_strip_annotated(inner))
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            if _is_selector(inner):
                return "json", {}
            return "object_list", {"model": inner}
        return "string_list", {}
    if origin is dict:
        args = get_args(t)
        return ("map", {}) if len(args) == 2 and args[1] is str else ("json", {})
    if t is bool:
        return "boolean", {}
    if t is int:
        return "integer", {}
    if t is float:
        return "number", {}
    if t is str:
        return (
            ("url", {})
            if name in URL_NAMES or name.endswith("_url")
            else (
                "string",
                {},
            )
        )
    return "json", {}


def _metadata(info: FieldInfo) -> list[Any]:
    """Constraints on the field, including those inside ``Annotated[...] | None``."""
    found = list(info.metadata)
    t, _ = _strip_optional(info.annotation)
    while get_origin(t) is typing.Annotated:
        for m in get_args(t)[1:]:
            found.extend(m.metadata if isinstance(m, FieldInfo) else [m])
        t = get_args(t)[0]
    return found


def _bounds(info: FieldInfo) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in _metadata(info):
        if isinstance(m, at.Ge | at.Gt):
            out["min"] = float(getattr(m, "ge", getattr(m, "gt", 0)))
        if isinstance(m, at.Le | at.Lt):
            out["max"] = float(getattr(m, "le", getattr(m, "lt", 0)))
    return out


def _default(info: FieldInfo) -> Any:
    if info.is_required():
        return None
    try:
        value = info.get_default(call_default_factory=True)
    except TypeError:
        value = info.get_default()
    if value is PydanticUndefined:
        return None
    try:
        return to_jsonable_python(value)
    except (TypeError, ValueError):  # pydantic_core raises PydanticSerializationError
        return None


def model_fields(
    ctype: str, model: type[BaseModel], prefix: str = ""
) -> list[ConfigField]:
    out = []
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        extra = (
            info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        )
        kind, more = _kind(name, info.annotation)
        if isinstance(extra.get("kind"), str):
            kind = extra["kind"]
        nested = more.pop("model", None)
        help_text = (
            info.description or HELP.get((ctype, path)) or HELP_BY_NAME.get(name) or ""
        )
        out.append(
            ConfigField(
                name=name,
                kind=kind,
                required=info.is_required(),
                help=help_text,
                default=_default(info),
                options=more.get("options"),
                fields=model_fields(ctype, nested, f"{path}.") if nested else None,
                **_bounds(info),
            )
        )
    return out


def collector_type_schemas() -> list[CollectorTypeSchema]:
    from blackkite.collectors import registry

    implemented = set(getattr(registry, "IMPLEMENTED", ()))
    out = []
    for ctype in COLLECTOR_TYPES:
        model = config_model(ctype)
        if model is not None:
            out.append(
                CollectorTypeSchema(
                    ctype, ctype in implemented, "model", model_fields(ctype, model)
                )
            )
            continue
        same = SAME_AS.get(ctype)
        same_model = config_model(same) if same else None
        fields = (
            model_fields(same, same_model)
            if same_model is not None
            else list(DECLARED.get(ctype, []))
        )
        out.append(CollectorTypeSchema(ctype, ctype in implemented, "declared", fields))
    return out
