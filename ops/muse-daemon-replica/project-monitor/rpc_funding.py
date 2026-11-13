#!/usr/bin/env python3
"""Indexer-free native funding discovery via archive JSON-RPC (E1 hist2).

Method (no explorer / no key):
  first inflow:
    1. N1 = first block where nonce(addr) > 0   (nonce is monotone → binary search)
    2. Before N1 the EOA cannot spend, so balance is non-decreasing on [0, N1].
       F = first block where balance(addr) > 0  (binary search on [0, N1])
    3. Fetch block F with full txs → tx with to==addr & value>0 (direct).
       Else debug_traceBlockByNumber(callTracer) → internal call to addr with value.
       Else funding_unknown_internal (no funder → never hard evidence).
  last gas funding within 7d before deploy:
    Segments where nonce is constant have no outgoing spend → balance monotone there.
    DFS from the right over [block(deploy-7d), block(deploy)-1]; for a constant-nonce
    segment with bal(r) > bal(l), bisect for the block where balance reached bal(r).
    Bounded by MAX_CALLS per query.

First inflow is immutable → cached forever in funding_rpc_cache.json (no secrets).
Keyed RPC URLs (PublicNode personal token) are loaded at runtime and only ever
reported through mask_url()/scrub().
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")
UA = "PadHunterFunding/1.0"

# Probed 2026-10-25 from the box: archive state (old eth_getBalance) works on these,
# keyless. trace=True → debug_traceBlockByNumber callTracer worked.
ARCHIVE_RPCS: dict[str, list[dict]] = {
    "base": [
        {"url": "https://mainnet.base.org", "trace": False},
        {"url": "https://base.drpc.org", "trace": True},
        {"url": "https://base-mainnet.public.blastapi.io", "trace": False},
        {"url": "https://base.gateway.tenderly.co", "trace": False},
    ],
    "bsc": [
        {"url": "https://bsc-mainnet.public.blastapi.io", "trace": False},
        {"url": "https://bsc.drpc.org", "trace": True},  # public rate limit often hit
    ],
    "robinhood": [
        {"url": "https://rpc-robinhood.blockmachine.io", "trace": True},
        {"url": "https://robinhood.rpc.pinax.network", "trace": True},
    ],
}
# PublicNode (Allnodes) personal-token archive endpoints. Token is a URL path segment →
# the URL itself is a secret: loaded at runtime from env or a mode-600 gitignored file,
# never logged / written (see mask_url). Verified 2026-10-25: archive eth_getBalance and
# debug_traceTransaction / debug_traceBlockByNumber(callTracer) incl. ~3M-block-old blocks.
PUBLICNODE_FILE = Path(__file__).resolve().parent / ".publicnode_rpc_urls"
PUBLICNODE_TOKEN_FILE = Path(__file__).resolve().parent / ".publicnode_token"
PUBLICNODE_ENV = {"bsc": "PADHUNTER_PUBLICNODE_BSC", "base": "PADHUNTER_PUBLICNODE_BASE",
                  "robinhood": "PADHUNTER_PUBLICNODE_ROBINHOOD"}
PUBLICNODE_TRACE = {"bsc": True, "base": True, "robinhood": True}
_SECRET_URLS: set[str] = set()
_SECRET_TOKENS: set[str] = set()


def load_publicnode_urls(path: Path | None = None, env: dict | None = None) -> dict[str, str]:
    """{chain: url}. Env PADHUNTER_PUBLICNODE_<CHAIN> overrides the file. Missing → {}."""
    env = os.environ if env is None else env
    path = PUBLICNODE_FILE if path is None else path
    file_vals: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            file_vals[k.strip().lower()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    out = {}
    for chain, ev in PUBLICNODE_ENV.items():
        u = (env.get(ev) or "").strip() or file_vals.get(chain, "")
        if u.startswith("https://"):
            out[chain] = u
    return out


def _register_secret(url: str) -> None:
    _SECRET_URLS.add(url)
    parts = url.split("/", 3)
    if len(parts) > 3 and parts[3]:
        for seg in parts[3].split("/"):
            if len(seg) >= 16:
                _SECRET_TOKENS.add(seg)


def mask_url(url: str) -> str:
    """https://host/<anything> → https://host/*** (host only). Safe for logs/JSON."""
    u = str(url or "")
    if "://" not in u:
        return scrub(u)
    scheme, rest = u.split("://", 1)
    host = rest.split("/", 1)[0].split("?", 1)[0]
    if "@" in host:
        host = host.split("@", 1)[1]
    tail = rest[len(rest.split("/", 1)[0]):]
    return f"{scheme}://{host}/***" if tail.strip("/") else f"{scheme}://{host}"


def scrub(text) -> str:
    """Remove any registered secret URL / token from free text (error messages)."""
    t = str(text if text is not None else "")
    for u in sorted(_SECRET_URLS, key=len, reverse=True):
        if u in t:
            t = t.replace(u, mask_url(u))
    for tok in _SECRET_TOKENS:
        if tok in t:
            t = t.replace(tok, "***")
    return t


def _install_publicnode(rpcs: dict, urls: dict[str, str] | None = None) -> list[str]:
    urls = load_publicnode_urls() if urls is None else urls
    try:
        tok = PUBLICNODE_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(tok) >= 16:
            _SECRET_TOKENS.add(tok)
    except Exception:
        pass
    added = []
    for chain, url in urls.items():
        if chain not in rpcs:
            continue
        _register_secret(url)
        lst = [r for r in rpcs[chain] if r.get("url") != url]
        rpcs[chain] = [{"url": url, "trace": PUBLICNODE_TRACE.get(chain, False), "keyed": True}] + lst
        added.append(chain)
    return added


PUBLICNODE_CHAINS = _install_publicnode(ARCHIVE_RPCS)

NON_ARCHIVE_NOTES = {
    "base": ["base-rpc.publicnode.com: keyless public = recent state only; personal token (Allnodes) "
             "→ archive+trace, used FIRST when .publicnode_rpc_urls / PADHUNTER_PUBLICNODE_BASE is set",
             "1rpc.io/base (pruned)"],
    "bsc": ["bsc-rpc.publicnode.com: keyless public = recent state only; personal token (Allnodes) "
            "→ archive+trace, used FIRST when .publicnode_rpc_urls / PADHUNTER_PUBLICNODE_BSC is set",
            "bsc-dataseed*.binance/defibit/ninicoin (pruned)",
            "1rpc.io/bnb (pruned)", "blockreq / blockvectra public (recent only)"],
    "robinhood": ["robinhood.drpc.org (state window only: 'Unknown state. First available …')",
                  "rpc.mainnet.chain.robinhood.com (no historical state)",
                  "robinhood-rpc.publicnode.com: keyless = no history; personal token → archive+trace, used FIRST when configured",
                  "rpc.ordofi.network / daybreak / blockreq / blockvectra (no history)"],
}
NATIVE = {"base": "ETH", "bsc": "BNB", "robinhood": "ETH"}

MAX_CALLS = 120          # per phase (first inflow / 7d gas), reset between phases
MIN_INTERVAL = 0.08      # seconds between calls per process
_last = [0.0]

# Hard time caps so live callers (onchain_lock runs build_ca_finds with timeout=60,
# fast_site_poll calls it in-process) are never stalled. Searches are resumable:
# historical balance/nonce/timestamp probes are immutable → memoized in the cache,
# so the next build continues where this one stopped.
PER_ADDRESS_S = float(os.environ.get("PADHUNTER_RPC_FUNDING_S", "8"))
PROCESS_BUDGET_S = float(os.environ.get("PADHUNTER_RPC_PROCESS_S", "15"))
PROCESS_WINDOW_S = float(os.environ.get("PADHUNTER_RPC_WINDOW_S", "120"))
_spent = [0.0]
_window = [time.time()]


def _budget_left() -> float:
    """Sliding window so a long-lived process (fast_site_poll) keeps getting budget."""
    now = time.time()
    if now - _window[0] > PROCESS_WINDOW_S:
        _window[0] = now
        _spent[0] = 0.0
    return PROCESS_BUDGET_S - _spent[0]
LAST_STATUS = {"status": None}  # complete | pending | none | error
MEMO_CAP = 600

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE if (_HERE / "factories.json").exists() else _HERE.parent
CACHE_PATH = _ROOT / "funding_rpc_cache.json"


class RpcBudget(Exception):
    pass


class RpcClient:
    """Failover JSON-RPC client for one chain. post() is injectable for tests."""

    def __init__(self, chain: str, rpcs: list[dict] | None = None, post=None,
                 max_calls: int = MAX_CALLS, deadline: float | None = None):
        self.chain = chain
        self.rpcs = list(rpcs if rpcs is not None else ARCHIVE_RPCS.get(chain, []))
        self._post = post or _curl_post
        self.calls = 0
        self.max_calls = max_calls
        self.bad: set[str] = set()  # raw urls (internal only) — report via bad_masked()
        self._bal: dict[int, int] = {}
        self._nonce: dict[int, int] = {}
        self._ts: dict[int, int] = {}
        self.deadline = deadline

    def bad_masked(self) -> list[str]:
        return sorted(mask_url(u) for u in self.bad)

    def rpcs_masked(self) -> list[str]:
        return [mask_url(r["url"]) for r in self.rpcs]

    def __repr__(self) -> str:
        return f"RpcClient({self.chain}, rpcs={self.rpcs_masked()}, bad={self.bad_masked()}, calls={self.calls})"

    def call(self, method: str, params: list, *, need_trace: bool = False):
        if self.calls >= self.max_calls:
            raise RpcBudget(method)
        if self.deadline is not None and time.time() > self.deadline:
            raise RpcBudget("deadline")
        last_err = None
        for attempt in range(2):
            res = self._try_all(method, params, need_trace)
            if res[0]:
                return res[1]
            last_err = res[1]
            if need_trace or attempt:
                break
            if self.deadline is not None and self.deadline - time.time() < 3:
                break
            time.sleep(1.5)  # transient (rate limit / timeout) → one backoff round
        raise RuntimeError(f"rpc_failed:{method}:{scrub(last_err or '')[:80]}")

    def _try_all(self, method, params, need_trace):
        last_err = None
        for r in self.rpcs:
            if r["url"] in self.bad or (need_trace and not r.get("trace")):
                continue
            wait = MIN_INTERVAL - (time.time() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
            self.calls += 1
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            if self.deadline is not None and self._post is _curl_post:
                left = self.deadline - time.time()
                if left <= 0:
                    raise RpcBudget("deadline")
                resp = _curl_post(r["url"], payload, timeout=max(2, min(15, int(left) + 1)))
            else:
                resp = self._post(r["url"], payload)
            if isinstance(resp, dict) and "result" in resp:
                return True, resp["result"]
            msg = scrub(str(((resp or {}).get("error") or {}).get("message") if isinstance(resp, dict) else resp))
            last_err = msg
            low = msg.lower()
            if any(s in low for s in ("archive", "historical state", "missing trie", "pruned",
                                      "not found", "not allowed", "not supported", "does not exist")):
                if not need_trace:
                    self.bad.add(r["url"])  # this RPC can't serve state → skip for this client
            if self.calls >= self.max_calls:
                raise RpcBudget(method)
        return False, last_err

    # --- helpers ---
    def tip(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def balance(self, addr: str, b: int) -> int:
        if b not in self._bal:
            self._bal[b] = int(self.call("eth_getBalance", [addr, hex(b)]), 16)
        return self._bal[b]

    def nonce(self, addr: str, b: int) -> int:
        if b not in self._nonce:
            self._nonce[b] = int(self.call("eth_getTransactionCount", [addr, hex(b)]), 16)
        return self._nonce[b]

    def block(self, b: int, full: bool = True) -> dict:
        return self.call("eth_getBlockByNumber", [hex(b), full]) or {}

    def block_ts(self, b: int) -> int:
        if b not in self._ts:
            self._ts[b] = int((self.block(b, False) or {}).get("timestamp", "0x0"), 16)
        return self._ts[b]


def _curl_post(url: str, payload: dict, timeout: int = 15):
    # URL goes via curl config on stdin (-K -), not argv → keyed URLs never show in `ps`.
    try:
        cfg = 'url = "' + url.replace("\\", "\\\\").replace('"', '\\"') + '"\n'
        out = subprocess.check_output(
            ["curl", "-sS", "--max-time", str(timeout), "-A", UA, "-K", "-",
             "-H", "content-type: application/json", "-d", json.dumps(payload)],
            input=cfg, text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception as e:
        return {"error": {"message": f"transport:{type(e).__name__}"}}


def _iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), SH).isoformat(timespec="seconds")


def _first_true(lo: int, hi: int, pred) -> int | None:
    """Smallest b in [lo,hi] with pred(b) True, assuming monotone False..True."""
    if not pred(hi):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if pred(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def block_at_or_before(cli: RpcClient, ts: int, tip: int) -> int:
    """Largest block with timestamp <= ts. Bisection on a fixed power-of-two grid
    (deterministic midpoints → memoized header timestamps are reused on resume)."""
    if cli.block_ts(tip) <= ts:
        return tip
    G = _grid_hi(tip)
    ts_at = lambda x: cli.block_ts(min(x, tip))
    lo, hi = 0, G
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if mid >= tip or ts_at(mid) > ts:
            hi = mid
        else:
            lo = mid
    return min(lo, tip)


def _walk_calls(node: dict, addr: str, out: list):
    if not isinstance(node, dict):
        return
    to = (node.get("to") or "").lower()
    try:
        val = int(node.get("value") or "0x0", 16)
    except Exception:
        val = 0
    if to == addr and val > 0 and (node.get("from") or "").lower() != addr:
        out.append({"from": (node.get("from") or "").lower(), "value": val})
    for c in node.get("calls") or []:
        _walk_calls(c, addr, out)


def inflow_in_block(cli: RpcClient, addr: str, b: int) -> dict:
    """Find the funding transfer to addr in block b. Returns row or {'unknown_internal':True,...}."""
    blk = cli.block(b, True)
    ts = int(blk.get("timestamp", "0x0"), 16) if blk else 0
    for tx in (blk.get("transactions") or []):
        if not isinstance(tx, dict):
            continue
        if (tx.get("to") or "").lower() == addr and int(tx.get("value") or "0x0", 16) > 0 \
                and (tx.get("from") or "").lower() != addr:
            return _row(cli.chain, addr, tx["from"].lower(), tx.get("hash"), int(tx["value"], 16), ts, b, "tx")
    # internal transfer → trace
    try:
        traces = cli.call("debug_traceBlockByNumber", [hex(b), {"tracer": "callTracer"}], need_trace=True)
    except RpcBudget:
        raise
    except Exception:
        traces = None
    for t in traces or []:
        found: list = []
        _walk_calls((t or {}).get("result") or {}, addr, found)
        if found:
            f = found[0]
            return _row(cli.chain, addr, f["from"], (t or {}).get("txHash"), f["value"], ts, b, "internal")
    # no trace available → fan-out heuristic: value-bearing tx whose calldata names addr
    # (multicall/disperse). Marked inferred → scored low, never hard evidence.
    a40 = addr[2:]
    for tx in (blk.get("transactions") or []):
        if not isinstance(tx, dict):
            continue
        if a40 in (tx.get("input") or "").lower() and int(tx.get("value") or "0x0", 16) > 0:
            row = _row(cli.chain, addr, (tx.get("from") or "").lower(), tx.get("hash"),
                       None, ts, b, "calldata")
            row["inferred"] = True
            row["amount"] = None  # exact amount unknown without trace
            row["note_zh"] = "批量转账（calldata 含部署者地址）推断资助方，仅作弱信号"
            return row
    return {"unknown_internal": True, "block": b, "funded_ts": ts, "funded_at": _iso(ts),
            "note_zh": "入金为内部转账/系统交易，未能定位资助方（funding_unknown_internal）"}


def _row(chain, addr, frm, tx, val, ts, b, via):
    if val is None:
        val = 0
    return {
        "from": frm, "to": addr, "tx": tx,
        "amount": f"{val / 1e18:.8f}".rstrip("0").rstrip("."),
        "value_wei": val, "funded_at": _iso(ts), "funded_ts": ts, "block": b,
        "asset": NATIVE.get(chain, "NATIVE"), "chain": chain, "via": f"rpc_{via}",
    }


def _grid_hi(tip: int) -> int:
    """Fixed power-of-two upper bound → bisection midpoints don't move with the tip,
    so memoized probes are reused across resumed runs."""
    g = 1
    while g < tip:
        g <<= 1
    return g


def first_inflow(cli: RpcClient, addr: str, tip: int | None = None) -> dict | None:
    addr = addr.lower()
    tip = tip if tip is not None else cli.tip()
    G = _grid_hi(tip)
    nonce_at = lambda b: cli.nonce(addr, min(b, tip))
    bal_at = lambda b: cli.balance(addr, min(b, tip))
    if nonce_at(G) > 0:
        n1 = _first_true(0, G, lambda b: nonce_at(b) > 0)
        hi = n1
    else:
        hi = G
    if bal_at(hi) == 0:
        return None
    f = _first_true(0, hi, lambda b: bal_at(b) > 0)
    if f is None:
        return None
    return inflow_in_block(cli, addr, min(f, tip))


def last_inflow_before(cli: RpcClient, addr: str, lo: int, hi: int, *, max_segments: int = 6) -> dict | None:
    """Right-most block in [lo,hi] where addr's balance increased (bounded).

    Walk constant-nonce segments right→left: nonce is monotone, so the start c of the
    segment ending at hi is a binary search. Inside [c,hi] there is no outgoing spend,
    so balance is monotone → an increase exists iff bal(hi) > bal(c); bisect for it.
    """
    addr = addr.lower()
    for _ in range(max_segments):
        if hi <= lo:
            return None
        n_hi = cli.nonce(addr, hi)
        c = lo if cli.nonce(addr, lo) == n_hi else _first_true(lo, hi, lambda x: cli.nonce(addr, x) >= n_hi)
        b_hi = cli.balance(addr, hi)
        if c is not None and c < hi and b_hi > cli.balance(addr, c):
            blk = _first_true(c + 1, hi, lambda x: cli.balance(addr, x) >= b_hi)
            return inflow_in_block(cli, addr, blk) if blk is not None else None
        if c is None or c <= lo:
            return None
        hi = c - 1
    return None


UNK_RETRY_MAX = 3


def _retry_unknown(cli: RpcClient, addr: str, ent: dict, key: str) -> None:
    """Cached funding_unknown_internal rows were produced when no trace RPC answered.
    Once a trace-capable RPC is configured (PublicNode token), re-trace that one block
    (1 block + 1 trace call), at most UNK_RETRY_MAX times per row."""
    row = ent.get(key)
    if not (isinstance(row, dict) and row.get("unknown_internal") and row.get("block")):
        return
    if not any(r.get("trace") for r in cli.rpcs):
        return
    rk = f"unk_retry:{key}"
    if int(ent.get(rk) or 0) >= UNK_RETRY_MAX:
        return
    ent[rk] = int(ent.get(rk) or 0) + 1
    again = inflow_in_block(cli, addr, int(row["block"]))
    if again and not again.get("unknown_internal"):
        ent[key] = again


# ---- cache ----
def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    try:
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        pass


def _memo_in(cli: RpcClient, ent: dict, ts_memo: dict) -> None:
    m = ent.get("memo") or {}
    cli._bal.update({int(k): int(v) for k, v in (m.get("bal") or {}).items()})
    cli._nonce.update({int(k): int(v) for k, v in (m.get("nonce") or {}).items()})
    cli._ts.update({int(k): int(v) for k, v in (ts_memo or {}).items()})


def _memo_out(cli: RpcClient, ent: dict, cache: dict, chain: str, tip: int | None) -> None:
    # never memoize the moving tip (balance there can still change)
    def keep(d):
        items = [(k, v) for k, v in d.items() if tip is None or k < tip]
        return {str(k): v for k, v in items[-MEMO_CAP:]}
    ent["memo"] = {"bal": keep(cli._bal), "nonce": keep(cli._nonce)}
    tsm = cache.setdefault("_block_ts", {}).setdefault(chain, {})
    tsm.update({str(k): v for k, v in cli._ts.items()})
    if len(tsm) > 4000:
        cache["_block_ts"][chain] = dict(list(tsm.items())[-4000:])


def fetch_native_inflows_rpc(address: str, chain: str, *, deployed_ts: int | None = None,
                             client: RpcClient | None = None, use_cache: bool = True,
                             time_budget_s: float | None = None) -> list[dict]:
    """Return up to 2 inflow rows (first inflow, last inflow ≤7d before deploy). Never raises.

    LAST_STATUS['status'] is 'complete', 'pending' (time/call budget hit — resumes next
    call from memo), 'none' (never funded / unknown internal) or 'error'.
    """
    addr = (address or "").lower()
    LAST_STATUS["status"] = None
    if chain not in ARCHIVE_RPCS and client is None:
        LAST_STATUS["status"] = "none"
        return []
    budget = PER_ADDRESS_S if time_budget_s is None else time_budget_s
    remaining_proc = _budget_left()
    if client is None and remaining_proc <= 0:
        LAST_STATUS["status"] = "pending"
        return []
    t_start = time.time()
    cli = client or RpcClient(chain, deadline=t_start + min(budget, remaining_proc))
    cache = _load_cache() if use_cache else {}
    ck = f"{chain}:{addr}"
    ent = cache.setdefault(ck, {})
    _memo_in(cli, ent, (cache.get("_block_ts") or {}).get(chain) or {})
    rows: list[dict] = []
    tip = None
    status = "complete"
    try:
        _retry_unknown(cli, addr, ent, "first")
        for gk0 in [k for k in ent if k.startswith("gas7d:")]:
            _retry_unknown(cli, addr, ent, gk0)
        first = ent.get("first")
        if not first:
            tip = cli.tip()
            first = first_inflow(cli, addr, tip)
            if first is not None:
                ent["first"] = first
        if first and not first.get("unknown_internal"):
            rows.append(first)
        elif not first or first.get("unknown_internal"):
            status = "none"
        if deployed_ts and first:
            gk = f"gas7d:{int(deployed_ts)}"
            gas = ent.get(gk)
            if gas is None:
                cli.calls = 0  # fresh per-phase call budget (time deadline still applies)
                tip = tip if tip is not None else cli.tip()
                b_dep = block_at_or_before(cli, int(deployed_ts), tip)
                b_lo = block_at_or_before(cli, int(deployed_ts) - 7 * 86400, b_dep)
                if first.get("block") and first["block"] > b_lo:
                    b_lo = first["block"]
                gas = last_inflow_before(cli, addr, b_lo, max(b_lo, b_dep - 1)) or {}
                ent[gk] = gas
            if gas and not gas.get("unknown_internal") and gas.get("tx") != first.get("tx"):
                rows.append(gas)
    except RpcBudget:
        status = "pending"
    except Exception:
        status = "error"
    finally:
        if client is None:
            _spent[0] += time.time() - t_start
        if use_cache:
            if ent.get("first") and all(k == "first" or k.startswith(("gas7d:", "unk_retry:")) or k == "memo"
                                        for k in ent) \
                    and status == "complete":
                ent.pop("memo", None)  # done → drop probe memo
            else:
                _memo_out(cli, ent, cache, chain, tip)
            _save_cache(cache)
    LAST_STATUS["status"] = status
    return rows


def probe(chain: str, addr: str = "0xf977814e90da44bfa03b6295a0616a897441acec") -> dict:
    """Archive capability per RPC. Keys are masked (host only) — safe to persist."""
    out = {}
    for r in ARCHIVE_RPCS.get(chain, []):
        cli = RpcClient(chain, rpcs=[r], max_calls=6)
        k = mask_url(r["url"])
        try:
            t = cli.tip()
            cli.balance(addr, max(1, t - 3_000_000))
            out[k] = "archive_ok"
        except Exception as e:
            out[k] = f"fail:{scrub(str(e))[:60]}"
    return out
