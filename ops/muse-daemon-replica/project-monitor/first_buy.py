#!/usr/bin/env python3
"""First-buy / first-EXTERNAL-buy time of a token (launch_config.json).

「开盘」listing_time = first EXTERNAL buy: the first ERC20 Transfer of the token OUT of a
liquidity holder (DEX pair / Uniswap v4 PoolManager / four.meme TokenManager2 / Virtuals
bonding) to a third party in a transaction OTHER than the token-creation tx. Creation-tx
dev buys are recorded as first_buy_time but do NOT count as 开盘.
Not pool add, not launchpad page listing.

Best effort, bounded, read-only public RPC:
  start block: explorer getcontractcreation (Blockscout chains) → else DexScreener
               pairCreatedAt → block by timestamp; else not derivable (null).
  scan: eth_getLogs(Transfer, topic1 ∈ holders) forward in max_log_range chunks.
Results cached in first_buy_cache.json (found: forever; not found: 30 min).
Solana (P1): DexScreener pairCreatedAt as first_external_buy estimate (no API key); optional Helius enhanced txs when .helius_api_key present (key never written to cache/output).
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
CACHE = BASE / "first_buy_cache.json"
SH = ZoneInfo("Asia/Shanghai")
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
HOLDER_FACTORY_IDS = {"univ4_pm_base", "univ4_pm_eth", "univ4_pm_rh", "fourmeme_tm2_bsc",
                      "virtuals_bonding_base"}
DS_CHAIN = {"ethereum": "ethereum", "bsc": "bsc", "base": "base", "robinhood": "robinhood", "ink": "ink",
            "hyperevm": "hyperevm"}
MAX_CHUNKS = 150
NEG_TTL = 1800
LOOKBACK_S = 3 * 86400
# per-chain log range overrides verified 2026-10-24 (robinhood RPC allows 10M blocks/query)
LOG_RANGE = {"robinhood": 5_000_000}        # single topic value per position
SCAN_RANGE = {"robinhood": 100_000}         # OR-list topics
ZERO_T = "0x" + "0" * 64
# extra public RPCs that serve recent eth_getLogs without a key (2026-10-24 probe)
LOGS_RPC_EXTRA = {"ethereum": ["https://rpc.flashbots.net", "https://eth.drpc.org"]}


def _get_logs(rpcs: list[str], flt: dict) -> dict:
    last = {}
    for attempt in range(3):
        for u in rpcs:
            r = _rpc(u, "eth_getLogs", [flt], 25)
            if "result" in r:
                return r
            last = r
        time.sleep(1.5 * (attempt + 1))
    return last


def _curl(args: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.check_output(["curl", "-sS", "--max-time", str(timeout), *args],
                                       stderr=subprocess.DEVNULL, timeout=timeout + 3).decode("utf-8", "replace")
    except Exception:
        return ""


def _rpc(url: str, method: str, params: list, timeout: int = 15) -> dict:
    out = _curl(["-H", "Content-Type: application/json", "-d",
                 json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}), url], timeout)
    try:
        return json.loads(out or "{}")
    except Exception:
        return {}


def _factories() -> dict:
    try:
        return json.loads((BASE / "factories.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _rpc_for(chain: str, fx: dict) -> str | None:
    for u in ((fx.get("chains") or {}).get(chain) or {}).get("rpc") or []:
        if _rpc(u, "eth_blockNumber", [], 8).get("result"):
            return u
    return None


def _block_ts(rpc: str, n: int) -> int | None:
    r = _rpc(rpc, "eth_getBlockByNumber", [hex(n), False]).get("result") or {}
    try:
        return int(r["timestamp"], 16)
    except Exception:
        return None


def _block_at(rpc: str, ts: int) -> int | None:
    """First block with timestamp >= ts. Bounded to recent history (pruned nodes)."""
    try:
        head = int(_rpc(rpc, "eth_blockNumber", []).get("result"), 16)
    except Exception:
        return None
    head_ts = _block_ts(rpc, head)
    back = min(head, 10000)
    ref_ts = _block_ts(rpc, head - back)
    if head_ts is None or ref_ts is None or head_ts <= ref_ts:
        return None
    bt = (head_ts - ref_ts) / back
    lo = max(0, int(head - (head_ts - ts) / bt * 1.5) - 1000)
    hi = head
    if (_block_ts(rpc, lo) or 0) > ts:
        lo = max(0, int(head - (head_ts - ts) / bt * 3))
    for _ in range(64):
        if lo >= hi:
            break
        mid = (lo + hi) // 2
        t = _block_ts(rpc, mid)
        if t is None:
            return None
        if t < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _dexscreener(addr: str) -> list[dict]:
    try:
        return json.loads(_curl([f"https://api.dexscreener.com/latest/dex/tokens/{addr}"]) or "{}").get("pairs") or []
    except Exception:
        return []


def _creation_block(chain: str, addr: str, fx: dict) -> int | None:
    api = ((fx.get("chains") or {}).get(chain) or {}).get("explorer_api")
    if not api:
        return None
    try:
        r = json.loads(_curl([f"{api}?module=contract&action=getcontractcreation&contractaddresses={addr}"]) or "{}")
        res = (r.get("result") or [None])[0] or {}
        return int(res.get("blockNumber")) if res.get("blockNumber") else None
    except Exception:
        return None


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: Path, c: dict) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def derive_first_buy(address: str, chain: str | None, *, cache_path: Path = CACHE,
                     use_network: bool = True, hint_time: str | None = None) -> dict:
    """{'first_buy_time': iso|None (any buy, may be creation-tx),
        'first_external_buy_time': iso|None (开盘; excludes creation-tx dev buy),
        'first_buy_tx', 'first_buy_block', 'holder', 'method', 'reason',
        'first_buy_in_creation_tx': bool}"""
    a = (address or "").strip()
    key = f"{chain}:{a.lower() if a.lower().startswith('0x') else a}"
    cache = _load_cache(cache_path)
    hit = cache.get(key)
    if hit and (hit.get("first_buy_time") or time.time() - hit.get("_ts", 0) < NEG_TTL):
        # normalize older cache rows written before first_external_buy_time was always set
        if hit.get("first_buy_time") and not hit.get("first_buy_in_creation_tx") and not hit.get("first_external_buy_time"):
            hit = dict(hit)
            hit["first_external_buy_time"] = hit["first_buy_time"]
            hit["first_external_buy_tx"] = hit.get("first_buy_tx")
        return hit
    if not use_network:
        return {"first_buy_time": None, "reason": "not checked (offline)"}
    res = _derive(a, chain, hint_time)
    res["_ts"] = time.time()
    cache = _load_cache(cache_path)
    cache[key] = res
    _save_cache(cache_path, cache)
    return res


def _mint_block(rpc: str, a: str, head: int, step: int) -> int | None:
    """Earliest Transfer-from-0x0 block, scanning backwards (only for wide-range RPCs)."""
    if step < 1_000_000:
        return None
    earliest = None
    hi = head
    for _ in range(40):
        lo = max(0, hi - step + 1)
        r = _rpc(rpc, "eth_getLogs", [{"address": a, "fromBlock": hex(lo), "toBlock": hex(hi),
                                       "topics": [TRANSFER, ZERO_T]}], 30)
        if "result" not in r:
            return earliest
        if r["result"]:
            earliest = min(int(x["blockNumber"], 16) for x in r["result"])
        elif earliest is not None:
            return earliest
        if lo == 0:
            break
        hi = lo - 1
    return earliest


def _redact(s: str, key: str | None) -> str:
    if key and key in s:
        return s.replace(key, "***")
    return s


def _helius_key() -> str | None:
    """Read Helius key from env or local file; never log or return into cached output fields."""
    import os
    k = (os.environ.get("HELIUS_API_KEY") or "").strip()
    if k:
        return k
    try:
        return (BASE / ".helius_api_key").read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def _derive_solana(a: str, hint_time: str | None = None) -> dict:
    """Best-effort Solana first external buy without leaking keys into the result.

    1) DexScreener pairCreatedAt (public) → treat as first_external_buy_time estimate
       (bonding/pool creation ≈ 开盘 for pump.fun-style mints).
    2) If Helius key available: scan recent signatures for the mint via public RPC +
       Helius parsed-tx enhancement to find first non-creator receive (best effort).
    """
    pairs = [p for p in _dexscreener(a) if (p.get("chainId") or "").lower() in ("solana", "sol")]
    pc = [p.get("pairCreatedAt") for p in pairs if p.get("pairCreatedAt")]
    if pc:
        ts = int(min(pc) / 1000)
        iso = datetime.fromtimestamp(ts, SH).isoformat(timespec="seconds")
        out = {
            "first_buy_time": iso,
            "first_external_buy_time": iso,
            "first_buy_in_creation_tx": False,
            "method": "dexscreener_pair_created_solana",
            "holder_known": True,
            "reason": None,
            "note_zh": "Solana：以 DexScreener 池创建时间近似第一笔外部买入（无密钥路径）",
        }
        # try to refine with Helius if key present (optional)
        refined = _solana_helius_first_buy(a)
        if refined.get("first_external_buy_time"):
            return refined
        return out
    refined = _solana_helius_first_buy(a)
    if refined.get("first_buy_time") or refined.get("reason"):
        return refined
    return {"first_buy_time": None, "reason": "solana: no DexScreener pair and no Helius refinement"}


def _solana_helius_first_buy(mint: str) -> dict:
    """Optional refinement via Helius. Key used only for the HTTP call; never stored in result."""
    key = _helius_key()
    if not key:
        return {"first_buy_time": None, "reason": "solana: no Helius key for refinement"}
    # Public RPC for signatures (no key)
    rpc = "https://api.mainnet-beta.solana.com"
    try:
        raw = _curl(["-H", "Content-Type: application/json", "-d",
                     json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                                 "params": [mint, {"limit": 100}]}), rpc], 20)
        sigs = (json.loads(raw or "{}").get("result") or [])
    except Exception as e:
        return {"first_buy_time": None, "reason": _redact(f"solana getSignatures failed: {str(e)[:60]}", None)}
    if not sigs:
        return {"first_buy_time": None, "reason": "solana: no signatures for mint"}
    # oldest first
    sigs = list(reversed(sigs))
    # Helius parsed transaction (key in URL only for request)
    url = f"https://api.helius.xyz/v0/transactions/?api-key={key}"
    creator = None
    for batch_i in range(0, min(len(sigs), 40), 10):
        chunk = [s.get("signature") for s in sigs[batch_i:batch_i + 10] if s.get("signature")]
        if not chunk:
            continue
        try:
            raw = _curl(["-H", "Content-Type: application/json", "-d", json.dumps({"transactions": chunk}), url], 25)
            txs = json.loads(raw or "[]")
            if not isinstance(txs, list):
                continue
        except Exception:
            continue
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            # tokenTransfers involving mint
            transfers = tx.get("tokenTransfers") or []
            ts = tx.get("timestamp")
            iso = datetime.fromtimestamp(ts, SH).isoformat(timespec="seconds") if ts else None
            for tr in transfers:
                if (tr.get("mint") or "") != mint:
                    continue
                frm = tr.get("fromUserAccount") or ""
                to = tr.get("toUserAccount") or ""
                if not to or to == frm:
                    continue
                # first mint-out from null/system ≈ create; skip as creation
                if not frm or frm in ("", "11111111111111111111111111111111"):
                    creator = creator or to
                    continue
                if creator and to == creator:
                    continue  # back to creator = not external buy
                return {
                    "first_buy_time": iso,
                    "first_external_buy_time": iso,
                    "first_buy_tx": tx.get("signature"),
                    "first_external_buy_tx": tx.get("signature"),
                    "first_buy_in_creation_tx": False,
                    "holder": frm,
                    "method": "helius_token_transfer_solana",
                    "holder_known": True,
                    "reason": None,
                    "note_zh": "Solana：Helius 解析到的首笔非创建者转入",
                }
    return {"first_buy_time": None, "reason": "solana: no external buy in recent Helius window"}


def _derive(a: str, chain: str | None, hint_time: str | None = None) -> dict:
    if not a.lower().startswith("0x"):
        return _derive_solana(a, hint_time)
    fx = _factories()
    if not chain or chain not in (fx.get("chains") or {}):
        return {"first_buy_time": None, "reason": f"unknown chain {chain}"}
    rpc = _rpc_for(chain, fx)
    if not rpc:
        return {"first_buy_time": None, "reason": f"no rpc for {chain}"}
    holders = {f["address"].lower() for f in fx.get("factories") or []
               if f.get("chain") == chain and f.get("id") in HOLDER_FACTORY_IDS}
    pairs = [p for p in _dexscreener(a) if p.get("chainId") == DS_CHAIN.get(chain)]
    for p in pairs:
        pa = (p.get("pairAddress") or "").lower()
        if pa.startswith("0x") and len(pa) == 42:
            holders.add(pa)
    if not holders:
        return {"first_buy_time": None, "reason": "no pool/bonding holder known"}
    try:
        head = int(_rpc(rpc, "eth_blockNumber", []).get("result"), 16)
    except Exception:
        return {"first_buy_time": None, "reason": "rpc head failed"}
    step = LOG_RANGE.get(chain) or int(((fx.get("chains") or {}).get(chain) or {}).get("max_log_range") or 2000)
    need_mint = False
    start = _creation_block(chain, a, fx)
    method = "explorer_creation"
    if start is None:
        start = _mint_block(rpc, a, head, step)
        method = "mint_log"
    if start is None:
        pc = [p.get("pairCreatedAt") for p in pairs if p.get("pairCreatedAt")]
        if pc:
            start = _block_at(rpc, int(min(pc) / 1000) - 600)
            method = "dexscreener_pair_created"
    if start is None and hint_time:
        try:
            ts = int(datetime.fromisoformat(hint_time).timestamp()) - LOOKBACK_S
            start = _block_at(rpc, ts)
            method, need_mint = "window_scan(mint must be inside window)", True
        except Exception:
            start = None
    if start is None:
        return {"first_buy_time": None, "reason": "token creation / pool creation block not derivable"}
    step = SCAN_RANGE.get(chain) or int(((fx.get("chains") or {}).get(chain) or {}).get("max_log_range") or 2000)
    saw_mint = False
    mint_tx = None
    found = None
    code_cache: dict[str, bool] = {}

    def _is_contract(x: str) -> bool:
        if x not in code_cache:
            c = _rpc(rpc, "eth_getCode", [x, "latest"]).get("result") or "0x"
            # EIP-7702 delegated EOAs start with ef0100 — not a pool
            code_cache[x] = len(c) > 2 and not c.lower().startswith("0xef0100")
        return code_cache[x]

    b = start
    for _ in range(MAX_CHUNKS):
        if b > head:
            break
        e = min(b + step - 1, head)
        r = _get_logs([rpc] + LOGS_RPC_EXTRA.get(chain, []),
                      {"address": a, "fromBlock": hex(b), "toBlock": hex(e), "topics": [TRANSFER]})
        if "result" not in r:
            return {"first_buy_time": None, "reason": f"getLogs failed at {b}: {str(r.get('error'))[:80]}"}
        for lg in sorted(r["result"], key=lambda x: (int(x["blockNumber"], 16), int(x.get("logIndex", "0x0"), 16))):
            if len(lg.get("topics") or []) < 3:
                continue
            frm = "0x" + lg["topics"][1][-40:]
            to = "0x" + lg["topics"][2][-40:]
            if int(frm, 16) == 0:
                if not saw_mint:
                    mint_tx = lg.get("transactionHash")
                saw_mint = True
                continue
            if int(to, 16) == 0 or to == frm or to in holders:
                continue
            known = frm in holders
            if not known and (frm == a.lower() or not _is_contract(frm)):
                continue  # EOA → anything is a seed / LP add / airdrop, not a buy
            if need_mint and not saw_mint:
                return {"first_buy_time": None,
                        "reason": "token existed before scan window (no mint in window) — first buy not provable"}
            bn = int(lg["blockNumber"], 16)
            ts = _block_ts(rpc, bn)
            iso = datetime.fromtimestamp(ts, SH).isoformat(timespec="seconds") if ts else None
            if found is None:
                found = {"first_buy_time": iso,
                         "first_buy_tx": lg.get("transactionHash"), "first_buy_block": bn, "holder": frm,
                         "method": (f"transfer_out_of_known_pool ({method})" if known
                                    else f"transfer_out_of_contract_heuristic ({method})"),
                         "holder_known": known, "reason": None,
                         "first_buy_in_creation_tx": bool(mint_tx and lg.get("transactionHash") == mint_tx)}
                if not found["first_buy_in_creation_tx"]:
                    # already an external buy → listing_time == first_buy_time
                    found["first_external_buy_time"] = iso
                    found["first_external_buy_tx"] = lg.get("transactionHash")
                    return found
                continue
            if lg.get("transactionHash") != mint_tx:
                # first buy in a different tx than token creation (dev buy inside create tx excluded)
                found["first_external_buy_time"] = iso
                found["first_external_buy_tx"] = lg.get("transactionHash")
                return found
        b = e + 1
    if found is not None:
        return found
    return {"first_buy_time": None, "reason": f"no buy found in {MAX_CHUNKS} chunks from block {start}"}


if __name__ == "__main__":
    import sys
    print(json.dumps(derive_first_buy(sys.argv[1], sys.argv[2], use_network=True,
                                      hint_time=(sys.argv[3] if len(sys.argv) > 3 else None)),
                     ensure_ascii=False, indent=1))
