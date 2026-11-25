"""GET /api/admin/collector-types: config form schema per collector type (spec 4.2),
read from the collectors' own config models."""

from __future__ import annotations

import sys
import types
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field

from blackkite.db.models import COLLECTOR_TYPES
from blackkite.sources import collector_types as ct
from tests.conftest import make_user, sign_in


@pytest.fixture
def admin_client(client, db, outbox):
    make_user(db, "admin@example.com", role="admin")
    return sign_in(client, outbox, "admin@example.com")


def _by_type(schemas):
    return {s["type"]: s for s in schemas}


def _field(fields, name):
    (f,) = [f for f in fields if f["name"] == name]
    return f


def test_every_type_is_listed_in_order(admin_client):
    r = admin_client.get("/api/admin/collector-types")
    assert r.status_code == 200, r.text
    assert [s["type"] for s in r.json()] == list(COLLECTOR_TYPES)
    for s in r.json():
        assert set(s) == {"type", "implemented", "schemaSource", "fields"}
        assert s["fields"], s["type"]


def test_html_list_fields_come_from_its_model(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["html_list"]
    assert s["implemented"] is True and s["schemaSource"] == "model"
    fields = s["fields"]
    assert [f["name"] for f in fields] == [
        "list_url",
        "pagination_pattern",
        "first_page",
        "max_pages",
        "selectors",
        "detail",
    ]
    url = _field(fields, "list_url")
    assert (url["kind"], url["required"]) == ("url", True) and url["help"]
    pages = _field(fields, "max_pages")
    assert (pages["kind"], pages["default"], pages["min"], pages["max"]) == (
        "integer",
        1,
        1,
        20,
    )
    sel = _field(fields, "selectors")
    assert sel["kind"] == "object" and sel["required"] is True
    assert _field(sel["fields"], "item")["kind"] == "string"
    title = _field(sel["fields"], "title")
    assert (title["kind"], title["required"]) == ("selector", True)
    assert _field(sel["fields"], "deadline")["required"] is False
    detail = _field(fields, "detail")
    assert detail["kind"] == "object" and detail["required"] is False
    assert _field(detail["fields"], "max_items")["default"] == 20


def test_search_query_fields(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["search_query"]
    assert s["schemaSource"] == "model"
    q = _field(s["fields"], "queries")
    assert (q["kind"], q["required"]) == ("string_list", True)
    days = _field(s["fields"], "recency_days")
    assert (days["kind"], days["min"], days["max"]) == ("integer", 1, 365)


def test_types_without_a_model_get_their_spec_fields(monkeypatch):
    monkeypatch.setattr(ct, "config_model", lambda t: None)
    schemas = {s.type: s for s in ct.collector_type_schemas()}
    assert [f.name for f in schemas["rss"].fields] == ["feed_url"]
    assert [f.name for f in schemas["json_api"].fields] == [
        "endpoint",
        "params",
        "field_mapping",
    ]
    assert [f.name for f in schemas["email_ingest"].fields] == ["sender"]
    assert [f.name for f in schemas["custom"].fields] == ["class_name"]
    assert all(s.schema_source == "declared" for s in schemas.values())


def test_browser_list_falls_back_to_html_list_fields():
    if ct.config_model("browser_list") is not None:
        pytest.skip("browser_list has its own config model now")
    s = {s.type: s for s in ct.collector_type_schemas()}["browser_list"]
    assert s.schema_source == "declared"
    assert [f.name for f in s.fields][:2] == ["list_url", "pagination_pattern"]


def test_a_new_collector_model_is_picked_up_by_convention(monkeypatch):
    """A module blackkite.collectors.<type> with a <Type>Config model replaces the
    declared fields with no change here; descriptions become help text."""

    class Mapping(BaseModel):
        title: str
        url: str = "link"

    class JsonApiConfig(BaseModel):
        endpoint: str = Field(description="Where the JSON comes from.")
        method: Literal["GET", "POST"] = "GET"
        page_size: Annotated[int, Field(ge=1, le=100)] | None = None
        params: dict[str, str] = {}
        mapping: Mapping
        flags: list[Mapping] = []
        raw: dict[str, int] = {}
        insecure: bool = False

    mod = types.ModuleType("blackkite.collectors.json_api")
    mod.JsonApiConfig = JsonApiConfig
    monkeypatch.setitem(sys.modules, "blackkite.collectors.json_api", mod)
    s = {s.type: s for s in ct.collector_type_schemas()}["json_api"]
    assert s.schema_source == "model"
    got = {f.name: f for f in s.fields}
    assert (got["endpoint"].kind, got["endpoint"].help) == (
        "url",
        "Where the JSON comes from.",
    )
    assert (got["method"].kind, got["method"].options) == ("choice", ["GET", "POST"])
    assert (got["page_size"].min, got["page_size"].max) == (1, 100)
    assert got["params"].kind == "map" and got["raw"].kind == "json"
    assert got["mapping"].kind == "object"
    assert [f.name for f in got["mapping"].fields] == ["title", "url"]
    assert got["flags"].kind == "object_list"
    assert got["insecure"].kind == "boolean" and got["insecure"].default is False


def test_a_collector_that_fails_to_import_falls_back(monkeypatch):
    real = ct.importlib.import_module

    def boom(name):
        if name == "blackkite.collectors.rss":
            raise RuntimeError("broken collector")
        return real(name)

    monkeypatch.setattr(ct.importlib, "import_module", boom)
    s = {s.type: s for s in ct.collector_type_schemas()}["rss"]
    assert s.schema_source == "declared" and s.fields
