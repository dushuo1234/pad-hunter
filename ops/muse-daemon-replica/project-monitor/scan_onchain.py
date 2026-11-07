#!/usr/bin/env python3
"""On-chain factory / event watcher for Pad Hunter listing+CA early warning.

- Loads factories.json + watchlist.json
- Infers likely chains per locked project
- eth_getCode on factories (size only — not full bytecode dumps)
- eth_getLogs in capped block windows for TokenCreated / PairCreated-style activity
- Writes onchain_scan_latest.json

Does NOT invent API keys. Uses public RPCs listed in factories.json.
Blockscout HTTP APIs may be Cloudflare-blocked; RPC is preferred.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
FACTORIES = BASE / "factories.json"
WATCHLIST = BASE / "watchlist.json"
LATEST = BASE / "onchain_scan_latest.json"
PREV = BASE / "onchain_scan_previous.json"
SH = ZoneInfo("Asia/Shanghai")

# topic0 = keccak256 of canonical event sig (first 4 bytes of keccak as 32-byte hex left-padded — full 32 bytes)
# Computed with pysha3 if available, else leave None and just pull all logs.
KNOWN_TOPICS = {
    # Uniswap V2 PairCreated(address,address,address,uint256)
    "PairCreated": "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9",
}


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def now_label() -> str:
    return datetime.now(SH).strftime("%Y-%m-%d %H:%M:%S Asia/Shanghai")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def rpc_call(rpc_url: str, method: str, params: list, timeout: int = 25) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    cmd = [
        "curl", "-sS", "--max-time", str(timeout),
        "-X", "POST", rpc_url,
        "-H", "content-type: application/json",
        "-H", "user-agent: PadHunterOnchain/1.0",
        "-d", payload,
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception as e:
        return {"error": {"message": str(e)[:200]}}


def pick_rpc(chain_cfg: dict) -> tuple[str | None, int | None]:
    """Return (rpc_url, block_number). Reuses the successful eth_blockNumber so callers
    do not race a second call that can miss result intermittently."""
    for u in chain_cfg.get("rpc") or []:
        r = rpc_call(u, "eth_blockNumber", [])
        res = r.get("result")
        if res:
            try:
                return u, int(res, 16)
            except Exception:
                continue
    return None, None


def code_size(rpc: str, address: str) -> dict:
    r = rpc_call(rpc, "eth_getCode", [address, "latest"])
    code = r.get("result") or ""
    if not isinstance(code, str) or not code.startswith("0x"):
        return {"address": address, "ok": False, "bytes": 0, "error": str(r.get("error") or "no code")}
    nbytes = max(0, (len(code) - 2) // 2)
    return {"address": address, "ok": nbytes > 0, "bytes": nbytes, "error": ""}


def topic_to_address(topic: str) -> str | None:
    if not topic or not topic.startswith("0x") or len(topic) != 66:
        return None
    return "0x" + topic[-40:]


def extract_addrs_from_log(log: dict) -> list[str]:
    addrs = []
    for t in (log.get("topics") or [])[1:]:
        a = topic_to_address(t)
        if a and a != "0x0000000000000000000000000000000000000000":
            addrs.append(a)
    data = (log.get("data") or "")[2:]
    # naive: every 32-byte word ending that looks like an address (12 zero bytes + 20)
    for i in range(0, len(data), 64):
        word = data[i : i + 64]
        if len(word) == 64 and word[:24] == "0" * 24:
            addrs.append("0x" + word[24:])
    # dedupe preserve order
    seen = set()
    out = []
    for a in addrs:
        al = a.lower()
        if al not in seen:
            seen.add(al)
            out.append(a)
    return out


def get_logs_chunked(rpc: str, address: str, from_block: int, to_block: int, max_range: int, topics: list | None = None) -> tuple[list, list]:
    """Return (logs, errors)."""
    logs: list = []
    errors: list = []
    start = from_block
    while start <= to_block:
        end = min(to_block, start + max_range - 1)
        filt: dict = {
            "address": address,
            "fromBlock": hex(start),
            "toBlock": hex(end),
        }
        if topics:
            filt["topics"] = topics
        r = rpc_call(rpc, "eth_getLogs", [filt], timeout=40)
        if r.get("error"):
            errors.append({"from": start, "to": end, "error": r["error"]})
            # if range too large, shrink
            msg = str(r["error"])
            if "block range" in msg.lower() and max_range > 200:
                max_range = max(200, max_range // 2)
                continue
            start = end + 1
            continue
        batch = r.get("result") or []
        if isinstance(batch, list):
            logs.extend(batch)
        start = end + 1
        time.sleep(0.05)
    return logs, errors


def infer_project_chains(wl_projects: list, hints: dict) -> list[dict]:
    out = []
    for p in wl_projects:
        name = p["name"]
        hint = hints.get(name) or {}
        chains = list(hint.get("chains") or [])
        # also from project.chain field
        ch = (p.get("chain") or "").lower()
        if "robinhood" in ch and "robinhood" not in chains:
            chains.append("robinhood")
        if ch in ("eth", "ethereum") and "ethereum" not in chains:
            chains.append("ethereum")
        if "hyper" in ch and "hyperevm" not in chains:
            chains.append("hyperevm")
        if "kaspa" in ch and "kaspa" not in chains:
            chains.append("kaspa")
        if "ordinal" in ch and "ordinals" not in chains:
            chains.append("ordinals")
        if not chains:
            chains = ["unknown"]
        out.append({
            "name": name,
            "handle": p.get("handle"),
            "declared_chain": p.get("chain"),
            "inferred_chains": chains,
            "notes": hint.get("notes"),
            "status": p.get("status"),
            "listing": p.get("listing"),
            "ca": p.get("ca"),
        })
    return out


def main() -> int:
    fac_doc = load_json(FACTORIES, {})
    wl = load_json(WATCHLIST, {})
    projects = wl.get("projects") or []
    chains_cfg = fac_doc.get("chains") or {}
    factories = fac_doc.get("factories") or []
    hints = fac_doc.get("project_chain_hints") or {}

    project_map = infer_project_chains(projects, hints)

    # which chains are relevant given watchlist
    needed = set()
    for pm in project_map:
        for c in pm["inferred_chains"]:
            if c not in ("unknown",):
                needed.add(c)

    chain_status = {}
    for cid, cfg in chains_cfg.items():
        # Solana is workbench/Helius-only — never eth_* poll here
        if cid == "solana" or (cfg.get("note") or "").lower().find("non-evm") >= 0:
            chain_status[cid] = {
                "rpc": None, "block": None, "skipped": True,
                "note": "solana_workbench_only — no RPC poll (see solana_scan_pref.json)",
            }
            continue
        if not cfg.get("rpc"):
            chain_status[cid] = {"rpc": None, "block": None, "note": cfg.get("note") or "no rpc", "skipped": cid not in needed and cid not in {f["chain"] for f in factories}}
            continue
        rpc, bn = pick_rpc(cfg)
        if not rpc or bn is None:
            chain_status[cid] = {"rpc": None, "block": None, "error": "all rpcs failed", "note": cfg.get("note")}
            continue
        chain_status[cid] = {"rpc": rpc, "block": bn, "chain_id": cfg.get("chain_id"), "max_log_range": cfg.get("max_log_range", 1000)}

    factory_results = []
    new_deploy_hints = []

    prev = load_json(LATEST, {})
    prev_tx = set()
    for item in (prev.get("new_deploy_hints") or []):
        if item.get("tx"):
            prev_tx.add(item["tx"].lower())

    for f in factories:
        chain = f["chain"]
        st = chain_status.get(chain) or {}
        rpc = st.get("rpc")
        entry = {
            "id": f["id"],
            "name": f["name"],
            "chain": chain,
            "address": f["address"],
            "relevance": f.get("relevance"),
            "code": None,
            "logs_scanned": 0,
            "recent_logs": [],
            "errors": [],
        }
        if not rpc:
            entry["errors"].append("no working rpc")
            factory_results.append(entry)
            continue

        entry["code"] = code_size(rpc, f["address"])
        bn = st["block"]
        max_range = int(st.get("max_log_range") or 1000)
        # look back ~ max_range * 3 (capped)
        lookback = min(bn, max_range * 3)
        from_b = max(0, bn - lookback)
        logs, errs = get_logs_chunked(rpc, f["address"], from_b, bn, max_range)
        entry["errors"].extend(errs)
        entry["logs_scanned"] = len(logs)
        entry["from_block"] = from_b
        entry["to_block"] = bn

        # summarize unique topic0 + sample decoded addresses
        by_topic: dict[str, int] = {}
        samples = []
        # Ambient DEX factories are noisy — only emit NEW_DEPLOY for launchpad-like factories
        # or when topic0 is PairCreated on univ2 (still high volume; marked ambient).
        alertable = f["id"] in {
            "nftx_public_gate_rh", "nftx_locker_rh",
            "launchpad_meme_hyperevm", "spinup_memelaunchpad",
        }
        ambient = f["id"] in {"univ2_eth", "univ4_pm_rh", "hyperswap_v3_factory"}
        pair_created = KNOWN_TOPICS["PairCreated"]
        for log in logs[-30:]:  # keep last 30 for samples
            topics = log.get("topics") or []
            t0 = topics[0] if topics else None
            if t0:
                by_topic[t0] = by_topic.get(t0, 0) + 1
            addrs = extract_addrs_from_log(log)
            sample = {
                "tx": log.get("transactionHash"),
                "block": int(log.get("blockNumber"), 16) if log.get("blockNumber") else None,
                "topic0": t0,
                "addresses": addrs[:6],
            }
            samples.append(sample)
            tx = (log.get("transactionHash") or "").lower()
            if not (tx and tx not in prev_tx and addrs):
                continue
            if alertable:
                new_deploy_hints.append({
                    "factory_id": f["id"],
                    "factory": f["address"],
                    "chain": chain,
                    "tx": log.get("transactionHash"),
                    "block": sample["block"],
                    "topic0": t0,
                    "addresses": addrs[:6],
                    "note": "Launchpad/factory log — correlate with watchlist names/symbols.",
                    "ambient": False,
                })
            elif ambient and f["id"] == "univ2_eth" and t0 == pair_created:
                # count only; do not flood digest — keep at most 3 ambient samples total later
                new_deploy_hints.append({
                    "factory_id": f["id"],
                    "factory": f["address"],
                    "chain": chain,
                    "tx": log.get("transactionHash"),
                    "block": sample["block"],
                    "topic0": t0,
                    "addresses": addrs[:6],
                    "note": "Ambient Uniswap V2 PairCreated (not matched to watchlist).",
                    "ambient": True,
                })
        entry["topic0_counts"] = by_topic
        entry["recent_logs"] = samples[-10:]
        factory_results.append(entry)

    # gaps honesty
    gaps = [
        "No Etherscan API key in env — cannot pull verified source via Etherscan-family APIs without a key; use explorer URLs + eth_getCode size instead.",
        "Robinhood Blockscout HTTP API is Cloudflare-blocked from this host; RPC eth_getLogs/eth_getCode works.",
        "QuantumPad V4 is a private ZK launchpad — public Uniswap factories may show nothing until reveal.",
        "$PKC: CA only in X bio — factory watching will not catch it early.",
        "Ballast tokens on ballast.exchange are other launches on that pad, not Ballast's own CA.",
        "Enter_Elysium / GIWA / Ink / Ordinals / Kaspa: no reliable public factory wired in this pass.",
        "OpenSea drop factory on Robinhood Chain referenced by third parties but address not confirmed here.",
        "HyperEVM RPC caps eth_getLogs to ~1000 blocks; scans use chunked windows.",
        "Matching a factory-emitted address to a named Pad Hunter project still needs X/TG/site confirmation (name/symbol).",
    ]

    report = {
        "checked_at": now_label(),
        "checked_at_iso": now_iso(),
        "watchlist_count": len(projects),
        "project_chain_map": project_map,
        "chain_status": chain_status,
        "factories": factory_results,
        "new_deploy_hints": (
            [h for h in new_deploy_hints if not h.get("ambient")][:40]
            + [h for h in new_deploy_hints if h.get("ambient")][:3]
        ),
        "gaps": gaps,
        "how_to_read_factory_code": [
            "1) eth_getCode(address) via public RPC — confirms deploy + size (proxy often <1KB).",
            "2) Open explorer URL: {explorer}/address/{addr}#code for verified Solidity when UI allows.",
            "3) Prefer watching event logs (PairCreated / TokenCreated / collection create) over dumping bytecode.",
            "4) When a new address appears in factory logs, cross-check project X bio/posts and site before treating as CA.",
        ],
    }

    if LATEST.exists():
        PREV.write_text(LATEST.read_text(encoding="utf-8"), encoding="utf-8")
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # update watchlist inferred fields (non-destructive)
    hint_by_name = {h["name"]: h for h in project_map}
    for p in projects:
        h = hint_by_name.get(p["name"])
        if h:
            p["inferred_chains"] = h["inferred_chains"]
            if h.get("notes") and not p.get("onchain_notes"):
                p["onchain_notes"] = h["notes"]
    wl["projects"] = projects
    wl["last_onchain_scan_at"] = now_iso()
    WATCHLIST.write_text(json.dumps(wl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # digest
    live = [f for f in factory_results if (f.get("code") or {}).get("ok")]
    with_logs = [f for f in factory_results if f.get("logs_scanned")]
    print(f"ONCHAIN factories_live={len(live)}/{len(factory_results)} with_recent_logs={len(with_logs)} new_hints={len(new_deploy_hints)}")
    for f in factory_results:
        c = f.get("code") or {}
        print(f"  {f['chain']:10} {f['id']:28} code={c.get('bytes',0):6} logs={f.get('logs_scanned',0):4} err={len(f.get('errors') or [])}")
    real = [h for h in new_deploy_hints if not h.get("ambient")]
    amb = [h for h in new_deploy_hints if h.get("ambient")]
    if real:
        for h in real[:8]:
            print(f"NEW_DEPLOY {h['chain']} {h['factory_id']} tx={h['tx']} addrs={','.join(h['addresses'][:3])}")
    elif amb:
        print(f"NEW_DEPLOY none watchlist-relevant; ambient_univ2_samples={len(amb)}")
    else:
        print("NEW_DEPLOY none in scanned window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
