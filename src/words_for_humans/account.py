"""Entitlement, and the seam between the free engine and the paid service.

The engine in this package is complete for the rules a program can decide by
inspection, and it stays that way whether or not anyone signs in. What an
account adds is the material the engine cannot carry on its own:

Full controlled vocabulary
    Rules 1.1 through 1.11 are judged against the ASD-STE100 dictionary, which
    ASD owns and this package therefore does not ship. Without an account the
    engine falls back to a starter list of fewer than a hundred words.

Company glossary
    Rule 1.8 requires technical nouns approved in your own company, industry, or
    subject field. That list is per customer by definition and lives with the
    service.

Judgment rules
    Thirty of the 53 rules need a reader who understands the text. Those run as
    model calls, which cost money per call, so they are metered.

History and attestation
    A single run reports one commit. Conformance evidence needs the trend, and
    an auditor needs a signed report tied to a commit, neither of which a
    stateless command can produce.

Nothing here gates the local linter. A check that runs on someone else's machine
cannot be enforced from inside the binary, and pretending otherwise would add
friction for honest users and stop nobody. The boundary that holds is the one
above: the paid tier serves data and runs inference the CLI does not have.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

DEFAULT_ENDPOINT = "https://api.wordsforhumans.io"
_CREDENTIALS = Path.home() / ".config" / "words-for-humans" / "credentials.json"
_TIMEOUT_SECONDS = 10


class Feature(StrEnum):
    FULL_DICTIONARY = "full_dictionary"
    COMPANY_GLOSSARY = "company_glossary"
    JUDGMENT_RULES = "judgment_rules"
    ORG_POLICY = "org_policy"
    HISTORY = "history"
    ATTESTATION = "attestation"


class Plan(StrEnum):
    FREE = "free"
    TEAM = "team"
    ENTERPRISE = "enterprise"


_PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.FREE: frozenset(),
    Plan.TEAM: frozenset(
        {Feature.FULL_DICTIONARY, Feature.COMPANY_GLOSSARY, Feature.JUDGMENT_RULES}
    ),
    Plan.ENTERPRISE: frozenset(Feature),
}


@dataclass(frozen=True)
class Entitlement:
    plan: Plan = Plan.FREE
    account: str | None = None
    features: frozenset[Feature] = field(default_factory=frozenset)

    def allows(self, feature: Feature) -> bool:
        return feature in self.features

    @property
    def signed_in(self) -> bool:
        return self.account is not None


FREE = Entitlement(plan=Plan.FREE, features=_PLAN_FEATURES[Plan.FREE])


def token() -> str | None:
    """Read the API token from the environment or the credentials file."""
    from_env = os.environ.get("WORDS_FOR_HUMANS_TOKEN")
    if from_env:
        return from_env.strip()
    try:
        data = json.loads(_CREDENTIALS.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("token")
    return str(value).strip() if value else None


def endpoint() -> str:
    return os.environ.get("WORDS_FOR_HUMANS_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def resolve(*, offline: bool = False) -> Entitlement:
    """Determine what this machine is entitled to.

    Any failure resolves to the free tier. The linter must keep working when
    the network is down, when a token has expired, and inside an air-gapped
    build, because a validator that fails closed on a billing lookup is worse
    than one that quietly checks fewer rules.
    """
    api_token = token()
    if offline or not api_token:
        return FREE

    try:
        payload = _get("/v1/entitlement", api_token)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return _cached_entitlement() or FREE

    try:
        plan = Plan(payload.get("plan", "free"))
    except ValueError:
        plan = Plan.FREE

    entitlement = Entitlement(
        plan=plan,
        account=payload.get("account"),
        features=frozenset(_PLAN_FEATURES.get(plan, frozenset())),
    )
    _cache_entitlement(payload)
    return entitlement


def sync_dictionary(destination: Path, *, api_token: str | None = None) -> bool:
    """Download the full dictionary and company glossary into the local cache.

    Returns False when the account is not entitled to it, which leaves the
    starter list in place.
    """
    api_token = api_token or token()
    if not api_token:
        return False
    try:
        payload = _get("/v1/dictionary", api_token)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    if not payload.get("approved"):
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return True


def _get(path: str, api_token: str) -> dict:
    request = urllib.request.Request(  # noqa: S310  # the tool's own configured HTTPS endpoint
        f"{endpoint()}{path}",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "words-for-humans",
        },
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _cache_path() -> Path:
    return _CREDENTIALS.parent / "entitlement.json"


def _cache_entitlement(payload: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n")
    except OSError:
        pass


def _cached_entitlement() -> Entitlement | None:
    """Fall back to the last known entitlement when the service is unreachable.

    A build that runs offline, or during an outage, keeps the plan it had.
    """
    try:
        payload = json.loads(_cache_path().read_text())
        plan = Plan(payload.get("plan", "free"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return Entitlement(
        plan=plan,
        account=payload.get("account"),
        features=frozenset(_PLAN_FEATURES.get(plan, frozenset())),
    )
