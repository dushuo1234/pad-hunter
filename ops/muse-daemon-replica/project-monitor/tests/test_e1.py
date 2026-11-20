#!/usr/bin/env python3
"""E1 funding-link + veto tests (spec v2 §12.3 / §12.4). No network."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

BASE = Path("/workspace/project-monitor")
_drop = {str(BASE / "p0_staging"), str(BASE / "p1_staging"), str(BASE / "e1_staging"),
         str(BASE / "e1_hist_staging"), str(BASE)}
sys.path[:] = [str(BASE / "e1_staging"), str(BASE)] + [p for p in sys.path if p not in _drop]
for m in list(sys.modules):
    if m in ("ca_confidence", "funding_links", "build_ca_finds", "ca_gate", "first_buy",
             "watched_wallets", "onchain_lock") or m.startswith("ca_confidence"):
        sys.modules.pop(m, None)

import funding_links as fl  # noqa: E402
import ca_confidence as cc  # noqa: E402


TEAM = "0x1111111111111111111111111111111111111111"
DEP = "0x2222222222222222222222222222222222222222"
MID = "0x3333333333333333333333333333333333333333"
GRAPH = "0x4444444444444444444444444444444444444444"
BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"  # in known_public_funders
TORNADO = "0x722122df12d4e14e13ac3b6895a86e84145b6967"
TX = "0xabc1111111111111111111111111111111111111111111111111111111111111"
DEP_AT = "2026-10-24T12:00:00+08:00"
FUND_AT = "2026-10-20T10:00:00+08:00"  # within 7d
FUND_OLD = "2026-06-01T10:00:00+08:00"  # >90d


class TestFundingScore(unittest.TestCase):
    def setUp(self):
        self.pub = fl.load_public_funders()

    def test_direct_high_is_hard(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx=TX, amount="0.5",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=self.pub, asset="BNB")
        self.assertEqual(link["kind"], "direct")
        self.assertEqual(link["confidence"], "high")
        self.assertEqual(link["excluded_reason"], "")
        self.assertTrue(fl.is_hard_evidence(link))
        self.assertIn("资金关联", fl.basis_zh(link))

    def test_direct_medium_is_hard_but_needs_peer(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx=TX, amount="0.1",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="medium", public=self.pub)
        self.assertEqual(link["confidence"], "medium")
        self.assertTrue(fl.is_hard_evidence(link))

    def test_shared_non_public_is_hard(self):
        link = fl.score_shared_funder(
            shared=TEAM, deployer=DEP, graph_wallet=GRAPH,
            deployer_tx=TX, deployer_amount="0.2", deployer_funded_at=FUND_AT,
            graph_tx=TX, graph_amount="0.3", graph_funded_at=FUND_AT,
            deployed_at=DEP_AT, public=self.pub)
        self.assertEqual(link["kind"], "shared_funder")
        self.assertEqual(link["confidence"], "medium")
        self.assertTrue(fl.is_hard_evidence(link))

    def test_public_exchange_excluded(self):
        link = fl.score_direct(funder=BINANCE, deployer=DEP, tx=TX, amount="1",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=self.pub)
        self.assertTrue(link["excluded_reason"].startswith("public_funder:"))
        self.assertFalse(fl.is_hard_evidence(link))

    def test_mixer_excluded(self):
        link = fl.score_direct(funder=TORNADO, deployer=DEP, tx=TX, amount="1",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier=None, public=self.pub)
        self.assertIn("mixer", link["excluded_reason"])
        self.assertFalse(fl.is_hard_evidence(link))

    def test_one_hop_not_hard(self):
        link = fl.score_one_hop(
            team=TEAM, intermediate=MID, deployer=DEP,
            hop1_tx=TX, hop1_amount="1", hop1_at=FUND_AT,
            hop2_tx=TX, hop2_amount="0.5", hop2_at=FUND_AT,
            deployed_at=DEP_AT, public=self.pub)
        self.assertEqual(link["kind"], "one_hop")
        self.assertEqual(link["hops"], 1)
        self.assertEqual(link["confidence"], "low")
        self.assertFalse(fl.is_hard_evidence(link))

    def test_over_90d_not_hard(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx=TX, amount="0.5",
                               funded_at=FUND_OLD, deployed_at=DEP_AT,
                               funder_tier="high", public=self.pub)
        self.assertEqual(link["excluded_reason"], "funding_older_than_90d")
        self.assertFalse(fl.is_hard_evidence(link))

    def test_missing_tx_not_hard(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx="", amount="0.5",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=self.pub)
        self.assertFalse(fl.is_hard_evidence(link))

    def test_missing_amount_not_hard(self):
        link = {"from": TEAM, "to": DEP, "hops": 0, "kind": "direct", "tx": TX,
                "amount": "", "funded_at": FUND_AT, "deployed_at": DEP_AT,
                "confidence": "high", "excluded_reason": ""}
        self.assertFalse(fl.is_hard_evidence(link))

    def test_missing_time_not_hard(self):
        link = {"from": TEAM, "to": DEP, "hops": 0, "kind": "direct", "tx": TX,
                "amount": "0.5", "funded_at": None, "deployed_at": DEP_AT,
                "confidence": "high", "excluded_reason": ""}
        self.assertFalse(fl.is_hard_evidence(link))

    def test_pattern_not_hard(self):
        link = fl.score_pattern(funder=TEAM, deployer=DEP, peers=[GRAPH],
                                tx=TX, amount="0.5", funded_at=FUND_AT,
                                deployed_at=DEP_AT)
        self.assertEqual(link["confidence"], "low")
        self.assertFalse(fl.is_hard_evidence(link))

    def test_analyze_with_fetcher_direct(self):
        def fetcher(addr, chain, limit=50, sort="asc"):
            if addr.lower() == DEP:
                return [{"from": TEAM, "to": DEP, "tx": TX, "amount": "0.5",
                         "funded_at": FUND_AT, "funded_ts": 1760925600,
                         "asset": "ETH", "chain": chain}]
            return []
        # funded_ts approx for 2026-10-20 — use parsed
        from funding_links import _parse_ts
        ts = _parse_ts(FUND_AT)
        def fetcher2(addr, chain, limit=50, sort="asc"):
            if addr.lower() == DEP.lower():
                return [{"from": TEAM, "to": DEP, "tx": TX, "amount": "0.5",
                         "funded_at": FUND_AT, "funded_ts": ts,
                         "asset": "ETH", "chain": chain}]
            return []
        res = fl.analyze_deployer(
            DEP, "ethereum", deployed_at=DEP_AT,
            graph_wallets={TEAM: {"confidence": "high"}},
            public=self.pub, fetcher=fetcher2)
        self.assertTrue(fl.is_hard_evidence(res["funding_link"]))
        self.assertEqual(res["funding_link"]["kind"], "direct")


    def test_analyze_shared_funder(self):
        """Funder not in graph, but also funded a graph wallet → shared_funder hard evidence."""
        ts = fl._parse_ts(FUND_AT)
        def fetcher(addr, chain, limit=50, sort="asc"):
            a = addr.lower()
            if a == DEP.lower():
                return [{"from": MID, "to": DEP, "tx": TX, "amount": "0.5",
                         "funded_at": FUND_AT, "funded_ts": ts, "asset": "ETH", "chain": chain}]
            if a == GRAPH.lower():
                return [{"from": MID, "to": GRAPH, "tx": TX, "amount": "0.3",
                         "funded_at": FUND_AT, "funded_ts": ts, "asset": "ETH", "chain": chain}]
            return []
        res = fl.analyze_deployer(
            DEP, "ethereum", deployed_at=DEP_AT,
            graph_wallets={GRAPH: {"confidence": "high"}},
            public=self.pub, fetcher=fetcher)
        link = res["funding_link"]
        self.assertEqual(link["kind"], "shared_funder")
        self.assertTrue(fl.is_hard_evidence(link))

class TestH2InConfidence(unittest.TestCase):
    def test_funding_high_plus_site_confirms(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx=TX, amount="0.5",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=fl.load_public_funders())
        find = {
            "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "handle": "demo",
            "sources": [{"origin": "js", "source": "tokenAddress=0xaaa", "key": "tokenAddress"}],
            "funding_link": link,
            "traced_from": DEP,
        }
        prov = {"wallet_factory": False, "official_x": False, "name_only": False,
                "soft_wallet": False, "creator": DEP, "wallet_confidence": None}
        out = cc.assess(find, verified_ok=True, ca_role="token", prov=prov,
                        funding_link=link)
        self.assertIn("funding_link", [e["kind"] for e in out["evidence"]])
        self.assertIn("site_semantic_ca", [e["kind"] for e in out["evidence"]])
        self.assertGreaterEqual(out["hard_evidence_count"], 2)
        self.assertEqual(out["ca_status"], "confirmed")
        self.assertIn("funding_link", out["matched_by"])

    def test_funding_alone_is_candidate(self):
        link = fl.score_direct(funder=TEAM, deployer=DEP, tx=TX, amount="0.5",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=fl.load_public_funders())
        find = {"address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "handle": "demo", "sources": [], "traced_from": DEP}
        prov = {"wallet_factory": False, "official_x": False, "name_only": False,
                "soft_wallet": False, "creator": DEP}
        out = cc.assess(find, verified_ok=True, ca_role="token", prov=prov,
                        funding_link=link)
        self.assertEqual(out["hard_evidence_count"], 1)
        self.assertEqual(out["ca_status"], "candidate")

    def test_site_js_and_html_one_evidence(self):
        find = {
            "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "handle": "demo",
            "sources": [
                {"origin": "js", "source": "token=0xaaa", "key": "token"},
                {"origin": "html", "source": "tokenAddress=0xaaa", "key": "tokenAddress"},
            ],
        }
        prov = {"wallet_factory": False, "official_x": False, "name_only": False,
                "soft_wallet": False, "creator": None}
        ev = cc.collect_hard_evidence(find, prov)
        kinds = [e["kind"] for e in ev]
        self.assertEqual(kinds.count("site_semantic_ca"), 1)


class TestVetoes(unittest.TestCase):
    def test_multi_same_name_no_link(self):
        find = {"address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "handle": "demo", "sources": []}
        prov = {"wallet_factory": False, "official_x": False, "name_only": True,
                "soft_wallet": False, "creator": None}
        sibs = [{"address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]
        vs = cc.collect_vetoes(find, prov, sibling_same_name=sibs)
        self.assertTrue(any(v["kind"] == "multi_same_name_no_link" for v in vs))
        out = cc.assess(find, verified_ok=True, ca_role="token", prov={
            "wallet_factory": False, "official_x": False, "name_only": False,
            "soft_wallet": False, "creator": None,
        }, sibling_same_name=sibs)
        # with 0 hard evidence + veto → candidate (not confirmed)
        self.assertNotEqual(out["ca_status"], "confirmed")

    def test_public_funder_veto_blocks_confirm(self):
        link = fl.score_direct(funder=BINANCE, deployer=DEP, tx=TX, amount="1",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier="high", public=fl.load_public_funders())
        # even with a second hard evidence path via high wallet, public funder veto fires
        find = {
            "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "handle": "demo",
            "sources": [{"origin": "js", "source": "token=0xaaa", "key": "token"}],
            "traced_from": DEP,
        }
        prov = {"wallet_factory": True, "official_x": False, "name_only": False,
                "soft_wallet": False, "creator": DEP, "wallet_confidence": "high"}
        out = cc.assess(find, verified_ok=True, ca_role="token", prov=prov,
                        wallet_meta={DEP: {"confidence": "high", "source": "nft_deployer"}},
                        watched_wallets={DEP}, funding_link=link)
        self.assertTrue(any(v["kind"] == "public_funder" for v in (out.get("vetoes") or [])))
        # high_watched + factory would be 2 hard, but veto → candidate
        self.assertEqual(out["ca_status"], "candidate")

    def test_mixer_veto(self):
        link = fl.score_direct(funder=TORNADO, deployer=DEP, tx=TX, amount="1",
                               funded_at=FUND_AT, deployed_at=DEP_AT,
                               funder_tier=None, public=fl.load_public_funders())
        vs = cc.collect_vetoes({"sources": []}, {"wallet_factory": False, "name_only": False,
                                                 "soft_wallet": False, "creator": None,
                                                 "official_x": False}, funding_link=link)
        self.assertTrue(any(v["kind"] == "mixer_no_graph" for v in vs))

    def test_deploy_far_from_window(self):
        find = {"address": "0xaaa", "detected_at": "2026-01-01T00:00:00+08:00",
                "expected_window": {"start": "2026-10-20T00:00:00+08:00",
                                    "end": "2026-10-25T00:00:00+08:00"},
                "sources": []}
        vs = cc.collect_vetoes(find, {"wallet_factory": False, "name_only": False,
                                      "soft_wallet": False, "creator": None,
                                      "official_x": False},
                               expected_window=find["expected_window"])
        self.assertTrue(any(v["kind"] == "deploy_far_from_window" for v in vs))

    def test_official_x_not_blocked_by_veto(self):
        find = {"address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "handle": "demo", "sources": [{"source": "https://x.com/demo/status/1"}],
                "detected_at": "2026-01-01T00:00:00+08:00",
                "expected_window": {"start": "2026-10-20T00:00:00+08:00",
                                    "end": "2026-10-25T00:00:00+08:00"}}
        prov = {"wallet_factory": False, "official_x": True, "name_only": False,
                "soft_wallet": False, "creator": None, "x_url": "https://x.com/demo/status/1"}
        out = cc.assess(find, verified_ok=True, ca_role="token", prov=prov,
                        expected_window=find["expected_window"])
        self.assertEqual(out["ca_status"], "confirmed")


class TestCoverageStats(unittest.TestCase):
    def test_coverage_stats_shape(self):
        import importlib
        sys.path.insert(0, str(BASE))
        sys.modules.pop("build_ca_finds", None)
        b = importlib.import_module("build_ca_finds")
        rows = [
            {"handle": "a", "address": "0x1", "ca_status": "confirmed",
             "official_x_confirmed": True, "provenance": "official_x",
             "lock_time": "2026-10-24T10:00:00+08:00",
             "listing_time": "2026-10-24T12:00:00+08:00", "lead_seconds": 7200,
             "matched_by": ["official_x"]},
            {"handle": "b", "address": "0x2", "ca_status": "confirmed",
             "official_x_confirmed": True, "provenance": "official_x",
             "lock_time": "2026-10-24T12:00:00+08:00",
             "listing_time": "2026-10-24T11:00:00+08:00", "lead_seconds": -3600,
             "matched_by": ["official_x"]},
        ]
        st = b.compute_coverage_stats(rows)
        self.assertEqual(st["total_projects_with_final_ca"], 2)
        self.assertEqual(st["prelaunch_locked_total"], 2)
        self.assertEqual(st["prelaunch_locked_correct"], 1)
        self.assertEqual(st["coverage"], 0.5)
        self.assertEqual(st["precision"], 0.5)
        self.assertEqual(st["median_lead_seconds"], 7200)


if __name__ == "__main__":
    unittest.main()
