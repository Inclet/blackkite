"""GET /api/admin/collector-types: config form schema per collector type (spec 4.2),
read from the collectors' own config forms (registry.config_forms)."""

from __future__ import annotations

import pytest

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
    assert url["help"] == "Address of the listing page (page 1)."
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


def test_every_type_comes_from_its_config_model(admin_client):
    for s in admin_client.get("/api/admin/collector-types").json():
        assert s["implemented"] is True and s["schemaSource"] == "model", s["type"]


def test_rss_fields(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["rss"]
    assert [f["name"] for f in s["fields"]] == [
        "feed_url",
        "max_items",
        "author_as_organisation",
    ]
    feed = _field(s["fields"], "feed_url")
    assert (feed["kind"], feed["required"]) == ("url", True)
    flag = _field(s["fields"], "author_as_organisation")
    assert (flag["kind"], flag["default"]) == ("boolean", False)


def test_json_api_fields(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["json_api"]
    f = {x["name"]: x for x in s["fields"]}
    assert f["endpoint"]["kind"] == "url"
    # Values may be numbers too, but strings are accepted: a map editor works.
    assert f["params"]["kind"] == "map" and f["params"]["default"] == {}
    pag = f["pagination"]
    assert pag["kind"] == "json" and pag["required"] is False
    assert "mode page: param, start, max_pages" in pag["help"]
    assert "mode next_link: path (required), max_pages" in pag["help"]
    mapping = f["mapping"]
    assert mapping["kind"] == "object" and mapping["required"] is True
    assert _field(mapping["fields"], "title")["kind"] == "string"
    assert _field(mapping["fields"], "extra")["kind"] == "map"
    # mapping.url is a dotted path into each item ("link"), not an address.
    assert _field(mapping["fields"], "url")["kind"] == "string"
    assert _field(mapping["fields"], "url_template")["kind"] == "string"


def test_only_top_level_address_fields_are_urls(admin_client):
    by = _by_type(admin_client.get("/api/admin/collector-types").json())
    assert _field(by["html_list"]["fields"], "list_url")["kind"] == "url"
    assert _field(by["browser_list"]["fields"], "list_url")["kind"] == "url"
    assert _field(by["json_api"]["fields"], "endpoint")["kind"] == "url"
    assert _field(by["rss"]["fields"], "feed_url")["kind"] == "url"

    def nested_urls(fields):
        for f in fields:
            for n in f.get("fields") or []:
                if n["kind"] == "url":
                    yield f"{f['name']}.{n['name']}"
                yield from nested_urls([n])

    for s in by.values():
        assert list(nested_urls(s["fields"])) == [], s["type"]


def test_nested_field_named_url_is_a_string():
    f = ct.to_field(
        {
            "name": "mapping",
            "type": "object",
            "required": True,
            "help": "h",
            "fields": [
                {"name": "url", "type": "string", "required": True, "help": "p"},
                {"name": "page_url", "type": "string", "required": False, "help": "p"},
            ],
        }
    )
    assert [n.kind for n in f.fields] == ["string", "string"]
    top = ct.to_field({"name": "url", "type": "string", "required": True, "help": "h"})
    assert top.kind == "url"


def test_email_ingest_fields(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["email_ingest"]
    sender = _field(s["fields"], "sender")
    assert (sender["kind"], sender["required"]) == ("string", True)
    mode = _field(s["fields"], "parse_mode")
    assert (mode["kind"], mode["options"], mode["default"]) == (
        "choice",
        ["links", "message"],
        "links",
    )


def test_custom_fields_name_each_collectors_options(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["custom"]
    which = _field(s["fields"], "collector")
    assert which["kind"] == "choice" and "jsonld_events" in which["options"]
    opts = _field(s["fields"], "options")
    assert opts["kind"] == "json"
    assert "jsonld_events: list_url (required)" in opts["help"]


def test_browser_list_has_html_list_fields_and_wait_for(admin_client):
    s = _by_type(admin_client.get("/api/admin/collector-types").json())
    names = [f["name"] for f in s["browser_list"]["fields"]]
    assert names == [f["name"] for f in s["html_list"]["fields"]] + ["wait_for"]


def test_every_field_kind_is_one_the_editor_knows():
    kinds = {
        "string", "url", "integer", "number", "boolean", "choice", "string_list",
        "selector", "object", "object_list", "map", "json",
    }  # fmt: skip

    def walk(fields):
        for f in fields:
            assert f.kind in kinds and f.help, f
            if f.kind in ("object", "object_list"):
                assert f.fields
                walk(f.fields)
            else:
                assert f.fields is None, f

    for s in ct.collector_type_schemas():
        walk(s.fields)


def test_object_lists_map_to_nested_fields():
    f = ct.to_field(
        {
            "name": "rows",
            "required": False,
            "help": "Rows.",
            "type": "array",
            "items": {
                "type": "object",
                "fields": [
                    {"name": "a", "required": True, "help": "A.", "type": "integer"}
                ],
            },
            "minimum": None,
        }
    )
    assert f.kind == "object_list" and [x.name for x in f.fields] == ["a"]


def test_requires_admin(client, db, outbox):
    make_user(db, "m@example.com")
    member = sign_in(client, outbox, "m@example.com")
    assert member.get("/api/admin/collector-types").status_code == 403


DEMO_SOURCE = {
    "name": "Demo Example",
    "home_url": "https://demo.example.com",
    "publisher": "Demo",
    "streams": ["event"],
    "kind": "publisher",
    "collector_type": "custom",
    "config": {"collector": "demo_fictional", "options": {}},
}


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_demo_fictional_only_offered_and_accepted_in_dev(admin_client, bk_env, env):
    bk_env(env)
    s = _by_type(admin_client.get("/api/admin/collector-types").json())["custom"]
    which = _field(s["fields"], "collector")
    opts = _field(s["fields"], "options")
    created = admin_client.post("/api/admin/sources", json=DEMO_SOURCE)
    preview = admin_client.post(
        "/api/admin/sources/test-run",
        json={k: DEMO_SOURCE[k] for k in ("home_url", "collector_type", "config")},
    )
    if env == "dev":
        assert which["options"] == ["demo_fictional", "jsonld_events"]
        assert "demo_fictional: none." in opts["help"]
        assert created.status_code == 201, created.text
        assert preview.status_code == 200, preview.text
        return
    assert which["options"] == ["jsonld_events"]
    assert "demo_fictional" not in which["help"] + opts["help"]
    for r in (created, preview):
        assert r.status_code == 422, r.text
        assert "unknown custom collector" in r.text
