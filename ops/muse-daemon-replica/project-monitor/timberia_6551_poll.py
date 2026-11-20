#!/usr/bin/env python3
"""Poll @PlayTimberia via 6551 REST + timberia.io APIs; on official CA → fire_buy (robinhood).

Usage:
  /workspace/project-monitor/.venv/bin/python timberia_6551_poll.py
Env:
  TIMBERIA_POLL_SEC=20
  TIMBERIA_DRY_RUN=1   # default honor sniper_config dry_run
  TIMBERIA_BUY_ETH=0.003  # native ETH amount for RH buy (sniper amount override)
"""
from __future__ import annotations
import json, os, re, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(BASE))
from x6551 import user_tweets, X6551Error  # noqa
from sniper_buy import fire_buy, load_config  # noqa

SH = ZoneInfo("Asia/Shanghai")
HANDLE = "PlayTimberia"
FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"
RPC = "https://rpc.mainnet.chain.robinhood.com"
EVM_CA = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")
# known non-TIM / infra / mocks / fakes from research
BLOCKLIST = {
  x.lower() for x in [
    "0xF7D128Fcf42606Ae255645b7072d540053e13367",  # TEST mock
    "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e",
    "0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044",
    "0xe33E9E479dF8802cb0866d5d05258bEc4cF62948",
    "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b",
    "0xcA11bde05977b3631167028862bE2a173976CA11",
    "0x78F3556b67E17Df817D51Ef5a990cDaF09E8d3A9",
    "0x8366a39cc670b4001a1121b8f6a443a643e40951",
    "0x86adcd56e3f899e3ac7a2d85f3eff68dbc3b5856",
    "0xfe5f5c5258579ddfa9fec20db1a0fcb46c70ecdf",
    "0x8387A37e",  # truncated fakes ignored by full match
    "0x0000000000000000000000000000000000000000",
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
  ]
}
STATE = BASE / "alerts" / "timberia_poll_state.json"
LOG = BASE / "alerts" / "timberia_poll.jsonl"
STATUS_FILE = BASE / "alerts" / "timberia_poll_status.json"

def now():
  return datetime.now(SH).isoformat(timespec="milliseconds")

def log(row):
  LOG.parent.mkdir(parents=True, exist_ok=True)
  with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": now(), **row}, ensure_ascii=False) + "\n")

def save_status(d):
  STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
  STATUS_FILE.write_text(json.dumps({"ts": now(), **d}, ensure_ascii=False, indent=2))

def load_state():
  try:
    return json.loads(STATE.read_text())
  except Exception:
    return {"bought": [], "seen_tweet_ids": [], "last_ca": None}

def save_state(st):
  STATE.parent.mkdir(parents=True, exist_ok=True)
  STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2))

def http_json(url, timeout=12):
  req = urllib.request.Request(url, headers={"User-Agent": "timberia-poll/1.0"})
  with urllib.request.urlopen(req, timeout=timeout) as r:
    return json.loads(r.read().decode())

def rpc_call(to, data):
  body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                     "params": [{"to": to, "data": data}, "latest"]}).encode()
  req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
  with urllib.request.urlopen(req, timeout=15) as r:
    j = json.load(r)
  if "error" in j:
    raise RuntimeError(j)
  return j["result"]

def pons_launched(token: str) -> bool:
  """getLaunchedToken(address) — treat non-empty curve / exists flag as launched."""
  # try common selector getLaunchedToken(address)
  from Crypto.Hash import keccak
  def sel(sig):
    k = keccak.new(digest_bits=256); k.update(sig.encode()); return k.hexdigest()[:8]
  pad = token.lower().replace("0x", "").zfill(64)
  for sig in ("getLaunchedToken(address)", "tokenInfo(address)", "launchedTokens(address)"):
    try:
      out = rpc_call(FACTORY, "0x" + sel(sig) + pad)
      h = out[2:] if out.startswith("0x") else out
      if not h or set(h) == {"0"}:
        continue
      # if any non-zero word, likely exists
      words = [int(h[i:i+64], 16) for i in range(0, len(h), 64)]
      if any(w != 0 for w in words):
        return True
    except Exception:
      continue
  return False

def extract_cas(text: str) -> list[str]:
  out = []
  for m in EVM_CA.finditer(text or ""):
    ca = m.group(1)
    if ca.lower() in BLOCKLIST:
      continue
    if len(ca) != 42:
      continue
    out.append(ca)
  # dedupe preserve order
  seen = set(); res = []
  for c in out:
    if c.lower() not in seen:
      seen.add(c.lower()); res.append(c)
  return res

def site_signals():
  info = {}
  try:
    info["stats"] = http_json("https://timberia.io/api/public/stats")
  except Exception as e:
    info["stats_err"] = type(e).__name__
  try:
    info["token"] = http_json("https://timberia.io/api/public/token")
  except Exception as e:
    info["token_err"] = type(e).__name__
  return info

def consider_ca(ca: str, source: str, st: dict) -> dict | None:
  cl = ca.lower()
  if cl in BLOCKLIST:
    return None
  if cl in [x.lower() for x in st.get("alerted") or []]:
    return {"ok": True, "skipped": "already_alerted", "ca": ca}
  launched = None
  try:
    launched = pons_launched(ca)
  except Exception as e:
    launched = f"err:{e}"
  log({"event": "ca_candidate", "ca": ca, "source": source, "pons_launched": launched})
  if cl == "0xf7d128fcf42606ae255645b7072d540053e13367":
    return None

  alert = {
    "ts": now(),
    "ca": ca,
    "source": source,
    "chain": "robinhood",
    "symbol": "TIM",
    "pons_launched": launched,
    "pons_url": f"https://ponsfamily.com/launchpad/{ca}",
    "site": "https://timberia.io/",
    "mode": "notify_only",
  }
  alert_path = BASE / "alerts" / "timberia_ca_alert.json"
  alert_path.write_text(json.dumps(alert, ensure_ascii=False, indent=2))
  # also append history
  with open(BASE / "alerts" / "timberia_ca_alerts.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(alert, ensure_ascii=False) + "\n")
  st.setdefault("alerted", []).append(ca)
  st["last_ca"] = ca
  st["last_alert"] = alert
  save_state(st)
  log({"event": "ca_alert", "ca": ca, "source": source, "pons_launched": launched})

  # optional buy only if TIMBERIA_LIVE_BUY=1
  if os.environ.get("TIMBERIA_LIVE_BUY", "0").strip() not in ("1", "true", "yes"):
    return {"ok": True, "alerted": True, "ca": ca, "buy": None, "alert": alert}

  eth = os.environ.get("TIMBERIA_BUY_ETH", "0.003")
  time.sleep(float(os.environ.get("TIMBERIA_TAX_WAIT_SEC", "5")))
  result = fire_buy(
    ca=ca, chain="robinhood", project="Timberia", handle=HANDLE,
    source="6551", amount=eth,
    extra={"layer": "timberia_6551_poll", "pons_launched": launched, "src": source},
  )
  st.setdefault("bought", []).append(ca)
  st["last_buy"] = result
  save_state(st)
  log({"event": "buy_attempt", "ca": ca, "result": result})
  (BASE / "alerts" / "timberia_buy_notify.json").write_text(
    json.dumps({"ts": now(), "ca": ca, "result": result}, ensure_ascii=False, indent=2)
  )
  return {"ok": True, "alerted": True, "ca": ca, "buy": result, "alert": alert}

def poll_once(st: dict) -> dict:
  summary = {"tweets": 0, "cas": [], "site": None}
  # site
  site = site_signals()
  summary["site"] = {
    "showCa": (site.get("stats") or {}).get("showCa"),
    "token": site.get("token"),
  }
  token = site.get("token") or {}
  # if official token API flips off TEST
  tca = (token.get("address") or token.get("ca") or token.get("token") or "")
  if isinstance(tca, dict):
    tca = tca.get("address") or ""
  sym = str(token.get("symbol") or token.get("name") or "").upper()
  if tca and isinstance(tca, str) and tca.startswith("0x") and len(tca) == 42:
    if sym not in ("TEST",) and tca.lower() != "0xf7d128fcf42606ae255645b7072d540053e13367":
      summary["cas"].append(("site_token", tca))
  # landing ca in stats?
  for k in ("landingCa", "ca", "tokenAddress", "timCa"):
    v = (site.get("stats") or {}).get(k)
    if isinstance(v, str) and v.startswith("0x") and len(v) == 42:
      summary["cas"].append(("site_stats", v))

  # tweets
  try:
    tweets = user_tweets(HANDLE, 10)
  except X6551Error as e:
    summary["tweet_error"] = str(e)
    tweets = []
  summary["tweets"] = len(tweets)
  seen = set(st.get("seen_tweet_ids") or [])
  for tw in tweets:
    tid = str(tw.get("id") or "")
    text = tw.get("text") or ""
    for ca in extract_cas(text):
      summary["cas"].append((f"tweet:{tid}", ca))
    if tid:
      seen.add(tid)
  st["seen_tweet_ids"] = list(seen)[-200:]
  save_state(st)

  # fire first new ca
  bought = {x.lower() for x in st.get("bought") or []}
  for source, ca in summary["cas"]:
    if ca.lower() in bought or ca.lower() in BLOCKLIST:
      continue
    # require either pons launched OR showCa true OR site_token non-TEST
    show = (site.get("stats") or {}).get("showCa")
    ok_gate = False
    try:
      if pons_launched(ca):
        ok_gate = True
    except Exception:
      pass
    if show is True:
      ok_gate = True
    if source.startswith("site_"):
      ok_gate = True
    # official tweet with CA after launch window: allow if showCa or pons
    if not ok_gate and source.startswith("tweet"):
      # still try pons; if unknown allow tweet CA only if text strongly signals
      if re.search(r"\b(CA|contract|\$TIM)\b", source.split(":",1)[-1] and text if False else (tw.get("text") if False else ""), re.I):
        pass
      # re-get text from tweets list
      for tw in tweets:
        if f"tweet:{tw.get('id')}" == source:
          if re.search(r"(?i)(\$TIM|token\s*ca|contract\s*address|ca\s*:)", tw.get("text") or ""):
            ok_gate = True
    if not ok_gate:
      log({"event": "ca_hold", "ca": ca, "source": source, "reason": "unverified"})
      continue
    return {"summary": summary, "buy": consider_ca(ca, source, st)}
  return {"summary": summary, "buy": None}

def main():
  interval = float(os.environ.get("TIMBERIA_POLL_SEC", "20"))
  st = load_state()
  log({"event": "start", "interval": interval, "dry_run": load_config().get("dry_run")})
  while True:
    try:
      out = poll_once(st)
      save_status({"ok": True, "interval": interval, "last": out.get("summary"), "buy": out.get("buy"),
                   "dry_run": load_config().get("dry_run")})
      if out.get("buy") and not out["buy"].get("skipped"):
        # keep running but slow after buy
        interval = max(interval, 60)
    except Exception as e:
      log({"event": "error", "error": type(e).__name__ + ":" + str(e)[:240]})
      save_status({"ok": False, "error": type(e).__name__ + ":" + str(e)[:240]})
    time.sleep(interval)

if __name__ == "__main__":
  main()
