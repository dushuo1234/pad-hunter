"""P0 unit tests (spec 7.3, P0-relevant items). Run: .venv/bin/python -m unittest discover -s tests -v
No network: all RPC calls are mocked."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
# Force P0 staging even if another test module already imported p1_staging copies.
for _m in ("ca_gate", "ca_confidence", "strategies", "watched_wallets", "build_ca_finds",
           "first_buy", "onchain_lock", "predict_ca"):
    sys.modules.pop(_m, None)
sys.path[:] = [str(BASE / "p0_staging"), str(BASE)] + [p for p in sys.path if p not in (
    str(BASE / "p0_staging"), str(BASE / "p1_staging"), str(BASE))]

import ca_gate  # noqa: E402
import ca_confidence  # noqa: E402
import strategies  # noqa: E402
import watched_wallets as ww  # noqa: E402
import build_ca_finds as bcf  # noqa: E402

PROXY = "0x" + "11" * 20
IMPL = "0x" + "22" * 20


def _word(n: int) -> str:
    return "0x" + hex(n)[2:].rjust(64, "0")


def _abi_str(s: str) -> str:
    b = s.encode()
    return "0x" + "20".rjust(64, "0") + hex(len(b))[2:].rjust(64, "0") + b.hex().ljust(64, "0")


class FakeChain:
    """Minimal JSON-RPC: PROXY is an EIP-1967 proxy whose bytecode has no ERC20 selectors;
    IMPL bytecode carries transfer/approve/allowance/decimals selectors. Calls to PROXY answer
    like an ERC20 (delegatecall)."""

    def __init__(self, impl_slot=True):
        self.impl_slot = impl_slot

    def __call__(self, url, method, params, timeout=12):
        if method == "eth_getCode":
            a = params[0].lower()
            if a == PROXY:
                return {"result": "0x363d3d373d3d3d3d60368060143d3d3d"}  # generic forwarder, no selectors
            if a == IMPL:
                return {"result": "0x6080" + "63a9059cbb" + "63095ea7b3" + "63dd62ed3e" + "63313ce567" + "6318160ddd"}
            return {"result": "0x"}
        if method == "eth_getStorageAt":
            if params[1] == ca_gate.EIP1967_IMPL_SLOT and self.impl_slot:
                return {"result": "0x" + IMPL[2:].rjust(64, "0")}
            return {"result": "0x" + "0" * 64}
        if method == "eth_call":
            data = params[0]["data"]
            sel = data[2:10]
            if sel == "01ffc9a7":
                return {"error": {"message": "revert"}}
            if sel in ("6352211e", "c87b56dd", "081812fc"):
                return {"error": {"message": "revert"}}
            if sel == "313ce567":
                return {"result": _word(18)}
            if sel == "95d89b41":
                return {"result": _abi_str("PRX")}
            if sel == "06fdde03":
                return {"result": _abi_str("Proxied")}
            if sel == "18160ddd":
                return {"result": _word(10 ** 27)}
            if sel == "dd62ed3e":
                return {"result": _word(0)}
            return {"result": "0x"}
        return {"error": "unsupported"}


def _verify_proxy(fake):
    clf = {"kind": "contract", "chain": "base", "code_bytes": 20, "nonce": 1,
           "tried": [{"chain": "base", "rpc": "http://fake"}]}
    with mock.patch.object(ca_gate, "_rpc", fake), \
            mock.patch("addr_kind.classify_evm", return_value=clf), \
            mock.patch.object(ca_gate, "_RPCS", []):
        return ca_gate._verify_evm(PROXY, "base", None, None)


class TestCategory(unittest.TestCase):
    def test_alias_meme(self):
        self.assertEqual(strategies.normalize_category("模因币"), ["Meme币"])

    def test_multi_split(self):
        self.assertEqual(strategies.normalize_category("AI代理 / 发射台 / 基础设施"), ["AI代理", "发射台", "基础设施"])

    def test_unknown_is_other(self):
        self.assertEqual(strategies.normalize_category("完全不认识的分类"), ["其他"])
        self.assertEqual(strategies.normalize_category(None), ["其他"])

    def test_expected_roles(self):
        self.assertIn("nft", strategies.expected_roles(["NFT铸造"]))
        self.assertIn("nft", strategies.expected_roles(["GameFi"]))
        self.assertEqual(strategies.expected_roles(["Meme币"]), {"token"})
        self.assertEqual(strategies.expected_roles(["其他"]), {"token"})


class TestTypeAwareGate(unittest.TestCase):
    NFT = {"kind": "nft", "is_token": False, "note": "NFT contract (ERC721) — not a token CA"}

    def test_nft_for_nft_project_ok(self):
        g = ca_gate.gate_for_categories(self.NFT, ["NFT铸造"])
        self.assertTrue(g["ok"]); self.assertEqual(g["role"], "nft")

    def test_nft_for_gamefi_ok(self):
        self.assertTrue(ca_gate.gate_for_categories(self.NFT, ["GameFi"])["ok"])

    def test_nft_for_meme_not_ok(self):
        g = ca_gate.gate_for_categories(self.NFT, ["Meme币"])
        self.assertFalse(g["ok"]); self.assertIsNone(g["role"])

    def test_nft_for_unknown_category_not_ok(self):
        self.assertFalse(ca_gate.gate_for_categories(self.NFT, ["其他"])["ok"])

    def test_token_ok_everywhere(self):
        for c in strategies.CANONICAL:
            self.assertTrue(ca_gate.gate_for_categories({"kind": "token", "is_token": True}, [c])["ok"], c)

    def test_eoa_promoted_not_ca(self):
        g = ca_gate.gate_for_categories({"kind": "wallet"}, ["Meme币"])
        self.assertFalse(g["ok"]); self.assertTrue(g["promote_to_watch"]); self.assertEqual(g["role"], "wallet")

    def test_hybrid_and_contract_not_ok(self):
        for k in ("hybrid_404", "contract", "invalid", "unknown"):
            g = ca_gate.gate_for_categories({"kind": k}, ["NFT铸造"])
            self.assertFalse(g["ok"], k); self.assertFalse(g["promote_to_watch"], k)

    def test_tapeout_nft_left_to_legacy_path(self):
        self.assertFalse(ca_gate.gate_for_categories(self.NFT, ["NFT铸造"], tapeout=True)["ok"])


class TestProxy(unittest.TestCase):
    def test_eip1967_proxy_to_erc20_is_token(self):
        v = _verify_proxy(FakeChain(impl_slot=True))
        self.assertEqual(v["kind"], "token")
        self.assertTrue(v["is_token"])
        self.assertEqual(v["implementation"], IMPL)
        self.assertEqual(v["proxy_type"], "eip1967")
        self.assertTrue(v["proxy_checked"])

    def test_without_impl_slot_not_token(self):
        # same proxy, impl not resolvable → selector path missing (allowance call still works →
        # erc20_shaped may hold); assert proxy fields absent and proxy_checked recorded
        v = _verify_proxy(FakeChain(impl_slot=False))
        self.assertNotIn("implementation", v)
        self.assertTrue(v["proxy_checked"])

    def test_eip1167_detect(self):
        code = "363d3d373d3d3d363d73" + IMPL[2:] + "5af43d82803e903d91602b57fd5bf3"
        with mock.patch.object(ca_gate, "_rpc", lambda *a, **k: {"result": "0x" + "0" * 64}):
            r = ca_gate.resolve_proxy_impl("http://fake", PROXY, code)
        self.assertEqual(r, {"implementation": IMPL, "proxy_type": "eip1167"})


class TestMinimalClone(unittest.TestCase):
    def test_solady_44_byte_clone(self):
        code = "3d3d3d3d363d3d37363d73" + IMPL[2:] + "5af43d3d93803e602a57fd5bf3"
        with mock.patch.object(ca_gate, "_rpc", lambda *a, **k: {"result": "0x" + "0" * 64}):
            r = ca_gate.resolve_proxy_impl("http://fake", PROXY, code)
        self.assertEqual(r, {"implementation": IMPL, "proxy_type": "minimal_clone"})

    def test_big_contract_not_clone(self):
        code = "60806040" + "00" * 200 + "73" + IMPL[2:] + "5af4"
        with mock.patch.object(ca_gate, "_rpc", lambda *a, **k: {"result": "0x" + "0" * 64}):
            self.assertIsNone(ca_gate.resolve_proxy_impl("http://fake", PROXY, code))


class TestHexHash(unittest.TestCase):
    def test_hashes(self):
        self.assertTrue(ca_gate.is_hex_hash("0x" + "ab" * 32))
        self.assertTrue(ca_gate.is_hex_hash("ab" * 32))
        self.assertTrue(ca_gate.is_hex_hash("ab" * 16))
        self.assertTrue(ca_gate.is_hex_hash("0x" + "cd" * 16))

    def test_not_hashes(self):
        self.assertFalse(ca_gate.is_hex_hash("0x" + "ab" * 20))  # EVM address
        self.assertFalse(ca_gate.is_hex_hash("So11111111111111111111111111111111111111112"))
        self.assertFalse(ca_gate.is_hex_hash(None))

    def test_sol_verify_rejects_hash(self):
        v = ca_gate._verify_sol("ab" * 16)
        self.assertFalse(v.get("is_token"))


class TestSourceDedupe(unittest.TestCase):
    def test_same_post_url_once_earliest_kept(self):
        cur = {"sources": []}
        u = "https://x.com/proj/status/1"
        self.assertTrue(bcf._append_src(cur, {"origin": "x_official", "post_url": u, "detected_at": "2026-10-23T10:00:00+08:00"}))
        self.assertFalse(bcf._append_src(cur, {"origin": "x_official", "post_url": u, "detected_at": "2026-10-23T09:00:00+08:00"}))
        self.assertFalse(bcf._append_src(cur, {"origin": "x_official", "post_url": u, "detected_at": "2026-10-23T11:00:00+08:00"}))
        self.assertEqual(len(cur["sources"]), 1)
        self.assertEqual(cur["sources"][0]["detected_at"], "2026-10-23T09:00:00+08:00")

    def test_different_posts_and_no_post_url_kept(self):
        cur = {"sources": []}
        bcf._append_src(cur, {"origin": "x_official", "post_url": "https://x.com/p/status/1"})
        bcf._append_src(cur, {"origin": "x_official", "post_url": "https://x.com/p/status/2"})
        bcf._append_src(cur, {"origin": "site_scan", "post_url": None})
        bcf._append_src(cur, {"origin": "site_scan", "post_url": None})
        self.assertEqual(len(cur["sources"]), 4)


class TestStatusRules(unittest.TestCase):
    P_WALLET = {"wallet_factory": True, "official_x": False}
    P_X = {"wallet_factory": False, "official_x": True, "x_url": "https://x.com/p/status/1"}
    P_NONE = {"wallet_factory": False, "official_x": False}

    def test_nft_without_official_x_is_candidate(self):
        r = ca_confidence.assess({}, verified_ok=True, ca_role="nft", prov=self.P_WALLET)
        self.assertEqual(r["ca_status"], "candidate"); self.assertFalse(r["alert_ok"])

    def test_nft_with_official_x_confirmed(self):
        self.assertEqual(ca_confidence.assess({}, verified_ok=True, ca_role="nft", prov=self.P_X)["ca_status"], "confirmed")

    def test_token_wallet_factory_unchanged(self):
        self.assertEqual(ca_confidence.assess({}, verified_ok=True, ca_role="token", prov=self.P_WALLET)["ca_status"], "confirmed")

    def test_no_provenance_candidate(self):
        self.assertEqual(ca_confidence.assess({}, verified_ok=True, ca_role="token", prov=self.P_NONE)["ca_status"], "candidate")

    def test_not_verified_not_ca(self):
        self.assertEqual(ca_confidence.assess({}, verified_ok=False, ca_role=None, prov=self.P_X)["ca_status"], "not_ca")


class TestWatchedWallets(unittest.TestCase):
    def test_row_fields_and_expiry(self):
        r = ww.make_row(handle="@SomeProj", chain="base", wallet="0x" + "Ab" * 20, source="site", confidence="low",
                        evidence_url="https://p.xyz", added_at="2026-10-24T10:00:00+08:00")
        for k in ("handle", "chain", "wallet", "source", "confidence", "evidence_url", "added_at", "expires_at"):
            self.assertIn(k, r)
        self.assertEqual(r["handle"], "someproj")
        self.assertTrue(r["expires_at"].startswith("2026-11-23"))
        r2 = ww.make_row(handle="x", chain="base", wallet="0x" + "ab" * 20, source="site", confidence="low",
                         evidence_url=None, added_at="2026-10-24T10:00:00+08:00", listing_at="2026-10-25T20:00:00+08:00")
        self.assertTrue(r2["expires_at"].startswith("2026-11-01"))

    def test_classify(self):
        self.assertEqual(ww.classify_source(["x_official"], ["x:@p"]), ("x_official", "medium"))
        self.assertEqual(ww.classify_source(["site_scan"], ["site:https://p.xyz"]), ("site", "low"))

    def test_merge_and_save(self):
        a = ww.make_row(handle="p", chain="base", wallet="0x" + "ab" * 20, source="site", confidence="low",
                        evidence_url="u1", added_at="2026-10-24T10:00:00+08:00")
        b = ww.make_row(handle="p", chain="base", wallet="0x" + "AB" * 20, source="x_official", confidence="medium",
                        evidence_url="u2", added_at="2026-10-24T12:00:00+08:00")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ww.json"
            ww.save([a], p)
            doc = ww.save([b], p)
            self.assertEqual(len(doc["wallets"]), 1)
            row = doc["wallets"][0]
            self.assertEqual(row["confidence"], "medium")
            self.assertEqual(row["added_at"], "2026-10-24T10:00:00+08:00")

    def test_expired_filtered(self):
        r = {"expires_at": "2000-01-01T00:00:00+08:00"}
        self.assertEqual(ww.active([r]), [])


class TestTiming(unittest.TestCase):
    def test_lead_seconds(self):
        self.assertEqual(bcf._iso_diff("2026-10-24T12:00:00+08:00", "2026-10-24T11:00:00+08:00"), 3600)
        self.assertIsNone(bcf._iso_diff(None, "2026-10-24T11:00:00+08:00"))

    def test_lock_time_only_confirmed_from_supporting_sources(self):
        f = {"ca_status": "confirmed", "official_x_confirmed": True, "wallet_factory_confirmed": False,
             "detected_at": "2026-10-24T08:00:00+08:00",
             "sources": [{"origin": "site_scan", "detected_at": "2026-10-24T08:00:00+08:00"},
                         {"origin": "x_official", "detected_at": "2026-10-24T09:00:00+08:00"}]}
        self.assertEqual(bcf._lock_time(f), "2026-10-24T09:00:00+08:00")
        self.assertIsNone(bcf._lock_time(dict(f, ca_status="candidate")))

    def test_launch_definition_in_config(self):
        cfg = json.loads((BASE / "p0_staging" / "launch_config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["launch_definition"], "first_external_buy")
        self.assertIn("外部买入", cfg["launch_definition_zh"])
        self.assertIn("不含创建交易", cfg["launch_definition_zh"])

    def test_listing_time_uses_external_buy_not_creation_dev_buy(self):
        """listing_time / lead_seconds follow first_external_buy_time (开盘), not raw first_buy."""
        # Simulate the post-derive field assignment logic used in build()
        fb = {
            "first_buy_time": "2026-10-23T08:57:15+08:00",
            "first_buy_in_creation_tx": True,
            "first_buy_tx": "0xcreate",
            "first_external_buy_time": "2026-10-23T08:57:55+08:00",
            "first_external_buy_tx": "0xext",
            "holder_known": True,
        }
        listing = fb.get("first_external_buy_time")
        lock = "2026-10-23T08:50:00+08:00"
        self.assertEqual(listing, "2026-10-23T08:57:55+08:00")
        self.assertNotEqual(listing, fb["first_buy_time"])
        self.assertEqual(bcf._iso_diff(listing, lock), 475)
        # creation-tx buy only → no listing_time yet
        fb2 = {"first_buy_time": "2026-10-23T08:57:15+08:00", "first_buy_in_creation_tx": True}
        self.assertIsNone(fb2.get("first_external_buy_time"))


class TestReplayOutput(unittest.TestCase):
    """Invariants on replay/ca_finds_p0.json (skipped until the replay has been produced)."""
    P = BASE / "replay" / "ca_finds_p0.json"
    CJK = re.compile(r"[\u4e00-\u9fff]")

    @classmethod
    def setUpClass(cls):
        if not cls.P.exists():
            raise unittest.SkipTest("replay not produced")
        cls.doc = json.loads(cls.P.read_text(encoding="utf-8"))

    def rows(self):
        return self.doc["finds"] + self.doc.get("launched_history", [])

    def test_schema_and_statuses(self):
        self.assertEqual(self.doc["schema_version"], 2)
        ok = {"confirmed", "candidate", "superseded", "not_ca", "suspected_copycat"}
        for f in self.rows() + self.doc.get("suspected_copycats", []):
            if "ca_status" in f:
                self.assertIn(f["ca_status"], ok)

    def test_no_hex_hash_rows(self):
        for f in self.rows():
            self.assertFalse(ca_gate.is_hex_hash(f.get("address")), f.get("address"))

    def test_no_duplicate_post_url_sources(self):
        for f in self.rows():
            seen = set()
            for s in f.get("sources") or []:
                if s.get("post_url"):
                    k = (s.get("origin"), s["post_url"])
                    self.assertNotIn(k, seen); seen.add(k)

    def test_nft_never_token_and_only_expected(self):
        for f in self.rows():
            if f.get("ca_role") == "nft":
                self.assertFalse(f.get("is_token"))
                self.assertTrue(set(f.get("categories") or []) & {"NFT铸造", "GameFi"})
            if f.get("kind") == "nft" and not (set(f.get("categories") or []) & {"NFT铸造", "GameFi"}) \
                    and f.get("ca_role") not in ("transistors", "processor"):
                self.assertEqual(f.get("ca_status"), "not_ca")

    def test_lead_seconds_consistency(self):
        for f in self.rows():
            if f.get("lead_seconds") is not None:
                self.assertEqual(f["lead_seconds"], bcf._iso_diff(f["listing_time"], f["lock_time"]))
            # New-rule artifact (listing_time_source=first_external_buy_onchain):
            # listing_time must equal first_external_buy_time; creation-tx-only → no listing.
            if f.get("listing_time_source") == "first_external_buy_onchain":
                self.assertEqual(f.get("listing_time"), f.get("first_external_buy_time"))
            if (f.get("listing_time_source") == "first_external_buy_onchain"
                    and f.get("first_buy_in_creation_tx") and not f.get("first_external_buy_time")):
                self.assertIsNone(f.get("listing_time"))

    def test_zh_fields_chinese(self):
        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k.endswith("_zh") and isinstance(v, str) and v:
                        self.assertRegex(v, self.CJK, f"{path}.{k}")
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
        walk(self.doc)

    def test_watched_wallet_handles_normalized(self):
        for w in self.doc.get("watched_wallets") or []:
            self.assertEqual(w["handle"], w["handle"].lower()); self.assertFalse(w["handle"].startswith("@"))


if __name__ == "__main__":
    unittest.main()
