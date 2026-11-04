#!/usr/bin/env python3
"""HARD CA GATE — single source of truth for "is this scraped address a token CA?".

No address may become CA / NEW_CA / NEW_JS_CA / ca_finds(合约CA) / alert unless
verify_address() returns is_token=True.

  EVM:    eth_getCode != 0x (not EIP-7702 delegation) AND pure ERC20:
            - decimals() returns 0..36
            - totalSupply() succeeds
            - transfer/approve/allowance selectors present in bytecode
              (or allowance() call succeeds)
            - NOT ERC721/1155 per ERC165 (0x80ac58cd / 0xd9b67a26 / 0x5b5e139f)
            - ownerOf(1) / tokenURI(1) / getApproved(1) do NOT succeed
          ERC404/DN404 hybrids (ERC20-shaped AND NFT-shaped) → kind=hybrid_404,
          is_token=False (never 已确认CA / 代币 / alert).
  Solana: getAccountInfo owner == SPL Token / Token-2022 AND account is a mint
          AND decimals > 0. decimals==0 (incl. supply 1 or SFT) → nft.
  Hex-only strings (git SHAs, hashes) are never Solana addresses.

kinds: token | nft | hybrid_404 | contract (non-token) | wallet | invalid | unknown
label_zh: 合约CA | NFT合约 | 混合404合约 | 合约(非代币) | 扫出钱包 | 非地址 | 未确认地址
Results cached in addr_verify_cache.json (token/wallet/nft/hybrid/invalid 24h; unknown 10m).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

BASE = Path("/workspace/project-monitor")
CACHE = BASE / "addr_verify_cache.json"
TOKEN_PROGRAMS = {"TokenkegQfeZyiNwAJbNbGqPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}
SYSTEM_PROGRAM = "11111111111111111111111111111111"
B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
LABEL = {
    "token": "合约CA",
    "nft": "NFT合约",
    "hybrid_404": "混合404合约",
    "contract": "合约(非代币)",
    "wallet": "扫出钱包",
    "invalid": "非地址",
    "unknown": "未确认地址",
}

# ERC20 / NFT function selectors (4-byte)
SEL_TRANSFER = "a9059cbb"
SEL_APPROVE = "095ea7b3"
SEL_ALLOWANCE = "dd62ed3e"
SEL_DECIMALS = "313ce567"
SEL_TOTAL_SUPPLY = "18160ddd"
SEL_OWNER_OF = "6352211e"
SEL_TOKEN_URI = "c87b56dd"
SEL_GET_APPROVED = "081812fc"
SEL_SAFE_TF_721 = "42842e0e"  # safeTransferFrom(address,address,uint256)
SEL_SAFE_TF_721_DATA = "b88d4fde"


def _note_zh(kind: str, note: str | None = None, *, symbol: str | None = None,
             decimals=None, chain: str | None = None) -> str:
    """Human-facing Chinese note for UI; keep English `note` for logs."""
    k = kind or "unknown"
    if k == "token":
        bits = ["已确认 ERC20"]
        if symbol:
            bits.append(f"符号 {symbol}")
        if decimals is not None:
            bits.append(f"精度 {decimals}")
        if chain:
            bits.append(f"链 {chain}")
        return " · ".join(bits)
    if k == "nft":
        return "NFT合约（非代币），不作为CA"
    if k == "hybrid_404":
        bits = ["混合404/DN404（兼具 ERC20+NFT），不作为纯代币 CA"]
        if symbol:
            bits.append(f"符号 {symbol}")
        if decimals is not None:
            bits.append(f"精度 {decimals}")
        return " · ".join(bits)
    if k == "wallet":
        return "链上无合约代码 → 钱包（EOA），不当作 CA；已进入关联钱包监控"
    if k == "contract":
        return "有合约字节码但不是 ERC20 代币形态，不当作代币 CA"
    if k == "invalid":
        n = (note or "").lower()
        if "hex string" in n or "git" in n:
            return "十六进制哈希/非地址，已丢弃"
        if "base58" in n or "malformed" in n:
            return "地址格式无效"
        return "非有效地址"
    if k == "unknown":
        n = (note or "").lower()
        if "does not exist" in n:
            return "链上账户不存在"
        if "unreachable" in n:
            return "RPC 暂不可达，待重试"
        return "未能确认地址类型"
    return note or LABEL.get(k, "未确认地址")


TTL = {"unknown": 600}
DEFAULT_TTL = 86400
_RPCS = None


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    try:
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(CACHE)
    except Exception:
        pass


def _rpc(url: str, method: str, params: list, timeout: int = 12) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    try:
        out = subprocess.check_output(["curl", "-sS", "--max-time", str(timeout), "-H",
                                       "Content-Type: application/json", "-d", payload, url],
                                      stderr=subprocess.DEVNULL, timeout=timeout + 2)
        return json.loads(out.decode("utf-8", "replace") or "{}")
    except Exception as e:
        return {"error": str(e)[:120]}


def _eth_call(rpc: str, to: str, data: str) -> str | None:
    r = _rpc(rpc, "eth_call", [{"to": to, "data": data}, "latest"])
    res = r.get("result")
    return res if isinstance(res, str) and res.startswith("0x") and len(res) > 2 else None


def _decode_str(h: str | None) -> str | None:
    if not h:
        return None
    try:
        b = bytes.fromhex(h[2:])
        if len(b) >= 64:
            ln = int.from_bytes(b[32:64], "big")
            if 0 < ln <= 64 and len(b) >= 64 + ln:
                return b[64:64 + ln].decode("utf-8", "replace")
        return b.rstrip(b"\x00").decode("utf-8", "replace").strip("\x00") or None
    except Exception:
        return None


def _code_hex(rpc: str, addr: str) -> str:
    r = _rpc(rpc, "eth_getCode", [addr, "latest"])
    res = r.get("result") or ""
    return res[2:] if isinstance(res, str) and res.startswith("0x") else ""


def _has_sel(code_hex: str, sel: str) -> bool:
    return bool(code_hex) and sel.lower() in code_hex.lower()


# EIP-1967 slots (P0, spec 4.8): keccak('eip1967.proxy.implementation')-1 / ('eip1967.proxy.beacon')-1
EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
_EIP1167_RE = re.compile(r"363d3d373d3d3d363d73([0-9a-f]{40})5af43d82803e903d91602b57fd5bf3")
_MIN_CLONE_RE = re.compile(r"73([0-9a-f]{40})5af4")


def _slot_addr(rpc: str, addr: str, slot: str) -> str | None:
    r = _rpc(rpc, "eth_getStorageAt", [addr, slot, "latest"])
    v = r.get("result")
    if not isinstance(v, str) or not v.startswith("0x"):
        return None
    h = v[2:].rjust(64, "0")[-40:]
    return None if int(h, 16) == 0 else "0x" + h


def resolve_proxy_impl(rpc: str, addr: str, code_hex: str | None = None) -> dict | None:
    """Return {'implementation': 0x…, 'proxy_type': eip1967|eip1967_beacon|eip1167} or None.
    Resolved BEFORE any not-a-token verdict so a proxied ERC20 is not misread as 合约(非代币)."""
    impl = _slot_addr(rpc, addr, EIP1967_IMPL_SLOT)
    if impl:
        return {"implementation": impl, "proxy_type": "eip1967"}
    beacon = _slot_addr(rpc, addr, EIP1967_BEACON_SLOT)
    if beacon:
        r = _eth_call(rpc, beacon, "0x5c60da1b")  # implementation()
        if r and len(r) >= 66 and int(r[-40:], 16) != 0:
            return {"implementation": "0x" + r[-40:], "proxy_type": "eip1967_beacon", "beacon": beacon}
    ch = (code_hex or "").lower().removeprefix("0x")
    m = _EIP1167_RE.search(ch)
    if m:
        return {"implementation": "0x" + m.group(1), "proxy_type": "eip1167"}
    # other minimal-clone layouts (e.g. Solady LibClone 44-byte / PUSH0 variants):
    # tiny runtime code that PUSH20s a fixed address straight into DELEGATECALL
    m = _MIN_CLONE_RE.search(ch) if len(ch) <= 2 * 64 else None
    if m:
        return {"implementation": "0x" + m.group(1), "proxy_type": "minimal_clone"}
    return None


def _erc_probe(rpc: str, addr: str) -> dict:
    """Probe ERC20 / ERC721 / ERC1155 / hybrid signals. Never trusts decimals alone.
    Proxies (EIP-1967 / beacon / EIP-1167): calls go to the proxy (it delegatecalls), but the
    selector scan uses proxy code + implementation code."""
    out: dict = {}
    code_hex = _code_hex(rpc, addr)
    out["code_hex_len"] = len(code_hex) // 2
    out["proxy_checked"] = True
    try:
        px = resolve_proxy_impl(rpc, addr, code_hex)
    except Exception:
        px = None
    if px:
        impl_code = _code_hex(rpc, px["implementation"])
        if impl_code:
            out["implementation"] = px["implementation"]
            out["proxy_type"] = px["proxy_type"]
            code_hex = code_hex + impl_code

    # --- ERC165 ---
    # Reliable only if supportsInterface(0xffffffff) does NOT return true.
    # Revert / empty → treat as "no reliable ERC165" (do not skip NFT checks).
    bogus = _eth_call(rpc, addr, "0x01ffc9a7" + "ffffffff".ljust(64, "0"))
    if bogus is not None and int(bogus, 16) == 1:
        out["erc165_reliable"] = False
    elif bogus is not None and int(bogus, 16) == 0:
        out["erc165_reliable"] = True
        for iface, tag in (
            ("80ac58cd", "erc721"),
            ("d9b67a26", "erc1155"),
            ("5b5e139f", "erc721_metadata"),
        ):
            r = _eth_call(rpc, addr, "0x01ffc9a7" + iface.ljust(64, "0"))
            if r and int(r, 16) == 1:
                out[tag] = True
    else:
        # reverted / empty — no ERC165; still run behavioral NFT checks
        out["erc165_reliable"] = False

    # --- Behavioral NFT checks (work even without ERC165) ---
    # Success (non-revert returning data) on ownerOf/tokenURI/getApproved ⇒ NFT-shaped.
    owner_of = _eth_call(rpc, addr, "0x6352211e" + "1".zfill(64))
    if owner_of and len(owner_of) >= 66:
        out["owner_of_1"] = True
    token_uri = _eth_call(rpc, addr, "0xc87b56dd" + "1".zfill(64))
    if token_uri and len(token_uri) >= 66:
        out["token_uri_1"] = True
    get_approved = _eth_call(rpc, addr, "0x081812fc" + "1".zfill(64))
    if get_approved and len(get_approved) >= 66:
        out["get_approved_1"] = True

    # Bytecode NFT selectors (even if calls revert for unminted id)
    out["sel_owner_of"] = _has_sel(code_hex, SEL_OWNER_OF)
    out["sel_token_uri"] = _has_sel(code_hex, SEL_TOKEN_URI)
    out["sel_safe_tf_721"] = _has_sel(code_hex, SEL_SAFE_TF_721) or _has_sel(code_hex, SEL_SAFE_TF_721_DATA)

    # --- ERC20 shape ---
    dec = _eth_call(rpc, addr, "0x313ce567")
    if dec:
        try:
            v = int(dec[:66], 16)
            if 0 <= v <= 36:
                out["decimals"] = v
        except Exception:
            pass
    out["symbol"] = _decode_str(_eth_call(rpc, addr, "0x95d89b41"))
    out["name"] = _decode_str(_eth_call(rpc, addr, "0x06fdde03"))
    ts = _eth_call(rpc, addr, "0x18160ddd")
    out["has_total_supply"] = bool(ts)
    if ts:
        try:
            out["total_supply"] = int(ts[:66], 16)
        except Exception:
            pass

    # allowance(0,0) succeeding is a strong ERC20 signal (ERC721 approve has different sig)
    allowance = _eth_call(rpc, addr, "0xdd62ed3e" + ("0" * 128))
    out["has_allowance"] = allowance is not None

    out["sel_transfer"] = _has_sel(code_hex, SEL_TRANSFER)
    out["sel_approve"] = _has_sel(code_hex, SEL_APPROVE)
    out["sel_allowance"] = _has_sel(code_hex, SEL_ALLOWANCE)
    out["sel_decimals"] = _has_sel(code_hex, SEL_DECIMALS)

    # NFT-shaped if ERC165 says so, OR behavioral call succeeded, OR
    # (ownerOf+tokenURI selectors present AND no ERC20 transfer/allowance selectors).
    nft_iface = bool(out.get("erc721") or out.get("erc1155") or out.get("erc721_metadata"))
    nft_behavior = bool(out.get("owner_of_1") or out.get("token_uri_1") or out.get("get_approved_1"))
    nft_sel_only = (
        (out.get("sel_owner_of") and out.get("sel_token_uri"))
        and not (out.get("sel_transfer") and out.get("sel_allowance"))
    )
    out["nft_shaped"] = bool(nft_iface or nft_behavior or nft_sel_only)

    # ERC20 transfer path: need transfer+approve+allowance selectors, or working allowance()
    erc20_sels = out.get("sel_transfer") and out.get("sel_approve") and out.get("sel_allowance")
    out["erc20_shaped"] = (
        "decimals" in out
        and out.get("has_total_supply")
        and (erc20_sels or out.get("has_allowance"))
        and (out.get("symbol") or out.get("has_total_supply"))
    )
    return out


def _verify_evm(addr: str, chain_hint: str | None, snippet: str | None, source: str | None) -> dict:
    global _RPCS
    from addr_kind import classify_evm, pick_rpcs
    if _RPCS is None:
        _RPCS = pick_rpcs()
    clf = classify_evm(addr, chain_hint=chain_hint, snippet=snippet, source=source, rpcs=_RPCS, stop_on_contract=True)
    k = clf.get("kind")
    base = {"chain": clf.get("chain"), "code_bytes": clf.get("code_bytes"), "nonce": clf.get("nonce")}
    if k == "wallet":
        return {**base, "kind": "wallet", "is_token": False, "note": "eth_getCode empty / 7702 → EOA wallet"}
    if k != "contract":
        return {**base, "kind": "unknown", "is_token": False, "note": clf.get("note") or "no bytecode on probed chains"}
    rpc = next((t.get("rpc") for t in clf.get("tried") or [] if t.get("chain") == clf.get("chain") and t.get("rpc")), None)
    erc = _erc_probe(rpc, addr) if rpc else {}
    base.update({k2: erc.get(k2) for k2 in ("symbol", "name", "decimals", "implementation", "proxy_type",
                                            "proxy_checked") if erc.get(k2) is not None})

    nft_shaped = bool(erc.get("nft_shaped"))
    erc20_shaped = bool(erc.get("erc20_shaped"))

    if nft_shaped and erc20_shaped:
        # ERC404 / DN404 style — show separately, never pure 代币 CA
        which = "ERC721" if (erc.get("erc721") or erc.get("owner_of_1") or erc.get("sel_owner_of")) else "ERC1155"
        return {**base, "kind": "hybrid_404", "is_token": False,
                "note": (f"hybrid_404 ({which}+ERC20 dec={erc.get('decimals')} "
                         f"sym={erc.get('symbol')}) — not a pure token CA")}
    if nft_shaped:
        which = (
            "ERC1155" if erc.get("erc1155")
            else "ERC721" if (erc.get("erc721") or erc.get("erc721_metadata") or erc.get("owner_of_1")
                              or erc.get("sel_owner_of"))
            else "NFT"
        )
        return {**base, "kind": "nft", "is_token": False,
                "note": f"NFT contract ({which}) — not a token CA"}
    if erc20_shaped:
        px = f" via {erc.get('proxy_type')} proxy → impl {erc.get('implementation')}" if erc.get("implementation") else ""
        return {**base, "kind": "token", "is_token": True,
                "note": f"ERC20 verified: {erc.get('symbol')} dec={erc.get('decimals')}{px}"}
    # decimals alone (legacy slip path) is NOT enough without totalSupply + transfer path
    if "decimals" in erc and (erc.get("symbol") or erc.get("has_total_supply")) and not nft_shaped:
        return {**base, "kind": "contract", "is_token": False,
                "note": ("contract has decimals/symbol but missing ERC20 transfer/approve/allowance "
                         "path — not a token CA")}
    return {**base, "kind": "contract", "is_token": False,
            "note": "contract bytecode but no ERC20 decimals/symbol — not a token CA"}


def _sol_rpcs() -> list[str]:
    urls = ["https://api.mainnet-beta.solana.com"]
    try:
        k = (BASE / ".helius_api_key").read_text().strip()
        if k:
            urls.append(f"https://mainnet.helius-rpc.com/?api-key={k}")
    except Exception:
        pass
    return urls


def _verify_sol(addr: str) -> dict:
    if re.fullmatch(r"[0-9a-f]+", addr) or re.fullmatch(r"[0-9A-F]+", addr) or is_hex_hash(addr):
        return {"kind": "invalid", "is_token": False, "chain": "未知", "note": "hex string (hash / git SHA), not a Solana address"}
    if not B58.match(addr):
        return {"kind": "invalid", "is_token": False, "chain": "未知", "note": "not base58 address"}
    for url in _sol_rpcs():
        r = _rpc(url, "getAccountInfo", [addr, {"encoding": "jsonParsed"}])
        if "result" not in r:
            msg = json.dumps(r.get("error") or "").lower()
            if "invalid" in msg and ("param" in msg or "pubkey" in msg):
                return {"kind": "invalid", "is_token": False, "chain": "未知", "note": "not a valid Solana pubkey"}
            continue
        v = (r.get("result") or {}).get("value")
        if v is None:
            return {"kind": "unknown", "is_token": False, "chain": "solana", "note": "account does not exist on Solana mainnet"}
        owner = v.get("owner")
        data = v.get("data")
        ptype = data.get("parsed", {}).get("type") if isinstance(data, dict) else None
        if owner in TOKEN_PROGRAMS and ptype == "mint":
            info = data.get("parsed", {}).get("info", {})
            dec = info.get("decimals")
            supply = str(info.get("supply") or "")
            # Fungible SPL CA requires decimals > 0. decimals==0 is NFT / SFT — never token CA.
            if dec == 0:
                return {"kind": "nft", "is_token": False, "chain": "solana", "decimals": 0,
                        "note": f"SPL mint decimals=0 supply={supply} → NFT/SFT, not a fungible token CA"}
            if dec is None:
                return {"kind": "unknown", "is_token": False, "chain": "solana",
                        "note": "SPL mint missing decimals"}
            try:
                di = int(dec)
            except Exception:
                di = -1
            if di <= 0:
                return {"kind": "nft", "is_token": False, "chain": "solana", "decimals": di,
                        "note": f"SPL mint decimals={di} → not fungible token CA"}
            return {"kind": "token", "is_token": True, "chain": "solana", "decimals": di,
                    "note": f"SPL mint verified (owner {owner[:6]}…, dec={di})"}
        if owner in TOKEN_PROGRAMS:
            return {"kind": "contract", "is_token": False, "chain": "solana", "note": f"SPL {ptype or 'account'} (not a mint)"}
        if owner == SYSTEM_PROGRAM:
            return {"kind": "wallet", "is_token": False, "chain": "solana", "note": "system-owned account → wallet"}
        if v.get("executable"):
            return {"kind": "contract", "is_token": False, "chain": "solana", "note": "Solana program, not a token mint"}
        return {"kind": "contract", "is_token": False, "chain": "solana", "note": f"owned by {owner} (not token program)"}
    return {"kind": "unknown", "is_token": False, "chain": "solana", "note": "solana rpc unreachable"}


def verify_address(address: str, chain_hint: str | None = None, *, snippet: str | None = None,
                   source: str | None = None, use_cache: bool = True) -> dict:
    addr = (address or "").strip()
    key = addr.lower() if addr.lower().startswith("0x") else addr
    cache = _load_cache() if use_cache else {}
    hit = cache.get(key)
    now = time.time()
    # P0: cached EVM 'contract' verdicts from before proxy resolution are re-probed once.
    stale_proxy = bool(hit and hit.get("kind") == "contract" and key.startswith("0x")
                       and not hit.get("proxy_checked"))
    if hit and not stale_proxy and now - hit.get("_ts", 0) < TTL.get(hit.get("kind"), DEFAULT_TTL):
        return hit
    try:
        if addr.lower().startswith("0x") and len(addr) == 42 and re.fullmatch(r"0x[0-9a-fA-F]{40}", addr):
            res = _verify_evm(addr, chain_hint, snippet, source)
        elif addr.lower().startswith("0x"):
            res = {"kind": "invalid", "is_token": False, "chain": "未知", "note": "malformed 0x address"}
        else:
            res = _verify_sol(addr)
    except Exception as e:
        res = {"kind": "unknown", "is_token": False, "note": f"verify error {e}"[:160]}
    res["address"] = addr
    res["label_zh"] = LABEL.get(res.get("kind"), "未确认地址")
    res["note_zh"] = _note_zh(
        res.get("kind"), res.get("note"),
        symbol=res.get("symbol"), decimals=res.get("decimals"), chain=res.get("chain"),
    )
    if res.get("kind") == "token" and res.get("symbol") is not None and not res.get("implementation"):
        res["note"] = f"ERC20 verified: {res.get('symbol')} dec={res.get('decimals')}"
    elif res.get("kind") == "hybrid_404":
        res["note"] = res.get("note") or "hybrid_404 — not a pure token CA"
    res["_ts"] = now
    cache = _load_cache() if use_cache else cache
    cache[key] = res
    _save_cache(cache)
    return res


_HEX_HASH = re.compile(r"^(?:0x)?(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{64})$")


def is_hex_hash(address: str | None) -> bool:
    """32/64-hex strings (tx hashes, md5/sha fragments, git ids) — never an address.
    EVM addresses are exactly 0x + 40 hex. Spec 4.4: these never enter finds, log only."""
    a = (address or "").strip()
    return bool(a) and bool(_HEX_HASH.match(a))


NFT_NOTE_OK_ZH = "核验：NFT 合约（项目铸造合约）"
NFT_NOTE_NOT_EXPECTED_ZH = "NFT合约（非代币），本项目类型不以 NFT 为目标，不作为CA"
EOA_NOTE_ZH = "核验：EOA 钱包，已加入创建者监控"


def gate_for_categories(v: dict, categories, *, tapeout: bool = False) -> dict:
    """Type-aware CA gate (spec 4.8 [D]) on top of a verify_address() result.

    Returns {ok, role, note_zh, promote_to_watch, kind}.
      token (ERC20 / SPL mint)      → ok, role token (every category expects token)
      erc721/erc1155 (kind nft)     → ok, role nft ONLY if a category expects nft (NFT铸造 / GameFi);
                                      otherwise not ok (an NFT is never shown as a token CA)
      wallet (EOA)                  → not ok, role wallet, promote_to_watch
      hybrid_404 / contract / invalid / unknown → not ok
    TapeOut transistors/processor roles are decided by the caller (legacy path, untouched)."""
    from strategies import expected_roles
    k = (v or {}).get("kind") or "unknown"
    exp = expected_roles(categories)
    if k == "token":
        return {"ok": True, "role": "token", "kind": k, "promote_to_watch": False, "note_zh": None}
    if k == "nft" and not tapeout:
        if "nft" in exp:
            return {"ok": True, "role": "nft", "kind": k, "promote_to_watch": False, "note_zh": NFT_NOTE_OK_ZH}
        return {"ok": False, "role": None, "kind": k, "promote_to_watch": False, "note_zh": NFT_NOTE_NOT_EXPECTED_ZH}
    if k == "wallet":
        return {"ok": False, "role": "wallet", "kind": k, "promote_to_watch": True, "note_zh": EOA_NOTE_ZH}
    return {"ok": False, "role": None, "kind": k, "promote_to_watch": False, "note_zh": None}


def is_token_ca(address: str, chain_hint: str | None = None, **kw) -> bool:
    return bool(verify_address(address, chain_hint, **kw).get("is_token"))


def invalidate_cache(addresses: list[str] | None = None) -> int:
    """Drop cache entries so the next verify_address re-probes on-chain.
    addresses=None clears the whole cache. Returns number of keys removed."""
    cache = _load_cache()
    if not cache:
        return 0
    if addresses is None:
        n = len(cache)
        _save_cache({})
        return n
    n = 0
    for a in addresses:
        key = a.lower() if a.lower().startswith("0x") else a
        if key in cache:
            del cache[key]
            n += 1
    _save_cache(cache)
    return n


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        print(json.dumps(verify_address(a, use_cache=False), ensure_ascii=False))
