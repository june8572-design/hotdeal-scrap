"""Naver affiliate/non-affiliate URL classification helpers.

Single source of truth for classification rules used by:
- had_backend API preflight checks
- hotdeal enrichment pipeline
- brandconnect issuance scripts
"""

from __future__ import annotations

import json
from typing import Any


def classify_naver_url(url: str | None) -> tuple[int | None, str | None]:
    """Classify a single URL.

    Returns:
      (1, "brandconnect") for brandconnect URLs containing /affiliate/ or /affiliates/
      (1, "naver_me") for naver.me links
      (0, <type>) for known non-affiliate domains
      (None, "unknown") for unknown URLs
      (None, None) for empty input
    """
    u = (url or "").strip().lower()
    if not u:
        return None, None

    # brandconnect domain rule: affiliate path required
    if "brandconnect.naver.com" in u:
        if "/affiliate/" in u or "/affiliates/" in u:
            return 1, "brandconnect"
        return 0, "brandconnect_non_affiliate"

    if "naver.me/" in u:
        return 1, "naver_me"

    # more specific mobile domains first
    if "m.brand.naver.com/" in u:
        return 0, "m_brand_store"
    if "m.smartstore.naver.com/" in u:
        return 0, "m_smartstore"

    if "smartstore.naver.com/" in u:
        return 0, "smartstore"
    if "brand.naver.com/" in u:
        return 0, "brand_store"
    if "shopping.naver.com/" in u:
        return 0, "shopping"
    if "shoppinglive.naver.com/" in u:
        return 0, "shoppinglive"

    if "pay.naver.com" in u or "campaign2.naver.com" in u or "ofw.adison.co" in u:
        return 0, "naver_pay"

    return None, "unknown"


def classify_out_links(out_links: list[str] | None) -> tuple[int | None, str | None]:
    """Classify a list of links with priority: affiliate > non-affiliate > unknown."""
    links = out_links or []
    best_aff = None
    best_type = None

    for link in links:
        aff, typ = classify_naver_url(link)
        if aff == 1:
            return 1, typ
        if aff == 0 and best_aff is None:
            best_aff = 0
            best_type = typ

    if best_aff is not None:
        return best_aff, best_type
    return None, best_type


def parse_out_links_json(raw: Any) -> list[str]:
    """Parse DB out_links_json field safely into a list of strings."""
    if raw is None:
        return []

    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, str) and x.strip()]

    if not isinstance(raw, str):
        return []

    try:
        parsed = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [x for x in parsed if isinstance(x, str) and x.strip()]
