"""Urgent alert email (spec 8). Like the digest, rendering is a pure function of
a typed view; choosing the items happens in delivery/alerts.py."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from blackkite.delivery.digest import (
    CTA_LABEL,
    DEFAULT_LOGO_SRC,
    DigestItem,
    LinkUrl,
    _env,
    _Model,
)

FOOTER_LINE = (
    "You get these alerts when an item fits one of your profiles at your alert "
    "level and closes within 5 days."
)


class AlertView(_Model):
    subject: str
    issue_date: date
    heading: str
    intro: str
    items: list[DigestItem] = Field(min_length=1)
    cta_url: LinkUrl
    settings_url: LinkUrl
    # Signed one-click link that turns alerts off (decision 43).
    unsubscribe_url: LinkUrl
    footer_line: str = FOOTER_LINE

    @property
    def issue_date_text(self) -> str:
        d = self.issue_date
        return f"{d:%A} {d.day} {d:%B} {d.year}"


def _text(view: AlertView) -> str:
    lines = [view.heading, "", view.intro, ""]
    for item in view.items:
        date_line = item.date_line + (
            f" · {item.trust_note}" if item.trust_note else ""
        )
        lines += [item.label, item.title, item.summary]
        if item.value_line:
            lines.append(item.value_line)
        lines += [date_line, item.url, ""]
    lines += [
        f"{CTA_LABEL}: {view.cta_url}",
        "",
        "--",
        view.footer_line,
        f"Change alert settings: {view.settings_url}",
        f"Stop these alerts: {view.unsubscribe_url}",
        "",
    ]
    return "\n".join(lines)


def render_alert(
    view: AlertView, logo_src: str = DEFAULT_LOGO_SRC
) -> tuple[str, str, str]:
    """(subject, html, text) for one urgent alert email."""
    html = (
        _env()
        .get_template("alert.html.j2")
        .render(v=view, logo_src=logo_src, cta_label=CTA_LABEL)
    )
    return view.subject, html, _text(view)
