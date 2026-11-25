"""Admin-facing refusals in plain words: test runs and saves answer
{detail, errors} with no Pydantic boilerplate and no URLs; a test run refused
before any request reports 0 requests."""

from __future__ import annotations

import re

import pytest

from blackkite.collectors.problems import Problem, config_label, label, plain
from blackkite.routes.sources import get_preview_client_factory
from tests.conftest import make_user, sign_in
from tests.fakes import FakeWeb, make_client
from tests.test_sources_api import HTML_CONFIG, LIST_HTML, add_source, body, new_client


@pytest.fixture
def web(app) -> FakeWeb:
    w = FakeWeb()
    w.html("notices.example", "/tenders", LIST_HTML)
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(w)
    )
    return w


@pytest.fixture
def admin(app, db, outbox):
    make_user(db, "admin@example.com", role="admin")
    return sign_in(new_client(app), outbox, "admin@example.com")


BOILERPLATE = re.compile(
    r"validation error|errors\.pydantic|input_value|type=|Value error|"
    r"Field required|Extra inputs|https?://",
    re.IGNORECASE,
)
TEST_RUN = "/api/admin/sources/test-run"


def check_plain(out: dict) -> None:
    assert set(out) == {"detail", "errors"}
    assert out["detail"].endswith(".")
    assert not BOILERPLATE.search(out["detail"]), out["detail"]
    for e in out["errors"]:
        assert set(e) == {"field", "message"}
        assert not BOILERPLATE.search(e["message"]), e


@pytest.mark.parametrize(
    "run, detail, errors",
    [
        (
            {"collector_type": "rss", "config": {"feed_url": "http://127.0.0.1/feed"}},
            "Feed URL: address 127.0.0.1 is not public.",
            [
                {
                    "field": "config.feed_url",
                    "message": "address 127.0.0.1 is not public",
                }
            ],
        ),
        (
            {"collector_type": "rss", "config": {}},
            "Feed URL: is required.",
            [{"field": "config.feed_url", "message": "is required"}],
        ),
        (
            {
                "collector_type": "html_list",
                "config": {
                    "list_url": "https://x.example/",
                    "selectors": {"item": "li[", "title": "a"},
                },
            },
            "Item selector: invalid CSS selector 'li[': Can't parse CSS selector.",
            [
                {
                    "field": "config.selectors.item",
                    "message": "invalid CSS selector 'li[': Can't parse CSS selector",
                }
            ],
        ),
        (
            {
                "collector_type": "html_list",
                "config": HTML_CONFIG,
                "homeUrl": "http://10.0.0.1/",
            },
            "Home page: address 10.0.0.1 is not public.",
            [{"field": "homeUrl", "message": "address 10.0.0.1 is not public"}],
        ),
        (
            {"collector_type": "search_query", "config": {"queries": []}},
            None,
            None,
        ),
    ],
)
def test_unsaved_test_run_refusals_are_plain(admin, web, run, detail, errors):
    r = admin.post(TEST_RUN, json=run)
    assert r.status_code == 422
    out = r.json()
    check_plain(out)
    if detail is not None:
        assert out == {"detail": detail, "errors": errors}
    assert web.requests == []


def test_several_problems_one_sentence_each(admin, web):
    r = admin.post(
        TEST_RUN,
        json={
            "collector_type": "html_list",
            "config": {"list_url": "http://127.0.0.1/", "bogus": 1},
            "rateLimit": 0.5,
        },
    )
    out = r.json()
    check_plain(out)
    assert out["detail"] == (
        "List URL: address 127.0.0.1 is not public. "
        "Selectors: is required. "
        "Bogus: is not a setting this accepts. "
        "Seconds between requests: must be at least 1."
    )
    assert {e["field"] for e in out["errors"]} == {
        "rateLimit",
        "config.list_url",
        "config.selectors",
        "config.bogus",
    }


def test_save_refusals_are_plain(admin, db):
    cases = [
        (
            body(collector_type="rss", config={"feed_url": "http://192.168.1.1/x"}),
            "Feed URL: address 192.168.1.1 is not public.",
        ),
        (body(home_url="http://localhost/"), "Home page: localhost is not allowed."),
        (body(name=""), "Name: must not be empty."),
        (body(rate_limit=0.1), "Seconds between requests: must be at least 1."),
        (
            body(
                kind="original",
                collector_type="search_query",
                config={"queries": ["x"]},
            ),
            None,
        ),
    ]
    for b, detail in cases:
        r = admin.post("/api/admin/sources", json=b)
        assert r.status_code == 422, r.text
        check_plain(r.json())
        if detail:
            assert r.json()["detail"] == detail
    kind = admin.post(
        "/api/admin/sources",
        json=body(
            kind="original", collector_type="search_query", config={"queries": ["x"]}
        ),
    ).json()
    assert kind["errors"][0]["field"] == "kind"
    assert kind["detail"].startswith("Kind: a search_query source cannot be")

    s = add_source(db, "X")
    r = admin.patch(
        f"/api/admin/sources/{s.id}", json={"config": {"list_url": "http://127.0.0.1/"}}
    )
    assert r.status_code == 422
    check_plain(r.json())
    assert r.json()["detail"] == (
        "List URL: address 127.0.0.1 is not public. Selectors: is required."
    )
    r = admin.patch(f"/api/admin/sources/{s.id}", json={"name": None, "kind": None})
    assert r.json() == {
        "detail": "Kind: cannot be cleared. Name: cannot be cleared.",
        "errors": [
            {"field": "kind", "message": "cannot be cleared"},
            {"field": "name", "message": "cannot be cleared"},
        ],
    }
    add_source(db, "Taken")
    r = admin.patch(f"/api/admin/sources/{s.id}", json={"name": "Taken"})
    assert r.status_code == 409
    assert r.json() == {
        "detail": "A source with that name already exists.",
        "errors": [
            {"field": "name", "message": "a source with that name already exists"}
        ],
    }


def test_saved_test_run_with_a_bad_stored_config(admin, db, web):
    rss = add_source(
        db, "Feed", collector_type="rss", config={"feed_url": "http://127.0.0.1/"}
    )
    out = admin.post(f"/api/admin/sources/{rss.id}/test-run").json()
    assert out["ok"] is False
    assert out["error"] == "Feed URL: address 127.0.0.1 is not public."
    assert out["errors"] == [
        {"field": "config.feed_url", "message": "address 127.0.0.1 is not public"}
    ]
    assert out["requestsMade"] == 0 and web.requests == []


def test_guard_refusal_before_any_request_reports_0_requests(app, admin):
    w = FakeWeb()
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(w, resolver=lambda h, p: ["10.0.0.7"])
    )
    out = admin.post(
        TEST_RUN, json={"collector_type": "html_list", "config": HTML_CONFIG}
    ).json()
    assert out["ok"] is False and "non-public" in out["error"]
    assert out["requestsMade"] == 0 and out["errors"] == []
    assert w.requests == []


def test_successful_preview_has_no_errors(admin, web):
    out = admin.post(
        TEST_RUN, json={"collector_type": "html_list", "config": HTML_CONFIG}
    ).json()
    assert out["ok"] and out["errors"] == [] and out["requestsMade"] == 2


def test_labels_and_plain_messages():
    assert label(("config", "feed_url")) == "Feed URL"
    assert label(("home_url",)) == "Home page"
    assert label(("homeUrl",)) == "Home page"
    assert label(("config", "selectors", "item")) == "Item selector"
    assert label(("config", "detail_selectors", "deadline")) == (
        "Detail page deadline selector"
    )
    assert label(("config", "queries", 0)) == "Queries, item 1"
    assert config_label(("options", "list_url")) == "Options, list URL"
    assert label(()) == "Request"
    assert Problem(("home_url",), "x").field == "homeUrl"
    assert Problem(("config", "selectors", "item"), "x").field == (
        "config.selectors.item"
    )
    assert Problem((), "x").field is None
    assert plain("Value error, cannot fetch https://a.example/x.") == (
        "cannot fetch the address"
    )
    assert plain("Input should be a valid integer") == "must be a valid integer"


def test_other_admin_422s_use_the_same_shape(admin):
    r = admin.get("/api/admin/sources", params={"status": "bogus"})
    assert r.status_code == 422
    check_plain(r.json())
    assert r.json()["errors"][0]["field"] == "status"
    r = admin.post(
        TEST_RUN, content=b"{not json", headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    check_plain(r.json())
