"""Config form schema per collector type (spec 4.2), for the admin source editor.

GET /api/admin/collector-types. Every collector type has its own Pydantic config
model now (``blackkite.collectors.registry.CONFIG_MODELS``), so the fields come
straight from ``registry.config_forms()`` (``collectors/forms.py``), mapped here to
the field format the web editor reads (docs/api-contract.md section 4):

    {name, kind, required, help, default, options, min, max, fields}

``kind`` values: string, url, integer, number, boolean, choice (with ``options``),
string_list, selector (a CSS string or ``{css, attr}``), object (with ``fields``),
object_list (with ``fields``), map (string to string), json.

Shapes the web form has no widget for are sent as ``json`` with the shapes spelled
out in the help text: a choice of variants (json_api ``pagination``) and the
per-collector ``options`` of ``custom``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from blackkite.db.models import COLLECTOR_TYPES

URL_NAMES = frozenset({"url", "endpoint", "feed_url", "list_url"})
SELECTOR_FIELDS = frozenset({"css", "attr"})


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
    schema_source: str  # always "model": every type has a config model
    fields: list[ConfigField] = field(default_factory=list)


def _names(fields: list[dict[str, Any]]) -> str:
    return ", ".join(
        f["name"] + ("" if not f.get("required") else " (required)") for f in fields
    )


def _variants_help(f: dict[str, Any]) -> str:
    disc = f.get("discriminator")
    parts = []
    for variant in f["variants"]:
        tag = next((v for v in variant if v["name"] == disc), None)
        label = f"{disc} {tag['choices'][0]}" if tag and tag.get("choices") else "or"
        rest = [v for v in variant if v["name"] != disc]
        parts.append(f"{label}: {_names(rest)}" if rest else label)
    return "JSON object, one of: " + "; ".join(parts) + "."


def _is_url_field(f: dict[str, Any], top_level: bool) -> bool:
    """An address the editor should check as a URL: a top-level config field named
    url/endpoint/feed_url/list_url or ending in ``_url``. The config models type
    these as plain ``str`` (validated by ``safe_url``), so the name is the signal.
    Fields nested inside an object (a json_api ``mapping``, a selector set) are
    never URLs: there ``url`` is a dotted path or a CSS selector for the link."""
    name = f["name"]
    return top_level and (name in URL_NAMES or name.endswith("_url"))


def _kind(f: dict[str, Any], top_level: bool = True) -> str:
    t = f["type"]
    if t == "enum":
        return "choice"
    if t == "string":
        return "url" if _is_url_field(f, top_level) else "string"
    if t in ("integer", "number", "boolean"):
        return t
    if t == "array":
        items = f.get("items") or {}
        if items.get("fields"):
            return "object_list"
        return "string_list" if items.get("type") == "string" else "json"
    if t == "object":
        if "variants" in f:
            return "json"
        sub = f.get("fields")
        if sub is not None:
            return (
                "selector" if {s["name"] for s in sub} == SELECTOR_FIELDS else "object"
            )
        return "map" if f.get("free_form") and f.get("values") == "string" else "json"
    return "json"


def to_field(f: dict[str, Any], top_level: bool = True) -> ConfigField:
    """One field of ``forms.describe`` in the editor's format. ``top_level`` is
    False for fields nested inside an object or a list of objects."""
    kind = _kind(f, top_level)
    help_text = f["help"]
    if "variants" in f:
        help_text = f"{help_text} {_variants_help(f)}"
    nested: list[dict[str, Any]] | None = None
    if kind == "object":
        nested = f["fields"]
    elif kind == "object_list":
        nested = f["items"]["fields"]
    choices = f.get("choices")
    return ConfigField(
        name=f["name"],
        kind=kind,
        required=f["required"],
        help=help_text,
        default=f.get("default"),
        options=[str(c) for c in choices] if kind == "choice" and choices else None,
        min=f.get("minimum"),
        max=f.get("maximum"),
        fields=[to_field(n, top_level=False) for n in nested]
        if nested is not None
        else None,
    )


def _custom_options_help(collectors: dict[str, dict[str, Any]]) -> str:
    return " ".join(
        f"{name}: {_names(c['fields'])}." if c.get("fields") else f"{name}: none."
        for name, c in sorted(collectors.items())
    )


def form_fields(form: dict[str, Any]) -> list[ConfigField]:
    out = [to_field(f) for f in form["fields"]]
    collectors = form.get("collectors")
    if collectors:
        for f in out:
            if f.name == "options":
                f.help = f"{f.help} {_custom_options_help(collectors)}"
    return out


def collector_type_schemas() -> list[CollectorTypeSchema]:
    from blackkite.collectors import registry

    forms = registry.config_forms()
    implemented = set(registry.IMPLEMENTED)
    return [
        CollectorTypeSchema(
            ctype, ctype in implemented, "model", form_fields(forms[ctype])
        )
        for ctype in COLLECTOR_TYPES
    ]
