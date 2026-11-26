"""Urgent alerts (spec 8): fit word at least the user's alert level (spec 12,
never the numeric score), deadline under 5 days, found today, once per item."""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from blackkite.db.models import AlertLog, DigestSetting
from blackkite.delivery.alert import AlertView, render_alert
from blackkite.delivery.alerts import send_alerts, users_with_alerts
from blackkite.delivery.mail import MemoryTransport
from tests import factories as f
from tests.conftest import make_user
from tests.factories import NOW, kigali

TODAY_9AM = kigali(2026, 11, 24, 9)
YESTERDAY = NOW - timedelta(days=1)


@pytest.fixture
def ana(db):
    u = make_user(db, "ana@example.com")
    db.add(
        DigestSetting(
            user_id=u.id,
            channel="email",
            address="ana@example.com",
            alert_min_fit="good",
        )
    )
    db.commit()
    return u


@pytest.fixture
def w(db, ana):
    ns = type("NS", (), {})()
    ns.src = f.source(db, "Src", publisher="Job in Rwanda")
    ns.prof = f.profile(db, ana, "Ironji-Trade")
    db.commit()
    return ns


def urgent(
    db,
    user,
    w,
    title,
    value=80,
    *,
    fit="strong",
    created=TODAY_9AM,
    scored=None,
    **kw,
):
    kw.setdefault("deadline_at", NOW + timedelta(days=3))
    o = f.opportunity(db, title, created_at=created, **kw)
    f.link(db, o, w.src, f"https://example.org/{title.replace(' ', '-')}")
    s = f.score(
        db,
        user,
        o,
        w.prof,
        value,
        reason="It asks for cold chain transport",
        fit_word=fit,
    )
    s.created_at = scored or created
    db.flush()
    return o


def test_sends_once_for_new_urgent_items(db, ana, w, settings):
    a = urgent(db, ana, w, "Cold chain tender", 90, deadline_at=NOW + timedelta(days=2))
    b = urgent(db, ana, w, "Dry freight tender", 75)
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 2
    [mail] = out.outbox
    assert mail.subject == "Two items close within 5 days"
    assert mail.to == "ana@example.com"
    assert 'src="cid:kite-logo"' in mail.html and mail.inline[0].cid == "kite-logo"
    assert mail.text.index("Cold chain tender") < mail.text.index("Dry freight tender")
    assert "Closing within 5 days" in mail.text
    assert "Closes Thursday 26 November 2026, 2pm" in mail.text
    assert {x.opportunity_id for x in db.scalars(sa.select(AlertLog))} == {a.id, b.id}
    # Later the same day (another ingest cycle): nothing new, nothing sent.
    assert send_alerts(db, ana, settings, out, NOW + timedelta(hours=2)) == 0
    assert len(out.outbox) == 1


def test_only_qualifying_items(db, ana, w, settings):
    ben = make_user(db, "ben@example.com")
    urgent(db, ana, w, "Possible fit", 95, fit="possible")  # below "good"
    urgent(db, ana, w, "Six days", 90, deadline_at=NOW + timedelta(days=6))
    urgent(db, ana, w, "Passed", 90, deadline_at=NOW - timedelta(hours=1))
    urgent(db, ana, w, "Found yesterday", 90, created=YESTERDAY)
    rescored = urgent(
        db, ana, w, "Old item, scored today", 90, created=YESTERDAY, scored=TODAY_9AM
    )
    dismissed = urgent(db, ana, w, "Dismissed", 90)
    f.state(db, ana, dismissed, "dismissed")
    testing = f.source(db, "Testing", status="testing")
    hidden = f.opportunity(
        db, "Testing only", deadline_at=NOW + timedelta(days=2), created_at=TODAY_9AM
    )
    f.link(db, hidden, testing)
    f.score(db, ana, hidden, w.prof, 99)
    filtered = urgent(db, ana, w, "Filtered", 90)
    db.execute(
        sa.text(
            "UPDATE user_opportunity_score SET score_breakdown = "
            "jsonb_set(score_breakdown, '{hard_filtered}', '\"ineligible\"') "
            "WHERE opportunity_id = :o"
        ),
        {"o": filtered.id},
    )
    f.opportunity(
        db,
        "Ben's private",
        visibility="private",
        owner_user_id=ben.id,
        deadline_at=NOW + timedelta(days=1),
        created_at=TODAY_9AM,
    )
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    assert out.outbox[0].subject == (
        "Closes Friday 27 November 2026: Old item, scored today"
    )
    assert [x.opportunity_id for x in db.scalars(sa.select(AlertLog))] == [rescored.id]


def test_null_min_fit_means_no_alerts(db, ana, w, settings):
    urgent(db, ana, w, "Urgent", 99)
    db.execute(sa.update(DigestSetting).values(alert_min_fit=None))
    db.commit()
    assert users_with_alerts(db) == []
    assert send_alerts(db, ana, settings, MemoryTransport(), NOW) == 0


def test_failed_send_is_retried_later(db, ana, w, settings):
    urgent(db, ana, w, "Urgent", 99)
    db.commit()

    class Broken:
        def send(self, mail):
            raise OSError("down")

    with pytest.raises(OSError):
        send_alerts(db, ana, settings, Broken(), NOW)
    assert db.scalar(sa.select(sa.func.count()).select_from(AlertLog)) == 0
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1


def test_alert_html_is_email_safe():
    from blackkite.delivery.digest import DigestItem

    view = AlertView(
        subject="s",
        issue_date=NOW.date(),
        heading="Closing within 5 days",
        intro="Found today.",
        items=[
            DigestItem(
                stream="tender",
                title="<b>T</b>",
                url="https://example.org/x",
                summary="Org.",
                date_line="Closes Thursday 26 November 2026",
            )
        ],
        cta_url="https://testserver/",
        settings_url="https://testserver/settings/digest",
        unsubscribe_url="https://testserver/unsubscribe#token=abc",
    )
    _, html, _ = render_alert(view)
    assert "<b>T</b>" not in html and "&lt;b&gt;T&lt;/b&gt;" in html
    for bad in ("<svg", "<style", "class=", "display: flex"):
        assert bad not in html


def test_inactive_profiles_are_ignored(db, ana, w, settings):
    old = f.profile(db, ana, "Old")
    old.active = False
    # Active profile below the alert level; the inactive one's Strong does not count.
    low = urgent(db, ana, w, "Low for the active profile", 50, fit="possible")
    f.score(db, ana, low, old, 99)
    # Scored only by the inactive profile.
    only_old = f.opportunity(
        db,
        "Only the old profile",
        deadline_at=NOW + timedelta(days=2),
        created_at=TODAY_9AM,
    )
    f.link(db, only_old, w.src)
    f.score(db, ana, only_old, old, 99)
    # Found yesterday by the active profile; today's row is the inactive one's,
    # so it was not found today.
    stale = urgent(db, ana, w, "Found yesterday", 90, created=YESTERDAY)
    f.score(db, ana, stale, old, 99).created_at = TODAY_9AM
    db.commit()
    assert send_alerts(db, ana, settings, MemoryTransport(), NOW) == 0

    old.active = True
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 3


def _set_min_fit(db, value):
    db.execute(sa.update(DigestSetting).values(alert_min_fit=value))
    db.commit()


def test_strong_item_with_a_low_score_alerts_under_strong(db, ana, w, settings):
    _set_min_fit(db, "strong")
    o = urgent(db, ana, w, "Strong but low score", 20, fit="strong")
    urgent(db, ana, w, "Good with a high score", 99, fit="good")
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    assert [x.opportunity_id for x in db.scalars(sa.select(AlertLog))] == [o.id]
    assert "Strong but low score" in out.outbox[0].subject
    assert "a strong fit for one of your profiles" in out.outbox[0].text


def test_possible_item_with_a_high_score_does_not_alert_under_good(
    db, ana, w, settings
):
    _set_min_fit(db, "good")
    urgent(db, ana, w, "Possible but high score", 99, fit="possible")
    urgent(db, ana, w, "No fit word", 99, fit=None)
    db.commit()
    assert send_alerts(db, ana, settings, MemoryTransport(), NOW) == 0
    good = urgent(db, ana, w, "Good with a low score", 10, fit="good")
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    assert [x.opportunity_id for x in db.scalars(sa.select(AlertLog))] == [good.id]
    assert "a good or strong fit" in out.outbox[0].text


def test_best_profile_is_the_one_the_feed_shows(db, ana, w, settings):
    """The fit word of the best active profile (highest score) decides, as on the
    feed; a lower-scoring profile's Strong does not lift it."""
    _set_min_fit(db, "strong")
    other = f.profile(db, ana, "AI lab")
    o = urgent(db, ana, w, "Two profiles", 80, fit="good")
    f.score(db, ana, o, other, 40, fit_word="strong")
    db.commit()
    assert send_alerts(db, ana, settings, MemoryTransport(), NOW) == 0


def test_provisional_profile_label_in_alerts(db, ana, w, settings):
    lab = f.profile(db, ana, "AI lab", provisional=True)
    o = f.opportunity(
        db,
        "Data platform",
        deadline_at=NOW + timedelta(days=2),
        created_at=TODAY_9AM,
    )
    f.link(db, o, w.src, "https://example.org/data-platform")
    f.score(db, ana, o, lab, 85, fit_word="strong", provisional=True)
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    [mail] = out.outbox
    assert "Change alert settings: https://testserver/settings/digest" in mail.text
    assert 'href="https://testserver/settings/digest"' in mail.html
    assert "TENDER · FOR AI LAB (PROVISIONAL)" in mail.text
    assert "TENDER · FOR AI LAB (PROVISIONAL)" in mail.html


def test_unchosen_instrument_kind_never_alerts(db, ana, w, settings):
    """Decision 54: even with a fit word, an investment of a kind the user did
    not choose is not alerted; a chosen kind is."""
    w.prof = f.profile(
        db,
        ana,
        "Personal",
        "personal",
        streams=["investment"],
        instruments=["treasury bonds and bills", "RSE shares"],
    )
    urgent(
        db,
        ana,
        w,
        "Example Power corporate bond",
        stream="investment",
        subtype="corporate bond",
    )
    urgent(
        db,
        ana,
        w,
        "Two-year treasury bond",
        stream="investment",
        subtype="treasury bond",
    )
    db.commit()
    out = MemoryTransport()
    assert send_alerts(db, ana, settings, out, NOW) == 1
    assert "Two-year treasury bond" in out.outbox[0].text
    assert "corporate bond" not in out.outbox[0].text.replace("treasury bond", "")
