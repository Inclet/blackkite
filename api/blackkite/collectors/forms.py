"""Form descriptions of collector config models, for the admin config editor.

``describe(Model)`` turns a Pydantic config model into a list of fields::

    {"name": "feed_url", "type": "string", "required": True,
     "help": "Address of the RSS or Atom feed.", "default": None}

``type`` is one of ``string``, ``integer``, ``number``, ``boolean``, ``array``,
``object`` (or ``enum`` with ``choices``). Arrays carry ``items`` (the item type,
or the item fields for arrays of objects); nested objects carry ``fields``; a
choice of shapes carries ``variants`` (a field list each) and the
``discriminator`` field that tells them apart; free-form objects (a mapping of
names to values) carry ``free_form: true`` and ``values``: ``"string"`` when every
value may be a string (string-to-string maps), else ``"any"``. Every
field has help text: a model without a description on some field is a bug, and
``describe`` raises so the tests catch it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _resolve(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref:
        return defs[ref.rsplit("/", 1)[-1]]
    return schema


def _non_null(schema: dict[str, Any], defs: dict[str, Any]) -> tuple[dict, bool]:
    """(the schema without its null branch, whether null was allowed)."""
    schema = _resolve(schema, defs)
    options = schema.get("anyOf")
    if not options:
        return schema, False
    rest = [o for o in options if o.get("type") != "null"]
    nullable = len(rest) < len(options)
    if len(rest) == 1:
        merged = {**_resolve(rest[0], defs)}
        for k in ("description", "default", "title"):
            if k in schema:
                merged.setdefault(k, schema[k])
        return merged, nullable
    # A union of several shapes (e.g. a selector string or {css, attr}): offer the
    # first one in the form; the API accepts every documented shape.
    merged = {**_resolve(rest[0], defs), "alternatives": len(rest)}
    for k in ("description", "default"):
        if k in schema:
            merged[k] = schema[k]
    return merged, nullable


def _value_type(schema: Any, defs: dict[str, Any]) -> str:
    """ "string" when a free-form object's values may all be given as strings."""
    if not isinstance(schema, dict):
        return "any"
    schema = _resolve(schema, defs)
    options = schema.get("anyOf") or [schema]
    types_ = {_resolve(o, defs).get("type") for o in options}
    return "string" if "string" in types_ and None not in types_ else "any"


def _field(
    name: str,
    schema: dict[str, Any],
    required: bool,
    defs: dict[str, Any],
    help_text: str | None,
) -> dict[str, Any]:
    s, _ = _non_null(schema, defs)
    help_text = help_text or s.get("description")
    if not help_text:
        raise ValueError(f"config field {name!r} has no help text")
    out: dict[str, Any] = {"name": name, "required": required, "help": help_text}
    if "enum" in s or "const" in s:
        out["type"] = "enum"
        out["choices"] = list(s.get("enum") or [s["const"]])
    else:
        out["type"] = s.get("type", "object")
    if "default" in schema or "default" in s:
        out["default"] = schema.get("default", s.get("default"))
    for k in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
        if k in s:
            out[k] = s[k]
    if "oneOf" in s:
        # A choice of shapes (e.g. pagination by page number or by next link): one
        # set of fields per variant, told apart by the discriminator field.
        out["type"] = "object"
        disc = (s.get("discriminator") or {}).get("propertyName")
        if disc:
            out["discriminator"] = disc
        out["variants"] = [_fields(_resolve(v, defs), defs) for v in s["oneOf"]]
        return out
    if out["type"] == "array":
        items, _ = _non_null(s.get("items", {}), defs)
        if items.get("type") == "object" and "properties" in items:
            out["items"] = {"type": "object", "fields": _fields(items, defs)}
        else:
            out["items"] = {"type": items.get("type", "string")}
    elif out["type"] == "object" and "properties" in s:
        out["fields"] = _fields(s, defs)
    elif out["type"] == "object":
        out["free_form"] = True
        out["values"] = _value_type(s.get("additionalProperties", True), defs)
    if s.get("alternatives"):
        out["alternatives"] = s["alternatives"]
    return out


def _fields(schema: dict[str, Any], defs: dict[str, Any]) -> list[dict[str, Any]]:
    required = set(schema.get("required", []))
    return [
        _field(name, prop, name in required, defs, prop.get("description"))
        for name, prop in schema.get("properties", {}).items()
    ]


def describe(model: type[BaseModel]) -> list[dict[str, Any]]:
    schema = model.model_json_schema()
    return _fields(schema, schema.get("$defs", {}))
