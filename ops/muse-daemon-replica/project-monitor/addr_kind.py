#!/usr/bin/env python3
"""Shared EVM address kind: contract (CA) vs EOA/wallet via eth_getCode.

Used by fast_site_poll (classify before NEW_JS_CA), trace_wallet_ca, build_ca_finds.
Never invents addresses — only classifies what callers already scraped.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

BASE = Path("/workspace/project-monitor")
FACTORIES = BASE / "factories.json"

# Prefer chains radar actually watches; hint always tried first.
CHAIN_ORDER_DEFAULT = (
    "ethereum", "bsc", "base", "robinhood", "hyperevm", "ink",
)

# EIP-1167 minimal proxy is always 45 bytes starting like this.
_MIN_PROXY_PREFIX = "0x363d3d373d3d3d363d73"
_MIN_PROXY_SUFFIX = "5af43d82803e903d91602b57fd5bf3"

_CHAIN_ALIAS = {
    "eth": "ethereum", "ethereum": "ethereum", "mainnet": "ethereum",
    "bsc": "bsc", "bnb": "bsc", "binance": "bsc", "bnb chain": "bsc",
    "base": "base",
    "robinhood": "robinhood", "rh": "robinhood",
    "hyperevm": "hyperevm", "hyperliquid": "hyperevm", "hype": "hyperevm",
    "ink": "ink",
    "evm": "evm",
}

_SNIPPET_CHAIN_RE = re.compile(
    r"(?:\b(?:on|在|chain[:\s]*)\s*)?(BSC|BNB\s*Chain|BNB|Ethereum|ETH|Base|Robinhood|HyperEVM|Ink)\b"
    r"|/(bnb|bsc|eth|base)/",
    re.I,
)


def load_factories() -> dict:
    try:
        return json.loads(FACTORIES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def rpc_call(rpc_url: str, method: str, params: list, timeout: int = 12) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    cmd = [
        "curl", "-sS", "--max-time", str(timeout),
        "-H", "Content-Type: application/json",
        "-d", payload, rpc_url,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout + 2)
        return json.loads(out.decode("utf-8", errors="replace") or "{}")
    except Exception as e:
        return {"error": str(e)[:160]}


def pick_rpcs(factories: dict | None = None) -> dict[str, str]:
    factories = factories or load_factories()
    out: dict[str, str] = {}
    for cid, cfg in (factories.get("chains") or {}).items():
        for u in cfg.get("rpc") or []:
            r = rpc_call(u, "eth_blockNumber", [], timeout=10)
            if r.get("result"):
                out[cid] = u
                break
    return out


def normalize_chain(hint: str | None) -> str | None:
    if not hint:
        return None
    h = hint.strip().lower()
    return _CHAIN_ALIAS.get(h) or (h if h in CHAIN_ORDER_DEFAULT else None)


def chain_hint_from_text(*parts: str | None) -> str | None:
    """Pull BSC/ETH/Base… from bio/snippet/source text."""
    blob = " ".join(p for p in parts if p) or ""
    if not blob:
        return None
    m = _SNIPPET_CHAIN_RE.search(blob)
    if not m:
        # utter.cash/bnb/… style already covered by second alt; also bare "在 BSC"
        if re.search(r"\bBSC\b", blob, re.I):
            return "bsc"
        return None
    g = (m.group(1) or m.group(2) or "").strip().lower()
    if g in ("bnb", "bnb chain", "bsc"):
        return "bsc"
    if g in ("ethereum", "eth"):
        return "ethereum"
    if g == "base":
        return "base"
    if g == "robinhood":
        return "robinhood"
    if g == "hyperevm":
        return "hyperevm"
    if g == "ink":
        return "ink"
    return normalize_chain(g)


def is_eip1167_proxy(code_hex: str, nbytes: int) -> bool:
    if nbytes != 45:
        return False
    c = (code_hex or "").lower()
    return c.startswith(_MIN_PROXY_PREFIX) and c.endswith(_MIN_PROXY_SUFFIX)


def code_and_nonce(rpc: str, address: str) -> dict:
    code_r = rpc_call(rpc, "eth_getCode", [address, "latest"])
    code = code_r.get("result") or ""
    err = None
    prefix = ""
    if code_r.get("error"):
        err = str(code_r["error"])[:160]
        nbytes = -1
    elif isinstance(code, str) and code.startswith("0x"):
        nbytes = max(0, (len(code) - 2) // 2)
        prefix = code[:10].lower()
    else:
        nbytes = -1
        err = "bad code result"
    nonce_r = rpc_call(rpc, "eth_getTransactionCount", [address, "latest"])
    nonce = None
    if nonce_r.get("result"):
        try:
            nonce = int(nonce_r["result"], 16)
        except Exception:
            nonce = None
    elif nonce_r.get("error") and not err:
        err = str(nonce_r["error"])[:160]
    # EIP-7702 delegation designator only — NOT EIP-1167 (45B proxy = real CA)
    eip7702 = nbytes == 23 and prefix.startswith("0xef0100")
    min_proxy = is_eip1167_proxy(code if isinstance(code, str) else "", nbytes)
    eoa_like = bool(eip7702)  # short non-proxy bytecode treated as contract
    return {
        "bytes": nbytes,
        "nonce": nonce,
        "error": err,
        "ok": nbytes >= 0,
        "eip7702": eip7702,
        "minimal_proxy": min_proxy,
        "eoa_like_code": eoa_like,
        "code_prefix": prefix,
        "code_hex": code if isinstance(code, str) and len(code) <= 200 else (code[:66] + "…" if isinstance(code, str) else ""),
    }


def chains_to_try(chain_hint: str | None, factories: dict | None = None) -> list[str]:
    factories = factories or load_factories()
    have = {cid for cid, cfg in (factories.get("chains") or {}).items() if cfg.get("rpc")}
    hint = normalize_chain(chain_hint)
    if hint and hint in have and hint != "evm":
        ordered = [hint] + [c for c in CHAIN_ORDER_DEFAULT if c != hint]
    else:
        ordered = list(CHAIN_ORDER_DEFAULT)
    # also any other factory chains with rpc not already listed
    extra = [c for c in have if c not in ordered and c not in ("solana", "ordinals", "kaspa", "elysium", "giwa")]
    return [c for c in ordered + extra if c in have]


def classify_evm(
    address: str,
    *,
    chain_hint: str | None = None,
    snippet: str | None = None,
    source: str | None = None,
    rpcs: dict[str, str] | None = None,
    factories: dict | None = None,
    stop_on_contract: bool = True,
) -> dict:
    """Return {kind: contract|wallet|unknown, chain, code_bytes, nonce, label_zh, tried, ...}."""
    addr = (address or "").strip()
    if not (addr.lower().startswith("0x") and len(addr) == 42):
        return {
            "kind": "unknown",
            "chain": chain_hint or "unknown",
            "code_bytes": None,
            "nonce": None,
            "label_zh": None,
            "addr_kind": "unknown",
            "tried": [],
            "error": "not_evm",
        }
    factories = factories or load_factories()
    rpcs = rpcs if rpcs is not None else pick_rpcs(factories)
    text_hint = chain_hint_from_text(snippet, source, chain_hint)
    hint = normalize_chain(chain_hint) or text_hint
    tried = []
    best_contract = None
    best_wallet = None
    for chain in chains_to_try(hint, factories):
        rpc = rpcs.get(chain)
        if not rpc:
            tried.append({"chain": chain, "error": "no rpc"})
            continue
        info = code_and_nonce(rpc, addr)
        row = {"chain": chain, **{k: info[k] for k in info if k != "code_hex"}, "rpc": rpc}
        if info.get("minimal_proxy"):
            row["minimal_proxy"] = True
        tried.append(row)
        if info["bytes"] and info["bytes"] > 0 and not info.get("eoa_like_code"):
            best_contract = row
            if stop_on_contract:
                break
        if info["bytes"] == 0 or info.get("eoa_like_code"):
            if best_wallet is None:
                best_wallet = row
            elif (info.get("nonce") or 0) > (best_wallet.get("nonce") or 0):
                best_wallet = row
        time.sleep(0.03)
    if best_contract:
        note = None
        if best_contract.get("minimal_proxy"):
            note = "EIP-1167 minimal proxy (contract/CA)"
        return {
            "kind": "contract",
            "addr_kind": "contract",
            "chain": best_contract["chain"],
            "code_bytes": best_contract["bytes"],
            "nonce": best_contract.get("nonce"),
            "label_zh": "合约CA",
            "note": note,
            "minimal_proxy": bool(best_contract.get("minimal_proxy")),
            "tried": tried,
        }
    if best_wallet:
        return {
            "kind": "wallet",
            "addr_kind": "wallet",
            "chain": best_wallet["chain"] if (best_wallet.get("nonce") or 0) > 0 or hint is None
            else (hint or best_wallet["chain"]),
            "code_bytes": best_wallet.get("bytes") or 0,
            "nonce": best_wallet.get("nonce"),
            "label_zh": "扫出钱包",
            "note": "classified as EOA/wallet via eth_getCode",
            "eip7702": bool(best_wallet.get("eip7702")),
            "tried": tried,
        }
    # Prefer text/bio hint for display even when unknown
    return {
        "kind": "unknown",
        "addr_kind": "unknown",
        "chain": hint or (chain_hint or "evm"),
        "code_bytes": None,
        "nonce": None,
        "label_zh": "未确认地址",
        "note": "no bytecode on probed EVM chains (may be other L1/L2 or placeholder)",
        "tried": tried,
    }


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 1 else "0xaacbc156435dbab7815a61bccba1c827e52a7777"
    hint = sys.argv[2] if len(sys.argv) > 2 else "bsc"
    snip = sys.argv[3] if len(sys.argv) > 3 else "在 BSC CA:"
    print(json.dumps(classify_evm(a, chain_hint=hint, snippet=snip), ensure_ascii=False, indent=2))
