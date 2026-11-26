"""Rules (spec 7): hard filters, rule flags, and the value / time / source components.

Everything here is deterministic and reads only the opportunity, the profile, the
carrying sources and the caller's own mutes.

Hard filters, in the order checked (first hit wins, stored in ``hard_filtered``):

* ``deadline_passed``: the item is ``expired``, its deadline is past, or (events,
  no deadline) the event has ended.
* ``outside_rwanda``: the location names another country or a city outside Rwanda
  and nothing in Rwanda. An unstated location never filters.
* ``stream_not_selected``: the profile lists its streams and this is not one.
* ``muted_source_only``: every source carrying the item is muted by the user.
* ``ineligible``: the notice explicitly limits applicants to NGOs / non-profits (or
  excludes for-profits) and the profile is not one; or it states a capacity
  threshold above what the profile states. An owned-vehicle threshold above the
  owned fleet is kept and flagged "May require owned fleet" while the partner
  network covers the number (spec 7.1); it filters only when the network does
  not either.
* ``below_min_value``: a tender whose value is stated in RWF under the profile's
  ``min_contract_rwf``.

Missing profile data never filters (spec 7): a null profile field turns the
matching requirement into a flag and lowers eligibility confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from blackkite.db.models import Opportunity, Profile
from blackkite.pipeline.extract import normalise_for_match
from blackkite.scoring.settings import ScoringSettings

# --- carrying sources -----------------------------------------------------------------


@dataclass(frozen=True)
class CarryingSource:
    name: str
    kind: str
    home_url: str
    url: str
    is_original: bool
    muted: bool


@dataclass
class Flag:
    code: str
    label: str
    quote: str | None
    to_check: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "quote": self.quote,
            "to_check": self.to_check,
        }


# Rule flag codes, in display order (the first flag is the row's topFlag).
RULE_FLAGS = {
    "owned_fleet": "May require owned fleet",
    "transport_licence": "Requires transport licence",
    "umucyo_registration": "Needs Umucyo supplier registration",
    "check_capacity": "Check capacity",
    "value_unknown": "Value unknown",
}
RULE_FLAG_ORDER = list(RULE_FLAGS)


@dataclass
class RuleResult:
    hard_filtered: str | None = None
    filter_reason: str | None = None
    flags: list[Flag] = field(default_factory=list)


# --- helpers --------------------------------------------------------------------------


def _who(opp: Opportunity) -> str:
    return opp.organisation_short or opp.organisation or "The notice"


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:!?])\s+|\n+", text) if s.strip()]


def _quote_around(text: str, m: re.Match[str], limit: int = 160) -> str:
    """The sentence of ``text`` holding the match, trimmed to ``limit`` characters
    around it; always a verbatim substring of ``text``."""
    start = max(
        text.rfind(".", 0, m.start()) + 1,
        text.rfind("\n", 0, m.start()) + 1,
        text.rfind(";", 0, m.start()) + 1,
    )
    ends = [i for i in (text.find(c, m.end()) for c in ".\n;") if i != -1]
    end = min(ends) if ends else len(text)
    if end - start > limit:
        start = max(start, m.start() - limit // 3)
        end = min(end, m.end() + limit // 3)
    return text[start:end].strip()


def _find(pattern: re.Pattern[str], parts: list[str]) -> str | None:
    for part in parts:
        m = pattern.search(part)
        if m:
            return _quote_around(part, m)
    return None


def _norm_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).lower() for v in value if v]
    if isinstance(value, str):
        return [value.lower()]
    return []


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    return None


# --- location ------------------------------------------------------------------------

RWANDA_TERMS = re.compile(
    r"\b(rwanda|rwandan|kigali|musanze|huye|rubavu|gisenyi|rusizi|nyagatare|"
    r"muhanga|rwamagana|karongi|kayonza|bugesera|nyanza|gicumbi|ruhengeri|butare|"
    r"kicukiro|gasabo|nyarugenge|online|virtual|remote|hybrid)\b",
    re.IGNORECASE,
)
ELSEWHERE_TERMS = re.compile(
    r"\b(kenya|nairobi|mombasa|uganda|kampala|tanzania|dar es salaam|arusha|dodoma|"
    r"burundi|bujumbura|gitega|congo|drc|kinshasa|goma|bukavu|ethiopia|addis ababa|"
    r"south sudan|juba|somalia|mogadishu|nigeria|lagos|abuja|ghana|accra|senegal|"
    r"dakar|south africa|johannesburg|cape town|pretoria|egypt|cairo|morocco|"
    r"marrakech|casablanca|rabat|zambia|lusaka|malawi|lilongwe|mozambique|maputo|"
    r"zimbabwe|harare|botswana|gaborone|namibia|windhoek|cameroon|douala|yaounde|"
    r"ivory coast|cote d'ivoire|abidjan|tunisia|tunis|algeria|madagascar|mauritius|"
    r"united states|usa|new york|washington|united kingdom|london|france|paris|"
    r"germany|berlin|belgium|brussels|netherlands|amsterdam|switzerland|geneva|"
    r"india|china|dubai|united arab emirates|qatar|doha|singapore)\b",
    re.IGNORECASE,
)


def outside_rwanda(location: str | None) -> bool:
    if not location or not location.strip():
        return False
    return bool(ELSEWHERE_TERMS.search(location)) and not RWANDA_TERMS.search(location)


# --- eligibility ---------------------------------------------------------------------

_NGO = (
    r"(?:(?:local |national |international |registered )*"
    r"(?:ngos?|non[- ]governmental organi[sz]ations?|civil society organi[sz]ations?|"
    r"csos?|non[- ]profits?(?: organi[sz]ations?)?|not[- ]for[- ]profits?"
    r"(?: organi[sz]ations?)?|community[- ]based organi[sz]ations?|cbos?|"
    r"faith[- ]based organi[sz]ations?))"
)
NGO_ONLY = re.compile(
    rf"\b(?:only|exclusively|solely|restricted to|limited to|reserved for|"
    rf"open only to)\s+(?:to\s+)?(?:eligible\s+)?{_NGO}"
    rf"|\b{_NGO}\s+only\b"
    rf"|\bonly\s+{_NGO}\s+(?:are|will be|may)\b"
    rf"|\bfor[- ]profit (?:entities|companies|organi[sz]ations|firms|businesses)"
    rf"\s+(?:are|will) not (?:be )?eligible\b",
    re.IGNORECASE,
)
NGO_PROFILE_TYPES = {"ngo", "non-profit", "nonprofit", "cso", "cbo", "not-for-profit"}


_NGO_SPLIT = re.compile(r"\s+or\s+|\s*[/,;&]\s*|\s+and\s+")


def _is_ngo(profile: Profile) -> bool:
    """The profile's organisation_type names a non-profit: "ngo", "non-profit",
    "nonprofit", ..., alone or as one of several ("ngo or non-profit",
    "NGO / CSO"). Empty or anything else is not an NGO (decision 37)."""
    kind = (profile.data or {}).get("organisation_type")
    if not isinstance(kind, str):
        return False
    text = " ".join(kind.strip().lower().split())
    parts = {p.strip(" .") for p in _NGO_SPLIT.split(text)} | {text}
    return bool(parts & NGO_PROFILE_TYPES)


def eligibility_parts(opp: Opportunity, documents: list[str]) -> list[str]:
    parts = [opp.title]
    if opp.eligibility:
        parts.append(opp.eligibility)
    parts.extend(r for r in (opp.requirements or []) if isinstance(r, str))
    if opp.submission_method:
        parts.append(opp.submission_method)
    for key, entry in (opp.evidence or {}).items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        if isinstance(entry.get("snippet"), str):
            parts.append(entry["snippet"])
        if isinstance(entry.get("snippets"), list):
            parts.extend(s for s in entry["snippets"] if isinstance(s, str))
    parts.extend(d for d in documents if d)
    return [normalise_for_match(p) for p in parts if p]


# --- capacity ------------------------------------------------------------------------

_VEHICLE = r"(?:trucks?|lorries|lorry|vehicles?|trailers?|reefers?)"
_AT_LEAST = (
    r"(?:a minimum of|minimum of|minimum|min\.?|at least|not less than|no fewer than|"
    r"no less than)"
)
CAPACITY_RE = re.compile(
    rf"(?P<pre>[^.;\n]{{0,60}}?)\b{_AT_LEAST}\s+(?P<n>\d[\d,]*)\s+(?:\(\d+\)\s+)?"
    rf"(?P<adj>(?:own(?:ed)?|registered|refrigerated|reefer|cold[- ]chain|"
    rf"insulated|operational|roadworthy|functional|heavy|\s)*)\s*{_VEHICLE}"
    rf"|\bfleet of\s+(?:{_AT_LEAST}\s+)?(?P<n2>\d[\d,]*)\s+(?P<adj2>(?:refrigerated |"
    rf"reefer |cold[- ]chain )?){_VEHICLE}?",
    re.IGNORECASE,
)
TONNAGE_RE = re.compile(
    rf"\b(?:capacity|payload)\s+(?:of\s+)?(?:{_AT_LEAST}\s+)?(?P<n>\d[\d,.]*)\s*"
    rf"(?:tonnes|tons|t|mt|metric tons?)\b"
    rf"|\b{_AT_LEAST}\s+(?P<n2>\d[\d,.]*)\s*(?:tonnes|tons|mt|metric tons?)\s+"
    rf"(?:of\s+)?(?:capacity|payload|carrying capacity)\b",
    re.IGNORECASE,
)
_OWN = re.compile(r"\b(?:own|owns|owned|ownership|in the name of)\b", re.IGNORECASE)
_COLD = re.compile(r"refrigerat|reefer|cold", re.IGNORECASE)


@dataclass
class CapacityCheck:
    ineligible: str | None = None  # reason
    check: str | None = None  # quote needing a capacity check
    owned: str | None = None  # quote of an ownership threshold the profile lacks


def check_capacity(profile: Profile, parts: list[str]) -> CapacityCheck:
    cap = (profile.data or {}).get("capacity")
    cap = cap if isinstance(cap, dict) else {}
    out = CapacityCheck()
    for part in parts:
        for m in CAPACITY_RE.finditer(part):
            n = int((m.group("n") or m.group("n2")).replace(",", ""))
            adj = (
                (m.group("adj") or m.group("adj2") or "") + " " + (m.group("pre") or "")
            )
            quote = _quote_around(part, m)
            owned = bool(_OWN.search(adj))
            if owned:
                key = "owned_trucks"
            elif _COLD.search(adj):
                key = "refrigerated_in_network"
            else:
                key = "trucks_in_network"
            have = _num(cap.get(key))
            if key == "trucks_in_network" and have is None:
                have = _num(cap.get("owned_trucks"))
            network = _num(cap.get("trucks_in_network"))
            # Spec 7.1: the volume is there through the partner network; the
            # ownership may not be. Keep and flag "May require owned fleet" when
            # the network covers the number; filter only when it does not.
            if (
                owned
                and (have is None or have < n)
                and network is not None
                and network >= n
            ):
                out.owned = out.owned or quote
                continue
            if have is None:
                if owned:
                    out.owned = out.owned or quote
                else:
                    out.check = out.check or quote
            elif have < n:
                out.ineligible = out.ineligible or (
                    f"It asks for {n} {'owned ' if owned else ''}vehicles "
                    f"(“{quote}”); this profile states {int(have)}."
                )
        for m in TONNAGE_RE.finditer(part):
            n = float((m.group("n") or m.group("n2")).replace(",", ""))
            have = _num(cap.get("tonnage"))
            quote = _quote_around(part, m)
            if have is None:
                out.check = out.check or quote
            elif have < n:
                out.ineligible = out.ineligible or (
                    f"It asks for {n:g} tonnes of capacity (“{quote}”); "
                    f"this profile states {have:g}."
                )
    return out


# --- 7.1 flags -----------------------------------------------------------------------

OWNED_FLEET_RE = re.compile(
    r"\blog ?books?\b|\bcartes? jaunes?\b"
    r"|\b(?:vehicle |truck )?registration (?:cards?|certificates?|documents?)\b"
    r"[^.;\n]{0,60}\b(?:in the name of|owned by|belonging to|registered to)\b"
    r"|\bproof of (?:vehicle |fleet |truck )?ownership\b"
    r"|\b(?:vehicles?|trucks?|fleet) (?:must be |should be |are )?(?:owned by|"
    r"registered in the name of|belonging to) the (?:bidder|applicant|company|firm|"
    r"supplier|tenderer)\b"
    r"|\bownership of (?:the )?(?:vehicles?|trucks?|fleet)\b",
    re.IGNORECASE,
)
TRANSPORT_LICENCE_RE = re.compile(
    r"\b(?:goods |road |public )?transport(?:ation)? (?:operator(?:'s|s)? )?"
    r"(?:licen[cs]e|authori[sz]ation|permit)\b"
    r"|\boperator(?:'s|s)? licen[cs]e\b"
    r"|\brura (?:transport )?licen[cs]e\b"
    r"|\blicen[cs]e (?:issued by rura )?to (?:operate|carry out|provide) "
    r"(?:goods |road |freight )?transport",
    re.IGNORECASE,
)
UMUCYO_RE = re.compile(r"\bumucyo\b", re.IGNORECASE)


def _holds(profile: Profile, pattern: str) -> bool:
    held = _norm_list((profile.data or {}).get("registrations_held"))
    return any(re.search(pattern, h) for h in held)


def _owns_fleet(profile: Profile) -> bool:
    cap = (profile.data or {}).get("capacity")
    owned = _num(cap.get("owned_trucks")) if isinstance(cap, dict) else None
    return owned is not None and owned > 0


def umucyo_published(opp: Opportunity, sources: list[CarryingSource]) -> bool:
    for s in sources:
        for u in (s.home_url, s.url):
            host = (urlsplit(u).hostname or "").lower()
            if host == "umucyo.gov.rw" or host.endswith(".umucyo.gov.rw"):
                return True
    return False


def rule_flags(
    opp: Opportunity,
    profile: Profile,
    sources: list[CarryingSource],
    parts: list[str],
    capacity: CapacityCheck,
) -> list[Flag]:
    if profile.type != "business" or opp.stream not in ("tender", "funding"):
        return []
    who = _who(opp)
    flags: list[Flag] = []
    # An ownership threshold the stated owned fleet does not meet flags even when
    # the profile owns some trucks (check_capacity keeps it via the network).
    if capacity.owned or not _owns_fleet(profile):
        quote = capacity.owned or _find(OWNED_FLEET_RE, parts)
        if quote:
            flags.append(
                Flag(
                    "owned_fleet",
                    RULE_FLAGS["owned_fleet"],
                    quote,
                    f"{who} asks for “{quote}”, so this one may require "
                    "an owned fleet; check whether subcontracting or a joint bid "
                    "is allowed.",
                )
            )
    if not _holds(profile, r"transport|operator licen|rura"):
        quote = _find(TRANSPORT_LICENCE_RE, parts)
        if quote:
            flags.append(
                Flag(
                    "transport_licence",
                    RULE_FLAGS["transport_licence"],
                    quote,
                    f"{who} asks for “{quote}”, which this profile does not list.",
                )
            )
    if opp.stream == "tender" and not _holds(profile, r"umucyo"):
        quote = _find(UMUCYO_RE, parts)
        if quote or umucyo_published(opp, sources):
            flags.append(
                Flag(
                    "umucyo_registration",
                    RULE_FLAGS["umucyo_registration"],
                    quote,
                    "Bids go through Umucyo, which needs a supplier account this "
                    "profile does not list yet.",
                )
            )
    if capacity.check:
        flags.append(
            Flag(
                "check_capacity",
                RULE_FLAGS["check_capacity"],
                capacity.check,
                f"{who} asks for “{capacity.check}”; this profile does "
                "not state that capacity.",
            )
        )
    if (
        opp.stream == "tender"
        and _num((profile.data or {}).get("min_contract_rwf")) is not None
        and opp.value_amount is None
    ):
        flags.append(
            Flag(
                "value_unknown",
                RULE_FLAGS["value_unknown"],
                None,
                "The notice states no value, so it was kept although this profile "
                "has a minimum contract size.",
            )
        )
    return flags


# --- hard filters --------------------------------------------------------------------


def _fmt_rwf(v: float) -> str:
    return f"FRW {v:,.0f}"


# How a stream reads in "This profile does not follow ...".
STREAM_PLURALS = {
    "tender": "tenders",
    "funding": "funding calls",
    "investment": "investments",
    "event": "events",
}


def check_rules(
    opp: Opportunity,
    profile: Profile,
    sources: list[CarryingSource],
    documents: list[str],
    now: datetime,
) -> RuleResult:
    data = profile.data or {}
    # deadline passed
    ended = opp.event_end or opp.event_start
    if (
        opp.status == "expired"
        or (opp.deadline_at is not None and opp.deadline_at < now)
        or (opp.deadline_at is None and ended is not None and ended < now)
    ):
        return RuleResult("deadline_passed", "The deadline has passed.")
    if outside_rwanda(opp.location):
        return RuleResult(
            "outside_rwanda", f"It is located outside Rwanda ({opp.location})."
        )
    streams = data.get("streams")
    if isinstance(streams, list) and streams and opp.stream not in streams:
        return RuleResult(
            "stream_not_selected",
            f"This profile does not follow {STREAM_PLURALS.get(opp.stream, opp.stream)}.",
        )
    if sources and all(s.muted for s in sources):
        return RuleResult(
            "muted_source_only", "Every source carrying it is muted by you."
        )
    parts = eligibility_parts(opp, documents)
    if not _is_ngo(profile):
        quote = _find(NGO_ONLY, parts)
        if quote:
            return RuleResult(
                "ineligible", f"Only non-profit organisations may apply (“{quote}”)."
            )
    capacity = check_capacity(profile, parts)
    if capacity.ineligible:
        return RuleResult("ineligible", capacity.ineligible)
    min_rwf = _num(data.get("min_contract_rwf"))
    if (
        opp.stream == "tender"
        and min_rwf is not None
        and opp.value_amount is not None
        and opp.value_currency == "RWF"
        and float(opp.value_amount) < min_rwf
    ):
        return RuleResult(
            "below_min_value",
            f"Its stated value, {_fmt_rwf(float(opp.value_amount))}, is under this "
            f"profile's minimum of {_fmt_rwf(min_rwf)}.",
        )
    return RuleResult(flags=rule_flags(opp, profile, sources, parts, capacity))


# --- components (0..1; multiplied by the weights) -----------------------------------


def time_score(opp: Opportunity, now: datetime, settings: ScoringSettings) -> float:
    rule = settings.time_rules.get(opp.stream)
    when = opp.deadline_at
    if opp.stream == "event":
        when = opp.event_start or opp.deadline_at
    if when is None or rule is None:
        return settings.time_unknown
    days = (when - now).total_seconds() / 86400
    if days < rule.min_days:
        return rule.too_late
    if days >= rule.ideal_days:
        return 1.0
    span = rule.ideal_days - rule.min_days
    return rule.floor + (1.0 - rule.floor) * (days - rule.min_days) / span


def value_score(opp: Opportunity, profile: Profile) -> float:
    if opp.stream not in ("tender", "funding"):
        return 0.5
    min_rwf = _num((profile.data or {}).get("min_contract_rwf"))
    if opp.value_amount is None:
        return 0.4 if min_rwf is not None else 0.5
    if opp.stream == "tender" and min_rwf and opp.value_currency == "RWF":
        ratio = float(opp.value_amount) / min_rwf
        return min(1.0, 0.6 + 0.4 * (ratio - 1) / 3) if ratio >= 1 else 0.0
    return 0.7


def source_score(
    opp: Opportunity, sources: list[CarryingSource], settings: ScoringSettings
) -> float:
    if (opp.evidence or {}).get("_trust") == "conflict":
        ver = settings.conflict_score
    else:
        ver = settings.verification_scores.get(opp.verification, 0.5)
    if sources:
        kind = max(settings.kind_scores.get(s.kind, 0.5) for s in sources)
    else:
        kind = settings.private_item_kind_score
    share = settings.verification_share
    return share * ver + (1 - share) * kind
