"""P1 unit tests. Run: .venv/bin/python -m unittest tests.test_p1 -v
No network: RPC / Helius calls mocked. Imports p1_staging (not live)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
for _m in ("ca_gate", "ca_confidence", "strategies", "watched_wallets", "build_ca_finds",
           "first_buy", "onchain_lock", "predict_ca"):
    sys.modules.pop(_m, None)
sys.path[:] = [str(BASE / "p1_staging"), str(BASE)] + [p for p in sys.path if p not in (
    str(BASE / "p0_staging"), str(BASE / "p1_staging"), str(BASE))]

import ca_confidence as cc  # noqa: E402
import watched_wallets as ww  # noqa: E402
import onchain_lock as ol  # noqa: E402
import predict_ca  # noqa: E402
import first_buy  # noqa: E402


class TestScoreMatchTier(unittest.TestCase):
    def test_high_wallet_plus_token_is_high_not_confirmed(self):
        c, r, p = ol.score_match(
            [{"handle": "p", "project": "P", "confidence": "high"}],
            [{"handle": "p", "project": "P", "via": "symbol:X", "explicit": True}],
        )
        self.assertEqual(c, "high")
        self.assertIn("wallet+token", r)
        self.assertNotEqual(c, "confirmed")

    def test_low_wallet_plus_token_is_low(self):
        c, r, _ = ol.score_match(
            [{"handle": "p", "project": "P", "confidence": "low"}],
            [{"handle": "p", "project": "P", "via": "symbol:X"}],
        )
        self.assertEqual(c, "low")
        self.assertIn("soft_wallet", r)

    def test_medium_wallet_alone_is_medium(self):
        c, r, _ = ol.score_match([{"handle": "p", "confidence": "medium"}], [])
        self.assertEqual(c, "medium")
        self.assertEqual(r, "soft_wallet_deployer")

    def test_name_only_never_confirmed(self):
        c, _, _ = ol.score_match(
            [], [{"handle": "p", "via": "symbol:X", "explicit": True, "ambiguous": False}]
        )
        self.assertEqual(c, "medium")
        self.assertNotEqual(c, "confirmed")


class TestHardEvidenceGate(unittest.TestCase):
    HIGH_META = {"0x" + "ab" * 20: {"confidence": "high", "source": "nft_deployer", "handle": "p"}}

    def _find(self, **kw):
        base = {
            "address": "0x" + "cd" * 20,
            "handle": "p",
            "traced_from": "0x" + "ab" * 20,
            "sources": [{"origin": "onchain_lock", "reason": "wallet_deployer",
                         "via": "factory:fourmeme_tm2_bsc:TokenCreate"}],
        }
        base.update(kw)
        return base

    def test_one_hard_evidence_is_candidate(self):
        # high deployer but NO factory via → only 1 hard evidence
        f = self._find(sources=[{"origin": "onchain_lock", "reason": "wallet_deployer", "via": "other"}])
        prov = cc.provenance(f, official_x={}, watched_wallets=set(), wallet_meta=self.HIGH_META)
        self.assertTrue(prov["wallet_factory"])
        r = cc.assess(f, verified_ok=True, ca_role="token", prov=prov, wallet_meta=self.HIGH_META)
        self.assertEqual(r["hard_evidence_count"], 1)
        self.assertEqual(r["ca_status"], "candidate")
        self.assertFalse(r["alert_ok"])

    def test_two_hard_evidences_confirmed(self):
        f = self._find()
        prov = cc.provenance(f, official_x={}, watched_wallets=set(), wallet_meta=self.HIGH_META)
        r = cc.assess(f, verified_ok=True, ca_role="token", prov=prov, wallet_meta=self.HIGH_META)
        self.assertGreaterEqual(r["hard_evidence_count"], 2)
        self.assertEqual(r["ca_status"], "confirmed")
        self.assertTrue(r["alert_ok"])

    def test_official_x_alone_still_confirmed(self):
        f = {"address": "0x" + "cd" * 20, "handle": "p", "sources": [
            {"origin": "x_official", "source": "x:@p", "post_url": "https://x.com/p/status/1"}]}
        ox = {("0x" + "cd" * 20).lower(): {"post_url": "https://x.com/p/status/1"}}
        prov = cc.provenance(f, official_x=ox, watched_wallets=set())
        r = cc.assess(f, verified_ok=True, ca_role="token", prov=prov)
        self.assertEqual(r["ca_status"], "confirmed")
        self.assertTrue(r["official_x_confirmed"])

    def test_low_wallet_plus_name_is_candidate_not_confirmed(self):
        low = {"0x" + "ab" * 20: {"confidence": "low", "source": "site", "handle": "p"}}
        f = self._find(sources=[{"origin": "onchain_lock", "reason": "wallet+token:symbol:X",
                                 "via": "factory:x:TokenCreate"}])
        prov = cc.provenance(f, official_x={}, watched_wallets=set(), wallet_meta=low)
        self.assertFalse(prov["wallet_factory"])
        self.assertTrue(prov["soft_wallet"])
        r = cc.assess(f, verified_ok=True, ca_role="token", prov=prov, wallet_meta=low)
        self.assertEqual(r["ca_status"], "candidate")
        self.assertEqual(r["hard_evidence_count"], 0)

    def test_name_only_suspected_copycat(self):
        f = {"address": "0x" + "cd" * 20, "handle": "p", "traced_from": None,
             "sources": [{"origin": "onchain_lock", "reason": "symbol:X", "via": "factory:x:Y"}]}
        prov = cc.provenance(f, official_x={}, watched_wallets=set())
        self.assertTrue(prov["name_only"])
        r = cc.assess(f, verified_ok=True, ca_role="token", prov=prov)
        self.assertEqual(r["ca_status"], "suspected_copycat")

    def test_reason_wallet_substring_alone_not_wallet_factory(self):
        """Weak-path fix: backtest_inject 'wallet+token:...' without real watched deployer."""
        f = {"address": "0x" + "cd" * 20, "handle": "p",
             "traced_from": "0x" + "00" * 20,
             "sources": [{"origin": "onchain_lock", "reason": "wallet+token:symbol:SIEGE",
                          "via": "backtest_inject"}]}
        prov = cc.provenance(f, official_x={}, watched_wallets=set(), wallet_meta={})
        self.assertFalse(prov["wallet_factory"])
        self.assertTrue(prov["name_only"])

    def test_nft_still_needs_official_x(self):
        f = self._find()
        prov = cc.provenance(f, official_x={}, watched_wallets=set(), wallet_meta=self.HIGH_META)
        r = cc.assess(f, verified_ok=True, ca_role="nft", prov=prov, wallet_meta=self.HIGH_META)
        self.assertEqual(r["ca_status"], "candidate")


class TestConflict(unittest.TestCase):
    def test_two_cas_marked_conflict_and_demoted(self):
        rows = [
            {"handle": "p", "project": "P", "address": "0x" + "11" * 20, "ca_role": "token",
             "ca_status": "confirmed", "hard_evidence_count": 2, "official_x_confirmed": False,
             "alert_ok": True},
            {"handle": "p", "project": "P", "address": "0x" + "22" * 20, "ca_role": "token",
             "ca_status": "candidate", "hard_evidence_count": 1, "official_x_confirmed": False,
             "alert_ok": False},
        ]
        cc.mark_conflicts(rows)
        self.assertTrue(all(r["conflict"] for r in rows))
        self.assertEqual(rows[0]["ca_status"], "candidate")
        self.assertFalse(rows[0]["alert_ok"])
        self.assertEqual(set(rows[0]["conflict_cas"]),
                         {("0x" + "11" * 20).lower(), ("0x" + "22" * 20).lower()})

    def test_different_roles_do_not_conflict(self):
        rows = [
            {"handle": "p", "address": "0x" + "11" * 20, "ca_status": "confirmed",
             "ca_role": "token", "hard_evidence_count": 2, "official_x_confirmed": False, "alert_ok": True},
            {"handle": "p", "address": "0x" + "22" * 20, "ca_status": "confirmed",
             "ca_role": "processor", "hard_evidence_count": 2, "official_x_confirmed": False, "alert_ok": True},
        ]
        cc.mark_conflicts(rows)
        self.assertFalse(rows[0].get("conflict"))
        self.assertEqual(rows[0]["ca_status"], "confirmed")
        self.assertEqual(rows[1]["ca_status"], "confirmed")

    def test_official_x_confirmed_not_demoted_on_conflict(self):
        rows = [
            {"handle": "p", "address": "0x" + "11" * 20, "ca_role": "token", "ca_status": "confirmed",
             "hard_evidence_count": 1, "official_x_confirmed": True, "alert_ok": True},
            {"handle": "p", "address": "0x" + "22" * 20, "ca_role": "token", "ca_status": "candidate",
             "hard_evidence_count": 1, "official_x_confirmed": False, "alert_ok": False},
        ]
        cc.mark_conflicts(rows)
        self.assertTrue(rows[0]["conflict"])
        self.assertEqual(rows[0]["ca_status"], "confirmed")  # X-confirmed kept


class TestWatchedMeta(unittest.TestCase):
    def test_index_prefers_higher_confidence(self):
        rows = [
            ww.make_row(handle="p", chain="base", wallet="0x" + "ab" * 20, source="site",
                        confidence="low", evidence_url=None, added_at="2026-10-24T10:00:00+08:00"),
            ww.make_row(handle="p", chain="base", wallet="0x" + "AB" * 20, source="nft_deployer",
                        confidence="high", evidence_url=None, added_at="2026-10-24T11:00:00+08:00"),
        ]
        idx = ww.index_by_address(rows)
        self.assertEqual(idx["0x" + "ab" * 20]["confidence"], "high")


class TestPredictCa(unittest.TestCase):
    def test_create_deterministic(self):
        a1 = predict_ca.predict_create("0x" + "00" * 20, 0)
        a2 = predict_ca.predict_create("0x" + "00" * 20, 0)
        self.assertEqual(a1, a2)
        self.assertTrue(a1.startswith("0x") and len(a1) == 42)

    def test_create2_vector(self):
        # salt/init_code_hash all zeros
        a = predict_ca.predict_create2("0x" + "00" * 20, "00" * 32, "00" * 32)
        self.assertTrue(a.startswith("0x") and len(a) == 42)

    def test_next_nonces(self):
        rows = predict_ca.predict_next_nonces("0x" + "11" * 20, 3, count=3)
        self.assertEqual([r["nonce"] for r in rows], [3, 4, 5])


class TestSolanaFirstBuy(unittest.TestCase):
    def test_dexscreener_path(self):
        pairs = [{"chainId": "solana", "pairCreatedAt": 1_700_000_000_000}]
        with mock.patch.object(first_buy, "_dexscreener", return_value=pairs), \
                mock.patch.object(first_buy, "_helius_key", return_value=None):
            r = first_buy._derive_solana("So11111111111111111111111111111111111111112")
        self.assertIsNotNone(r.get("first_external_buy_time"))
        self.assertEqual(r.get("method"), "dexscreener_pair_created_solana")
        # no key material in result
        blob = json.dumps(r)
        self.assertNotIn("api-key", blob)
        self.assertNotIn("HELIUS_API_KEY", blob)

    def test_non_evm_routes_to_solana(self):
        with mock.patch.object(first_buy, "_derive_solana",
                               return_value={"first_buy_time": None, "reason": "x"}) as m:
            r = first_buy._derive("SomeSolMint1111111111111111111111111111111", "solana")
        m.assert_called_once()
        self.assertEqual(r.get("reason"), "x")


class TestReplayP1Invariants(unittest.TestCase):
    P = BASE / "replay" / "ca_finds_p1.json"

    @classmethod
    def setUpClass(cls):
        if not cls.P.exists():
            raise unittest.SkipTest("p1 replay not produced yet")
        cls.doc = json.loads(cls.P.read_text(encoding="utf-8"))

    def test_schema(self):
        self.assertEqual(self.doc["schema_version"], 2)

    def test_x_confirmed_still_present(self):
        rows = self.doc["finds"] + self.doc.get("launched_history", [])
        x_conf = [f for f in rows if f.get("ca_status") == "confirmed" and f.get("official_x_confirmed")]
        self.assertGreaterEqual(len(x_conf), 2)

    def test_evidence_fields_on_confirmed_non_x(self):
        for f in self.doc["finds"] + self.doc.get("launched_history", []):
            if f.get("ca_status") == "confirmed" and not f.get("official_x_confirmed"):
                self.assertGreaterEqual(f.get("hard_evidence_count") or 0, 2, f.get("handle"))
                self.assertFalse(f.get("conflict"))


if __name__ == "__main__":
    unittest.main()
