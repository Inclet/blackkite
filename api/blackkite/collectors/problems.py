"""Plain-language config problems for admins (spec 4.3: "fix the config until the
preview is right").

A ``Problem`` is one thing wrong with one field: a machine path (for the web to
place it next to the field) and a short message without Pydantic boilerplate or
URLs. ``ConfigInvalid`` carries the problems of one collector config;
``FieldValueError`` lets a request-body validator name the field it is about.

``sentence`` renders a problem in the admin's words: ``"Feed URL: address
127.0.0.1 is not public."``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from pydantic.alias_generators import to_snake

from blackkite.collectors.base import CollectorError

Path = tuple[str | int, ...]

_URL = re.compile(r"\b(?:https?|ftp|file)://[^\s'\"<>]+", re.IGNORECASE)
_WORDS = {
    "url": "URL",
    "urls": "URLs",
    "css": "CSS",
    "id": "ID",
    "api": "API",
    "json": "JSON",
    "rss": "RSS",
    "imap": "IMAP",
    "http": "HTTP",
}
# Top-level fields of a source (SourceIn, SourcePatch, PreviewIn, StatusIn),
# as the admin screen names them.
SOURCE_LABELS = {
    "name": "Name",
    "home_url": "Home page",
    "publisher": "Publisher",
    "streams": "Streams",
    "kind": "Kind",
    "collector_type": "Collector type",
    "config": "Config",
    "schedule": "Schedule",
    "rate_limit": "Seconds between requests",
    "access_note": "Access note",
    "suggestion_id": "Suggestion",
    "status": "Status",
}
_SELECTOR_GROUPS = {"selectors": "", "detail_selectors": "Detail page "}


@dataclass(frozen=True, slots=True)
class Problem:
    path: Path  # () = the whole request or config
    message: str  # plain, no trailing full stop

    @property
    def field(self) -> str | None:
        """Dotted path for the web: top-level keys camelCase (``homeUrl``),
        keys inside ``config`` as the collector names them (``config.feed_url``,
        ``config.selectors.item``, ``config.queries.0``)."""
        if not self.path:
            return None
        head, *rest = self.path
        top = _camel(str(head))
        return ".".join([top, *(str(p) for p in rest)])


def _camel(name: str) -> str:
    snake = to_snake(name)
    first, *others = snake.split("_")
    return first + "".join(w.capitalize() for w in others)


def humanize(name: str, *, capital: bool = True) -> str:
    words = [w for w in to_snake(name).split("_") if w]
    out = [_WORDS.get(w, w) for w in words]
    if out and capital:
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def label(path: Path) -> str:
    """A field path in the admin's words."""
    if not path:
        return "Request"
    head = to_snake(str(path[0]))
    if head != "config" or len(path) == 1:
        return SOURCE_LABELS.get(head, humanize(head))
    return config_label(path[1:])


def config_label(path: Path) -> str:
    """A path inside a collector config: ``feed_url`` -> "Feed URL",
    ``selectors.item`` -> "Item selector", ``queries.0`` -> "Queries, item 1"."""
    if not path:
        return "Config"
    names = [p for p in path if isinstance(p, str)]
    index = next((p for p in reversed(path) if isinstance(p, int)), None)
    if len(names) >= 2 and names[-2] in _SELECTOR_GROUPS:
        child = humanize(names[-1], capital=False)
        text = f"{_SELECTOR_GROUPS[names[-2]]}{child} selector"
        text = text[:1].upper() + text[1:]
    elif names:
        text = ", ".join(
            [humanize(names[0])] + [humanize(n, capital=False) for n in names[1:]]
        )
    else:
        text = "Config"
    if index is not None:
        text += f", item {index + 1}"
    return text


def plain(message: str) -> str:
    """A message without Pydantic's prefixes, URLs or a trailing full stop."""
    text = str(message).strip()
    for prefix in ("Value error, ", "Assertion failed, "):
        text = text.removeprefix(prefix)
    text = _URL.sub("the address", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("Input should be"):
        text = "must be" + text[len("Input should be") :]
    return text.rstrip(".").strip() or "is not valid"


def from_error(err: dict[str, Any], prefix: Path = ()) -> list[Problem]:
    """Problems from one Pydantic error dict (``ValidationError.errors()``)."""
    loc = tuple(err.get("loc") or ())
    ctx = err.get("ctx") or {}
    cause = ctx.get("error")
    if isinstance(cause, FieldValueError | ConfigInvalid):
        # Their paths are already from the top of the model being validated
        # (``("config", "feed_url")``), whichever validator raised them.
        return [Problem(prefix + p.path, p.message) for p in cause.problems]
    kind = err.get("type", "")
    if not prefix + loc and kind in ("missing", "model_attributes_type", "dict_type"):
        message = "must be a JSON object"
    elif kind == "missing":
        message = "is required"
    elif kind == "extra_forbidden":
        message = "is not a setting this accepts"
    elif kind == "string_too_short" and ctx.get("min_length") == 1:
        message = "must not be empty"
    elif kind == "greater_than_equal":
        message = f"must be at least {_num(ctx.get('ge'))}"
    elif kind == "less_than_equal":
        message = f"must be at most {_num(ctx.get('le'))}"
    elif kind == "json_invalid":
        message = "is not valid JSON"
    else:
        message = plain(err.get("msg", ""))
    return [Problem(prefix + loc, message)]


def _num(v: Any) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def from_validation(e: ValidationError, prefix: Path = ()) -> list[Problem]:
    out: list[Problem] = []
    for err in e.errors():
        out.extend(from_error(err, prefix))
    return out


def sentence(p: Problem, labeller=label) -> str:
    message = p.message.rstrip(".")
    return f"{labeller(p.path)}: {message}."


def sentences(problems: Iterable[Problem], labeller=label) -> str:
    seen: list[str] = []
    for p in problems:
        s = sentence(p, labeller)
        if s not in seen:
            seen.append(s)
    return " ".join(seen)


class FieldValueError(ValueError):
    """A validator's refusal that names the field(s) it is about."""

    def __init__(self, problems: Sequence[Problem]) -> None:
        self.problems = list(problems)
        super().__init__(sentences(self.problems))

    @classmethod
    def at(cls, path: Path, message: str) -> FieldValueError:
        return cls([Problem(path, message)])


class ConfigInvalid(CollectorError):
    """A collector config that does not validate. ``problems`` have paths
    relative to the config; ``str()`` is the run-log text ("invalid rss config:
    Feed URL: address 127.0.0.1 is not public.")."""

    def __init__(self, collector_type: str, problems: Sequence[Problem]) -> None:
        self.collector_type = collector_type
        self.problems = [Problem(("config", *p.path), p.message) for p in problems]
        super().__init__(f"invalid {collector_type} config: {self.text}")

    @property
    def text(self) -> str:
        """The plain sentences alone, for the admin screen."""
        return sentences(self.problems)
