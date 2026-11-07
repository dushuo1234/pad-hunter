"""PublicNode personal-token archive RPCs: runtime loading + URL masking (no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
import rpc_funding as rf  # noqa: E402

TOK = "REDACTED" * 24 + "0123456789abcdef" * 2
U_BSC = f"https://bsc-rpc.publicnode.com/{TOK}"
U_BASE = f"https://base-rpc.publicnode.com/{TOK}"


class TestLoad(unittest.TestCase):
    def _file(self, d, body):
        p = Path(d) / ".publicnode_rpc_urls"
        p.write_text(body, encoding="utf-8")
        return p

    def test_file_and_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._file(d, f"# c\nBSC={U_BSC}\nBASE={U_BASE}\nROBINHOOD=notaurl\n")
            got = rf.load_publicnode_urls(p, env={})
            self.assertEqual(got, {"bsc": U_BSC, "base": U_BASE})
            got = rf.load_publicnode_urls(p, env={"PADHUNTER_PUBLICNODE_BSC": "https://x.example/y" * 1})
            self.assertEqual(got["bsc"], "https://x.example/y")

    def test_missing_file_silent(self):
        self.assertEqual(rf.load_publicnode_urls(Path("/nonexistent/.pn"), env={}), {})
        rpcs = {"bsc": [{"url": "https://a", "trace": False}]}
        self.assertEqual(rf._install_publicnode(rpcs, {}), [])
        self.assertEqual(len(rpcs["bsc"]), 1)

    def test_install_first_with_trace_no_dupes(self):
        rpcs = {"bsc": [{"url": "https://bsc-mainnet.public.blastapi.io", "trace": False}],
                "base": [{"url": "https://mainnet.base.org", "trace": False}]}
        for _ in range(2):
            added = rf._install_publicnode(rpcs, {"bsc": U_BSC, "base": U_BASE, "eth": "https://e/k"})
        self.assertEqual(sorted(added), ["base", "bsc"])
        self.assertEqual(rpcs["bsc"][0]["url"], U_BSC)
        self.assertTrue(rpcs["bsc"][0]["trace"])
        self.assertEqual(len(rpcs["bsc"]), 2)
        self.assertNotIn("eth", rpcs)


class TestMask(unittest.TestCase):
    def setUp(self):
        rf._register_secret(U_BSC)
        patcher = mock.patch.object(rf.time, "sleep", lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mask_url(self):
        self.assertEqual(rf.mask_url(U_BSC), "https://bsc-rpc.publicnode.com/***")
        self.assertEqual(rf.mask_url("https://mainnet.base.org"), "https://mainnet.base.org")
        self.assertEqual(rf.mask_url("https://u:p@h.io/k?x=1"), "https://h.io/***")
        self.assertNotIn(TOK, rf.mask_url(U_BSC))

    def test_scrub_error_and_client_reporting(self):
        def post(url, payload):
            return {"error": {"message": f"archive state missing at {url} token {TOK}"}}
        cli = rf.RpcClient("bsc", rpcs=[{"url": U_BSC, "trace": True}], post=post, max_calls=5)
        with self.assertRaises(RuntimeError) as cm:
            cli.call("eth_getBalance", ["0x" + "11" * 20, "0x1"])
        self.assertNotIn(TOK, str(cm.exception))
        self.assertIn(U_BSC, cli.bad)  # raw kept internally for skipping
        self.assertEqual(cli.bad_masked(), ["https://bsc-rpc.publicnode.com/***"])
        self.assertNotIn(TOK, repr(cli))

    def test_probe_masks_keys(self):
        def post(url, payload):
            if payload["method"] == "eth_blockNumber":
                return {"result": hex(5_000_000)}
            return {"error": {"message": f"boom {url}"}}
        rpcs = {"bsc": [{"url": U_BSC, "trace": True}, {"url": "https://ok.example", "trace": False}]}
        orig_init = rf.RpcClient.__init__

        def init(self, chain, rpcs=None, post_=None, **kw):
            orig_init(self, chain, rpcs=rpcs, post=post, **kw)
        with mock.patch.object(rf, "ARCHIVE_RPCS", rpcs), mock.patch.object(rf.RpcClient, "__init__", init):
            out = rf.probe("bsc")
        dump = json.dumps(out)
        self.assertNotIn(TOK, dump)
        self.assertIn("https://bsc-rpc.publicnode.com/***", out)

    def test_status_file_host_only(self):
        import funding_links as fl
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(fl, "V2_STATUS_FILE", Path(d) / "s.json"):
                fl.record_rpc_archive_status({"bsc": {rf.mask_url(U_BSC): "archive_ok", U_BSC: "archive_ok"}})
                txt = (Path(d) / "s.json").read_text()
        self.assertNotIn(TOK, txt)
        self.assertIn("bsc-rpc.publicnode.com", txt)
        self.assertIn("personal token", txt)  # updated note


class TestUnknownRetry(unittest.TestCase):
    def test_unknown_internal_retraced_once_trace_available(self):
        addr = "0x" + "ab" * 20
        funder = "0x" + "cd" * 20
        calls = []

        def post(url, payload):
            m = payload["method"]
            calls.append(m)
            if m == "eth_getBlockByNumber":
                return {"result": {"timestamp": hex(1_790_000_000), "transactions": []}}
            if m == "debug_traceBlockByNumber":
                return {"result": [{"txHash": "0xt", "result": {"from": "0x1", "to": "0x2", "value": "0x0",
                        "calls": [{"from": funder, "to": addr, "value": hex(10**17)}]}}]}
            return {"error": {"message": "unexpected"}}
        ent = {"first": {"unknown_internal": True, "block": 123}}
        cli = rf.RpcClient("base", rpcs=[{"url": "https://t.example", "trace": True}], post=post)
        rf._retry_unknown(cli, addr, ent, "first")
        self.assertEqual(ent["first"]["from"], funder)
        self.assertEqual(ent["first"]["via"], "rpc_internal")
        n = len(calls)
        rf._retry_unknown(cli, addr, ent, "first")  # resolved → no more calls
        self.assertEqual(len(calls), n)

    def test_no_retry_without_trace_and_capped(self):
        ent = {"first": {"unknown_internal": True, "block": 5}}
        cli = rf.RpcClient("bsc", rpcs=[{"url": "https://n.example", "trace": False}],
                           post=lambda u, p: self.fail("no call expected"))
        rf._retry_unknown(cli, "0x" + "ab" * 20, ent, "first")
        self.assertNotIn("unk_retry:first", ent)
        cli2 = rf.RpcClient("bsc", rpcs=[{"url": "https://t.example", "trace": True}],
                            post=lambda u, p: {"result": {"timestamp": "0x1", "transactions": []}}
                            if p["method"] == "eth_getBlockByNumber" else {"result": []})
        for _ in range(5):
            rf._retry_unknown(cli2, "0x" + "ab" * 20, ent, "first")
        self.assertEqual(ent["unk_retry:first"], rf.UNK_RETRY_MAX)
        self.assertTrue(ent["first"]["unknown_internal"])


if __name__ == "__main__":
    unittest.main()
