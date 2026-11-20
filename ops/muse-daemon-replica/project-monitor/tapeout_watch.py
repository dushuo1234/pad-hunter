#!/usr/bin/env python3
"""TapeRobot / TapeOut immediate CA watcher (BSC only).

Sources (all feed tapeout_push.push_candidate, first one wins):
  factory:tapeout   getLogs on TapeOut factory 0x6822…F7e2, create topic 0x2e8868f1…
                    (topic1=processor, topic2=transistors, topic3=creator, data=name,cap,price).
                    Alert ONLY when creator ∈ watched wallets (or official X confirms).
                    Name-only match (TapeRobot/ROBOT, creator not watched) = name_match_unconfirmed:
                    logged, never pushed as alert / Pages CA (copycat fix 2026-10-21).
                    Every create is logged to tapeout_factory_events.jsonl.
  factory:fourmeme  getLogs on four.meme TokenManager2 TokenCreate (creator,token,…,name,symbol).
                    Alert when creator ∈ watched wallets OR name/symbol matches.
  wallet:activity   eth_getTransactionCount for each watched wallet; on nonce bump resolve
                    each new tx (binary-search blocks), log activity + WALLET_ACTIVITY alert.
                    If the tx created a contract (bytecode), also push_candidate as today.
State: tapeout_watch_state.json.  Status: tapeout_watch_status.json.
Activity: tapeout_wallet_activity.jsonl + tapeout_activity_alerts.jsonl (relay).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
_VENV = BASE / ".venv/lib"
for _p in sorted(_VENV.glob("python*/site-packages")):
    sys.path.insert(0, str(_p))
sys.path.insert(0, str(BASE))
from Crypto.Hash import keccak  # noqa: E402
from tapeout_push import push_candidate, seed  # noqa: E402

SH = ZoneInfo("Asia/Shanghai")
CFG = BASE / "tapeout_watch_wallets.json"
STATE = BASE / "tapeout_watch_state.json"
STATUS = BASE / "tapeout_watch_status.json"
FAC_EVENTS = BASE / "tapeout_factory_events.jsonl"
WALLET_ACTIVITY = BASE / "tapeout_wallet_activity.jsonl"
ACTIVITY_ALERTS = BASE / "tapeout_activity_alerts.jsonl"
RPCS = [
    "https://tapeout.net/rpc",
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.binance.org",
    "https://1rpc.io/bnb",
    "https://bsc.publicnode.com",
]
TAPEOUT = "0x68224f668083c29e9800be2a646d42d18cedf7e2"
TAPEOUT_T0 = "0x2e8868f18a1eaf0222b5b09484fdf12163e9741393f8457cd79d2ae42b2d2290"
FOURMEME = "0x5c952063c7fc8610ffdb798152d69f0b9550762b"
FOURMEME_T0 = "0x396d5e902b675b032348d3d2e9517ee8f0c4a926603fbc075d3d282ff00cad20"
NAME_RE = re.compile(r"tape\s*-?_?robot|^robot$|^\$?robot$", re.I)
MAX_RANGE = 40

BOOST_STATUS = BASE / "tapeout_boost_status.json"
X_WAKE = BASE / "tapeout_x_boost_wake.json"
LISTING_TIMES = BASE / "listing_times.json"


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def compute_boost(cfg: dict) -> dict:
    """Return {active, reason, interval_s, x_interval_s, targets[], next_x_due}.
    Active when any boost_target is in [listing_at-pre, listing_at+post] OR mint_live.
    Also merges listing_times.json for TapeRobot_bsc if present.
    """
    now = datetime.now(SH)
    boost_cfg = cfg.get("boost") or {}
    if not boost_cfg.get("enabled", True):
        return {"active": False, "reason": "disabled", "interval_s": float((boost_cfg.get("intervals") or {}).get("normal", {}).get("factory_wallets_s", 8)),
                "x_interval_s": float((boost_cfg.get("intervals") or {}).get("normal", {}).get("x_s", 300)), "targets": []}
    intervals = boost_cfg.get("intervals") or {}
    normal_i = float((intervals.get("normal") or {}).get("factory_wallets_s", 8))
    boost_i = float((intervals.get("boost") or {}).get("factory_wallets_s", 2))
    normal_x = float((intervals.get("normal") or {}).get("x_s", 300))
    boost_x = float((intervals.get("boost") or {}).get("x_s", 45))
    pre = int(boost_cfg.get("pre_listing_minutes", 10))
    post = int(boost_cfg.get("post_listing_minutes", 120))
    targets = list(cfg.get("boost_targets") or [])
    # merge listing_times for known handles
    try:
        lt = json.loads(LISTING_TIMES.read_text(encoding="utf-8"))
        by_h = {(p.get("handle") or "").lower(): p for p in (lt.get("projects") or [])}
        for t in targets:
            h = (t.get("handle") or "").lower()
            if h in by_h and by_h[h].get("listing_at") and not t.get("listing_at"):
                t["listing_at"] = by_h[h]["listing_at"]
    except Exception:
        pass
    active_targets = []
    reasons = []
    for t in targets:
        la = _parse_iso(t.get("listing_at"))
        if t.get("mint_live"):
            active_targets.append(t)
            reasons.append(f"{t.get('handle')}:mint_live")
            continue
        if not la:
            continue
        if la.tzinfo is None:
            la = la.replace(tzinfo=SH)
        start = la - timedelta(minutes=pre)
        end = la + timedelta(minutes=post)
        if start <= now <= end:
            active_targets.append(t)
            reasons.append(f"{t.get('handle')}:window {start.isoformat()}→{end.isoformat()}")
    active = bool(active_targets)
    return {
        "active": active,
        "reason": "; ".join(reasons) if reasons else "outside window",
        "interval_s": boost_i if active else normal_i,
        "x_interval_s": boost_x if active else normal_x,
        "targets": [{"handle": t.get("handle"), "listing_at": t.get("listing_at"), "mint_live": t.get("mint_live"),
                     "x_user_id": t.get("x_user_id"), "x_username": t.get("x_username")} for t in active_targets],
        "pre_listing_minutes": pre,
        "post_listing_minutes": post,
        "at": now.isoformat(timespec="seconds"),
    }


def now_iso():
    return datetime.now(SH).isoformat(timespec="seconds")


class Rpc:
    def __init__(self, urls):
        self.urls, self.i, self.cool = urls, 0, {}
        self.errors = 0

    def call(self, method, params, timeout=10):
        last = None
        for _ in range(len(self.urls) * 2):
            u = self.urls[self.i % len(self.urls)]; self.i += 1
            if self.cool.get(u, 0) > time.time():
                continue
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            try:
                out = subprocess.check_output(["curl", "-sS", "--max-time", str(timeout), "-X", "POST", u,
                                               "-H", "content-type: application/json", "-d", payload],
                                              text=True, stderr=subprocess.DEVNULL)
                d = json.loads(out)
                if "result" in d:
                    return d["result"]
                last = d.get("error")
            except Exception as e:
                last = str(e)[:100]
            self.cool[u] = time.time() + 4
            self.errors += 1
        raise RuntimeError(f"{method} failed: {last}")


def _rlp_bytes(b: bytes) -> bytes:
    if len(b) == 1 and b[0] < 0x80:
        return b
    if len(b) < 56:
        return bytes([0x80 + len(b)]) + b
    ln = len(b).to_bytes((len(b).bit_length() + 7) // 8, "big")
    return bytes([0xb7 + len(ln)]) + ln + b


def create_address(sender: str, nonce: int) -> str:
    nb = b"" if nonce == 0 else nonce.to_bytes((nonce.bit_length() + 7) // 8, "big")
    payload = _rlp_bytes(bytes.fromhex(sender[2:])) + _rlp_bytes(nb)
    rlp = bytes([0xc0 + len(payload)]) + payload
    h = keccak.new(digest_bits=256); h.update(rlp)
    return "0x" + h.hexdigest()[-40:]


def _word(b, i):
    return b[32 * i:32 * i + 32]


def _str_at(b, off):
    try:
        ln = int.from_bytes(b[off:off + 32], "big")
        return b[off + 32:off + 32 + ln].decode("utf-8", "replace")
    except Exception:
        return None


def load_json(p, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return d


def save_json(p, doc):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)



# Known-ish selectors for kind guessing (not exhaustive).
_WITHDRAW_SELS = {
    "0x3ccfd60b",  # withdraw()
    "0x2e1a7d4d",  # withdraw(uint256)
    "0x853828b6",  # withdrawAll()
    "0x51cff8d9",  # withdraw(address)
    "0xd9caed12",  # withdraw(address,uint256) common variant
    "0x00f714ce",  # withdraw(uint256,address)
    "0x441a3e70",  # withdraw(uint256,uint256)
}


def _guess_kind(to: str | None, value_wei: int, data: str, contract_address: str | None) -> str:
    if contract_address or not to:
        return "create"
    sel = (data or "0x")[:10].lower() if data and data != "0x" else ""
    if sel in _WITHDRAW_SELS:
        return "withdraw-like"
    if value_wei > 0 and (not data or data in ("0x", "0x0")):
        return "transfer"
    if sel:
        return "call"
    if value_wei > 0:
        return "transfer"
    return "call"


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class Watcher:
    def __init__(self, interval):
        self.base_interval = interval  # CLI default; overridden by boost config each loop
        self.interval = interval
        self.rpc = Rpc(RPCS)
        self.state = load_json(STATE, {})
        self.stats = {"started_at": now_iso(), "loops": 0, "tapeout_creates": 0, "fourmeme_creates": 0,
                      "alerts": 0, "nonce_bumps": 0, "errors": 0, "last_error": None}
        self.reload_cfg()
        for s in self.cfg.get("seed_seen") or []:
            for k in ("processor", "transistors"):
                if s.get(k):
                    seed(s[k], "seed", s.get("note") or "")
            # also seed RobotToken game ERC20 so we don't alert on known CA
            if s.get("token"):
                seed(s["token"], "seed", s.get("note") or "")

    def reload_cfg(self):
        self.cfg = load_json(CFG, {})
        self.wallets = {w["address"].lower(): w for w in self.cfg.get("wallets") or []}

    def apply_boost(self):
        b = compute_boost(self.cfg)
        self.interval = float(b["interval_s"])
        self.stats["boost"] = b
        save_json(BOOST_STATUS, b)
        # X wake: during boost, ask parent routine to poll @TapeRobot_bsc every x_interval_s
        last_x = self.state.get("last_x_wake_at") or 0
        if b["active"] and (time.time() - last_x) >= float(b["x_interval_s"]):
            wake = {
                "due": True,
                "boost": True,
                "at": now_iso(),
                "x_interval_s": b["x_interval_s"],
                "targets": b["targets"],
                "instruction": (
                    "Call x get_users_posts id=<x_user_id> since_id=<tapeout_x_state.json.since_id> "
                    "max_results=10 post.fields=created_at,entities,note_tweet (write_to_file), then "
                    "python3 /workspace/project-monitor/tapeout_x_ingest.py <file>. Deduped via tapeout_push."
                ),
            }
            save_json(X_WAKE, wake)
            self.state["last_x_wake_at"] = time.time()
        elif not b["active"]:
            save_json(X_WAKE, {"due": False, "boost": False, "at": now_iso(), "x_interval_s": b["x_interval_s"],
                               "reason": b["reason"]})
        return b

    # ---- factory logs
    def scan_logs(self, frm, to):
        for fac, t0, kind in ((TAPEOUT, TAPEOUT_T0, "tapeout"), (FOURMEME, FOURMEME_T0, "fourmeme")):
            logs = self.rpc.call("eth_getLogs", [{"address": fac, "topics": [t0],
                                                  "fromBlock": hex(frm), "toBlock": hex(to)}], timeout=12)
            for lg in logs or []:
                (self.on_tapeout if kind == "tapeout" else self.on_fourmeme)(lg)

    def on_tapeout(self, lg):
        t = lg.get("topics") or []
        if len(t) < 4:
            return
        proc, trans, creator = ("0x" + x[-40:] for x in t[1:4])
        b = bytes.fromhex((lg.get("data") or "0x")[2:])
        name = _str_at(b, int.from_bytes(_word(b, 0), "big")) if len(b) >= 96 else None
        cap = int.from_bytes(_word(b, 1), "big") if len(b) >= 64 else None
        price = int.from_bytes(_word(b, 2), "big") if len(b) >= 96 else None
        self.stats["tapeout_creates"] += 1
        watched = creator.lower() in self.wallets
        named = bool(name and NAME_RE.search(name))
        row = {"at": now_iso(), "block": int(lg["blockNumber"], 16), "tx": lg.get("transactionHash"),
               "processor": proc, "transistors": trans, "creator": creator, "name": name,
               "supply_cap": cap, "mint_price_wei": price, "creator_watched": watched, "name_match": named}
        with FAC_EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if not (watched or named):
            return
        why = "creator_watched" if watched else "name_match"
        if not watched:
            self.stats["name_match_unconfirmed"] = self.stats.get("name_match_unconfirmed", 0) + 1
        meta = {"tx": lg.get("transactionHash"), "block": row["block"], "creator": creator,
                "creator_role": (self.wallets.get(creator.lower()) or {}).get("role"),
                "name": name, "supply_cap": cap, "mint_price_bnb": (price / 1e18) if price else None,
                "factory": TAPEOUT, "processor": proc, "transistors": trans, "match": why,
                "creator_watched": watched, "tapeout_url": "https://tapeout.net/"}
        for addr, role in ((trans, "transistors"), (proc, "processor")):
            if push_candidate(addr, source=f"factory:tapeout:{why}", meta=meta, role_hint=role):
                self.stats["alerts"] += 1

    def on_fourmeme(self, lg):
        b = bytes.fromhex((lg.get("data") or "0x")[2:])
        if len(b) < 32 * 5:
            return
        creator = "0x" + _word(b, 0).hex()[-40:]
        token = "0x" + _word(b, 1).hex()[-40:]
        name = _str_at(b, int.from_bytes(_word(b, 3), "big"))
        sym = _str_at(b, int.from_bytes(_word(b, 4), "big"))
        self.stats["fourmeme_creates"] += 1
        watched = creator.lower() in self.wallets
        named = bool((name and NAME_RE.search(name)) or (sym and NAME_RE.search(sym)))
        if not (watched or named):
            return
        why = "creator_watched" if watched else "name_match"
        meta = {"tx": lg.get("transactionHash"), "block": int(lg["blockNumber"], 16), "creator": creator,
                "name": name, "symbol": sym, "factory": FOURMEME, "match": why, "creator_watched": watched,
                "fourmeme_url": f"https://four.meme/token/{token}"}
        if push_candidate(token, source=f"factory:fourmeme:{why}", meta=meta, role_hint="token"):
            self.stats["alerts"] += 1

    # ---- wallet nonce / activity
    def _nonce_at(self, address: str, block: int) -> int:
        return int(self.rpc.call("eth_getTransactionCount", [address, hex(block)]), 16)

    def find_tx_for_nonce(self, address: str, nonce: int, head: int | None = None) -> dict | None:
        """Binary-search the block where `address` first used `nonce`, then return that tx."""
        if head is None:
            head = int(self.rpc.call("eth_blockNumber", []), 16)

        def nonce_at(block: int) -> int | None:
            for attempt in range(4):
                try:
                    return self._nonce_at(address, block)
                except Exception:
                    time.sleep(0.2 * (attempt + 1))
            return None

        def unpack_tx(block: int, blk: dict) -> dict | None:
            addr_l = address.lower()
            for tx in blk.get("transactions") or []:
                if (tx.get("from") or "").lower() == addr_l and int(tx.get("nonce"), 16) == nonce:
                    ts = int(blk["timestamp"], 16)
                    at = datetime.fromtimestamp(ts, SH).isoformat(timespec="seconds")
                    to = tx.get("to")
                    data = tx.get("input") or "0x"
                    value_wei = int(tx.get("value") or "0x0", 16)
                    receipt = None
                    contract_address = None
                    try:
                        receipt = self.rpc.call("eth_getTransactionReceipt", [tx["hash"]], timeout=12)
                        if receipt:
                            ca = receipt.get("contractAddress")
                            if ca and int(ca, 16) != 0:
                                contract_address = ca
                    except Exception:
                        pass
                    if not contract_address and not to:
                        contract_address = create_address(address, nonce)
                    return {
                        "tx_hash": tx["hash"],
                        "block": block,
                        "at": at,
                        "to": to,
                        "value_wei": value_wei,
                        "value_bnb": value_wei / 1e18,
                        "input": data,
                        "selector": (data[:10].lower() if data and len(data) >= 10 else None),
                        "contractAddress": contract_address,
                        "status": (int(receipt.get("status"), 16) if receipt and receipt.get("status") else None),
                    }
            return None

        # Recent window first (BSC fast blocks); widen if needed.
        for window in (8_000, 40_000, 200_000):
            lo = max(0, head - window)
            c_lo = nonce_at(lo)
            if c_lo is None:
                continue
            if c_lo > nonce:
                continue  # need older history
            hi = head
            ok = True
            while lo < hi:
                mid = (lo + hi) // 2
                c = nonce_at(mid)
                if c is None:
                    ok = False
                    break
                if c > nonce:
                    hi = mid
                else:
                    lo = mid + 1
            if not ok:
                continue
            block = lo
            try:
                blk = self.rpc.call("eth_getBlockByNumber", [hex(block), True], timeout=15)
            except Exception:
                continue
            if not blk:
                continue
            found = unpack_tx(block, blk)
            if found:
                return found
        return None

    def _emit_wallet_activity(self, wallet: str, role: str | None, nonce: int, txinfo: dict | None) -> dict:
        """Append activity + alert lines. Never push_candidate for bare EOAs."""
        if txinfo:
            kind = _guess_kind(txinfo.get("to"), int(txinfo.get("value_wei") or 0),
                               txinfo.get("input") or "0x", txinfo.get("contractAddress"))
            # refine withdraw-like by selector set
            sel = (txinfo.get("selector") or "")
            if kind == "call" and sel in _WITHDRAW_SELS:
                kind = "withdraw-like"
            row = {
                "at": txinfo.get("at") or now_iso(),
                "wallet": wallet,
                "role": role,
                "nonce": nonce,
                "tx_hash": txinfo.get("tx_hash"),
                "to": txinfo.get("to"),
                "value_bnb": txinfo.get("value_bnb"),
                "selector": sel or None,
                "contractAddress": txinfo.get("contractAddress"),
                "kind": kind,
                "block": txinfo.get("block"),
                "bscscan_tx": f"https://bscscan.com/tx/{txinfo['tx_hash']}" if txinfo.get("tx_hash") else None,
            }
        else:
            kind = "unknown"
            row = {
                "at": now_iso(),
                "wallet": wallet,
                "role": role,
                "nonce": nonce,
                "tx_hash": None,
                "to": None,
                "value_bnb": None,
                "selector": None,
                "contractAddress": None,
                "kind": kind,
                "block": None,
                "bscscan_tx": None,
                "note": "nonce bumped but tx not resolved",
            }
        _append_jsonl(WALLET_ACTIVITY, row)
        alert = {
            "type": "WALLET_ACTIVITY",
            "dedupe_key": f"WALLET_ACTIVITY:{wallet.lower()}:{nonce}:{row.get('tx_hash') or 'pending'}",
            "project": "TapeRobot·TapeOut监控",
            "handle": "TapeOutWatch",
            "chain": "bsc",
            "at": row["at"],
            "at_label": row["at"].replace("T", " ")[:19] + " Asia/Shanghai",
            "wallet": wallet,
            "role": role,
            "nonce": nonce,
            "tx_hash": row.get("tx_hash"),
            "to": row.get("to"),
            "value_bnb": row.get("value_bnb"),
            "selector": row.get("selector"),
            "contractAddress": row.get("contractAddress"),
            "kind": kind,
            "block": row.get("block"),
            "bscscan_tx": row.get("bscscan_tx"),
            "alert_zh": (
                f"👀 TapeOut钱包动作 [{role or '?'}] `{wallet}` nonce={nonce} kind={kind}"
                + (f" to=`{row['to']}`" if row.get("to") else "")
                + (f" sel={row['selector']}" if row.get("selector") else "")
                + (f" value={row['value_bnb']:.4f}BNB" if row.get("value_bnb") else "")
                + (f" create=`{row['contractAddress']}`" if row.get("contractAddress") else "")
                + (f" {row['bscscan_tx']}" if row.get("bscscan_tx") else "")
            ),
        }
        _append_jsonl(ACTIVITY_ALERTS, alert)
        self.stats["wallet_activity"] = self.stats.get("wallet_activity", 0) + 1
        print(f"[tapeout_watch] {alert['alert_zh']}", flush=True)
        return row

    def scan_wallets(self):
        nonces = self.state.setdefault("nonces", {})

        def get(a):
            return a, int(self.rpc.call("eth_getTransactionCount", [a, "latest"]), 16)
        with ThreadPoolExecutor(max_workers=5) as ex:
            res = list(ex.map(lambda a: get(a), list(self.wallets)))
        head = None
        for a, n in res:
            old = nonces.get(a)
            nonces[a] = n
            if old is None or n <= old:
                continue
            self.stats["nonce_bumps"] += 1
            role = (self.wallets.get(a) or {}).get("role")
            if head is None:
                try:
                    head = int(self.rpc.call("eth_blockNumber", []), 16)
                except Exception:
                    head = self.state.get("last_block")
            for k in range(old, n):
                txinfo = None
                try:
                    txinfo = self.find_tx_for_nonce(a, k, head=head)
                except Exception as e:
                    print(f"[tapeout_watch] resolve tx fail {a} nonce={k}: {e}", flush=True)
                self._emit_wallet_activity(a, role, k, txinfo)
                # CREATE path unchanged: only push real contracts via ca_gate
                ca = None
                if txinfo and txinfo.get("contractAddress"):
                    ca = txinfo["contractAddress"]
                else:
                    derived = create_address(a, k)
                    try:
                        code = self.rpc.call("eth_getCode", [derived, "latest"])
                        if code and code != "0x":
                            ca = derived
                    except Exception:
                        pass
                if ca:
                    meta = {"creator": a, "creator_role": role, "nonce": k,
                            "match": "creator_watched", "creator_watched": True, "via": "contract_creation",
                            "tx": (txinfo or {}).get("tx_hash"), "block": (txinfo or {}).get("block")}
                    if push_candidate(ca, source="wallet:create", meta=meta):
                        self.stats["alerts"] += 1

    def loop_once(self):
        head = int(self.rpc.call("eth_blockNumber", []), 16)
        last = self.state.get("last_block") or (head - 20)
        # cap catch-up (publicnode limit 50 blocks/request) — walk forward in chunks
        frm = last + 1
        while frm <= head:
            to = min(head, frm + MAX_RANGE - 1)
            self.scan_logs(frm, to)
            self.state["last_block"] = to
            frm = to + 1
            if head - frm > 2000:  # too far behind: jump (log)
                self.stats["skipped_blocks"] = self.stats.get("skipped_blocks", 0) + (head - 200 - frm)
                frm = head - 200
        self.scan_wallets()
        self.stats["head"] = head
        save_json(STATE, self.state)

    def run(self):
        b0=self.apply_boost()
        print(f"[tapeout_watch] start wallets={len(self.wallets)} interval={self.interval}s boost={b0.get('active')} reason={b0.get('reason')} at={now_iso()}", flush=True)
        last_cfg = time.time()
        while True:
            t0 = time.time()
            try:
                self.loop_once()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{now_iso()} {str(e)[:200]}"
                print(f"[tapeout_watch] error {e}", flush=True)
                if self.stats["errors"] % 50 == 1:
                    traceback.print_exc()
            self.stats["loops"] += 1
            self.stats["last_loop_at"] = now_iso()
            self.stats["last_loop_ms"] = int((time.time() - t0) * 1000)
            self.stats["last_block"] = self.state.get("last_block")
            self.stats["rpc_errors"] = self.rpc.errors
            b = self.apply_boost()
            save_json(STATUS, {**self.stats, "wallets": list(self.wallets), "interval_s": self.interval,
                               "boost_active": b.get("active"), "boost_reason": b.get("reason"),
                               "sources": ["factory:tapeout", "factory:fourmeme", "wallet:create", "wallet:activity", "x:@TapeRobot_bsc (routine)"]})
            if time.time() - last_cfg > 60:
                self.reload_cfg(); last_cfg = time.time()
            time.sleep(max(0.2, self.interval - (time.time() - t0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        # known: 0x0a68… nonce→ RobotToken etc; check CREATE derivation against a known deploy
        print(create_address("0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0", 0),
              "expect 0xcd234a471b72ba2f1ccf0a70fcaba648a5eecd8d")
        return
    w = Watcher(a.interval)
    if a.once:
        w.loop_once(); print(json.dumps(w.stats, ensure_ascii=False)); return
    w.run()


if __name__ == "__main__":
    main()
