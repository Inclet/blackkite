"""collector_type -> collector class (spec 4.2), config validation and config forms.

``CONFIG_MODELS`` maps each collector type to its Pydantic config model. The admin
API renders the config editor from ``config_form(collector_type)`` (field name,
type, required, help text, default; plus the full JSON schema) and validates what
the admin sends with ``validate_config``.

Types without an implementation yet get ``UnimplementedCollector``, which raises
``CollectorError("not implemented yet")`` so a source of that type fails cleanly
and the run moves on.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, SecretStr

from blackkite.collectors import (
    custom,
    email_ingest,
    forms,
    html_list,
    json_api,
    rss,
    search_query,
)
from blackkite.collectors.base import Collector, CollectorError
from blackkite.collectors.http import FetchClient
from blackkite.db.models import COLLECTOR_TYPES

MAX_CONFIG_BYTES = 20_000

# collector_type -> config model (rendered as a form) and its parser (raises
# CollectorError with a readable message; also refuses seed placeholders).
CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "html_list": html_list.HtmlListConfig,
    "search_query": search_query.SearchQueryConfig,
    "rss": rss.RssConfig,
    "json_api": json_api.JsonApiConfig,
    "custom": custom.CustomConfig,
    "email_ingest": email_ingest.EmailIngestConfig,
}
_PARSERS: dict[str, Callable[[dict[str, Any]], BaseModel]] = {
    "html_list": html_list.parse_config,
    "search_query": search_query.parse_config,
    "rss": rss.parse_config,
    "json_api": json_api.parse_config,
    "custom": custom.parse_config,
    "email_ingest": email_ingest.parse_config,
}
IMPLEMENTED = tuple(CONFIG_MODELS)


class UnimplementedCollector:
    def __init__(self, collector_type: str) -> None:
        self.collector_type = collector_type

    def fetch(self, source):
        raise CollectorError(
            f"collector type {self.collector_type} is not implemented yet"
        )


def build_collector(
    collector_type: str,
    client: FetchClient,
    *,
    brave_api_key: SecretStr | None = None,
    preview: bool = False,
    mailbox_factory: Callable[[], email_ingest.Mailbox] | None = None,
) -> Collector:
    """A collector for one run. ``preview=True`` for test runs: smallest useful
    fetch, and nothing written anywhere (no flags set on a mailbox either).

    ``mailbox_factory`` (email_ingest) defaults to the IMAP inbox named by
    BK_INGEST_IMAP_*; tests pass fakes."""
    if collector_type == "html_list":
        return html_list.HtmlListCollector(client, preview=preview)
    if collector_type == "search_query":
        return search_query.SearchQueryCollector(client, brave_api_key, preview=preview)
    if collector_type == "rss":
        return rss.RssCollector(client, preview=preview)
    if collector_type == "json_api":
        return json_api.JsonApiCollector(client, preview=preview)
    if collector_type == "custom":
        return custom.CustomCollector(client, preview=preview)
    if collector_type == "email_ingest":
        return email_ingest.EmailIngestCollector(
            mailbox_factory or email_ingest.mailbox_from_env, preview=preview
        )
    if collector_type in COLLECTOR_TYPES:
        return UnimplementedCollector(collector_type)
    raise CollectorError(f"unknown collector type {collector_type!r}")


def validate_config(collector_type: str, config: Any) -> dict[str, Any]:
    """Check an admin-entered config. Raises ValueError (TypeError for a non-object)
    with a readable message. Returns the config as it should be stored.

    Implemented types are validated strictly (URLs through the URL guard, selectors
    compiled as CSS). Others are stored as given (size-limited) until their
    collector exists.
    """
    if not isinstance(config, dict):
        raise TypeError("config must be a JSON object")
    if len(json.dumps(config)) > MAX_CONFIG_BYTES:
        raise ValueError(f"config larger than {MAX_CONFIG_BYTES} bytes")
    parser = _PARSERS.get(collector_type)
    if parser is not None:
        try:
            return parser(config).model_dump(mode="json", exclude_none=True)
        except CollectorError as e:
            raise ValueError(str(e)) from None
    if collector_type not in COLLECTOR_TYPES:
        raise ValueError(f"unknown collector type {collector_type!r}")
    return config


def config_form(collector_type: str) -> dict[str, Any]:
    """What the admin config editor needs for one collector type::

    {"collector_type": "rss", "fields": [{name, type, required, help, default?,
     ...}], "json_schema": {...}}

    For ``custom`` it also has ``collectors``: per allowlisted class, its help
    line and the fields of its ``options``.
    """
    model = CONFIG_MODELS.get(collector_type)
    if model is None:
        raise ValueError(f"no config form for collector type {collector_type!r}")
    form: dict[str, Any] = {
        "collector_type": collector_type,
        "fields": forms.describe(model),
        "json_schema": model.model_json_schema(),
    }
    if collector_type == "custom":
        form["collectors"] = custom.option_forms()
    return form


def config_forms() -> dict[str, dict[str, Any]]:
    return {t: config_form(t) for t in CONFIG_MODELS}
