"""Weekly digest email: rendering, board fidelity, email safety."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from pydantic import ValidationError

from blackkite.delivery.digest import (
    DigestFooter,
    DigestItem,
    DigestView,
    allow_placeholder_links,
    render_digest,
    render_digest_preview,
)
from blackkite.delivery.fixtures import digest_reference
from blackkite.delivery.fixtures.digest_reference import REFERENCE

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "design" / "reference" / "digest-email.html"

needs_design = pytest.mark.skipif(not BOARD.exists(), reason="design/ not next to api/")


class _Collect(HTMLParser):
    """Visible text plus every start tag with its attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in ("title", "style", "svg"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("title", "style", "svg"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)

    def words(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.text).replace("\xa0", " ")).strip()


def _parse(html: str) -> _Collect:
    p = _Collect()
    p.feed(html)
    return p


# --- render_digest -------------------------------------------------------------


def test_render_returns_subject_html_text():
    subject, html, text = render_digest(REFERENCE)
    assert subject == "Six things this week, one closing Monday"
    assert html.startswith("<!doctype html>")
    assert "Good morning, Clet" in html and "Good morning, Clet" in text


@needs_design
def test_email_words_match_board_card_exactly():
    """Every word inside the board's card appears, in order, in the email."""
    board = BOARD.read_text("utf-8")
    card = board[board.index('<div style="background: #FFFFFF'):]
    _, html, _ = render_digest(REFERENCE)
    assert _parse(html).words() == _parse(card).words()


@needs_design
def test_preview_words_match_whole_board():
    assert _parse(render_digest_preview(REFERENCE)).words() == _parse(BOARD.read_text("utf-8")).words()


def test_full_issue_date():
    _, html, _ = render_digest(REFERENCE)
    assert "Monday 23 November 2026" in html


def test_labels_and_trust_note():
    _, html, text = render_digest(REFERENCE)
    for label in ("TENDER · FOR IRONJI-TRADE", "EVENT", "FUNDING", "FUNDING · FOR IRONJI-TRADE"):
        assert f">{label}<" in html
    assert "Closes Mon 30 Nov</strong> · not yet confirmed at the source" in html
    assert "Closes Mon 30 Nov · not yet confirmed at the source" in text


def test_text_alternative_has_every_item_and_link():
    view = REFERENCE.model_copy(update={
        "items": [i.model_copy(update={"url": f"https://example.org/o/{n}"})
                  for n, i in enumerate(REFERENCE.items)],
        "cta_url": "https://example.org/feed",
        "footer": REFERENCE.footer.model_copy(update={
            "change_frequency_url": "https://example.org/settings",
            "unsubscribe_url": "https://example.org/stop",
        }),
    })
    _, _, text = render_digest(view)
    for n, item in enumerate(view.items):
        assert item.title in text and item.summary in text and f"https://example.org/o/{n}" in text
    assert "Open your feed: https://example.org/feed" in text
    assert "2 more are waiting there." in text
    assert "All 8 sources were checked this week." in text
    assert "You get this every Monday." in text
    assert "Change how often: https://example.org/settings" in text
    assert "Stop these emails: https://example.org/stop" in text
    assert "<" not in text


def test_user_text_is_escaped():
    item = DigestItem(stream="tender", title="<script>x</script> & co", url="https://e.org/?a=1&b=2",
                      summary="s", date_line="d")
    _, html, _ = render_digest(REFERENCE.model_copy(update={"items": [item]}))
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt; &amp; co" in html
    assert 'href="https://e.org/?a=1&amp;b=2"' in html


def test_more_line_singular_and_absent():
    one = REFERENCE.model_copy(update={"more_count": 1})
    none = REFERENCE.model_copy(update={"more_count": 0})
    assert "1 more is waiting there." in render_digest(one)[1]
    assert "waiting there" not in render_digest(none)[1]


def test_investment_stream_has_colours():
    item = DigestItem(stream="investment", title="t", url="https://e.org/i", summary="s",
                      date_line="d")
    _, html, _ = render_digest(REFERENCE.model_copy(update={"items": [item]}))
    assert "#0E5F56" in html and "#1FA898" in html


def test_single_source_wording():
    f = DigestFooter(source_count=1, frequency="every Monday",
                     change_frequency_url="https://e.org/s", unsubscribe_url="https://e.org/u")
    assert f.sources_line == "The 1 source was checked this week."


def test_fixture_holds_no_email_address():
    src = Path(digest_reference.__file__).read_text("utf-8")
    assert "@" not in src
    assert REFERENCE.first_name == "Clet"


# --- Email-client sanity (decision 7) --------------------------------------------


def test_email_html_is_email_safe():
    _, html, _ = render_digest(REFERENCE)
    lower = html.lower()
    assert "<svg" not in lower
    assert "<style" not in lower
    assert "<link" not in lower
    assert "<script" not in lower
    assert "@font-face" not in lower and "@import" not in lower and "figtree" not in lower
    assert not re.search(r"display\s*:\s*(inline-)?flex", lower)
    assert not re.search(r"display\s*:\s*grid", lower)
    assert "gap:" not in lower.replace(" ", "")
    tags = _parse(html).tags
    for tag, attrs in tags:
        assert "class" not in attrs, tag
        assert "id" not in attrs, tag
    assert "Helvetica, Arial, sans-serif" in html


def test_email_logo_is_png_img_with_alt_and_size():
    _, html, _ = render_digest(REFERENCE)
    imgs = [a for t, a in _parse(html).tags if t == "img"]
    assert len(imgs) == 1
    img = imgs[0]
    assert img["src"] == "cid:kite-logo"
    assert img["alt"] == "Blackkite"
    assert (img["width"], img["height"]) == ("42", "28")


def test_layout_tables_are_presentational():
    tables = [a for t, a in _parse(render_digest(REFERENCE)[1]).tags if t == "table"]
    assert tables and all(a.get("role") == "presentation" for a in tables)


def test_preview_is_chrome_plus_the_email_card():
    """The preview page wraps exactly the email's card; only the chrome differs.

    The one preview-only change inside the card is `height: 100%` on the card and
    footer cell, which pins the footer to the bottom of the board's 1000 px frame.
    """
    _, html, _ = render_digest(REFERENCE, logo_src="kite.png")
    preview = render_digest_preview(REFERENCE, logo_src="kite.png")
    card_start = '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560"'
    email_card = html[html.index(card_start):html.index("\n</td>\n</tr>\n</table>\n</body>")]
    preview_card = preview[preview.index(card_start):preview.index("\n</div>\n</div>\n</body>")]
    assert preview_card.replace(" height: 100%;", "").replace("height: 100%; ", "") == email_card
    assert "Subject:" in preview and "Subject:" not in html


# --- Link safety: every href is an http(s) URL ----------------------------------

BAD_LINKS = [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "mailto:someone",
    "//evil.example/x",
    "/relative/path",
    "https://",
    "https://e.org/a b",
    "https://e.org/\nx",
    "",
    "#",  # placeholder: only inside allow_placeholder_links()
    "#top",
]


def _item(url: str) -> DigestItem:
    return DigestItem(stream="tender", title="t", url=url, summary="s", date_line="d")


@pytest.mark.parametrize("url", BAD_LINKS)
def test_item_url_rejects_non_http(url):
    with pytest.raises(ValidationError):
        _item(url)


@pytest.mark.parametrize("url", BAD_LINKS)
def test_cta_and_footer_urls_reject_non_http(url):
    good = "https://e.org/ok"
    with pytest.raises(ValidationError):
        DigestFooter(source_count=1, frequency="f", change_frequency_url=url, unsubscribe_url=good)
    with pytest.raises(ValidationError):
        DigestFooter(source_count=1, frequency="f", change_frequency_url=good, unsubscribe_url=url)
    data = REFERENCE.model_dump()
    data["cta_url"] = url
    data["items"] = [{**i, "url": good} for i in data["items"]]
    data["footer"].update(change_frequency_url=good, unsubscribe_url=good)
    with pytest.raises(ValidationError):
        DigestView.model_validate(data)


@pytest.mark.parametrize("url", ["https://e.org/o/1?x=1#frag", "http://localhost:5173/feed",
                                 "HTTPS://E.ORG/"])
def test_http_links_accepted(url):
    assert _item(url).url == url


def test_placeholder_only_inside_context():
    with allow_placeholder_links():
        assert _item("#").url == "#"
        with pytest.raises(ValidationError):
            _item("javascript:alert(1)")  # the context admits "#" only
    with pytest.raises(ValidationError):
        _item("#")


def test_fixture_round_trip_needs_placeholder_context():
    data = REFERENCE.model_dump()
    with pytest.raises(ValidationError):
        DigestView.model_validate(data)
    with allow_placeholder_links():
        assert DigestView.model_validate(data) == REFERENCE
