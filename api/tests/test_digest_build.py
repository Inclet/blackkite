"""Weekly digest built from scores (spec 8, contract section 3)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from blackkite.db.models import DigestLog, DigestSetting, UserSourceMute
from blackkite.delivery import wording as W
from blackkite.delivery.build import build_digest, send_digest
from blackkite.delivery.mail import MemoryTransport
from tests import factories as f
from tests.conftest import make_user
from tests.factories import KIGALI, kigali

MONDAY = datetime(2026, 11, 30, 7, 0, tzinfo=KIGALI)
NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture
def ana(db):
    u = make_user(db, "ana@example.com")
    u.name = "Ana Uwase"
    db.add(
        DigestSetting(user_id=u.id, channel="email", address="ana.digest@example.com")
    )
    db.commit()
    return u


@pytest.fixture
def world(db, ana):
    """One active publisher source, one original, two profiles."""
    w = type("W", (), {})()
    w.src = f.source(db, "Job in Rwanda, tenders", publisher="Job in Rwanda")
    w.orig = f.source(db, "UNGM", kind="original", publisher="UNGM")
    w.ironji = f.profile(db, ana, "Ironji-Trade")
    w.personal = f.profile(
        db, ana, "Personal", "personal", streams=["investment", "event"]
    )
    db.commit()
    return w


def item(
    db, user, w, title, value=70, *, stream="tender", prof=None, original=False, **kw
):
    kw.setdefault("deadline_at", kigali(2026, 12, 10))
    o = f.opportunity(db, title, stream=stream, **kw)
    f.link(
        db,
        o,
        w.orig if original else w.src,
        f"https://example.org/{title.replace(' ', '-')}",
        is_original=original,
    )
    bd = {"fit_word": "strong" if stream in ("tender", "funding") else None}
    if prof is not False:
        f.score(
            db,
            user,
            o,
            prof or (w.personal if stream in ("event", "investment") else w.ironji),
            value,
            **bd,
        )
    return o


def test_items_fields_and_full_dates(db, ana, world, settings):
    o = f.opportunity(
        db,
        "Logistics, transport and warehousing support",
        organisation="World Food Programme",
        deadline_at=kigali(2026, 12, 3, 17),
        value_amount=Decimal(12000000),
        value_currency="RWF",
        evidence={"_trust": "unconfirmed"},
    )
    f.link(db, o, world.src, "https://www.jobinrwanda.com/jobs/tender/123")
    f.score(
        db,
        ana,
        o,
        world.ironji,
        90,
        reason="It asks for transport and warehousing, which you offer",
        fit_word="strong",
    )
    ev = f.opportunity(
        db,
        "ABH Summit and Grand Finale",
        stream="event",
        organisation="Africa's Business Heroes",
        location="Kigali Convention Centre",
        event_start=kigali(2026, 12, 1, 9),
        event_end=kigali(2026, 12, 2, 18),
        evidence={"_trust": "confirmed"},
        verification="verified_original",
    )
    f.link(db, ev, world.orig, "https://africabusinessheroes.org/", is_original=True)
    f.score(db, ana, ev, world.personal, 50, fit_word=None)
    db.commit()
    built = build_digest(db, ana, settings, MONDAY)
    v = built.view
    assert v.first_name == "Ana" and v.greeting == "Good morning"
    assert v.issue_date_text == "Monday 30 November 2026"
    assert v.subject == "Two things this week, one closing Thursday"
    assert v.intro == "Two things made your list this week."
    first, second = v.items
    assert first.label == "TENDER · FOR IRONJI-TRADE"
    assert first.url == "https://www.jobinrwanda.com/jobs/tender/123"
    assert first.summary == (
        "World Food Programme. It asks for transport and warehousing, which you offer."
    )
    assert first.date_line == "Closes Thursday 3 December 2026, 5pm"
    assert first.trust_note == "not yet confirmed at the source"
    assert first.value_line == "Value: FRW 12,000,000"
    assert second.summary == "Kigali Convention Centre."
    assert second.date_line == "Tuesday 1 to Wednesday 2 December 2026"
    assert second.trust_note is None and second.value_line is None
    assert v.cta_url == "https://testserver/"
    assert v.footer.change_frequency_url == "https://testserver/settings/digest"
    assert v.footer.unsubscribe_url.startswith("https://testserver/unsubscribe#token=")
    assert v.more_count == 0 and v.closing_soon == []


def test_provisional_profile_label(db, ana, world, settings):
    """Spec 7.1: "TENDER · FOR AI LAB (PROVISIONAL)" in the digest, HTML and text."""
    lab = f.profile(db, ana, "AI lab", provisional=True)
    o = item(db, ana, world, "Data platform", 90, prof=lab)
    db.execute(
        sa.text(
            "UPDATE user_opportunity_score SET score_breakdown = "
            "jsonb_set(score_breakdown, '{provisional}', 'true') "
            "WHERE opportunity_id = :o"
        ),
        {"o": o.id},
    )
    item(db, ana, world, "Trucks", 80)
    db.commit()
    v = build_digest(db, ana, settings, MONDAY).view
    labels = [i.label for i in v.items]
    assert labels == ["TENDER · FOR AI LAB (PROVISIONAL)", "TENDER · FOR IRONJI-TRADE"]
    out = MemoryTransport()
    assert send_digest(db, ana, settings, out, MONDAY).status == "sent"
    [mail] = out.outbox
    assert "TENDER · FOR AI LAB (PROVISIONAL)" in mail.text
    assert "TENDER · FOR AI LAB (PROVISIONAL)" in mail.html
    assert "IRONJI-TRADE (PROVISIONAL)" not in mail.text
    assert "Change how often: https://testserver/settings/digest" in mail.text
    assert "Stop these emails: https://testserver/unsubscribe#token=" in mail.text


def test_rules_only_reason_is_never_printed(db, ana, world, settings):
    """A score made without the model uses its rules reason in the digest."""
    o = f.opportunity(
        db, "Cold chain tender", organisation="RBC", deadline_at=kigali(2026, 12, 10)
    )
    f.link(db, o, world.src, "https://example.org/cold")
    f.score(
        db,
        ana,
        o,
        world.ironji,
        60,
        reason="Scored without the model",
        fit_word="possible",
        reasons=[
            "Scored without the model",
            "It mentions cold chain, which this profile lists.",
        ],
    )
    bare = f.opportunity(
        db, "Bare tender", organisation="MINAGRI", deadline_at=kigali(2026, 12, 11)
    )
    f.link(db, bare, world.src, "https://example.org/bare")
    f.score(
        db,
        ana,
        bare,
        world.ironji,
        50,
        reason="Scored without the model.",
        fit_word="possible",
        reasons=["Scored without the model."],
    )
    db.commit()
    out = MemoryTransport()
    assert send_digest(db, ana, settings, out, MONDAY).status == "sent"
    [mail] = out.outbox
    assert "RBC. It mentions cold chain, which this profile lists." in mail.text
    assert "MINAGRI.\n" in mail.text
    assert "without the model" not in mail.text
    assert "without the model" not in mail.html


def test_no_name_greets_without_one(db, ana, world, settings):
    ana.name = None
    item(db, ana, world, "Cold chain tender", 80)
    db.commit()
    out = MemoryTransport()
    assert send_digest(db, ana, settings, out, MONDAY).status == "sent"
    [mail] = out.outbox
    assert mail.text.startswith("Good morning\n")
    assert ">Good morning</td>" in mail.html
    assert "there" not in mail.text.split("\n")[0]


def test_wording_helpers():
    assert (
        W.deadline_line(kigali(2026, 12, 7, 23, 59)) == "Closes Monday 7 December 2026"
    )
    assert W.deadline_line(kigali(2026, 12, 7, 0, 0)) == "Closes Monday 7 December 2026"
    assert (
        W.deadline_line(kigali(2026, 12, 7, 9, 30))
        == "Closes Monday 7 December 2026, 9:30am"
    )
    assert W.event_line(kigali(2026, 11, 30), kigali(2026, 12, 2)) == (
        "Monday 30 November to Wednesday 2 December 2026"
    )
    assert W.event_line(kigali(2026, 12, 31), kigali(2027, 1, 1)) == (
        "Thursday 31 December 2026 to Friday 1 January 2027"
    )
    assert W.event_line(kigali(2026, 12, 1), None) == "Tuesday 1 December 2026"
    assert W.value_line(None, None, "Up to €100,000") == "Value: Up to €100,000"
    assert W.value_line(Decimal("2500.50"), "USD", None) == "Value: USD 2,500.50"
    assert W.value_line(None, None, None) is None


def test_selection_caps_and_exclusions(db, ana, world, settings):
    ben = make_user(db, "ben@example.com")
    # 14 strong tenders: only 12 fit, 2 more wait.
    tenders = [item(db, ana, world, f"Tender {i:02d}", 90 - i) for i in range(14)]
    # 5 events and 4 investments: 3 of each at most, but they rank below tenders
    # anyway; give them top scores to prove the stream cap.
    for i in range(5):
        item(
            db,
            ana,
            world,
            f"Event {i}",
            99,
            stream="event",
            event_start=kigali(2026, 12, 5 + i),
            deadline_at=None,
        )
    for i in range(4):
        item(db, ana, world, f"Bond {i}", 98, stream="investment", deadline_at=None)
    # Never in a digest:
    weak = item(db, ana, world, "Weak tender", 100)
    weak_score = db.scalars(
        sa.text("SELECT id FROM user_opportunity_score WHERE opportunity_id = :o"),
        {"o": weak.id},
    ).one()
    db.execute(
        sa.text(
            "UPDATE user_opportunity_score SET score_breakdown = jsonb_set(score_breakdown, '{fit_word}', 'null') WHERE id = :i"
        ),
        {"i": weak_score},
    )
    item(db, ana, world, "Unscored", prof=False)
    filtered = item(db, ana, world, "Filtered", prof=False)
    f.score(db, ana, filtered, world.ironji, 100, hard_filtered="ineligible")
    dismissed = item(db, ana, world, "Dismissed", 100)
    f.state(db, ana, dismissed, "dismissed")
    done = item(db, ana, world, "Done", 100)
    f.state(db, ana, done, "done")
    item(db, ana, world, "Expired", 100, deadline_at=kigali(2026, 11, 29))
    testing = f.source(db, "Testing", status="testing")
    hidden = f.opportunity(db, "Testing only", deadline_at=kigali(2026, 12, 10))
    f.link(db, hidden, testing)
    f.score(db, ana, hidden, world.ironji, 100, fit_word="strong")
    private = f.opportunity(
        db, "Ben's private", visibility="private", owner_user_id=ben.id
    )
    assert private.id
    muted_src = f.source(db, "Muted")
    muted = f.opportunity(db, "Muted only", deadline_at=kigali(2026, 12, 10))
    f.link(db, muted, muted_src)
    f.score(db, ana, muted, world.ironji, 100, fit_word="strong")
    db.add(UserSourceMute(user_id=ana.id, source_id=muted_src.id))
    db.commit()

    v = build_digest(db, ana, settings, MONDAY).view
    titles = [i.title for i in v.items]
    assert len(titles) == 12
    assert titles[:6] == ["Event 0", "Event 1", "Event 2", "Bond 0", "Bond 1", "Bond 2"]
    assert titles[6:] == [t.title for t in tenders[:6]]
    assert v.more_count == 8 + 2 + 1  # 8 tenders, 2 events, 1 bond
    assert (
        v.intro
        == "23 things made your list this week. Here are the twelve to look at first."
    )
    assert v.subject == "23 things this week"


def test_streams_setting_limits_the_digest(db, ana, world, settings):
    item(db, ana, world, "Tender")
    item(
        db,
        ana,
        world,
        "Event",
        stream="event",
        event_start=kigali(2026, 12, 4),
        deadline_at=None,
    )
    db.execute(sa.update(DigestSetting).values(streams=["event"]))
    db.commit()
    assert [i.title for i in build_digest(db, ana, settings, MONDAY).view.items] == [
        "Event"
    ]


def test_closing_in_7_days_block_for_saved_items(db, ana, world, settings):
    soon = item(db, ana, world, "Saved soon", 60, deadline_at=kigali(2026, 12, 4))
    f.state(db, ana, soon, "saved")
    acting = item(db, ana, world, "Acting soon", 60, deadline_at=kigali(2026, 12, 2))
    f.state(db, ana, acting, "acting")
    later = item(db, ana, world, "Saved later", 60, deadline_at=kigali(2026, 12, 20))
    f.state(db, ana, later, "saved")
    # Saved but unscored still shows in the block (the user chose it).
    unscored = item(
        db, ana, world, "Saved unscored", prof=False, deadline_at=kigali(2026, 12, 6)
    )
    f.state(db, ana, unscored, "saved")
    db.commit()
    v = build_digest(db, ana, settings, MONDAY).view
    assert [i.title for i in v.closing_soon] == [
        "Acting soon",
        "Saved soon",
        "Saved unscored",
    ]
    assert [i.title for i in v.items] == ["Saved later"]


def test_send_logs_once_per_day_and_mails_multipart(db, ana, world, settings):
    o = item(db, ana, world, "Tender")
    db.commit()
    out = MemoryTransport()
    r = send_digest(db, ana, settings, out, MONDAY)
    assert r.status == "sent"
    [mail] = out.outbox
    assert mail.to == "ana.digest@example.com"
    assert mail.subject == "One thing this week"
    assert 'src="cid:kite-logo"' in mail.html
    assert mail.inline[0].cid == "kite-logo" and mail.inline[0].data.startswith(
        b"\x89PNG"
    )
    assert "Tender" in mail.text
    [entry] = db.scalars(sa.select(DigestLog)).all()
    assert entry.digest_date.isoformat() == "2026-11-30"
    assert entry.opportunity_ids == [o.id]
    assert entry.details["items"][0]["id"] == str(o.id)
    assert entry.details["items"][0]["profile_id"] == str(world.ironji.id)
    # Again the same day: nothing sent.
    assert (
        send_digest(db, ana, settings, out, MONDAY + timedelta(hours=3)).status
        == "already_sent"
    )
    assert len(out.outbox) == 1


def test_unchanged_items_are_not_resent_next_week(db, ana, world, settings):
    same = item(db, ana, world, "Same", 90, deadline_at=kigali(2026, 12, 20))
    moved = item(db, ana, world, "Moved", 80, deadline_at=kigali(2026, 12, 20))
    revalued = item(db, ana, world, "Revalued", 70, deadline_at=kigali(2026, 12, 20))
    db.commit()
    out = MemoryTransport()
    assert send_digest(db, ana, settings, out, MONDAY).status == "sent"
    moved.deadline_at = kigali(2026, 12, 22)
    revalued.value_amount = Decimal(6000000)
    revalued.value_currency = "RWF"
    item(db, ana, world, "New", 60, deadline_at=kigali(2026, 12, 21))
    db.commit()
    built = build_digest(db, ana, settings, NEXT_MONDAY)
    assert [i.title for i in built.view.items] == ["Moved", "Revalued", "New"]
    assert built.more_count == 1  # "Same" still waits in the feed
    assert same.id


def test_off_empty_inactive_and_failed_sends(db, ana, world, settings):
    out = MemoryTransport()
    assert send_digest(db, ana, settings, out, MONDAY).status == "empty"
    item(db, ana, world, "Tender")
    db.execute(sa.update(DigestSetting).values(frequency="off"))
    db.commit()
    assert send_digest(db, ana, settings, out, MONDAY).status == "off"
    db.execute(sa.update(DigestSetting).values(frequency="weekly"))
    db.commit()

    class Broken:
        def send(self, mail):
            raise OSError("smtp down")

    with pytest.raises(OSError):
        send_digest(db, ana, settings, Broken(), MONDAY)
    assert db.scalar(sa.select(sa.func.count()).select_from(DigestLog)) == 0
    assert send_digest(db, ana, settings, out, MONDAY).status == "sent"
    ana.status = "deactivated"
    db.commit()
    assert send_digest(db, ana, settings, out, NEXT_MONDAY).status == "inactive"
    assert out.outbox and all(m.to == "ana.digest@example.com" for m in out.outbox)


def test_user_without_a_setting_gets_weekly_to_account_email(db, settings):
    u = make_user(db, "carol@example.com")
    src = f.source(db, "S")
    p = f.profile(db, u, "P")
    o = f.opportunity(db, "T", deadline_at=kigali(2026, 12, 10))
    f.link(db, o, src)
    f.score(db, u, o, p, 70, fit_word="good")
    db.commit()
    out = MemoryTransport()
    assert send_digest(db, u, settings, out, MONDAY).status == "sent"
    assert out.outbox[0].to == "carol@example.com"
    assert out.outbox[0].text.startswith("Good morning\n")  # no name set


def test_best_profile_is_chosen_among_active_profiles(db, ana, world, settings):
    old = f.profile(db, ana, "Old")
    old.active = False
    both = item(db, ana, world, "Both", 60)  # Ironji-Trade, 60
    f.score(db, ana, both, old, 100, fit_word="strong")
    higher = item(db, ana, world, "Higher for Ironji", 80)
    only_old = item(db, ana, world, "Only the old profile", prof=False)
    f.score(db, ana, only_old, old, 100, fit_word="strong")
    db.commit()
    v = build_digest(db, ana, settings, MONDAY).view
    assert [(i.title, i.profile_label) for i in v.items] == [
        ("Higher for Ironji", "Ironji-Trade"),
        ("Both", "Ironji-Trade"),
    ]
    assert higher.id
