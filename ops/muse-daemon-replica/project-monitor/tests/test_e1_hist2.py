"""E1 hist2: archive-RPC binary-search funding adapter (mock chain, no network)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
H2 = BASE / "e1_hist2_staging"
_drop = {str(H2), str(BASE / "e1_staging"), str(BASE / "e1_hist_staging"),
         str(BASE / "p0_staging"), str(BASE / "p1_staging"), str(BASE)}
sys.path[:] = [str(H2), str(BASE / "e1_staging"), str(BASE)] + [p for p in sys.path if p not in _drop]
for m in ("funding_links", "rpc_funding"):
    sys.modules.pop(m, None)
import rpc_funding as rf  # noqa: E402
import funding_links as fl  # noqa: E402

ADDR = "0x" + "ab" * 20
FUNDER = "0x" + "cd" * 20
GASSER = "0x" + "ef" * 20
TEAM = "0x" + "11" * 20
TIP = 10_000
T0 = 1_790_000_000
BT = 2  # seconds per block


class FakeChain:
    """Scripted account history. events: list of (block, kind, data)."""

    def __init__(self, inflows, outflows, *, trace=True, internal=(), calldata=(), err_first=None):
        self.inflows = dict(inflows)        # block -> (from, value, via) via in tx|internal|calldata
        self.outflows = set(outflows)       # blocks where addr sends a tx (nonce+1, -1 wei fee)
        self.trace = trace
        self.err_first = err_first
        self.calls = []

    def bal(self, b):
        v = 0
        for blk, (_f, val, _v) in self.inflows.items():
            if blk <= b:
                v += val
        v -= sum(1 for o in self.outflows if o <= b)
        return max(v, 0)

    def nonce(self, b):
        return sum(1 for o in self.outflows if o <= b)

    def post(self, url, payload):
        m, p = payload["method"], payload["params"]
        self.calls.append((url, m))
        if self.err_first and url == self.err_first:
            return {"error": {"message": "missing trie node (archive required)"}}
        if m == "eth_blockNumber":
            return {"result": hex(TIP)}
        if m == "eth_getBalance":
            return {"result": hex(self.bal(int(p[1], 16)))}
        if m == "eth_getTransactionCount":
            return {"result": hex(self.nonce(int(p[1], 16)))}
        if m == "eth_getBlockByNumber":
            b = int(p[0], 16)
            txs = []
            if b in self.inflows:
                f, val, via = self.inflows[b]
                if via == "tx":
                    txs.append({"from": f, "to": ADDR, "value": hex(val), "hash": f"0xtx{b}", "input": "0x"})
                elif via == "calldata":
                    txs.append({"from": f, "to": "0x" + "ca" * 20, "value": hex(val * 3),
                                "hash": f"0xmc{b}", "input": "0xdeadbeef" + ADDR[2:].rjust(64, "0")})
            txs.append({"from": "0x" + "99" * 20, "to": "0x" + "98" * 20, "value": "0x5", "hash": "0xnoise", "input": "0x"})
            return {"result": {"timestamp": hex(T0 + b * BT), "transactions": txs if p[1] else [t["hash"] for t in txs]}}
        if m == "debug_traceBlockByNumber":
            if not self.trace:
                return {"error": {"message": "method not allowed"}}
            b = int(p[0], 16)
            out = []
            if b in self.inflows and self.inflows[b][2] == "internal":
                f, val, _ = self.inflows[b]
                out.append({"txHash": f"0xin{b}", "result": {"from": "0x" + "77" * 20, "to": "0x" + "66" * 20,
                            "value": "0x0", "calls": [{"from": f, "to": ADDR, "value": hex(val)}]}})
            return {"result": out}
        return {"error": {"message": "unknown"}}


def _cli(chain, fc, rpcs=None, max_calls=400):
    rpcs = rpcs or [{"url": "https://a", "trace": fc.trace}]
    return rf.RpcClient(chain, rpcs=rpcs, post=fc.post, max_calls=max_calls)


class TestFirstInflow(unittest.TestCase):
    def setUp(self):
        rf.MIN_INTERVAL = 0

    def test_direct_tx_base(self):
        fc = FakeChain({4321: (FUNDER, 10**17, "tx")}, {5000, 6000})
        r = rf.first_inflow(_cli("base", fc), ADDR)
        self.assertEqual(r["from"], FUNDER)
        self.assertEqual(r["block"], 4321)
        self.assertEqual(r["tx"], "0xtx4321")
        self.assertEqual(r["via"], "rpc_tx")
        self.assertEqual(r["asset"], "ETH")
        self.assertEqual(r["funded_ts"], T0 + 4321 * BT)

    def test_internal_via_trace_robinhood(self):
        fc = FakeChain({777: (FUNDER, 5 * 10**16, "internal")}, {900})
        r = rf.first_inflow(_cli("robinhood", fc), ADDR)
        self.assertEqual((r["from"], r["tx"], r["via"]), (FUNDER, "0xin777", "rpc_internal"))

    def test_calldata_inferred_when_no_trace(self):
        fc = FakeChain({300: (FUNDER, 10**17, "calldata")}, {400}, trace=False)
        r = rf.first_inflow(_cli("base", fc), ADDR)
        self.assertTrue(r["inferred"])
        self.assertEqual(r["from"], FUNDER)
        self.assertIsNone(r["amount"])

    def test_unknown_internal_bsc(self):
        fc = FakeChain({300: (FUNDER, 10**17, "internal")}, {400}, trace=False)
        r = rf.first_inflow(_cli("bsc", fc), ADDR)
        self.assertTrue(r["unknown_internal"])
        self.assertIn("funding_unknown_internal", r["note_zh"])

    def test_never_funded(self):
        fc = FakeChain({}, set())
        self.assertIsNone(rf.first_inflow(_cli("bsc", fc), ADDR))

    def test_failover_skips_non_archive(self):
        fc = FakeChain({50: (FUNDER, 10**18, "tx")}, {60}, err_first="https://pruned")
        cli = rf.RpcClient("bsc", rpcs=[{"url": "https://pruned"}, {"url": "https://arch"}], post=fc.post, max_calls=400)
        r = rf.first_inflow(cli, ADDR)
        self.assertEqual(r["block"], 50)
        self.assertIn("https://pruned", cli.bad)
        self.assertEqual(sum(1 for u, _ in fc.calls if u == "https://pruned"), 1)

    def test_call_count_logarithmic(self):
        fc = FakeChain({4321: (FUNDER, 10**17, "tx")}, {5000})
        cli = _cli("base", fc)
        rf.first_inflow(cli, ADDR)
        self.assertLess(cli.calls, 40)

    def test_budget_bound(self):
        fc = FakeChain({4321: (FUNDER, 10**17, "tx")}, {5000})
        cli = _cli("base", fc, max_calls=5)
        with self.assertRaises(rf.RpcBudget):
            rf.first_inflow(cli, ADDR)


class TestGas7d(unittest.TestCase):
    def setUp(self):
        rf.MIN_INTERVAL = 0

    def test_last_inflow_before_deploy_between_spends(self):
        fc = FakeChain({100: (FUNDER, 10**18, "tx"), 9000: (GASSER, 2 * 10**17, "tx")},
                       {200, 5000, 9500, 9800})
        cli = _cli("bsc", fc)
        r = rf.last_inflow_before(cli, ADDR, 8000, 9900)
        self.assertEqual((r["from"], r["block"]), (GASSER, 9000))

    def test_block_at_or_before(self):
        fc = FakeChain({}, set())
        cli = _cli("base", fc)
        self.assertEqual(rf.block_at_or_before(cli, T0 + 1234 * BT + 1, TIP), 1234)
        self.assertEqual(rf.block_at_or_before(cli, T0 + 99999 * BT, TIP), TIP)

    def test_fetch_rows_first_and_gas_with_cache(self):
        fc = FakeChain({100: (FUNDER, 10**18, "tx"), 9000: (GASSER, 2 * 10**17, "tx")},
                       {200, 5000, 9500})
        with tempfile.TemporaryDirectory() as d:
            rf.CACHE_PATH = Path(d) / "c.json"
            dep_ts = T0 + 9600 * BT
            rows = rf.fetch_native_inflows_rpc(ADDR, "bsc", deployed_ts=dep_ts, client=_cli("bsc", fc))
            self.assertEqual([r["from"] for r in rows], [FUNDER, GASSER])
            self.assertEqual(rows[0]["asset"], "BNB")
            n = len(fc.calls)
            rows2 = rf.fetch_native_inflows_rpc(ADDR, "bsc", deployed_ts=dep_ts, client=_cli("bsc", fc))
            self.assertEqual(rows2, rows)
            self.assertEqual(len(fc.calls), n)  # served from cache

    def test_never_raises(self):
        def boom(url, payload):
            return {"error": {"message": "rate limit"}}
        cli = rf.RpcClient("base", rpcs=[{"url": "https://x"}], post=boom)
        with tempfile.TemporaryDirectory() as d:
            rf.CACHE_PATH = Path(d) / "c.json"
            self.assertEqual(rf.fetch_native_inflows_rpc(ADDR, "base", client=cli), [])


class TestResumeAndBudget(unittest.TestCase):
    def setUp(self):
        rf.MIN_INTERVAL = 0

    def test_resume_from_memo_after_budget(self):
        fc = FakeChain({4321: (FUNDER, 10**17, "tx")}, {5000, 6000})
        with tempfile.TemporaryDirectory() as d:
            rf.CACHE_PATH = Path(d) / "c.json"
            full = FakeChain({4321: (FUNDER, 10**17, "tx")}, {5000, 6000})
            rf.first_inflow(_cli("base", full), ADDR)
            single = len(full.calls)
            r1 = rf.fetch_native_inflows_rpc(ADDR, "base", client=_cli("base", fc, max_calls=12))
            self.assertEqual(r1, [])
            self.assertEqual(rf.LAST_STATUS["status"], "pending")
            r2 = rf.fetch_native_inflows_rpc(ADDR, "base", client=_cli("base", fc, max_calls=400))
            self.assertEqual(r2[0]["block"], 4321)
            self.assertEqual(rf.LAST_STATUS["status"], "complete")
            self.assertLessEqual(len(fc.calls), single + 4)  # memo avoided redoing work
            import json as _j
            self.assertNotIn("memo", _j.loads(rf.CACHE_PATH.read_text())[f"base:{ADDR}"])

    def test_process_budget_exhausted_is_pending(self):
        with tempfile.TemporaryDirectory() as d:
            rf.CACHE_PATH = Path(d) / "c.json"
            old = rf._spent[0]
            rf._spent[0] = rf.PROCESS_BUDGET_S + 1
            try:
                with mock.patch.object(rf, "_curl_post", side_effect=AssertionError("no network")):
                    self.assertEqual(rf.fetch_native_inflows_rpc(ADDR, "bsc"), [])
                self.assertEqual(rf.LAST_STATUS["status"], "pending")
            finally:
                rf._spent[0] = old

    def test_deadline_raises_budget(self):
        fc = FakeChain({}, set())
        cli = rf.RpcClient("base", rpcs=[{"url": "https://a"}], post=fc.post, deadline=0.0)
        with self.assertRaises(rf.RpcBudget):
            cli.tip()

    def test_analyze_pending_note(self):
        def fake(*a, **k):
            fl._rpc.LAST_STATUS["status"] = "pending"
            return []
        with mock.patch.object(fl, "_etherscan_api_key", return_value=None), \
                mock.patch.object(fl, "_factory_explorer_api", return_value=None), \
                mock.patch.object(fl._rpc, "fetch_native_inflows_rpc", side_effect=fake):
            res = fl.analyze_deployer(ADDR, "robinhood", deployed_at="2026-10-21T12:00:00+08:00",
                                      graph_wallets={}, public={})
        self.assertTrue(res.get("pending"))
        self.assertIn("续查", res["note_zh"])
        self.assertIsNone(res["funding_link"])


DEP_AT = "2026-10-21T12:00:00+08:00"
FUND_AT = "2026-10-20T12:00:00+08:00"


class TestWiring(unittest.TestCase):
    def test_chain_ready_and_adapters(self):
        for c in ("base", "bsc", "robinhood"):
            self.assertTrue(fl.chain_history_ready(c), msg=c)
            backends = [a["backend"] for a in fl.list_txlist_adapters(c)]
            self.assertIn("archive_rpc_bsearch", backends, msg=c)
        self.assertNotIn("archive_rpc_bsearch", [a["backend"] for a in fl.list_txlist_adapters("hyperevm")])

    def test_gaps_rpc_ready_despite_paid_required(self):
        st = {"hyperevm": "works", "base": "paid_required", "bsc": "paid_required", "robinhood": "paid_required"}
        with mock.patch.object(fl, "_etherscan_api_key", return_value="K_SECRET"), \
                mock.patch.object(fl, "v2_chain_status", side_effect=lambda c: st.get(c)):
            g = {x["chain"]: x for x in fl.gaps()}
            for c in ("base", "bsc", "robinhood"):
                self.assertIsNone(g[c]["gap"], msg=c)
                self.assertTrue(g[c]["ready"], msg=c)
                self.assertEqual(g[c]["method"], "archive_rpc_bsearch")
            self.assertNotIn("K_SECRET", str(g))

    def test_order_v2_before_rpc(self):
        v2row = [{"from": TEAM, "to": ADDR, "tx": "0xv2", "amount": "1", "funded_at": FUND_AT,
                  "funded_ts": fl._parse_ts(FUND_AT), "chain": "base"}]
        with mock.patch.object(fl, "_etherscan_api_key", return_value="K"), \
                mock.patch.object(fl, "_fetch_etherscan_v2_txlist", return_value=v2row), \
                mock.patch.object(fl._rpc, "fetch_native_inflows_rpc") as rpc:
            self.assertEqual(fl.fetch_native_inflows(ADDR, "base")[0]["tx"], "0xv2")
            rpc.assert_not_called()

    def test_rpc_used_when_v2_paid(self):
        row = [{"from": TEAM, "to": ADDR, "tx": "0xr", "amount": "0.5", "funded_at": FUND_AT,
                "funded_ts": fl._parse_ts(FUND_AT), "asset": "ETH", "chain": "base", "via": "rpc_tx"}]
        with mock.patch.object(fl, "_etherscan_api_key", return_value="K"), \
                mock.patch.object(fl, "_fetch_etherscan_v2_txlist", return_value=[]), \
                mock.patch.object(fl, "_factory_explorer_api", return_value=None), \
                mock.patch.object(fl._rpc, "fetch_native_inflows_rpc", return_value=row) as rpc:
            res = fl.analyze_deployer(ADDR, "base", deployed_at=DEP_AT,
                                      graph_wallets={TEAM: {"confidence": "high"}}, public={})
            rpc.assert_called()
            self.assertEqual(rpc.call_args.kwargs.get("deployed_ts"), fl._parse_ts(DEP_AT))
            self.assertTrue(fl.is_hard_evidence(res["funding_link"]))

    def test_inferred_never_hard(self):
        row = [{"from": TEAM, "to": ADDR, "tx": "0xmc", "amount": None, "funded_at": FUND_AT,
                "funded_ts": fl._parse_ts(FUND_AT), "asset": "ETH", "chain": "base",
                "via": "rpc_calldata", "inferred": True}]
        row2 = [dict(row[0], amount="0.5")]
        for rows in (row, row2):
            res = fl.analyze_deployer(ADDR, "base", deployed_at=DEP_AT,
                                      graph_wallets={TEAM: {"confidence": "high"}}, public={},
                                      fetcher=lambda a, c, limit=50, sort="asc", _r=rows: _r if a == ADDR else [])
            self.assertFalse(fl.is_hard_evidence(res["funding_link"]))
            self.assertEqual(res["funding_link"]["confidence"], "low")

    def test_record_rpc_status_no_secret(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(fl, "V2_STATUS_FILE", Path(d) / "s.json"):
                fl.record_rpc_archive_status({"base": {"https://mainnet.base.org": "archive_ok"}})
                txt = (Path(d) / "s.json").read_text()
        self.assertIn("mainnet.base.org", txt)
        self.assertIn("trace_hosts", txt)
        self.assertNotIn("apikey", txt.lower())


if __name__ == "__main__":
    unittest.main()
