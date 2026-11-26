"""Procurement record collectors: ``umucyo_awards`` and ``umucyo_plans`` (spec 2.6,
4.5, 6; M5). Allowlisted ``custom`` collectors (collectors/custom.py).

Umucyo publishes awarded contracts (with every bidder's price) and procurement
plans (tenders before they are advertised). Its real pages were not reachable
from the cloud environment and are untested until M0 (spec 2.1), so nothing here
assumes their markup: every field is a CSS selector in the source config, like
``html_list``, and the tests use synthetic pages only.

Both collectors fetch through the run's guarded ``FetchClient`` (URL guard,
robots.txt, per-host rate limit, size caps, cache), read a listing page and its
``{page}`` pagination, and return ``[]`` from ``fetch``: they never produce
opportunities. What they found is ``self.records`` (``collectors.base.Records``),
text as listed; the runner writes it through ``pipeline/awards.py`` or
``pipeline/plans.py``, which normalise it with the config's formats. A test run
(``preview=True``) reads the first page only (and at most 3 detail pages) and the
preview shows the records normalised, writing nothing.

Rows with none of the fields (table headers, spacer rows) are skipped silently;
rows with some fields but not the required ones are skipped with a run warning
(``record_skipped``).

Options (awards)::

    {"list_url": "https://.../awards", "pagination_pattern": "...?page={page}",
     "max_pages": 3, "max_items": 200,
     "selectors": {"item": "table.awards tbody tr",
                   "tender_ref": "td:nth-child(1)", "title": "td:nth-child(2)",
                   "entity": "td:nth-child(3)", "winner": "td:nth-child(4)",
                   "amount": "td:nth-child(5)", "award_date": "td:nth-child(6)",
                   "link": {"css": "a", "attr": "href"},
                   "bidders": {"row": "ul.bids li", "name": ".bidder",
                               "price": ".price"}},
     "detail": {"selectors": {"bidders": {...}, "period": ".period"},
                "max_items": 20},
     "date_formats": ["%d/%m/%Y"],
     "amounts": {"decimal_separator": ".", "thousands_separators": [",", " "],
                 "currency": "RWF"}}

Options (plans): ``selectors`` has ``item``, ``description`` (required),
``entity``, ``method``, ``estimated_value``, ``currency``, ``planned_date``,
``planned_quarter``, ``fiscal_year``, ``tender_ref``, ``link``; ``page`` holds
``entity`` / ``fiscal_year`` selectors read once from the whole page (plans are
often one page per entity and year); ``quarter_basis`` (``fiscal`` or
``calendar``) is required when quarters are read, because a quarter means
nothing without it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from selectolax.lexbor import LexborHTMLParser, LexborNode

from blackkite.collectors.base import (
    CollectorError,
    Formats,
    RawAward,
    RawBidder,
    RawPlan,
    Records,
)
from blackkite.collectors.common import safe_url, utc_now
from blackkite.collectors.html_list import (
    Sel,
    _check_css,
    _http_link,
    _parse,
    _sel,
    _value,
)
from blackkite.collectors.http import FetchClient

PREVIEW_DETAIL_ITEMS = 3
MAX_BIDDERS = 100
_SEL = "A CSS selector, or {css, attr} to read an attribute."
SELECTOR_FIELDS_AWARD = (
    "tender_ref",
    "title",
    "entity",
    "winner",
    "amount",
    "currency",
    "award_date",
    "period",
)
SELECTOR_FIELDS_PLAN = (
    "entity",
    "description",
    "method",
    "estimated_value",
    "currency",
    "planned_date",
    "planned_quarter",
    "fiscal_year",
    "tender_ref",
)


def _check_date_format(v: str) -> str:
    from blackkite.pipeline.procurement import check_date_format

    return check_date_format(v)


# --- shared option pieces -----------------------------------------------------------


Separator = Literal[",", ".", " ", "'"]


class AmountOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decimal_separator: Literal[".", ","] = Field(
        default=".", description="Character before the decimals in amounts."
    )
    thousands_separators: Annotated[list[Separator], Field(max_length=4)] = Field(
        default=[",", " "],
        description="Characters that group thousands in amounts (removed).",
    )
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = Field(
        default=None,
        description="Currency of amounts that do not name one (three letters, for "
        "example RWF). Leave empty if the page does not say: such amounts are "
        "kept without a currency and left out of price statistics.",
    )

    @model_validator(mode="after")
    def _distinct(self) -> AmountOptions:
        if self.decimal_separator in self.thousands_separators:
            raise ValueError(
                "the decimal separator cannot also be a thousands separator"
            )
        return self


class BidderSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: str = Field(description="CSS selector matching one node per bidder.")
    name: Sel = Field(description=f"Bidder name inside the row. {_SEL}")
    price: Sel | None = Field(
        default=None, description=f"Bid price inside the row. {_SEL}"
    )

    @field_validator("row")
    @classmethod
    def _row(cls, v: str) -> str:
        return _check_css(v)

    @field_validator("name", "price", mode="before")
    @classmethod
    def _wrap(cls, v: Any) -> Any:
        return _sel(v)


class Paging(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_url: str = Field(description="Address of the list page (page 1).")
    pagination_pattern: str | None = Field(
        default=None,
        description="Address of later pages with {page} where the number goes.",
    )
    first_page: Annotated[int, Field(ge=0, le=1000)] = Field(
        default=2, description="Page number of the first pattern page."
    )
    max_pages: Annotated[int, Field(ge=1, le=50)] = Field(
        default=1, description="Pages to read per run, counting list_url as 1."
    )
    max_items: Annotated[int, Field(ge=1, le=2000)] = Field(
        default=500, description="Keep at most this many records per run."
    )
    date_formats: Annotated[list[str], Field(max_length=10)] = Field(
        default=[],
        description="Date formats tried in order, strftime style, each with a "
        "year (for example %d/%m/%Y). Empty: day-first dates with a written year.",
    )
    amounts: AmountOptions = Field(
        default_factory=AmountOptions, description="How amounts are written."
    )

    @field_validator("list_url")
    @classmethod
    def _list_url(cls, v: str) -> str:
        return safe_url(v)

    @field_validator("pagination_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "{page}" not in v:
            raise ValueError("pagination_pattern must contain {page}")
        safe_url(v.replace("{page}", "1"))
        return v

    @field_validator("date_formats")
    @classmethod
    def _formats(cls, v: list[str]) -> list[str]:
        return [_check_date_format(f) for f in v]

    def page_urls(self) -> list[str]:
        urls = [self.list_url]
        if self.pagination_pattern:
            for i in range(self.max_pages - 1):
                urls.append(
                    self.pagination_pattern.replace("{page}", str(self.first_page + i))
                )
        return urls

    def formats(self, quarter_basis: Any = None) -> Formats:
        return Formats(
            date_formats=tuple(self.date_formats),
            decimal_separator=self.amounts.decimal_separator,
            thousands_separators=tuple(self.amounts.thousands_separators),
            currency=self.amounts.currency,
            quarter_basis=quarter_basis,
        )


def _wrap_fields(*names: str):
    return field_validator(*names, mode="before")(lambda cls, v: _sel(v))


# --- awards -------------------------------------------------------------------------


class AwardFieldSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tender_ref: Sel | None = Field(
        default=None, description=f"Tender reference number. {_SEL}"
    )
    title: Sel | None = Field(default=None, description=f"Tender title. {_SEL}")
    entity: Sel | None = Field(
        default=None, description=f"Procuring entity (the buyer). {_SEL}"
    )
    winner: Sel | None = Field(default=None, description=f"Winning bidder. {_SEL}")
    amount: Sel | None = Field(
        default=None, description=f"Winning (contract) price. {_SEL}"
    )
    currency: Sel | None = Field(
        default=None, description=f"Currency, when in its own cell. {_SEL}"
    )
    award_date: Sel | None = Field(
        default=None, description=f"Date of the award. {_SEL}"
    )
    period: Sel | None = Field(
        default=None, description=f"Contract period as listed. {_SEL}"
    )
    bidders: BidderSelectors | None = Field(
        default=None, description="Every bidder and its price, when listed."
    )

    wrap_selectors = _wrap_fields(*SELECTOR_FIELDS_AWARD)


class AwardSelectors(AwardFieldSelectors):
    item: str = Field(description="CSS selector matching one node per award.")
    link: Sel | None = Field(
        default=None,
        description=f"Link to the award notice (default: the first <a> in the "
        f"item). {_SEL}",
    )

    @field_validator("item")
    @classmethod
    def _item(cls, v: str) -> str:
        return _check_css(v)

    @field_validator("link", mode="before")
    @classmethod
    def _wrap_link(cls, v: Any) -> Any:
        return _sel(v)

    @model_validator(mode="after")
    def _identifies(self) -> AwardSelectors:
        if self.tender_ref is None and self.title is None:
            raise ValueError("set tender_ref or title: an award needs one of them")
        return self


class AwardDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selectors: AwardFieldSelectors = Field(
        description="Selectors on each award's own page; values found there "
        "replace the list's."
    )
    max_items: Annotated[int, Field(ge=1, le=50)] = Field(
        default=20, description="Follow at most this many award pages per run."
    )


class AwardsOptions(Paging):
    selectors: AwardSelectors = Field(description="Where each field is on the list.")
    detail: AwardDetail | None = Field(
        default=None, description="Optional: follow each award's link."
    )


# --- plans --------------------------------------------------------------------------


class PlanSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(description="CSS selector matching one node per planned tender.")
    description: Sel = Field(description=f"What will be procured. {_SEL}")
    entity: Sel | None = Field(
        default=None, description=f"Procuring entity, per row. {_SEL}"
    )
    method: Sel | None = Field(default=None, description=f"Procurement method. {_SEL}")
    estimated_value: Sel | None = Field(
        default=None, description=f"Estimated value. {_SEL}"
    )
    currency: Sel | None = Field(
        default=None, description=f"Currency, when in its own cell. {_SEL}"
    )
    planned_date: Sel | None = Field(
        default=None, description=f"Planned date of the tender notice. {_SEL}"
    )
    planned_quarter: Sel | None = Field(
        default=None, description=f"Planned quarter (Q1 to Q4). {_SEL}"
    )
    fiscal_year: Sel | None = Field(
        default=None, description=f"Fiscal year, per row (2026/27). {_SEL}"
    )
    tender_ref: Sel | None = Field(
        default=None, description=f"Tender reference, when planned. {_SEL}"
    )
    link: Sel | None = Field(
        default=None, description=f"Link to the plan entry, if any. {_SEL}"
    )

    wrap_selectors = _wrap_fields(*SELECTOR_FIELDS_PLAN, "link")

    @field_validator("item")
    @classmethod
    def _item(cls, v: str) -> str:
        return _check_css(v)


class PlanPageSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: Sel | None = Field(
        default=None,
        description=f"Procuring entity for the whole page (rows without one). {_SEL}",
    )
    fiscal_year: Sel | None = Field(
        default=None,
        description=f"Fiscal year for the whole page (rows without one). {_SEL}",
    )

    wrap_selectors = _wrap_fields("entity", "fiscal_year")


class PlansOptions(Paging):
    selectors: PlanSelectors = Field(description="Where each field is on the list.")
    page: PlanPageSelectors | None = Field(
        default=None, description="Optional: values stated once for the page."
    )
    quarter_basis: Literal["fiscal", "calendar"] | None = Field(
        default=None,
        description="What the plan's quarters count from: fiscal (Q1 = July to "
        "September, Rwanda's fiscal year) or calendar (Q1 = January to March). "
        "Required when quarters are read.",
    )

    @model_validator(mode="after")
    def _basis(self) -> PlansOptions:
        if self.selectors.planned_quarter is not None and self.quarter_basis is None:
            raise ValueError(
                "quarter_basis is required with a planned_quarter selector: "
                "a quarter is not a date without it"
            )
        return self


# --- fetching -----------------------------------------------------------------------


def _row_link(node: LexborNode, sel: Sel | None, base: str) -> str | None:
    if sel is not None:
        found = node.css_first(sel.css)
        if found is None:
            return None
        return _http_link(base, found.attributes.get(sel.attr or "href"))
    a = node if node.tag == "a" else node.css_first("a[href]")
    return _http_link(base, a.attributes.get("href")) if a is not None else None


def _bidders(root: LexborNode, sels: BidderSelectors | None) -> tuple[RawBidder, ...]:
    if sels is None:
        return ()
    out = []
    for row in root.css(sels.row)[:MAX_BIDDERS]:
        name = _value(row, sels.name, 300)
        price = _value(row, sels.price, 200)
        if name or price:
            out.append(RawBidder(name=name, price=price))
    return tuple(out)


class _RecordCollector:
    Options: ClassVar[type[Paging]]
    kind: ClassVar[str]

    def __init__(
        self,
        client: FetchClient,
        options: Any,
        *,
        preview: bool = False,
        now=utc_now,
    ) -> None:
        self.client = client
        self.options = options
        self.preview = preview
        self.now = now
        self.records: Records | None = None
        self.warnings: list[dict] = []

    def _pages(self, source):
        opts = self.options
        pages = opts.page_urls()[:1] if self.preview else opts.page_urls()
        for page_url in pages:
            resp = self.client.get(page_url, delay=source.rate_limit)
            tree = LexborHTMLParser(resp.text)
            nodes = _parse(resp.text, opts.selectors.item)
            if not nodes and page_url != pages[0]:
                break  # ran past the last page
            yield resp.url, tree, nodes

    def _skip(self, message: str) -> None:
        if len(self.warnings) < 50:
            self.warnings.append({"kind": "record_skipped", "message": message[:300]})


class UmucyoAwardsCollector(_RecordCollector):
    name: ClassVar[str] = "umucyo_awards"
    help: ClassVar[str] = (
        "Awarded contracts with winners, bidders and prices from a procurement "
        "portal's award list (Umucyo and similar), for price benchmarks. Writes "
        "awards, never opportunities."
    )
    Options: ClassVar[type[BaseModel]] = AwardsOptions
    kind: ClassVar[str] = "award"

    def fetch(self, source) -> list:
        opts: AwardsOptions = self.options
        sels = opts.selectors
        found: list[RawAward] = []
        seen: set[tuple] = set()
        for page_url, _tree, nodes in self._pages(source):
            fetched_at = self.now()
            for node in nodes:
                values = {
                    f: _value(node, getattr(sels, f)) for f in SELECTOR_FIELDS_AWARD
                }
                bidders = _bidders(node, sels.bidders)
                if not any(values.values()) and not bidders:
                    continue
                if not values["tender_ref"] and not values["title"]:
                    self._skip(f"award on {page_url} has no tender ref or title")
                    continue
                key = (values["tender_ref"], values["title"], values["entity"])
                if key in seen:
                    continue
                seen.add(key)
                link = _row_link(node, sels.link, page_url)
                found.append(
                    RawAward(
                        source_id=source.id,
                        url=link or page_url,
                        fetched_at=fetched_at,
                        bidders=bidders,
                        **values,
                    )
                )
                if len(found) >= opts.max_items:
                    break
            if len(found) >= opts.max_items:
                break
        if opts.detail is not None:
            limit = PREVIEW_DETAIL_ITEMS if self.preview else opts.detail.max_items
            found = [
                self._with_detail(a, opts.detail, source.rate_limit)
                if i < limit and a.url not in opts.page_urls()
                else a
                for i, a in enumerate(found)
            ]
        self.records = Records("award", found, opts.formats())
        return []

    def _with_detail(self, award: RawAward, detail: AwardDetail, delay) -> RawAward:
        try:
            resp = self.client.get(award.url, delay=delay)
            root = LexborHTMLParser(resp.text).body
        except CollectorError as e:
            self._skip(f"award page {award.url} not read: {str(e)[:200]}")
            return award
        if root is None:
            return award
        sels = detail.selectors
        changes: dict[str, Any] = {}
        for f in SELECTOR_FIELDS_AWARD:
            v = _value(root, getattr(sels, f))
            if v:
                changes[f] = v
        bidders = _bidders(root, sels.bidders)
        if bidders:
            changes["bidders"] = bidders
        return replace(award, **changes)


class UmucyoPlansCollector(_RecordCollector):
    name: ClassVar[str] = "umucyo_plans"
    help: ClassVar[str] = (
        "Planned tenders from a procurement plan list (Umucyo and similar): "
        "tenders before they are advertised. Writes plan items, never "
        "opportunities."
    )
    Options: ClassVar[type[BaseModel]] = PlansOptions
    kind: ClassVar[str] = "plan"

    def fetch(self, source) -> list:
        opts: PlansOptions = self.options
        sels = opts.selectors
        found: list[RawPlan] = []
        seen: set[tuple] = set()
        for page_url, tree, nodes in self._pages(source):
            fetched_at = self.now()
            page_values: dict[str, str | None] = {}
            root = tree.body
            if opts.page is not None and root is not None:
                page_values = {
                    "entity": _value(root, opts.page.entity, 300),
                    "fiscal_year": _value(root, opts.page.fiscal_year, 100),
                }
            for node in nodes:
                values = {
                    f: _value(node, getattr(sels, f)) for f in SELECTOR_FIELDS_PLAN
                }
                if not any(values.values()):
                    continue
                for f, v in page_values.items():
                    values[f] = values[f] or v
                if not values["description"] or not values["entity"]:
                    self._skip(
                        f"plan entry on {page_url} has no "
                        + ("description" if not values["description"] else "entity")
                    )
                    continue
                key = (values["entity"], values["description"], values["fiscal_year"])
                if key in seen:
                    continue
                seen.add(key)
                link = _row_link(node, sels.link, page_url) if sels.link else None
                found.append(
                    RawPlan(
                        source_id=source.id,
                        url=link or page_url,
                        fetched_at=fetched_at,
                        **values,
                    )
                )
                if len(found) >= opts.max_items:
                    break
            if len(found) >= opts.max_items:
                break
        self.records = Records("plan", found, opts.formats(opts.quarter_basis))
        return []
