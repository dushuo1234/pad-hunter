#!/usr/bin/env python3
"""Scrape Pad Hunter project site JS for contract addresses; match vs factory deploys.

Pipeline position (routine):
  1) scan_listing_ca.py
  2) scan_onchain.py
  3) scan_js_factory_match.py   ← this script (run after onchain for freshest deploys)

For each watchlist project with a usable official site URL:
  - fetch HTML (curl, timeouts, size cap)
  - discover <script src=...> (same-origin + absolute CDN on project host / common asset hosts)
  - download JS bundles (per-file and per-project size caps)
  - extract EVM 0x40 addresses (+ cautious Solana base58 near CA context)
  - fingerprint = sha256 of sorted addresses + key script URLs
  - time-window match against onchain_scan_latest.json (+ previous) factory log addresses

Alert-facing event types (also printed on digest):
  NEW_JS_CA          — address in JS not seen in previous scan for that project
  JS_FACTORY_MATCH   — JS address equals a recent factory-deployed address
  SITE_JS_CHANGE     — fingerprint changed (esp. near a deploy window)

Writes:
  js_factory_scan_latest.json
  js_factory_scan_previous.json
Does NOT invent CAs. Does not push GitHub.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
WATCHLIST = BASE / "watchlist.json"
ONCHAIN_LATEST = BASE / "onchain_scan_latest.json"
ONCHAIN_PREV = BASE / "onchain_scan_previous.json"
LATEST = BASE / "js_factory_scan_latest.json"
PREV = BASE / "js_factory_scan_previous.json"
EVENTS_OUT = BASE / "js_factory_events.jsonl"

SH = ZoneInfo("Asia/Shanghai")
UA = "Mozilla/5.0 (compatible; PadHunterJsFactoryScan/1.0)"

# concurrency / politeness
MAX_WORKERS = 6
HTML_MAX_BYTES = 800_000
JS_MAX_BYTES = 1_500_000
JS_TOTAL_PER_PROJECT = 4_000_000
MAX_SCRIPTS_PER_PROJECT = 12
CURL_TIMEOUT = 25
FETCH_TIMEOUT = 35

# match window: site/JS change vs factory deploy block time unknown → use scan times ± hours
WINDOW_HOURS = 24

EVM_RE = re.compile(r"(?<![a-fA-F0-9])(0x[a-fA-F0-9]{40})(?![a-fA-F0-9])", re.I)
SOL_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")
SCRIPT_SRC_RE = re.compile(
    r"""<script[^>]+src\s*=\s*["']([^"']+)["']""",
    re.I,
)
# inline script bodies (capped)
INLINE_SCRIPT_RE = re.compile(r"(?is)<script(?![^>]+src\s*=)[^>]*>(.*?)</script>")
FACTORYISH_RE = re.compile(
    r"(create2|CREATE2|factory\.create|createPair|createToken|deploy\(|"
    r"getCreate2Address|cloneDeterministic|minimal.?proxy)",
    re.I,
)

CA_CONTEXT = [
    "ca", "contract", "合约", "地址", "mint", "token address", "contract address",
    "合约地址", "token:", "ca:", "address",
]
# Stronger cues for minified JS (bare "address" floods SDK false positives)
CA_CONTEXT_JS = [
    "contractaddress", "tokenaddress", "合约地址", "ca:", "ca =", "ca=",
    "mintaddress", "token_address", "contract_address",
    '"ca"', "'ca'", "primaryca", "token.ca", "contract.ca",
    # richer project-owned cues (minified + config)
    "tokencontract", "nftcontract", "nftaddress", "collectionaddress",
    "deployer", "deployeraddress", "owneraddress", "creatoraddress",
    "factoryaddress", "proxyaddress", "implementation",
    "market", "exchange", "locker", "wrapper", "tribute",
    "batchexecutor", "processor", "transistors", "editions",
    "tokenaddr", "contractaddr", "mintaddr",
]

# well-known junk / ambient tokens — never treat as project CA
EVM_DENY = {
    "0x0000000000000000000000000000000000000000",
    "0x0000000000000000000000000000000000000001",
    "0x000000000000000000000000000000000000dead",
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "0xeeeeeeee14d718c2b47d9923deab1335e144eeee",  # ParaSwap ETH sentinel
    "0x00000000000c2e074ec69a0dfb2997ba6c7d2e1e",  # ENS registry
    # WETH / common stables / routers (mainnet + common)
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # UniswapV2Router02
    "0xe592427a0aece92de3edee1f18e0157c05861564",  # UniswapV3Router
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # SwapRouter02
    "0x1111111254eeb25477b68fb85ed929f73a960582",  # 1inch
    "0x1111111254fb6c44bac0bed2854e76f90643097d",
    "0xdef1c0ded9bec7b1dcb16571147d74891413f1aa",  # 0x
    "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",  # UniV2 factory
    "0x1f98431c8ad98523631ae4a59f267346ea31f984",  # UniV3 factory
    "0x000000000004444c5dc75cb358380d2e3de08a90",  # UniV4 PoolManager (eth)
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC on Base
    "0xca11bde05977b3631167028862be2a173976ca11",  # Multicall3 (all chains)
    "0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789",  # ERC-4337 EntryPoint
    "0x0000000071727de22e5e9d8baf0edac6f37da032",  # EntryPoint v0.7
    "0x2ce910fbe7ef78274cbddf97c93ac87221eb1a57",  # OpenSea conduit (common)
    "0x00000000000000adc04c56bf30ac9d3c0aaf14dc",  # Seaport 1.5
    "0x0000000000000068f116a894984e2db1123eb395",  # Seaport 1.6
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",  # Uniswap Universal Router
    "0x6131b5fae19ea4f9d964eac0408e4408b66337b5",  # Kyber
    # OP Stack predeploys / system (Base, OP, Ink, …)
    "0x4200000000000000000000000000000000000006",  # WETH predeploy
    "0x4200000000000000000000000000000000000007",
    "0x420000000000000000000000000000000000000f",
    "0x4200000000000000000000000000000000000010",
    "0x4200000000000000000000000000000000000014",
    "0x4200000000000000000000000000000000000015",
    "0x4200000000000000000000000000000000000016",
    # Hardhat / Anvil well-known accounts (never project CAs)
    "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
    "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc",
    "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",  # ambient factory univ2_eth
    "0x8366a39cc670b4001a1121b8f6a443a643e40951",  # ambient factory univ4_pm_rh
    "0xb1c0fa0b789320044a6f623cfe5ebda9562602e3",  # ambient factory hyperswap_v3_factory
    "0x8909dc15e40173ff4699343b6eb8132c65e18ec6",  # ambient factory univ2_base
    "0x33128a8fc17869897dce68ed026d694621f6fdfd",  # ambient factory univ3_base
    "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",  # ambient factory pancake_v2_bsc
    "0xfe57a6ba1951f69ae2ed4abe23e0f095df500c04",  # ambient factory univ2_ink
    "0x640887a9ba3a9c53ed27d0f7e8246a4f933f3424",  # ambient factory univ3_ink
    "0x1f98431c8ad98523631ae4a59f267346ea31f984",  # ambient factory univ3_eth
    "0x000000000004444c5dc75cb358380d2e3de08a90",  # ambient factory univ4_pm_eth
    "0x498581ff718922c3f8e6a244956af099b2652b2b",  # ambient factory univ4_pm_base
    "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865",  # ambient factory pancake_v3_bsc
    "0x724412c00059bf7d6ee7d4a1d0d5cd4de3ea1c48",  # ambient factory hyperswap_v2_factory
}
SOL_BLOCKLIST = {
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",  # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "BPFLoader2111111111111111111111111111111111",
    "BPFLoader1111111111111111111111111111111111",
    "BPFLoaderUpgradeab1e11111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
}

SKIP_HOST_PARTS = (
    "x.com", "twitter.com", "t.co", "t.me", "telegram.me", "youtube.com",
    "discord.com", "discord.gg", "medium.com", "linktr.ee", "linktree",
    "voxels.com", "hyperliquid.xyz",  # shared platforms, not project JS CA sources
)

# allow fetching JS from these CDNs even if host != site host
CDN_HOST_ALLOW = (
    "unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "esm.sh",
    "fastly.jsdelivr.net", "ga.jspm.io", "cdn.skypack.dev",
)


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


def is_usable_site(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if "..." in u or "…" in u:
        return False
    if u.endswith(":"):
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    for part in SKIP_HOST_PARTS:
        if part in host:
            return False
    return True


def curl_fetch(url: str, max_bytes: int) -> dict:
    t0 = time.time()
    try:
        out = subprocess.run(
            [
                "curl", "-sS", "-L", "--max-time", str(CURL_TIMEOUT),
                "-A", UA,
                "--max-filesize", str(max_bytes),
                "-w", "\n__CURLMETA__%{http_code}|%{time_total}|%{url_effective}",
                url,
            ],
            capture_output=True, text=True, timeout=FETCH_TIMEOUT,
        )
        raw = out.stdout or ""
        err = (out.stderr or "").strip()[:200]
        body, meta = raw, ""
        if "__CURLMETA__" in raw:
            body, meta = raw.rsplit("__CURLMETA__", 1)
        parts = meta.strip().split("|") if meta else []
        code = parts[0] if parts else "000"
        ttot = float(parts[1]) if len(parts) > 1 and parts[1] else round(time.time() - t0, 3)
        final = parts[2] if len(parts) > 2 else url
        ok = code.isdigit() and 200 <= int(code) < 400
        return {
            "url": url,
            "final_url": final,
            "ok": ok,
            "http_code": code,
            "time_s": round(ttot, 3),
            "error": "" if ok else (err or f"http {code}"),
            "body": body if ok else "",
            "bytes": len(body.encode("utf-8", errors="ignore")) if ok else 0,
        }
    except Exception as e:
        return {
            "url": url,
            "final_url": url,
            "ok": False,
            "http_code": "000",
            "time_s": round(time.time() - t0, 3),
            "error": str(e)[:200],
            "body": "",
            "bytes": 0,
        }


def near_ca_context(text: str, start: int, end: int, window: int = 80) -> bool:
    left = text[max(0, start - window): start].lower()
    right = text[end: min(len(text), end + window)].lower()
    blob = left + " " + right
    return any(c in blob for c in CA_CONTEXT)


def snippet_around(text: str, idx: int, width: int = 60) -> str:
    start = max(0, idx - width)
    end = min(len(text), idx + width)
    return text[start:end].replace("\n", " ").strip()[:160]


def extract_evm(text: str, source: str) -> list[dict]:
    out = []
    # Large JS SDK bundles embed many unrelated addresses; require CA-ish context
    # unless the hit is from HTML / inline config (higher signal).
    require_ctx = source.startswith("js:")
    for m in EVM_RE.finditer(text or ""):
        addr = "0x" + m.group(1)[2:].lower()
        if addr in EVM_DENY:
            continue
        # drop addresses with too many leading zeros (padding / sentinels)
        if addr[2:10] == "00000000" and addr not in EVM_DENY:
            # keep only if not almost-zero
            if addr[2:].rstrip("0") == "" or addr[2:24] == "0" * 22:
                continue
        if require_ctx:
            left = text[max(0, m.start() - 100): m.start()].lower()
            right = text[m.end(): min(len(text), m.end() + 100)].lower()
            blob = left + " " + right
            # strip spaces/underscores for compact key match
            compact = blob.replace(" ", "").replace("_", "")
            if not any(k.replace(" ", "") in compact for k in CA_CONTEXT_JS):
                continue
        out.append({
            "type": "evm",
            "address": addr,
            "source": source,
            "snippet": snippet_around(text, m.start()),
        })
    seen = set()
    uniq = []
    for c in out:
        if c["address"] not in seen:
            seen.add(c["address"])
            uniq.append(c)
    # Cap per-source flood from a single JS file
    if require_ctx and len(uniq) > 25:
        uniq = uniq[:25]
    return uniq


def looks_like_js_identifier(addr: str) -> bool:
    """CamelCase / PascalCase JS names share base58 charset — reject them."""
    if re.search(r"[a-z][A-Z]", addr):
        return True
    # long all-letter tokens with no digit are almost never mints
    if addr.isalpha():
        return True
    return False


def extract_sol(text: str, source: str) -> list[dict]:
    """Cautious Solana mint extraction — JS minbundles produce huge FPs otherwise."""
    out = []
    for m in SOL_RE.finditer(text or ""):
        addr = m.group(1)
        if addr in SOL_BLOCKLIST:
            continue
        if addr.startswith("http") or "://" in addr:
            continue
        if looks_like_js_identifier(addr):
            continue
        # must include a digit (real mints almost always do)
        if not any(ch.isdigit() for ch in addr):
            continue
        # length: typical mint = 32–44; prefer 43–44 for pubkeys
        if len(addr) < 32:
            continue
        if not near_ca_context(text, m.start(), m.end()):
            continue
        out.append({
            "type": "solana",
            "address": addr,
            "source": source,
            "snippet": snippet_around(text, m.start()),
        })
    seen = set()
    uniq = []
    for c in out:
        if c["address"] not in seen:
            seen.add(c["address"])
            uniq.append(c)
    return uniq


# --- enriched extraction (2026-10-22) ---
KEYED_ADDR_RE = re.compile(
    r"""(?ix)
    (?:["']?(?:tokenAddress|contractAddress|TOKEN_ADDRESS|CA_ADDRESS|token_address|
        contract_address|mintAddress|mint_address|deployer(?:Address)?|DEPLOYER|
        ownerAddress|creatorAddress|nftAddress|collectionAddress|proxyAddress|
        factoryAddress|FACTORY|MARKET|EXCHANGE|LOCKER|WRAPPER|CONTRACT|TOKEN|
        batchExecutor|processor|transistors|editions|tribute(?:Address)?|
        implementation|beacon)
      ["']?
    )
    \s*[:=]\s*
    [`'"]?(0x[a-fA-F0-9]{40})[`'"]?
    """
)
CONST_ADDR_RE = re.compile(
    r"""(?ix)
    (?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[`'"](0x[a-fA-F0-9]{40})[`'"]
    """
)
CONST_NAME_OK = re.compile(
    r"(?i)(ca|token|contract|mint|deploy|owner|creator|factory|market|exchange|"
    r"locker|wrapper|tribute|proxy|impl|nft|collection|processor|transistor|"
    r"edition|executor|router|pair|pool)$"
)
# Minified: Bd=`0x…` / exchange:'0x…' (name optional; require nearby CA cue or CA-ish name)
ASSIGN_ADDR_RE = re.compile(
    r"""(?ix)(?:([A-Za-z_$][\w$]*)\s*=\s*)?[`'"](0x[a-fA-F0-9]{40})[`'"]"""
)
EXPLORER_ADDR_RE = re.compile(
    r"(?i)(?:etherscan\.io|basescan\.org|bscscan\.com|arbiscan\.io|polygonscan\.com|"
    r"snowtrace\.io|hyperevmscan\.io|explorer\.[a-z0-9.-]+|"
    r"robinhoodchain\.blockscout\.com|inkonchain\.com)"
    r"[^\"'\s]*/(?:address|token)/(0x[a-fA-F0-9]{40})"
)
# third-party / feed noise cues in snippet or source
NOISE_SNIPPET = re.compile(
    r"(?i)(?:coinmarketcap|coingecko|dextools|dexscreener|birdeye|geckoterminal|"
    r"token.?icon|/icons?/|cdn\.sanity|img\.|ref=0x|utm_|affiliate|"
    r"third.?party|feed.?style|trending.?token|embed)"
)
CONFIG_PATHS = (
    "/config.json", "/contracts.json", "/addresses.json", "/abi.json",
    "/status.json", "/readiness.json", "/.well-known/contracts.json",
    "/api/config", "/api/contracts", "/api/addresses", "/static/contracts.json",
    "/data/contracts.json", "/assets/contracts.json",
)
MODULEPRELOAD_RE = re.compile(
    r"""<link[^>]+rel\s*=\s*["'](?:modulepreload|preload)["'][^>]+href\s*=\s*["']([^"']+)["']""",
    re.I,
)
SOURCEMAP_RE = re.compile(r"[#@]\s*sourceMappingURL\s*=\s*(\S+)")


def classify_signal(snippet: str | None, source: str | None, extract_method: str) -> dict:
    """Tag project-owned vs third-party/feed noise for discrimination (not a ca_gate bypass)."""
    snip = snippet or ""
    src = source or ""
    tags = []
    confidence = "medium"
    note_zh = ""
    if extract_method in ("keyed", "const", "explorer", "config"):
        tags.append("project_owned_cue")
        confidence = "high"
        note_zh = "代码/配置键或浏览器链接中的项目地址"
    if NOISE_SNIPPET.search(snip) or NOISE_SNIPPET.search(src):
        tags.append("third_party_feed")
        confidence = "low"
        note_zh = "疑似第三方 feed/图标/外链嵌入，未必是本项目 CA"
    if "ref=0x" in snip.lower() or "/?ref=0x" in snip.lower():
        tags.append("referral_param")
        confidence = "low"
        note_zh = "来自推荐链接参数，多半是推荐人钱包而非 CA"
    if any(x in snip.lower() for x in (
        "gaspriceoracle", "l2crossdomain", "l1block", "disputegame", "paymasterservice",
        "standardbridge", "optimismportal", "blockcreated",
    )):
        tags.append("chain_sdk_system")
        confidence = "low"
        note_zh = "链 SDK / 桥系统合约，不是项目代币 CA"
    if extract_method == "html_loose" and confidence != "low":
        confidence = "medium"
        note_zh = note_zh or "页面 HTML 中的地址"
    if extract_method == "js_context":
        note_zh = note_zh or "JS 包中带合约上下文的地址"
    return {"signal_tags": tags, "signal_confidence": confidence, "signal_note_zh": note_zh}


def extract_evm_enriched(text: str, source: str) -> list[dict]:
    """Richer EVM extraction: keyed config, const NAME='0x', explorer links, plus base extract_evm."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(addr: str, method: str, idx: int | None = None, extra_snip: str | None = None):
        a = "0x" + addr[2:].lower()
        if a in EVM_DENY or a in seen:
            return
        if a[2:10] == "00000000" and (a[2:].rstrip("0") == "" or a[2:24] == "0" * 22):
            return
        # OP Stack predeploy namespace 0x4200…0000–0x4200…00ff
        if a.startswith("0x42000000000000000000000000000000000000"):
            return
        snip = extra_snip if extra_snip is not None else (snippet_around(text, idx) if idx is not None else "")
        sig = classify_signal(snip, source, method)
        row = {
            "type": "evm",
            "address": a,
            "source": source,
            "snippet": snip,
            "extract_method": method,
            **sig,
        }
        seen.add(a)
        out.append(row)

    # keyed assignments / object fields
    for m in KEYED_ADDR_RE.finditer(text or ""):
        add(m.group(1), "keyed", m.start())
    # const/let/var NAME = '0x…' with CA-ish name
    for m in CONST_ADDR_RE.finditer(text or ""):
        name, addr = m.group(1), m.group(2)
        if CONST_NAME_OK.search(name) or name.upper() in {
            "CA", "TOKEN", "CONTRACT", "FACTORY", "MARKET", "EXCHANGE", "LOCKER",
            "WRAPPER", "DEPLOYER", "MINT", "POOL", "PAIR", "ROUTER",
        }:
            add(addr, "const", m.start())
    # Minified assignments / string literals with CA-ish name or nearby context
    for m in ASSIGN_ADDR_RE.finditer(text or ""):
        name, addr = m.group(1) or "", m.group(2)
        if addr.lower() in seen or ("0x" + addr[2:].lower()) in seen:
            continue
        ok = bool(name and (CONST_NAME_OK.search(name) or name.upper() in {
            "CA", "TOKEN", "CONTRACT", "FACTORY", "MARKET", "EXCHANGE", "LOCKER",
            "WRAPPER", "DEPLOYER", "MINT", "POOL", "PAIR", "ROUTER",
        }))
        if not ok:
            left = (text or "")[max(0, m.start() - 160): m.start()].lower()
            right = (text or "")[m.end(): min(len(text or ""), m.end() + 120)].lower()
            blob = left + " " + right
            compact = blob.replace(" ", "").replace("_", "").replace('"', "").replace("'", "")
            # Strong cues only — NEVER bare "address" (viem/OP SDK floods)
            strong = list(CA_CONTEXT_JS) + [
                "locker", "factory", "market", "wrapper", "deployer", "tribute",
                "processor", "transistor", "edition", "exchange", "executor",
                "collection", "proxy", "impl", "beacon",
                "合约", "代币",
            ]
            ok = any(k.replace(" ", "") in compact for k in strong)
            # Drop obvious chain-SDK / bridge system labels
            if ok and any(x in blob for x in (
                "gaspriceoracle", "l1block", "crossdomain", "messagepasser", "standardbridge",
                "erc721bridge", "outputoracle", "disputegame", "optimismportal", "paymasterservice",
                "l2outputoracle", "portal:{", "blockcreated", "l2erc721", "l2tol1", "poolmanager", "permit2",
            )):
                ok = False
        if ok:
            add(addr, "const", m.start())
    # explorer /address/0x
    for m in EXPLORER_ADDR_RE.finditer(text or ""):
        add(m.group(1), "explorer", m.start())

    # base extractor (context-gated for js:)
    for c in extract_evm(text, source):
        a = c["address"]
        if a in seen:
            continue
        method = "js_context" if source.startswith("js:") else "html_loose"
        sig = classify_signal(c.get("snippet"), source, method)
        c2 = dict(c)
        c2["extract_method"] = method
        c2.update(sig)
        seen.add(a)
        out.append(c2)
    return out


def extract_sparse_js_addrs(text: str, source: str, *, max_total: int = 14, max_keep: int = 8) -> list[dict]:
    """For small same-origin project bundles: keep hex string assigns when the file
    has few 0x hits overall (SDK bundles have dozens). Medium confidence.
    """
    if not source.startswith("js:"):
        return []
    # skip obvious CDN vendor chunks
    src_l = source.lower()
    if any(x in src_l for x in ("node_modules", "vendor", "framework", "webpack", "chunk-vendors")):
        return []
    # Count only non-deny / non-zero / non-OP-predeploy hits for the sparsity gate
    real_hits = []
    for m in EVM_RE.finditer(text or ""):
        a = "0x" + m.group(1)[2:].lower()
        if a in EVM_DENY:
            continue
        if a.startswith("0x42000000000000000000000000000000000000"):
            continue
        if a[2:].rstrip("0") == "" or a[2:24] == "0" * 22:
            continue
        real_hits.append(m)
    if not real_hits or len(real_hits) > max_total:
        return []
    out = []
    seen = set()
    for m in ASSIGN_ADDR_RE.finditer(text or ""):
        name, addr = m.group(1) or "", m.group(2)
        a = "0x" + addr[2:].lower()
        if a in EVM_DENY or a in seen:
            continue
        if a.startswith("0x42000000000000000000000000000000000000"):
            continue
        # skip hardhat-looking / clearly unnamed floods without a binding name
        if not name:
            continue
        snip = snippet_around(text or "", m.start())
        blob = ((text or "")[max(0, m.start()-80): m.end()+40]).lower()
        if any(x in blob for x in (
            "gaspriceoracle", "l1block", "crossdomain", "disputegame", "paymasterservice",
            "standardbridge", "blockcreated", "optimismportal", "poolmanager",
        )):
            continue
        seen.add(a)
        sig = classify_signal(snip, source, "const_sparse")
        sig["signal_confidence"] = "medium"
        sig["signal_note_zh"] = "小型同站 JS 包中的地址赋值（中等置信）"
        out.append({
            "type": "evm", "address": a, "source": source, "snippet": snip,
            "extract_method": "const_sparse", **sig,
        })
        if len(out) >= max_keep:
            break
    return out



def discover_extra_script_urls(html: str, page_url: str) -> list[str]:
    """Also pick modulepreload / preload JS the main script regex may miss."""
    page = urlparse(page_url)
    page_host = (page.hostname or "").lower()
    urls = []
    seen = set()
    for m in MODULEPRELOAD_RE.finditer(html or ""):
        src = (m.group(1) or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = urljoin(page_url, src)
        try:
            pu = urlparse(abs_url)
        except Exception:
            continue
        if pu.scheme not in ("http", "https"):
            continue
        host = (pu.hostname or "").lower()
        path = (pu.path or "").lower()
        looks_js = path.endswith(".js") or path.endswith(".mjs") or ".js?" in (pu.path + "?" + (pu.query or ""))
        same = same_registrable_hint(host, page_host)
        if not (same and looks_js):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        urls.append(abs_url)
    return urls


def fetch_config_sidecars(page_url: str, html: str) -> list[dict]:
    """Fetch same-origin config/contracts JSON (and readiness) when present."""
    out = []
    # paths referenced in page
    paths = list(CONFIG_PATHS)
    for m in re.finditer(r"""["'](/[^"']*(?:contract|address|config|abi|readiness|status)[^"']*\.(?:json|js|abi))["']""", html or "", re.I):
        p = m.group(1)
        if p not in paths and len(paths) < 24:
            paths.append(p)
    seen = set()
    for path in paths:
        abs_url = urljoin(page_url, path)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        fr = curl_fetch(abs_url, 300_000)
        if not fr.get("ok") or fr.get("bytes", 0) < 8:
            continue
        body = fr.get("body") or ""
        # reject HTML soft-404s (same page / SPA shell)
        head = body.lstrip()[:80].lower()
        if head.startswith("<!doctype") or head.startswith("<html") or "<script" in head[:200]:
            continue
        looks_json = body.lstrip()[:1] in "{["
        has_addr = bool(EVM_RE.search(body)) or bool(KEYED_ADDR_RE.search(body))
        if not (looks_json or has_addr):
            continue
        out.append({"url": abs_url, "path": path, "bytes": fr["bytes"], "body": body})
        if len(out) >= 6:
            break
        time.sleep(0.04)
    return out


def maybe_fetch_sourcemap(js_url: str, js_body: str) -> str:
    """If a same-origin .map is advertised and small, return its text (best-effort)."""
    m = SOURCEMAP_RE.search(js_body or "")
    if not m:
        return ""
    map_ref = m.group(1).strip().strip('"').strip("'")
    if not map_ref or map_ref.startswith("data:"):
        return ""
    abs_url = urljoin(js_url, map_ref)
    try:
        pu = urlparse(abs_url)
        ju = urlparse(js_url)
    except Exception:
        return ""
    if not same_registrable_hint(pu.hostname or "", ju.hostname or ""):
        return ""
    fr = curl_fetch(abs_url, 800_000)
    if not fr.get("ok") or fr.get("bytes", 0) < 20 or fr.get("bytes", 0) > 700_000:
        return ""
    body = fr.get("body") or ""
    if body.lstrip()[:1] != "{":
        return ""
    # Prefer sourcesContent if present (actual code), else raw map text for address scan
    try:
        doc = json.loads(body)
        parts = doc.get("sourcesContent") or []
        joined = "\n".join(p for p in parts if isinstance(p, str))
        if len(joined) > 50:
            return joined[:1_500_000]
    except Exception:
        pass
    return body[:1_500_000]


def estimate_completion(html: str, js_text: str, factoryish: list[str], addrs: list[dict], config_hits: int) -> dict:
    """Heuristic completion scores for upcoming-launch UI (0..1 or high/mid labels).

    Frontend treats >=0.8 / 'high' as 完成度高. Never invents listing times.
    """
    blob = ((html or "") + "\n" + (js_text or ""))[:2_000_000].lower()
    js_score = 0.0
    contract_score = 0.0
    game_score = 0.0
    reasons = []

    # site/JS readiness
    if re.search(r"readiness|healthz|/status\.json|\"ready\"\s*:\s*true", blob):
        js_score += 0.35
        reasons.append("readiness_endpoint")
    if config_hits:
        js_score += min(0.3, 0.12 * config_hits)
        reasons.append(f"config_sidecars={config_hits}")
    if addrs:
        js_score += min(0.35, 0.08 * len(addrs))
        reasons.append(f"addrs={len(addrs)}")
    if factoryish:
        js_score += 0.15
        reasons.append("factoryish_js")
    if re.search(r"mint\s*(?:live|open|now)|minting\s+now|sale\s+live", blob):
        js_score += 0.2
        reasons.append("mint_live_copy")

    # contract code cues
    if re.search(r"\bsolidity\b|pragma solidity|ethers\.contract|wagmi|viem|web3\.eth|contractabi|\"abi\"\s*:", blob):
        contract_score += 0.35
        reasons.append("contract_sdk")
    if any((a.get("extract_method") in ("keyed", "const", "explorer", "config")) for a in addrs):
        contract_score += 0.35
        reasons.append("keyed_contract_addr")
    if factoryish:
        contract_score += 0.2
        reasons.append("create2_or_factory_code")
    if re.search(r"verified\s+contract|sourcify|etherscan\.io/address", blob):
        contract_score += 0.15
        reasons.append("verified_link")

    # game code cues
    if re.search(r"unity|unreal|godot|phaser|three\.js|babylon|pixi\.js|playcanvas|game\.js|gameplay", blob):
        game_score += 0.45
        reasons.append("game_engine")
    if re.search(r"\blevel\b|\bquest\b|\binventory\b|\bspawn\b|game\s*state", blob) and re.search(r"canvas|webgl|wasm", blob):
        game_score += 0.35
        reasons.append("game_runtime")

    def clamp(x: float) -> float:
        return round(max(0.0, min(1.0, x)), 2)

    js_score, contract_score, game_score = clamp(js_score), clamp(contract_score), clamp(game_score)

    def label(v: float) -> str:
        if v >= 0.8:
            return "high"
        if v >= 0.5:
            return "medium"
        if v >= 0.25:
            return "low"
        return "unknown"

    return {
        "js_completion": js_score,
        "js_completion_label": label(js_score),
        "contract_code_completion": contract_score,
        "contract_code_completion_label": label(contract_score),
        "game_code_completion": game_score,
        "game_code_completion_label": label(game_score),
        "completion_reasons": reasons[:12],
        "high_completion": bool(js_score >= 0.8 or contract_score >= 0.8 or game_score >= 0.8),
    }



def find_factoryish(text: str) -> list[str]:
    found = sorted({m.group(0) for m in FACTORYISH_RE.finditer(text or "")})
    return found[:12]


def same_registrable_hint(host_a: str, host_b: str) -> bool:
    """Loose same-site check: equal host or one is subdomain of the other."""
    a = (host_a or "").lower().lstrip(".")
    b = (host_b or "").lower().lstrip(".")
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith("." + b) or b.endswith("." + a)


def discover_script_urls(html: str, page_url: str) -> list[str]:
    page = urlparse(page_url)
    page_host = (page.hostname or "").lower()
    urls: list[str] = []
    seen = set()
    for m in SCRIPT_SRC_RE.finditer(html or ""):
        src = (m.group(1) or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = urljoin(page_url, src)
        try:
            pu = urlparse(abs_url)
        except Exception:
            continue
        if pu.scheme not in ("http", "https"):
            continue
        host = (pu.hostname or "").lower()
        path = (pu.path or "").lower()
        # prefer JS-looking paths; still allow extensionless chunks on same origin
        looks_js = path.endswith(".js") or path.endswith(".mjs") or ".js?" in (pu.path + "?" + (pu.query or ""))
        same = same_registrable_hint(host, page_host)
        cdn = any(host == c or host.endswith("." + c) for c in CDN_HOST_ALLOW)
        if not (same or cdn):
            continue
        if not looks_js and not same:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        urls.append(abs_url)
        if len(urls) >= MAX_SCRIPTS_PER_PROJECT:
            break
    return urls


def fingerprint(addresses: list[str], script_urls: list[str]) -> dict:
    addr_payload = json.dumps(sorted(a.lower() for a in addresses), separators=(",", ":"))
    full_payload = json.dumps(
        {"addrs": sorted(a.lower() for a in addresses), "scripts": sorted(script_urls)},
        separators=(",", ":"),
    )
    return {
        "address_fp": hashlib.sha256(addr_payload.encode()).hexdigest()[:32],
        "full_fp": hashlib.sha256(full_payload.encode()).hexdigest()[:32],
    }


def collect_factory_deploys(onchain_docs: list[dict]) -> list[dict]:
    """Flatten factory log addresses + new_deploy_hints from one or more onchain reports."""
    deploys = []
    seen = set()
    for doc in onchain_docs:
        if not doc:
            continue
        checked = doc.get("checked_at_iso") or doc.get("checked_at")
        for h in doc.get("new_deploy_hints") or []:
            for a in h.get("addresses") or []:
                al = a.lower()
                if al in EVM_DENY:
                    continue
                key = (h.get("chain"), al, (h.get("tx") or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                deploys.append({
                    "address": al if al.startswith("0x") else a,
                    "chain": h.get("chain"),
                    "factory_id": h.get("factory_id"),
                    "factory": h.get("factory"),
                    "tx": h.get("tx"),
                    "block": h.get("block"),
                    "ambient": bool(h.get("ambient")),
                    "source": "new_deploy_hints",
                    "onchain_checked_at": checked,
                })
        for f in doc.get("factories") or []:
            for log in f.get("recent_logs") or []:
                for a in log.get("addresses") or []:
                    al = a.lower()
                    if al in EVM_DENY:
                        continue
                    key = (f.get("chain"), al, (log.get("tx") or "").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    deploys.append({
                        "address": al if al.startswith("0x") else a,
                        "chain": f.get("chain"),
                        "factory_id": f.get("id"),
                        "factory": f.get("address"),
                        "tx": log.get("tx"),
                        "block": log.get("block"),
                        "ambient": f.get("id") in {"univ2_eth", "univ4_pm_rh", "hyperswap_v3_factory"},
                        "source": "factory_recent_logs",
                        "onchain_checked_at": checked,
                        "from_block": f.get("from_block"),
                        "to_block": f.get("to_block"),
                    })
    return deploys


def parse_iso_loose(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # "2026-10-20T13:43:34+08:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        # "2026-10-20 13:43:34 Asia/Shanghai"
        if "Asia/Shanghai" in s:
            core = s.replace(" Asia/Shanghai", "").strip()
            return datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH)
    except Exception:
        pass
    return None


def within_window(t_a: datetime | None, t_b: datetime | None, hours: float = WINDOW_HOURS) -> bool:
    if not t_a or not t_b:
        # if either missing, still allow address equality match but flag window unknown
        return True
    return abs((t_a - t_b).total_seconds()) <= hours * 3600


def scan_one_project(proj: dict) -> dict:
    name = proj["name"]
    sites = [u for u in (proj.get("sites") or []) if is_usable_site(u)]
    # dedupe http/https and trailing slash variants prefer https
    preferred = []
    seen_host_path = set()
    for u in sorted(sites, key=lambda x: (0 if x.startswith("https") else 1, x)):
        p = urlparse(u)
        key = ((p.hostname or "").lower(), (p.path or "/").rstrip("/") or "/")
        if key in seen_host_path:
            continue
        seen_host_path.add(key)
        preferred.append(u)

    result = {
        "name": name,
        "handle": proj.get("handle"),
        "chain": proj.get("chain"),
        "inferred_chains": proj.get("inferred_chains") or [],
        "sites_considered": preferred,
        "sites_fetched": [],
        "scripts": [],
        "addresses": [],
        "factoryish_hits": [],
        "fingerprint": None,
        "errors": [],
        "skipped_reason": None,
    }
    if not preferred:
        result["skipped_reason"] = "no_usable_site"
        return result

    all_addrs: list[dict] = []
    script_urls_ok: list[str] = []
    factoryish: list[str] = []
    total_js_bytes = 0
    js_text_parts: list[str] = []
    config_sidecars: list[dict] = []

    for site_url in preferred:
        fr = curl_fetch(site_url, HTML_MAX_BYTES)
        site_meta = {
            "url": site_url,
            "ok": fr["ok"],
            "http_code": fr["http_code"],
            "time_s": fr["time_s"],
            "error": fr["error"],
            "final_url": fr.get("final_url"),
            "bytes": fr.get("bytes", 0),
        }
        result["sites_fetched"].append(site_meta)
        if not fr["ok"]:
            result["errors"].append(f"html:{site_url}:{fr['error']}")
            continue

        html = fr["body"]
        page_final = fr.get("final_url") or site_url

        # inline scripts
        for im in INLINE_SCRIPT_RE.finditer(html):
            body = im.group(1) or ""
            if len(body) < 20:
                continue
            src_label = f"inline:{site_url}"
            all_addrs.extend(extract_evm_enriched(body, src_label))
            all_addrs.extend(extract_sol(body, src_label))
            factoryish.extend(find_factoryish(body))
            js_text_parts.append(body[:200_000])
            if len(body) > 200_000:
                break

        # also scan raw HTML for embedded 0x (config dumps) + explorer links / keyed
        all_addrs.extend(extract_evm_enriched(html, f"html:{site_url}"))
        all_addrs.extend(extract_sol(html, f"html:{site_url}"))
        js_text_parts.append(html[:120_000])

        # same-origin config / contracts / readiness JSON
        configs = fetch_config_sidecars(page_final, html)
        for cfg in configs:
            config_sidecars.append({
                "url": cfg["url"], "path": cfg["path"], "bytes": cfg["bytes"],
            })
            all_addrs.extend(extract_evm_enriched(cfg["body"], f"config:{cfg['url']}"))
            all_addrs.extend(extract_sol(cfg["body"], f"config:{cfg['url']}"))
            factoryish.extend(find_factoryish(cfg["body"]))
            js_text_parts.append(cfg["body"][:200_000])

        script_urls = discover_script_urls(html, page_final)
        for extra in discover_extra_script_urls(html, page_final):
            if extra not in script_urls and len(script_urls) < MAX_SCRIPTS_PER_PROJECT + 4:
                script_urls.append(extra)
        for su in script_urls:
            if total_js_bytes >= JS_TOTAL_PER_PROJECT:
                result["errors"].append("js_budget_exhausted")
                break
            jr = curl_fetch(su, JS_MAX_BYTES)
            sm = {
                "url": su,
                "ok": jr["ok"],
                "http_code": jr["http_code"],
                "bytes": jr.get("bytes", 0),
                "error": jr["error"],
            }
            result["scripts"].append(sm)
            if not jr["ok"]:
                continue
            total_js_bytes += jr["bytes"]
            script_urls_ok.append(su)
            body = jr["body"]
            all_addrs.extend(extract_evm_enriched(body, f"js:{su}"))
            all_addrs.extend(extract_sparse_js_addrs(body, f"js:{su}"))
            all_addrs.extend(extract_sol(body, f"js:{su}"))
            factoryish.extend(find_factoryish(body))
            js_text_parts.append(body[:300_000])
            # best-effort same-origin sourcemap (sourcesContent) — capped
            if total_js_bytes < JS_TOTAL_PER_PROJECT * 0.85:
                try:
                    smap = maybe_fetch_sourcemap(su, body)
                except Exception:
                    smap = ""
                if smap:
                    total_js_bytes += min(len(smap), 400_000)
                    all_addrs.extend(extract_evm_enriched(smap, f"sourcemap:{su}"))
                    all_addrs.extend(extract_sol(smap, f"sourcemap:{su}"))
                    factoryish.extend(find_factoryish(smap))
                    js_text_parts.append(smap[:300_000])
                    sm["sourcemap"] = True
            time.sleep(0.05)  # polite between scripts

        time.sleep(0.08)

    # dedupe addresses (prefer richer extract_method / higher signal)
    METHOD_RANK = {"keyed": 5, "const": 4, "explorer": 4, "config": 4, "const_sparse": 3, "js_context": 2, "html_loose": 1}
    best: dict[tuple, dict] = {}
    for c in all_addrs:
        k = (c["type"], (c.get("address") or "").lower())
        prev = best.get(k)
        if not prev:
            best[k] = c
            continue
        if METHOD_RANK.get(c.get("extract_method") or "", 0) > METHOD_RANK.get(prev.get("extract_method") or "", 0):
            best[k] = c
        elif (c.get("signal_confidence") == "high" and prev.get("signal_confidence") != "high"):
            best[k] = c
    uniq = list(best.values())
    result["addresses"] = uniq
    result["factoryish_hits"] = sorted(set(factoryish))[:12]
    result["config_sidecars"] = config_sidecars
    fps = fingerprint(
        [c["address"] for c in uniq],
        script_urls_ok,
    )
    result["fingerprint"] = fps["full_fp"]
    result["address_fingerprint"] = fps["address_fp"]
    result["js_bytes_total"] = total_js_bytes
    result["completion"] = estimate_completion(
        html="",
        js_text="\n".join(js_text_parts)[:1_500_000],
        factoryish=result["factoryish_hits"],
        addrs=uniq,
        config_hits=len(config_sidecars),
    )
    # flatten completion onto result for easy merge into candidates
    for ck, cv in (result["completion"] or {}).items():
        if ck != "completion_reasons":
            result[ck] = cv
    result["checked_at"] = now_iso()
    return result


def main() -> int:
    wl = load_json(WATCHLIST, None)
    if not wl or not wl.get("projects"):
        print("ERROR no watchlist at", WATCHLIST)
        return 1

    projects = wl["projects"]
    prev_report = load_json(LATEST, {})
    prev_by_name = {r["name"]: r for r in (prev_report.get("results") or [])}

    onchain_latest = load_json(ONCHAIN_LATEST, {})
    onchain_prev = load_json(ONCHAIN_PREV, {})
    deploys = collect_factory_deploys([onchain_latest, onchain_prev])
    deploy_by_addr = {}
    for d in deploys:
        al = d["address"].lower()
        deploy_by_addr.setdefault(al, []).append(d)

    # only scan projects with at least one usable site
    to_scan = []
    skipped = []
    for p in projects:
        sites = [u for u in (p.get("sites") or []) if is_usable_site(u)]
        if sites:
            to_scan.append(p)
        else:
            skipped.append({"name": p["name"], "reason": "no_usable_site"})

    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(scan_one_project, p): p["name"] for p in to_scan}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({
                    "name": name,
                    "errors": [str(e)[:200]],
                    "addresses": [],
                    "fingerprint": None,
                    "skipped_reason": "exception",
                })
            print(f"  scanned {name}", flush=True)

    results.sort(key=lambda r: r.get("name") or "")

    events: list[dict] = []
    new_js_cas = []
    matches = []
    site_changes = []

    scan_time = datetime.now(SH)

    for r in results:
        name = r["name"]
        old = prev_by_name.get(name) or {}
        old_addrs = {
            (c.get("type"), (c.get("address") or "").lower())
            for c in (old.get("addresses") or [])
        }
        old_fp = old.get("fingerprint")

        for c in r.get("addresses") or []:
            key = (c["type"], c["address"].lower())
            if key not in old_addrs:
                try:
                    from ca_gate import verify_address
                    _v = verify_address(c["address"], r.get("chain"), snippet=c.get("snippet"), source=c.get("source"))
                except Exception as _e:
                    _v = {"kind": "unknown", "is_token": False, "label_zh": "未确认地址", "note": str(_e)[:100]}
                _etype = ("NEW_JS_CA" if _v.get("is_token") else "SCANNED_WALLET" if _v.get("kind") == "wallet"
                          else "NFT_CONTRACT" if _v.get("kind") == "nft" else "UNVERIFIED_ADDR")
                ev = {
                    "kind": _v.get("kind"), "label_zh": _v.get("label_zh"), "gate_note": _v.get("note"),
                    "gate_note_zh": _v.get("note_zh") or _v.get("label_zh"),
                    "type": _etype,
                    "name": name,
                    "handle": r.get("handle"),
                    "address": c["address"],
                    "addr_type": c["type"],
                    "source": c.get("source"),
                    "snippet": c.get("snippet"),
                    "extract_method": c.get("extract_method"),
                    "signal_tags": c.get("signal_tags") or [],
                    "signal_confidence": c.get("signal_confidence"),
                    "signal_note_zh": c.get("signal_note_zh"),
                    "at": now_iso(),
                }
                events.append(ev)
                if _etype == "NEW_JS_CA":
                    new_js_cas.append(ev)

            # factory match (EVM only for now)
            if c["type"] == "evm":
                for d in deploy_by_addr.get(c["address"].lower(), []):
                    # prefer non-ambient; still record ambient with flag
                    onchain_t = parse_iso_loose(d.get("onchain_checked_at"))
                    in_win = within_window(scan_time, onchain_t)
                    ev = {
                        "type": "JS_FACTORY_MATCH",
                        "name": name,
                        "handle": r.get("handle"),
                        "address": c["address"],
                        "chain_hint": r.get("inferred_chains") or [r.get("chain")],
                        "factory_id": d.get("factory_id"),
                        "factory": d.get("factory"),
                        "deploy_chain": d.get("chain"),
                        "tx": d.get("tx"),
                        "block": d.get("block"),
                        "ambient": d.get("ambient"),
                        "js_source": c.get("source"),
                        "window_hours": WINDOW_HOURS,
                        "window_ok": in_win,
                        "evidence": {
                            "snippet": c.get("snippet"),
                            "onchain_checked_at": d.get("onchain_checked_at"),
                            "deploy_source": d.get("source"),
                        },
                        "at": now_iso(),
                    }
                    events.append(ev)
                    matches.append(ev)

        fp = r.get("fingerprint")
        addr_fp = r.get("address_fingerprint")
        old_addr_fp = old.get("address_fingerprint")
        addr_changed = bool(old_addr_fp and addr_fp and old_addr_fp != addr_fp)
        # near-deploy: any non-ambient factory deploy on overlapping chain within window
        near = []
        chains = set((r.get("inferred_chains") or []) + ([r.get("chain")] if r.get("chain") else []))
        chains_l = {str(c).lower() for c in chains if c}
        for d in deploys:
            if d.get("ambient"):
                continue
            dc = (d.get("chain") or "").lower()
            if chains_l and dc and dc not in chains_l and "unknown" not in chains_l:
                continue
            onchain_t = parse_iso_loose(d.get("onchain_checked_at"))
            if within_window(scan_time, onchain_t):
                near.append({
                    "factory_id": d.get("factory_id"),
                    "address": d.get("address"),
                    "tx": d.get("tx"),
                    "chain": d.get("chain"),
                })
        # Alert when address set changed, or scripts changed *and* a nearby deploy exists
        scripts_changed = bool(old_fp and fp and old_fp != fp)
        if addr_changed or (scripts_changed and near):
            ev = {
                "type": "SITE_JS_CHANGE",
                "name": name,
                "handle": r.get("handle"),
                "prev_fingerprint": old_fp,
                "fingerprint": fp,
                "prev_address_fingerprint": old_addr_fp,
                "address_fingerprint": addr_fp,
                "address_set_changed": addr_changed,
                "address_count": len(r.get("addresses") or []),
                "prev_address_count": len(old.get("addresses") or []),
                "near_deploys": near[:8],
                "at": now_iso(),
            }
            events.append(ev)
            site_changes.append(ev)

    # dedupe JS_FACTORY_MATCH by (name, address, tx)
    seen_m = set()
    uniq_matches = []
    for m in matches:
        k = (m["name"], m["address"].lower(), (m.get("tx") or "").lower(), m.get("factory_id"))
        if k not in seen_m:
            seen_m.add(k)
            uniq_matches.append(m)
    matches = uniq_matches
    # rebuild events list with deduped matches
    events = (
        [e for e in events if e["type"] != "JS_FACTORY_MATCH"]
        + matches
    )

    fetched_ok = sum(
        1 for r in results
        if any(s.get("ok") for s in (r.get("sites_fetched") or []))
    )
    with_addrs = sum(1 for r in results if r.get("addresses"))
    total_addrs = sum(len(r.get("addresses") or []) for r in results)
    js_ok = sum(1 for r in results for s in (r.get("scripts") or []) if s.get("ok"))
    html_fail = sum(
        1 for r in results
        if r.get("sites_considered") and not any(s.get("ok") for s in (r.get("sites_fetched") or []))
    )
    high_comp = sum(1 for r in results if r.get("high_completion"))
    keyed_addrs = sum(
        1 for r in results for a in (r.get("addresses") or [])
        if (a.get("extract_method") or "") in ("keyed", "const", "explorer", "config")
    )
    noise_addrs = sum(
        1 for r in results for a in (r.get("addresses") or [])
        if "third_party_feed" in (a.get("signal_tags") or []) or "referral_param" in (a.get("signal_tags") or [])
    )

    report = {
        "checked_at": now_label(),
        "checked_at_iso": now_iso(),
        "watchlist_count": len(projects),
        "projects_with_usable_site": len(to_scan),
        "projects_skipped_no_site": len(skipped),
        "window_hours": WINDOW_HOURS,
        "factory_deploys_indexed": len(deploys),
        "summary": {
            "sites_fetch_ok": fetched_ok,
            "sites_fetch_all_failed": html_fail,
            "projects_with_js_addresses": with_addrs,
            "total_unique_addresses": total_addrs,
            "js_files_ok": js_ok,
            "new_js_ca": len(new_js_cas),
            "js_factory_match": len(matches),
            "site_js_change": len(site_changes),
            "high_completion_projects": high_comp,
            "keyed_or_const_addresses": keyed_addrs,
            "noise_tagged_addresses": noise_addrs,
            "elapsed_s": round(time.time() - t0, 1),
        },
        "events": events,
        "new_js_cas": new_js_cas,
        "js_factory_matches": matches,
        "site_js_changes": site_changes,
        "skipped": skipped,
        "results": results,
        "gaps": [
            "Many watchlist sites are X-only or truncated URLs (…); those are skipped.",
            "Shared platforms (linktr.ee, t.me, hyperliquid app links) are skipped as non-project JS sources.",
            "Cloudflare / bot walls return empty or challenge HTML — no JS extracted.",
            "SPA bundles may hide addresses behind runtime config/API; static JS scan will miss those.",
            "Enrichment (2026-10-22): keyed/const/explorer/config extraction + same-origin config sidecars + optional sourcemaps; still no runtime-only API secrets.",
            "signal_tags third_party_feed / referral_param mark likely non-project addresses — ca_gate still required before alert.",
            "Factory match uses addresses from onchain_scan_latest/previous only (capped log window); not full chain history.",
            "Ambient Uniswap V2 PairCreated matches are flagged ambient=true — correlate before alerting.",
            "Non-EVM chains (Solana/Kaspa/Ordinals) have weak or no factory wiring; Solana extraction is context-gated.",
            "Time window uses onchain scan timestamps, not exact block timestamps (RPC eth_getBlockByNumber not required each run).",
        ],
        "how_to_run": [
            "python3 /workspace/project-monitor/scan_onchain.py",
            "python3 /workspace/project-monitor/scan_js_factory_match.py",
            "Alert on events[].type in {NEW_JS_CA, JS_FACTORY_MATCH, SITE_JS_CHANGE} vs previous.",
        ],
    }

    if LATEST.exists():
        PREV.write_text(LATEST.read_text(encoding="utf-8"), encoding="utf-8")
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # append events jsonl for parent/routine consumption
    if events:
        with EVENTS_OUT.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # digest
    for e in new_js_cas:
        print(f"NEW_JS_CA {e['name']} {e['addr_type']} {e['address']} via {e.get('source')}")
    for e in matches:
        amb = " ambient" if e.get("ambient") else ""
        print(
            f"JS_FACTORY_MATCH{amb} {e['name']} {e['address']} "
            f"factory={e.get('factory_id')} chain={e.get('deploy_chain')} tx={e.get('tx')}"
        )
    for e in site_changes:
        print(
            f"SITE_JS_CHANGE {e['name']} fp {e['prev_fingerprint'][:8]}→{e['fingerprint'][:8]} "
            f"addrs={e['prev_address_count']}→{e['address_count']} near_deploys={len(e.get('near_deploys') or [])}"
        )
    if not events:
        print("none")

    print(
        f"SUMMARY usable_sites={len(to_scan)} fetch_ok={fetched_ok} "
        f"with_addrs={with_addrs} total_addrs={total_addrs} js_ok={js_ok} "
        f"new_js_ca={len(new_js_cas)} matches={len(matches)} "
        f"site_changes={len(site_changes)} skipped={len(skipped)} "
        f"high_comp={high_comp} keyed={keyed_addrs} noise={noise_addrs} "
        f"elapsed_s={report['summary']['elapsed_s']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
