#!/usr/bin/env python3
"""Standalone listing-time / listing-signal scanner daemon.

Runs scan_listing_ca.py (parallel site fetches) then extract_listing_times.py
on an interval, writing:
  listing_scan_latest.json / listing_scan_previous.json
  listing_times.json (+ push-radar mirror)
  listing_scan_status.json  (daemon heartbeat)

The main 开盘与CA预警 pipeline reads these files; it no longer runs the slow
sequential site crawl itself.

Never invents listing_at. Never prints tokens/secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
STATUS = BASE / "listing_scan_status.json"
PIDFILE = BASE / "listing_scan.pid"
LOG = BASE / "listing_scan_daemon.log"
SH = ZoneInfo("Asia/Shanghai")
PY = sys.executable


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def write_status(obj: dict) -> None:
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS)


def run_once(*, workers: int, publish: bool) -> dict:
    t0 = time.time()
    out: dict = {"at": now_iso(), "workers": workers, "ok": False}
    env = os.environ.copy()
    env["LISTING_SCAN_WORKERS"] = str(workers)

    steps = [
        ("scan_listing_ca.py", [PY, str(BASE / "scan_listing_ca.py"), "--workers", str(workers)], 1200),
        ("extract_listing_times.py", [PY, str(BASE / "extract_listing_times.py")], 300),
    ]
    step_results = []
    for name, cmd, timeout in steps:
        st = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=str(BASE), env=env, capture_output=True, text=True, timeout=timeout,
            )
            rc = proc.returncode
            # keep last 30 lines of stdout for status (no secrets expected)
            tail = "\n".join((proc.stdout or "").splitlines()[-30:])
            err_tail = "\n".join((proc.stderr or "").splitlines()[-10:])
            step_results.append({
                "name": name, "rc": rc, "elapsed_s": round(time.time() - st, 1),
                "stdout_tail": tail[-2000:], "stderr_tail": err_tail[-500:],
            })
            print(f"[{now_iso()}] {name} rc={rc} elapsed={time.time()-st:.1f}s", flush=True)
            if tail:
                print(tail, flush=True)
            if rc != 0:
                out["ok"] = False
                out["failed"] = name
                out["steps"] = step_results
                out["elapsed_s"] = round(time.time() - t0, 1)
                write_status(out)
                return out
        except subprocess.TimeoutExpired:
            step_results.append({"name": name, "rc": 124, "elapsed_s": round(time.time() - st, 1)})
            print(f"[{now_iso()}] {name} TIMEOUT>{timeout}s", flush=True)
            out["ok"] = False
            out["failed"] = name
            out["steps"] = step_results
            out["elapsed_s"] = round(time.time() - t0, 1)
            write_status(out)
            return out

    if publish:
        try:
            from publish_pages_file import put_file, put_file_to_branch
            local = Path("/workspace/push-radar/data/listing_times.json")
            if not local.is_file():
                local = BASE / "listing_times.json"
            if local.is_file():
                put_file(local, "public/data/listing_times.json",
                         message="data: listing_times (listing-scan daemon)")
                put_file_to_branch(local, "data/listing_times.json", "gh-pages",
                                   message="data: listing_times (listing-scan daemon) (gh-pages)")
                step_results.append({"name": "publish_listing_times", "rc": 0})
        except Exception as e:
            step_results.append({"name": "publish_listing_times", "rc": 1, "error": str(e)[:200]})
            print(f"[{now_iso()}] publish warn: {e}", flush=True)

    out["ok"] = True
    out["steps"] = step_results
    out["elapsed_s"] = round(time.time() - t0, 1)
    # pull digest numbers from listing_scan_latest if present
    try:
        latest = json.loads((BASE / "listing_scan_latest.json").read_text(encoding="utf-8"))
        out["watchlist_count"] = latest.get("watchlist_count")
        out["new_cas"] = len(latest.get("new_cas") or [])
        out["new_listing_signals"] = len(latest.get("new_listing_signals") or [])
        out["checked_at"] = latest.get("checked_at_iso") or latest.get("checked_at")
    except Exception:
        pass
    write_status(out)
    print(f"[{now_iso()}] listing_scan cycle ok elapsed={out['elapsed_s']}s", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=int(os.environ.get("LISTING_SCAN_INTERVAL", "900")),
                    help="seconds between cycles (default 900 = 15min)")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("LISTING_SCAN_WORKERS", "12")))
    ap.add_argument("--publish", action="store_true", help="publish listing_times.json to Pages")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        if STATUS.exists():
            print(STATUS.read_text(encoding="utf-8"))
        else:
            print("{}")
        return 0

    interval = max(120, int(args.interval))
    workers = max(1, min(32, int(args.workers)))

    if args.daemon:
        PIDFILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
        print(f"listing_scan_daemon start pid={os.getpid()} interval={interval}s workers={workers} publish={args.publish}",
              flush=True)
        try:
            while True:
                try:
                    run_once(workers=workers, publish=args.publish)
                except Exception as e:
                    print(f"[{now_iso()}] cycle exception: {e}", flush=True)
                    write_status({"at": now_iso(), "ok": False, "error": str(e)[:300]})
                time.sleep(interval)
        finally:
            try:
                if PIDFILE.exists() and PIDFILE.read_text().strip() == str(os.getpid()):
                    PIDFILE.unlink()
            except Exception:
                pass
        return 0

    # default: once
    res = run_once(workers=workers, publish=args.publish)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
