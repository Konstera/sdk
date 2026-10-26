"""Konstera Standard Context Pack v1 — typed constants (Python).

Mirror of ``Konstera.Sdk.Contexts`` (NuGet) and ``konstera-sdk-contexts`` (npm).

Reference canonical names so a typo fails at import, not at install::

    from konstera_sdk_contexts import ContextTerms, ContextSkills, ContextEntities

    manifest["contextRequirements"] = {
        "glossary": {
            "required": [ContextTerms.REFUND_WINDOW_DAYS, ContextTerms.VIP_TIER_EXCEPTION],
            "recommended": [ContextTerms.LIMITED_EDITION_RESTOCKING_FEE],
        },
        "skills": {
            "required": [ContextSkills.EVALUATE_REFUND_ELIGIBILITY],
        },
        "ontologyEntities": {
            "required": [ContextEntities.CUSTOMER, ContextEntities.ORDER, ContextEntities.REFUND],
        },
    }

The raw pack JSON (with descriptions, domains, canonical units) ships inside
the wheel at ``konstera_sdk_contexts/schemas/standard-context-pack-v1.json``.
Load it with :func:`load_pack` when you need the metadata, not just names.
"""
from __future__ import annotations

import importlib.resources as _res
import json as _json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version
from typing import Any

from ._generated import ContextEntities, ContextSkills, ContextTerms

# Read from the installed distribution so it always matches pyproject.toml.
try:
    __version__ = _dist_version("konstera-sdk-contexts")
except PackageNotFoundError:  # pragma: no cover - source tree not installed
    __version__ = "0.0.0+unknown"
PACK_VERSION = "v1"

__all__ = [
    "ContextEntities",
    "ContextSkills",
    "ContextTerms",
    "PACK_VERSION",
    "__version__",
    "load_pack",
]


def load_pack() -> dict[str, Any]:
    """Return the raw Standard Context Pack v1 JSON as a dict.

    Use this when you need the descriptions, domains, or canonical_units —
    e.g. to render a settings UI listing every available term. For runtime
    name references, prefer the typed constants in :class:`ContextTerms`,
    :class:`ContextSkills`, :class:`ContextEntities` so the type checker
    catches typos.
    """
    text = _res.files(__package__).joinpath("schemas/standard-context-pack-v1.json").read_text(encoding="utf-8")
    return _json.loads(text)
