"""Limits on member suggestions (per user, per day) and on admin test runs (at
most N in flight at once, browser_list included)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from blackkite.app import create_app
from blackkite.collectors import browser_list
from blackkite.db.models import SourceSuggestion
from blackkite.db.session import get_db
from blackkite.delivery.mail import get_mail_transport
from blackkite.routes.sources import get_preview_client_factory
from blackkite.sources.testrun import TEST_RUN_BUSY, TestRunBusy, TestRunGate
from tests.conftest import make_user, sign_in
from tests.fakes import FakeWeb, make_client

H = "notices.example"
LIST_HTML = '<ul><li><a href="/n/1">Invitation for Bids: cold rooms</a></li></ul>'
HTML_RUN = {
    "collector_type": "html_list",
    "config": {"list_url": f"https://{H}/t", "selectors": {"item": "li", "title": "a"}},
}
BROWSER_RUN = {
    "collector_type": "browser_list",
    "config": {
        "list_url": f"https://{H}/app",
        "selectors": {"item": "li", "title": "a"},
    },
}


def build(settings, Sessions, outbox, **over):
    app = create_app(settings.model_copy(update=over))

    def _db():
        with Sessions() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_mail_transport] = lambda: outbox
    web = FakeWeb()
    web.html(H, "/t", LIST_HTML)
    app.dependency_overrides[get_preview_client_factory] = lambda: (
        lambda: make_client(web)
    )
    return app


def signed_in(app, db, outbox, email, role="member"):
    make_user(db, email, role=role)
    return sign_in(TestClient(app, base_url="https://testserver"), outbox, email)


# --- suggestions ---------------------------------------------------------------------


def suggest(c, n):
    return c.post("/api/source-suggestions", json={"url": f"https://s{n}.example/"})


def test_suggestions_are_limited_per_user_per_day(settings, Sessions, db, outbox):
    app = build(settings, Sessions, outbox, suggestions_per_user_per_day=3)
    ana = signed_in(app, db, outbox, "ana@example.com")
    ben = signed_in(app, db, outbox, "ben@example.com")
    assert [suggest(ana, n).status_code for n in range(3)] == [201, 201, 201]
    r = suggest(ana, 3)
    assert r.status_code == 429
    assert r.json() == {
        "detail": "You can suggest up to 3 sources a day. Please try again tomorrow."
    }
    assert len(ana.get("/api/source-suggestions").json()) == 3
    # Another user has their own allowance.
    assert suggest(ben, 0).status_code == 201
    # Suggestions older than a day no longer count.
    db.execute(
        sa.update(SourceSuggestion).values(
            created_at=datetime.now(UTC) - timedelta(hours=25)
        )
    )
    db.commit()
    assert suggest(ana, 4).status_code == 201


def test_suggestion_limit_defaults_to_ten(app, db, outbox, settings):
    assert settings.suggestions_per_user_per_day == 10
    ana = signed_in(app, db, outbox, "ana@example.com")
    assert all(suggest(ana, n).status_code == 201 for n in range(10))
    assert suggest(ana, 10).status_code == 429


def test_suggestion_limit_holds_under_concurrent_requests(
    settings, Sessions, db, outbox
):
    app = build(settings, Sessions, outbox, suggestions_per_user_per_day=2)
    ana = signed_in(app, db, outbox, "ana@example.com")
    with ThreadPoolExecutor(6) as pool:
        codes = sorted(pool.map(lambda n: suggest(ana, n).status_code, range(6)))
    assert codes == [201, 201, 429, 429, 429, 429]


# --- test runs -----------------------------------------------------------------------


def test_gate_never_waits():
    gate = TestRunGate(2)
    with (
        gate.slot(),
        gate.slot(),
        pytest.raises(TestRunBusy, match="try again in a minute"),
        gate.slot(),
    ):
        pass
    with gate.slot():
        pass  # slots come back, also after an error
    with pytest.raises(RuntimeError), gate.slot():
        raise RuntimeError
    with gate.slot(), gate.slot():
        pass


def test_test_runs_over_the_cap_get_429(settings, Sessions, db, outbox):
    app = build(settings, Sessions, outbox)
    assert app.state.test_run_gate.limit == 2
    admin = signed_in(app, db, outbox, "admin@example.com", role="admin")
    gate: TestRunGate = app.state.test_run_gate
    with gate.slot(), gate.slot():  # two runs in progress
        r = admin.post("/api/admin/sources/test-run", json=HTML_RUN)
        assert r.status_code == 429
        assert r.json() == {"detail": TEST_RUN_BUSY}
        assert TEST_RUN_BUSY == (
            "Another test run is in progress; try again in a minute."
        )
    with gate.slot():  # one in progress: there is room
        r = admin.post("/api/admin/sources/test-run", json=HTML_RUN)
        assert r.status_code == 200 and r.json()["ok"], r.text


class BlockingRenderer:
    """A headless browser that stays on the page until released."""

    started = threading.Semaphore(0)
    release = threading.Event()

    def render(self, url, *, wait_for=None):
        BlockingRenderer.started.release()
        assert BlockingRenderer.release.wait(10)
        return browser_list.RenderedPage(url=url, html=LIST_HTML)

    def close(self):
        pass


def test_browser_list_test_runs_count_toward_the_cap(
    settings, Sessions, db, outbox, monkeypatch
):
    monkeypatch.setattr(
        browser_list, "default_renderer", lambda client: BlockingRenderer()
    )
    BlockingRenderer.release.clear()
    app = build(settings, Sessions, outbox, test_runs_max_concurrent=2)
    admin = signed_in(app, db, outbox, "admin@example.com", role="admin")
    with ThreadPoolExecutor(2) as pool:
        running = [
            pool.submit(admin.post, "/api/admin/sources/test-run", json=BROWSER_RUN)
            for _ in range(2)
        ]
        try:
            for _ in range(2):
                assert BlockingRenderer.started.acquire(timeout=10)
            # Two browser runs hold both slots: any third run is refused.
            for extra in (BROWSER_RUN, HTML_RUN):
                r = admin.post("/api/admin/sources/test-run", json=extra)
                assert r.status_code == 429 and r.json()["detail"] == TEST_RUN_BUSY
        finally:
            BlockingRenderer.release.set()
        results = [f.result(timeout=20) for f in running]
    assert [r.status_code for r in results] == [200, 200]
    assert all(r.json()["ok"] for r in results), [r.json() for r in results]
    # Slots are free again.
    r = admin.post("/api/admin/sources/test-run", json=HTML_RUN)
    assert r.status_code == 200
