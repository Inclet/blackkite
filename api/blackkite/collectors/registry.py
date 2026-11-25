"""collector_type -> collector class (spec 4.2), and config validation per type.

Types without an implementation yet get ``UnimplementedCollector``, which raises
``CollectorError("not implemented yet")`` so a source of that type fails cleanly
and the run moves on.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import SecretStr

from blackkite.collectors import html_list, search_query
from blackkite.collectors.base import Collector, CollectorError
from blackkite.collectors.http import FetchClient
from blackkite.db.models import COLLECTOR_TYPES

IMPLEMENTED = ("html_list", "search_query")
MAX_CONFIG_BYTES = 20_000


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
) -> Collector:
    if collector_type == "html_list":
        return html_list.HtmlListCollector(client, preview=preview)
    if collector_type == "search_query":
        return search_query.SearchQueryCollector(client, brave_api_key, preview=preview)
    if collector_type in COLLECTOR_TYPES:
        return UnimplementedCollector(collector_type)
    raise CollectorError(f"unknown collector type {collector_type!r}")


def validate_config(collector_type: str, config: Any) -> dict[str, Any]:
    """Check an admin-entered config. Raises ValueError (TypeError for a non-object)
    with a readable message.

    Implemented types are validated strictly (URLs through the URL guard, selectors
    compiled as CSS). Others are stored as given (size-limited) until their
    collector exists.
    """
    if not isinstance(config, dict):
        raise TypeError("config must be a JSON object")
    if len(json.dumps(config)) > MAX_CONFIG_BYTES:
        raise ValueError(f"config larger than {MAX_CONFIG_BYTES} bytes")
    try:
        if collector_type == "html_list":
            return html_list.parse_config(config).model_dump(exclude_none=True)
        if collector_type == "search_query":
            return search_query.parse_config(config).model_dump(exclude_none=True)
    except CollectorError as e:
        raise ValueError(str(e)) from None
    if collector_type not in COLLECTOR_TYPES:
        raise ValueError(f"unknown collector type {collector_type!r}")
    return config
