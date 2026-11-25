"""email_ingest collector: fake IMAP mailbox, synthetic emails. Offline."""

import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import ClassVar

import pytest

from blackkite.collectors import email_ingest as ei
from blackkite.collectors.base import CollectorError
from blackkite.collectors.registry import build_collector, validate_config
from blackkite.db.models import Source

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
SENDER = "alerts@board.example"
AUTH_OK = "mx.inbox.example; dkim=pass header.d=board.example; spf=pass"


def mail(
    subject="New tenders this week",
    sender=SENDER,
    html=None,
    text=None,
    auth=AUTH_OK,
    date="Tue, 24 Nov 2026 06:00:00 +0000",
) -> bytes:
    m = EmailMessage()
    m["From"] = f"Board Alerts <{sender}>"
    m["To"] = "ingest@inbox.example"
    m["Subject"] = subject
    m["Date"] = date
    for a in [auth] if isinstance(auth, str) else auth or []:
        m["Authentication-Results"] = a
    m.set_content(text or "See the HTML version.")
    if html:
        m.add_alternative(html, subtype="html")
    return bytes(m)


HTML = """<html><body>
<table><tr><td><a href="https://board.example/tender/1">Supply of cold rooms to district hospitals</a>
  Closing 10 Dec 2026</td></tr>
<tr><td><a href="https://board.example/tender/2">EOI: last-mile distribution services</a></td></tr>
<tr><td><a href="https://board.example/tender/1">Supply of cold rooms (again)</a></td></tr>
<tr><td><a href="http://192.168.0.10/admin">Internal link with a long enough title</a></td></tr>
<tr><td><a href="mailto:x@board.example">Write to us about anything at all</a></td></tr>
<tr><td><a href="https://board.example/unsubscribe">Unsubscribe</a></td></tr>
<tr><td><a href="https://social.example/board">Follow us on social media today</a></td></tr>
</table></body></html>"""


class FakeMailbox:
    def __init__(self, messages: dict[str, bytes], keywords=True, sizes=None):
        self.messages = messages
        self.keywords = keywords
        self.sizes = sizes or {}
        self.flags: dict[str, set[str]] = {u: set() for u in messages}
        self.calls: list[tuple] = []
        self.logged_out = False

    def select(self, folder, *, readonly):
        self.calls.append(("select", folder, readonly))

    def supports_keywords(self):
        return self.keywords

    def search(self, criteria):
        self.calls.append(("search", tuple(criteria)))
        flag = (
            criteria[criteria.index("UNKEYWORD") + 1]
            if "UNKEYWORD" in criteria
            else "\\Seen"
        )
        return [u for u in self.messages if flag not in self.flags[u]]

    def size(self, uid):
        return self.sizes.get(uid, len(self.messages[uid]))

    def fetch(self, uid):
        self.calls.append(("fetch", uid))
        return self.messages[uid]

    def add_flag(self, uids, flag):
        self.calls.append(("flag", tuple(uids), flag))
        for u in uids:
            self.flags[u].add(flag)

    def logout(self):
        self.logged_out = True


def source(config) -> Source:
    return Source(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        name="Board alerts",
        home_url="https://board.example",
        streams=["tender"],
        kind="publisher",
        collector_type="email_ingest",
        config=config,
    )


def collect(box, config, preview=False, commit=True):
    """One run's collector use: fetch, then (as the runner does once the ingest
    is committed) after_commit."""
    c = build_collector(
        "email_ingest", None, mailbox_factory=lambda: box, preview=preview
    )
    c.now = lambda: NOW
    src = source(config)
    items = c.fetch(src)
    if commit:
        c.after_commit(src)
    return items


def test_links_mode_items_and_marking():
    box = FakeMailbox({"7": mail(html=HTML)})
    cfg = {"sender": SENDER, "link_pattern": "https://board.example/tender/*"}
    items = collect(box, cfg)
    assert [(i.url, i.title) for i in items] == [
        (
            "https://board.example/tender/1",
            "Supply of cold rooms to district hospitals",
        ),
        ("https://board.example/tender/2", "EOI: last-mile distribution services"),
    ]
    first = items[0]
    assert first.listed_published == "2026-11-24T06:00:00+00:00"
    assert "Closing 10 Dec 2026" in first.snippet
    assert first.extra == {
        "email_subject": "New tenders this week",
        "email_from": SENDER,
    }
    kw = "BkDone123456781234"
    assert ("select", "INBOX", False) in box.calls
    search = next(c for c in box.calls if c[0] == "search")[1]
    assert search == ("SINCE", "11-Nov-2026", "UNKEYWORD", kw, "FROM", f'"{SENDER}"')
    assert ("flag", ("7",), kw) in box.calls and box.logged_out
    assert collect(box, cfg) == []  # already processed


def test_links_mode_without_pattern_drops_unsafe_and_short_links():
    box = FakeMailbox({"1": mail(html=HTML)})
    urls = [i.url for i in collect(box, {"sender": SENDER})]
    assert urls == [
        "https://board.example/tender/1",
        "https://board.example/tender/2",
        "https://social.example/board",
    ]  # internal address, mailto and "Unsubscribe" (too short) dropped


def test_message_mode_and_plain_text():
    text = (
        "Hello,\n\nTender: road maintenance in Musanze district\n"
        "https://board.example/tender/9\n\nRegards"
    )
    box = FakeMailbox({"1": mail(subject="Tender alert: roads", text=text)})
    (it,) = collect(box, {"sender": SENDER, "parse_mode": "message"})
    assert it.title == "Tender alert: roads"
    assert it.url == "https://board.example/tender/9"
    assert "road maintenance" in it.snippet
    box = FakeMailbox({"1": mail(text=text)})
    (it,) = collect(box, {"sender": SENDER})
    assert it.title == "Tender: road maintenance in Musanze district"


def test_sender_subject_and_authentication_filters():
    box = FakeMailbox(
        {
            "1": mail(html=HTML, sender="news@other.example"),
            "2": mail(html=HTML, subject="Weekly newsletter"),
            "3": mail(html=HTML, auth=None),
            "4": mail(
                html=HTML, auth="mx.inbox.example; dkim=pass header.d=evil.example"
            ),
            "5": mail(
                html=HTML, auth="mx.inbox.example; dkim=fail header.d=board.example"
            ),
            "6": mail(
                html=HTML,
                subject="New TENDERS posted",
                sender="jobs@board.example",
                auth="mx.inbox.example; dmarc=pass header.from=board.example",
            ),
        }
    )
    cfg = {"sender": "*@board.example", "subject_pattern": "*tenders*"}
    items = collect(box, cfg)
    assert {i.extra["email_from"] for i in items} == {"jobs@board.example"}
    flagged = [c for c in box.calls if c[0] == "flag"]
    assert flagged == [("flag", ("6",), "BkDone123456781234")]  # others left alone
    search = next(c for c in box.calls if c[0] == "search")[1]
    assert search[-2:] == ("FROM", '"@board.example"')
    # Opting out of the check accepts the unauthenticated one too.
    box2 = FakeMailbox({"3": mail(html=HTML, auth=None)})
    assert collect(box2, {"sender": SENDER, "require_authenticated": False})


AUTHSERV = "mx.inbox.example"


@pytest.fixture(autouse=True)
def _authserv_id(monkeypatch):
    monkeypatch.setenv("BK_INGEST_AUTHSERV_ID", AUTHSERV)


def with_results(*headers: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = SENDER
    for h in headers:
        m["Authentication-Results"] = h
    return m


def test_authentication_uses_topmost_header_only():
    m = with_results(
        "mx.inbox.example; dkim=fail",
        "mx.inbox.example; dkim=pass header.d=board.example",
    )
    assert not ei.authenticated(m, SENDER, AUTHSERV)
    m2 = with_results("mx.inbox.example; dkim=pass header.d=example")  # parent
    assert ei.authenticated(m2, "a@board.example", AUTHSERV)


def test_forged_header_above_the_real_one_is_ignored():
    # Another authserv-id on top (written by the sender or an outside hop).
    m = with_results(
        "forged.example; dmarc=pass header.from=board.example",
        "mx.inbox.example; dmarc=fail header.from=board.example",
    )
    assert not ei.authenticated(m, SENDER, AUTHSERV)
    # The real pass is found under a forged fail with another id.
    m = with_results(
        "forged.example; dmarc=fail",
        "MX.Inbox.Example 1; dmarc=pass header.from=board.example",
    )
    assert ei.authenticated(m, SENDER, AUTHSERV)


def test_forged_header_below_the_real_one_is_ignored():
    # The sender put a pass with our own id in the message; our server's
    # header is the topmost with that id and says fail.
    m = with_results(
        "mx.inbox.example; dmarc=fail header.from=board.example; dkim=none",
        "mx.inbox.example; dmarc=pass header.from=board.example",
    )
    assert not ei.authenticated(m, SENDER, AUTHSERV)
    # Only headers with other ids: nothing to trust.
    m = with_results("mx.other.example; dmarc=pass header.from=board.example")
    assert not ei.authenticated(m, SENDER, AUTHSERV)
    # The authserv-id must be the whole first token, not a prefix or suffix.
    m = with_results("mx.inbox.example.evil; dmarc=pass header.from=board.example")
    assert not ei.authenticated(m, SENDER, AUTHSERV)


def test_forged_headers_in_a_collected_message():
    forged_below = mail(
        html=HTML,
        auth=[
            "mx.inbox.example; dmarc=fail header.from=board.example",
            "mx.inbox.example; dmarc=pass header.from=board.example",
        ],
    )
    forged_other = mail(
        html=HTML, auth="relay.example; dmarc=pass header.from=board.example"
    )
    box = FakeMailbox({"1": forged_below, "2": forged_other, "3": mail(html=HTML)})
    items = collect(box, {"sender": SENDER})
    flagged = [c for c in box.calls if c[0] == "flag"]
    assert flagged == [("flag", ("3",), "BkDone123456781234")]
    assert items


def test_without_authserv_id_the_source_refuses_to_run(monkeypatch):
    monkeypatch.delenv("BK_INGEST_AUTHSERV_ID")
    box = FakeMailbox({"1": mail(html=HTML)})
    with pytest.raises(CollectorError, match="BK_INGEST_AUTHSERV_ID"):
        collect(box, {"sender": SENDER}, commit=False)
    assert box.calls == []  # the mailbox was never opened
    monkeypatch.setenv("BK_INGEST_AUTHSERV_ID", "  ")
    with pytest.raises(CollectorError, match="BK_INGEST_AUTHSERV_ID"):
        collect(box, {"sender": SENDER}, preview=True, commit=False)
    # Not needed when the source opts out of the check.
    assert collect(box, {"sender": SENDER, "require_authenticated": False})


def test_preview_is_read_only_and_seen_fallback():
    box = FakeMailbox({"1": mail(html=HTML)}, keywords=False)
    assert collect(box, {"sender": SENDER}, preview=True)
    assert ("select", "INBOX", True) in box.calls
    assert not [c for c in box.calls if c[0] == "flag"]
    collect(box, {"sender": SENDER})
    assert ("flag", ("1",), "\\Seen") in box.calls
    search = [c for c in box.calls if c[0] == "search"][-1][1]
    assert "UNSEEN" in search


def test_oversized_messages_are_skipped_unread():
    box = FakeMailbox({"1": mail(html=HTML)}, sizes={"1": 10_000_000})
    assert collect(box, {"sender": SENDER}) == []
    assert ("fetch", "1") not in box.calls


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"sender": "no-at-sign"},
        {"sender": 'a"@x.example'},
        {"sender": SENDER, "folder": "IN\\BOX"},
        {"sender": SENDER, "password": "hunter2"},
        {"sender": SENDER, "host": "imap.example"},
        {"sender": SENDER, "parse_mode": "attachments"},
        {"sender": SENDER, "since_days": 365},
    ],
)
def test_bad_config_rejected(config):
    with pytest.raises(ValueError):
        validate_config("email_ingest", config)


def test_mailbox_must_be_configured_in_env(monkeypatch):
    for k in ("HOST", "USER", "PASSWORD"):
        monkeypatch.delenv(f"BK_INGEST_IMAP_{k}", raising=False)
    with pytest.raises(CollectorError, match="no ingest mailbox configured"):
        ei.ImapMailbox(ei.ImapSettings(_env_file=None))


class FakeImaplib:
    """Stands in for imaplib.IMAP4_SSL: records commands, never touches a network."""

    instances: ClassVar[list["FakeImaplib"]] = []

    def __init__(self, host, port, *, ssl_context, timeout):
        self.args = (host, port, timeout)
        self.ssl_context = ssl_context
        self.commands = []
        FakeImaplib.instances.append(self)

    def login(self, user, password):
        self.commands.append(("login", user, password))
        return "OK", [b"logged in"]

    def select(self, mailbox, readonly):
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"3"]

    def response(self, code):
        if code == "UIDVALIDITY":
            return code, [b"1700000000"]
        return code, [b"(\\Seen \\Flagged \\*)"]

    def uid(self, command, *args):
        self.commands.append(("uid", command, *args))
        if command == "SEARCH":
            return "OK", [b"4 9"]
        if command == "FETCH" and args[1] == "(RFC822.SIZE)":
            return "OK", [b"4 (UID 4 RFC822.SIZE 1234)"]
        if command == "FETCH":
            return "OK", [(b"4 (UID 4 BODY[] {5}", b"hello"), b")"]
        return "OK", [None]

    def logout(self):
        self.commands.append(("logout",))
        return "BYE", []


def test_imap_mailbox_commands():
    s = ei.ImapSettings(
        _env_file=None, host="imap.inbox.example", user="ingest", password="pw"
    )
    box = ei.ImapMailbox(s, imap_class=FakeImaplib)
    imap = FakeImaplib.instances[-1]
    assert imap.args == ("imap.inbox.example", 993, 30.0)
    assert imap.ssl_context.verify_mode.name == "CERT_REQUIRED"
    box.select("INBOX", readonly=True)
    assert box.supports_keywords() and box.uid_validity() == "1700000000"
    assert box.search(["SINCE", "1-Nov-2026"]) == ["4", "9"]
    assert box.size("4") == 1234
    assert box.fetch("4") == b"hello"
    box.add_flag(["4", "9"], "BkDoneabc")
    box.logout()
    assert ("uid", "FETCH", "4", "(BODY.PEEK[])") in imap.commands
    assert ("uid", "STORE", "4,9", "+FLAGS.SILENT", "(BkDoneabc)") in imap.commands
    assert ("select", '"INBOX"', True) in imap.commands


def test_fetch_alone_flags_nothing_after_commit_flags():
    box = FakeMailbox({"7": mail(html=HTML)})
    c = build_collector("email_ingest", None, mailbox_factory=lambda: box)
    c.now = lambda: NOW
    src = source({"sender": SENDER})
    assert c.fetch(src)
    assert not [x for x in box.calls if x[0] == "flag"] and box.logged_out
    assert box.flags["7"] == set()
    box.logged_out = False
    c.after_commit(src)
    assert box.flags["7"] == {"BkDone123456781234"} and box.logged_out
    assert box.calls[-2:] == [
        ("select", "INBOX", False),
        ("flag", ("7",), "BkDone123456781234"),
    ]
    n = len(box.calls)
    c.after_commit(src)  # once only
    assert len(box.calls) == n


def test_without_commit_the_same_mail_is_read_again():
    box = FakeMailbox({"7": mail(html=HTML)})
    first = collect(box, {"sender": SENDER}, commit=False)
    assert collect(box, {"sender": SENDER}) == first


class ValidityMailbox(FakeMailbox):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.validities = ["1", "2"]

    def select(self, folder, *, readonly):
        super().select(folder, readonly=readonly)
        self.current = self.validities.pop(0)

    def uid_validity(self):
        return self.current


def test_uidvalidity_change_leaves_mail_unflagged():
    box = ValidityMailbox({"7": mail(html=HTML)})
    assert collect(box, {"sender": SENDER})
    assert box.flags["7"] == set()
    assert not [x for x in box.calls if x[0] == "flag"]
    box2 = ValidityMailbox({"7": mail(html=HTML)})
    box2.validities = ["5", "5"]
    collect(box2, {"sender": SENDER})
    assert box2.flags["7"] == {"BkDone123456781234"}


def test_preview_after_commit_is_a_no_op():
    box = FakeMailbox({"1": mail(html=HTML)})
    collect(box, {"sender": SENDER}, preview=True)
    assert [x for x in box.calls if x[0] == "select"] == [("select", "INBOX", True)]
    assert box.flags["1"] == set()
