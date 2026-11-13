#!/usr/bin/env python3
"""Project category normalization + expected CA roles (Pad Hunter spec 4.1 [A] / 4.2 [B]).

P0 only uses ``expected_roles`` (ca_gate type-aware check, spec 4.8 [D]). Collectors,
site_scan level and scan cadence (spec 4.2) are declared here for P2 but nothing reads
them yet — strategy routing is NOT active in P0.

Category source: push-radar/data/candidates.json ``category`` (mixed spellings such as
「模因币」「公平启动」「AI代理 / 发射台 / 基础设施」). Keys are lowercase handles without @.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CANDIDATES = Path("/workspace/push-radar/data/candidates.json")

CANONICAL = ["发射台", "Meme币", "GameFi", "NFT铸造", "DeFi协议", "AI代理", "基础设施", "其他"]

CATEGORY_ALIASES = {
    "模因币": "Meme币", "meme": "Meme币", "Meme": "Meme币", "meme币": "Meme币",
    "公平启动": "发射台", "launchpad": "发射台",
    "链游": "GameFi", "游戏": "GameFi", "gamefi": "GameFi",
    "NFT": "NFT铸造", "nft": "NFT铸造", "铸造": "NFT铸造",
    "AI": "AI代理", "ai": "AI代理", "Agent": "AI代理", "agent": "AI代理",
    "DeFi": "DeFi协议", "defi": "DeFi协议",
    "infra": "基础设施",
}

# expected_roles per canonical category (spec 4.2). Order = preference.
STRATEGIES: dict[str, dict] = {
    "Meme币": {"expected_roles": ["token"], "collectors": ["creator_wallet", "launchpad_factory", "x_official"],
              "site_scan": "light", "name_match": "assist_only"},
    "发射台": {"expected_roles": ["token"], "collectors": ["creator_wallet", "launchpad_factory", "x_official", "site"]},
    "NFT铸造": {"expected_roles": ["nft", "token"], "collectors": ["x_official", "site_config", "creator_wallet"],
               "promote_deployer_to_watch": True},
    "GameFi": {"expected_roles": ["token", "nft"],
               "collectors": ["creator_wallet", "site_config", "docs", "github", "testnet", "x_official"]},
    "AI代理": {"expected_roles": ["token"], "collectors": ["creator_wallet", "launchpad_factory", "x_official"],
             "launchpads": ["virtuals", "clanker"]},
    "DeFi协议": {"expected_roles": ["token"], "collectors": ["creator_wallet", "docs", "audit", "github", "x_official"]},
    "基础设施": {"expected_roles": ["token"], "collectors": ["creator_wallet", "docs", "audit", "github", "x_official"]},
    "其他": {"expected_roles": ["token"], "collectors": ["creator_wallet", "site", "x_official"]},
}

_SPLIT = re.compile(r"\s*(?:/|、|,|，|\||\+|&)\s*")


def _map_one(tok: str) -> str:
    t = (tok or "").strip()
    if not t:
        return "其他"
    if t in CANONICAL:
        return t
    if t in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[t]
    tl = t.lower()
    for c in CANONICAL:
        if c.lower() == tl:
            return c
    if tl in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[tl]
    return "其他"


def normalize_category(raw) -> list[str]:
    """'A / B / C' → one or more canonical categories (deduped, order kept). Unknown → ['其他']."""
    if raw is None:
        return ["其他"]
    parts = raw if isinstance(raw, (list, tuple)) else _SPLIT.split(str(raw))
    out: list[str] = []
    for p in parts:
        c = _map_one(str(p))
        if c not in out:
            out.append(c)
    return out or ["其他"]


def expected_roles(categories) -> set[str]:
    """Union of expected_roles over all categories (multi-type projects run every strategy)."""
    cats = normalize_category(categories) if isinstance(categories, str) or categories is None else list(categories)
    roles: set[str] = set()
    for c in cats or ["其他"]:
        roles.update(STRATEGIES.get(c, STRATEGIES["其他"])["expected_roles"])
    return roles


def primary_strategy(categories: list[str]) -> str:
    return (categories or ["其他"])[0]


def norm_handle(h) -> str:
    return str(h or "").strip().lstrip("@").lower()


def load_project_categories(path: Path = CANDIDATES) -> dict[str, list[str]]:
    """lowercase handle → canonical categories, from candidates.json."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = doc.get("candidates") if isinstance(doc, dict) else doc
    out: dict[str, list[str]] = {}
    for it in items or []:
        h = norm_handle(it.get("handle"))
        if h and it.get("category") is not None:
            out[h] = normalize_category(it.get("category"))
    return out
