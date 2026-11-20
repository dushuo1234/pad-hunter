#!/usr/bin/env python3
"""E1 hist adapters: base/bsc/robinhood/hyperevm mock txlist. No network, no secrets."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BASE = Path("/workspace/project-monitor")
HIST = BASE / "e1_hist_staging"
# Prefer hist staging for funding_links; keep e1_staging for other E1 modules.
_drop = {str(HIST), str(BASE / "e1_staging"), str(BASE / "e1_hist_staging"),
         str(BASE / "p0_staging"), str(BASE / "p1_staging"), str(BASE)}
sys.path[:] = [str(HIST), str(BASE / "e1_staging"), str(BASE)] + [
    p for p in sys.path if p not in _drop
]
for m in list(sys.modules):
    if m in ("funding_links", "ca_confidence") or m.startswith("funding_links"):
        sys.modules.pop(m, None)

import funding_links as fl  # noqa: E402

TEAM = "0x1111111111111111111111111111111111111111"
DEP = "0x2222222222222222222222222222222222222222"
TX = "0xabc1111111111111111111111111111111111111111111111111111111111111"
DEP_AT = "2026-10-24T12:00:00+08:00"
FUND_AT = "2026-10-20T10:00:00+08:00"


def _rows(chain, asset, ts=None):
    ts = ts or fl._parse_ts(FUND_AT)
    return [{
        "from": TEAM, "to": DEP, "tx": TX, "amount": "0.05",
        "funded_at": FUND_AT, "funded_ts": ts, "asset": asset, "chain": chain,
    }]


class TestAdapterCapability(unittest.TestCase):
    def test_adapters_listed_for_four_chains(self):
        for chain in ("base", "bsc", "robinhood", "hyperevm"):
            ads = fl.list_txlist_adapters(chain)
            self.assertTrue(ads, msg=chain)
            backends = {a["backend"] for a in ads}
            self.assertIn("etherscan_v2", backends, msg=chain)

    def test_hyperevm_marked_free(self):
        ads = fl.list_txlist_adapters("hyperevm")
        v2 = next(a for a in ads if a["backend"] == "etherscan_v2")
        self.assertTrue(v2["free"])
        self.assertEqual(v2["chain_id"], 999)

    def test_base_bsc_rh_marked_paid(self):
        for chain in ("base", "bsc", "robinhood"):
            v2 = next(a for a in fl.list_txlist_adapters(chain)
                      if a["backend"] == "etherscan_v2")
            self.assertFalse(v2["free"], msg=chain)

    def test_missing_keys_report_no_secret_values(self):
        # Ensure report never contains a key-shaped value even if env set
        with mock.patch.dict(os.environ, {"ETHERSCAN_API_KEY": "SECRETVALUE123"}, clear=False):
            # reload key detection uses env live
            rep = fl.missing_keys_report()
            blob = str(rep)
            self.assertNotIn("SECRETVALUE123", blob)
            self.assertIn("ETHERSCAN_API_KEY", blob)

    def test_gaps_without_key_marks_hyperevm(self):
        with mock.patch.object(fl, "_etherscan_api_key", return_value=None):
            g = {x["chain"]: x for x in fl.gaps()}
            self.assertEqual(g["hyperevm"]["gap"], "etherscan_v2_key_missing")
            self.assertFalse(g["hyperevm"].get("ready"))


class TestMockFetchFourChains(unittest.TestCase):
    def test_analyze_each_chain_with_mock_fetcher(self):
        ts = fl._parse_ts(FUND_AT)
        for chain, asset in (
            ("base", "ETH"), ("bsc", "BNB"),
            ("robinhood", "ETH"), ("hyperevm", "HYPE"),
        ):
            def fetcher(addr, ch, limit=50, sort="asc", _c=chain, _a=asset, _ts=ts):
                if addr.lower() == DEP.lower() and ch == _c:
                    return _rows(_c, _a, _ts)
                return []
            res = fl.analyze_deployer(
                DEP, chain, deployed_at=DEP_AT,
                graph_wallets={TEAM: {"confidence": "high"}},
                public=fl.load_public_funders(), fetcher=fetcher)
            self.assertIsNone(res.get("gap"), msg=chain)
            self.assertTrue(fl.is_hard_evidence(res["funding_link"]), msg=chain)
            self.assertEqual(res["funding_link"]["chain"], chain)
            self.assertEqual(res["funding_link"]["asset"], asset)

    def test_gap_without_fetcher_when_not_ready(self):
        with mock.patch.object(fl, "chain_history_ready", return_value=False):
            res = fl.analyze_deployer(
                DEP, "base", deployed_at=DEP_AT,
                graph_wallets={}, public={})
            self.assertEqual(res["gap"], "base")
            self.assertIn("降级", res["note_zh"] or "")


class TestParseTxlist(unittest.TestCase):
    def test_parse_etherscan_shape(self):
        raw = {
            "status": "1",
            "message": "OK",
            "result": [{
                "hash": TX,
                "from": TEAM,
                "to": DEP,
                "value": str(10**17),  # 0.1
                "timeStamp": str(fl._parse_ts(FUND_AT)),
                "isError": "0",
                "blockNumber": "123",
            }],
        }
        rows = fl._parse_txlist_rows(raw, DEP, "hyperevm")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset"], "HYPE")
        self.assertEqual(rows[0]["from"], TEAM.lower())

    def test_fetch_etherscan_v2_skips_without_key(self):
        with mock.patch.object(fl, "_etherscan_api_key", return_value=None):
            self.assertEqual(
                fl._fetch_etherscan_v2_txlist("hyperevm", DEP, limit=10, sort="asc"),
                [])

    def test_fetch_etherscan_v2_builds_call_without_logging_key(self):
        captured = {}

        def fake_curl(url, timeout=18):
            captured["url"] = url
            return {
                "status": "1", "message": "OK",
                "result": [{
                    "hash": TX, "from": TEAM, "to": DEP,
                    "value": "1000000000000000000",
                    "timeStamp": str(fl._parse_ts(FUND_AT)),
                    "isError": "0", "blockNumber": "1",
                }],
            }

        with mock.patch.object(fl, "_etherscan_api_key", return_value="KEY_NOT_FOR_LOG"), \
                mock.patch.object(fl, "v2_chain_status", return_value=None), \
                mock.patch.object(fl, "_save_v2_status"):
            with mock.patch.object(fl, "_curl_json", side_effect=fake_curl):
                rows = fl._fetch_etherscan_v2_txlist("base", DEP, limit=5, sort="asc")
        self.assertEqual(len(rows), 1)
        self.assertIn("chainid=8453", captured["url"])
        self.assertIn("apikey=KEY_NOT_FOR_LOG", captured["url"])  # used in request only
        # Public helpers must not echo it
        blob = str(fl.missing_keys_report()) + str(fl.gaps())
        self.assertNotIn("KEY_NOT_FOR_LOG", blob)


class TestPublicFundersExtended(unittest.TestCase):
    def test_hyperevm_system_address_excluded(self):
        pub = fl.load_public_funders()
        hype_sys = "0x2222222222222222222222222222222222222222"
        self.assertIsNotNone(fl.is_public_funder(hype_sys, pub))
        link = fl.score_direct(
            funder=hype_sys, deployer=DEP, tx=TX, amount="1",
            funded_at=FUND_AT, deployed_at=DEP_AT, funder_tier="high",
            public=pub, asset="HYPE", chain="hyperevm")
        self.assertTrue(link["excluded_reason"].startswith("public_funder:"))

    def test_base_bridge_excluded(self):
        pub = fl.load_public_funders()
        bridge = "0x4200000000000000000000000000000000000010"
        self.assertIsNotNone(fl.is_public_funder(bridge, pub))


class TestV2StatusGaps(unittest.TestCase):
    def test_paid_rejection_recorded_without_key(self):
        saved = {}

        def fake_save(chain, status, message=""):
            saved[chain] = (status, message)

        def fake_curl(url, timeout=18):
            return {"status": "0", "message": "NOTOK",
                    "result": "Free API access is not supported for this chain."}

        with mock.patch.object(fl, "_etherscan_api_key", return_value="K_SECRET"), \
                mock.patch.object(fl, "v2_chain_status", return_value=None), \
                mock.patch.object(fl, "_save_v2_status", side_effect=fake_save), \
                mock.patch.object(fl, "_curl_json", side_effect=fake_curl):
            self.assertEqual(fl._fetch_etherscan_v2_txlist("bsc", DEP, limit=1, sort="asc"), [])
        self.assertEqual(saved["bsc"][0], "paid_required")
        self.assertNotIn("K_SECRET", str(saved))

    def test_gaps_reflect_status(self):
        st = {"hyperevm": "works", "base": "paid_required", "bsc": "paid_required",
              "robinhood": "paid_required"}
        with mock.patch.object(fl, "_etherscan_api_key", return_value="K"), \
                mock.patch.object(fl, "v2_chain_status", side_effect=lambda c: st.get(c)):
            g = {x["chain"]: x for x in fl.gaps()}
            self.assertIsNone(g["hyperevm"]["gap"])
            self.assertTrue(g["hyperevm"]["ready"])
            for c in ("base", "bsc", "robinhood"):
                self.assertEqual(g[c]["gap"], "etherscan_v2_paid_required", msg=c)
            self.assertFalse(g["base"]["ready"])
            self.assertFalse(g["bsc"]["ready"])
            self.assertNotIn("'K'", str(g))
            self.assertFalse(fl.chain_history_ready("bsc"))
            self.assertTrue(fl.chain_history_ready("hyperevm"))


if __name__ == "__main__":
    unittest.main()
