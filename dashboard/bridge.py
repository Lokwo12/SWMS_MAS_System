"""
SWMS Web Dashboard Bridge
Tails log/logger_events.txt, parses logger output lines,
maintains live system state, and broadcasts via WebSocket.
"""

import asyncio
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

BASE_DIR   = Path(__file__).parent.parent
LOG_FILE   = BASE_DIR / "log" / "logger_events.txt"
STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Log line parser
# ---------------------------------------------------------------------------
# Matches:  [logger] INFO  event_name  key=val key=val ...
LINE_RE  = re.compile(r'\[logger\]\s+(INFO|WARN|ERROR)\s+(\S+)\s*(.*)', re.IGNORECASE)
FIELD_RE = re.compile(r'(\w+)=([^\s]+)')

def parse_line(raw: str) -> dict | None:
    m = LINE_RE.match(raw.strip())
    if not m:
        return None
    level, name, rest = m.groups()
    fields = {}
    for k, v in FIELD_RE.findall(rest):
        # rename fill-level field 'level' -> 'lvl' to avoid collision with severity
        if k == 'level':
            fields['lvl'] = v.rstrip('%')
        else:
            fields[k] = v
    return {"ts": time.time(), "level": level.lower(), "name": name, **fields}

# ---------------------------------------------------------------------------
# Live state
# ---------------------------------------------------------------------------
def fresh_state() -> dict:
    return {
        "bins": {
            "smartbin1": {"level": 0, "state": "idle", "history": [], "collections": 0, "last_emptied": None},
            "smartbin2": {"level": 0, "state": "idle", "history": [], "collections": 0, "last_emptied": None},
            "smartbin3": {"level": 0, "state": "idle", "history": [], "collections": 0, "last_emptied": None},
        },
        "trucks": {
            "truck1": {"state": "idle"},
            "truck2": {"state": "idle"},
            "truck3": {"state": "idle"},
        },
        "cc": {
            "req_seq":   0,
            "completed": 0,
            "failed":    0,
            "failures":  [],
            "req_times": [],   # timestamps of last 100 completions (for rate calc)
            "inflight":  {},
        },
        "started_at": time.time(),
        "events": [],
    }

state   = fresh_state()
recent  : deque = deque(maxlen=500)
clients : Set[WebSocket] = set()

def req_int(ev: dict) -> int | None:
    try:
        return int(ev.get("req", ""))
    except (ValueError, TypeError):
        return None

def update_state(ev: dict) -> None:
    name     = ev["name"]
    bin_name = ev.get("bin", "")
    truck    = ev.get("truck", "")
    rid      = req_int(ev)

    recent.appendleft(ev)
    state["events"] = list(recent)

    bins   = state["bins"]
    trucks = state["trucks"]
    cc     = state["cc"]

    # -- Bin fill level -------------------------------------------------------
    if name == "level_update" and bin_name and "lvl" in ev:
        if bin_name in bins:
            try:
                lvl = int(ev["lvl"])
                bins[bin_name]["level"] = lvl
                st = bins[bin_name]["state"]
                if lvl >= 100 and st not in ("full", "alerting"):
                    bins[bin_name]["state"] = "full"
                elif lvl < 100 and st == "full":
                    bins[bin_name]["state"] = "idle"
                hist = bins[bin_name].setdefault("history", [])
                # detect new fill cycle that started without a bin_reset
                if hist and lvl < hist[-1]["level"]:
                    hist.clear()
                if not hist or hist[-1]["level"] != lvl:
                    hist.append({"level": lvl, "ts": ev["ts"]})
            except ValueError:
                pass

    # -- Bin full (emitted by smart bin) -------------------------------------
    elif name == "bin_full" and bin_name:
        if bin_name in bins:
            bins[bin_name]["state"] = "full"

    # -- CC received bin_full alert ------------------------------------------
    elif name == "bin_full_received" and bin_name:
        if bin_name in bins:
            bins[bin_name]["state"] = "alerting"

    # -- Request opened -------------------------------------------------------
    elif name == "request_opened" and rid:
        cc["req_seq"] = max(cc["req_seq"], rid)
        cc["inflight"][str(rid)] = {
            "req": rid, "bin": bin_name, "truck": "",
            "stage": "opened", "ts": ev["ts"],
        }
        if bin_name in bins:
            bins[bin_name]["state"] = "alerting"

    # -- Pickup dispatched to truck -------------------------------------------
    elif name in ("pickup_dispatched", "pickup_request_sent") and rid:
        cc["req_seq"] = max(cc["req_seq"], rid)
        key = str(rid)
        if key not in cc["inflight"]:
            cc["inflight"][key] = {
                "req": rid, "bin": bin_name, "truck": truck,
                "stage": "awaiting_reply", "ts": ev["ts"],
            }
        else:
            inf = cc["inflight"][key]
            inf["truck"] = truck or inf.get("truck", "")
            inf["bin"]   = bin_name or inf.get("bin", "")
            inf["stage"] = "awaiting_reply"
        if truck in trucks:
            trucks[truck]["state"] = "busy"

    # -- Truck accepted the job -----------------------------------------------
    elif name == "pickup_accepted" and rid:
        key = str(rid)
        if key not in cc["inflight"]:
            cc["inflight"][key] = {
                "req": rid, "bin": bin_name, "truck": truck,
                "stage": "accepted", "ts": ev["ts"],
            }
        else:
            inf = cc["inflight"][key]
            inf["stage"] = "accepted"
            inf["bin"]   = bin_name or inf.get("bin", "")
            inf["truck"] = truck or inf.get("truck", "")

    # -- CC confirmed: job accepted -------------------------------------------
    elif name == "job_accepted" and rid:
        key = str(rid)
        if key not in cc["inflight"]:
            cc["inflight"][key] = {
                "req": rid, "bin": bin_name, "truck": truck,
                "stage": "moving", "ts": ev["ts"],
            }
        else:
            inf = cc["inflight"][key]
            inf["stage"] = "moving"
            inf["bin"]   = bin_name or inf.get("bin", "")
            inf["truck"] = truck or inf.get("truck", "")
        if truck in trucks:
            trucks[truck]["state"] = "moving"

    # -- Truck at bin, collecting ---------------------------------------------
    elif name == "collection_done" and rid:
        key = str(rid)
        if key not in cc["inflight"]:
            cc["inflight"][key] = {
                "req": rid, "bin": bin_name, "truck": truck,
                "stage": "collecting", "ts": ev["ts"],
            }
        else:
            inf = cc["inflight"][key]
            inf["stage"] = "collecting"
            inf["bin"]   = bin_name or inf.get("bin", "")
            inf["truck"] = truck or inf.get("truck", "")
        if truck in trucks:
            trucks[truck]["state"] = "collecting"

    # -- Collection complete, truck heading back -------------------------------
    elif name == "collection_complete" and rid:
        key = str(rid)
        eff_truck = truck
        if key in cc["inflight"]:
            inf = cc["inflight"][key]
            inf["stage"] = "awaiting_reset"
            inf["bin"]   = bin_name or inf.get("bin", "")
            eff_truck    = truck or inf.get("truck", "")
            inf["truck"] = eff_truck
        if eff_truck in trucks:
            trucks[eff_truck]["state"] = "idle"

    # -- Bin reset to empty ---------------------------------------------------
    elif name == "bin_reset":
        if bin_name in bins:
            bins[bin_name]["level"] = 0
            bins[bin_name]["state"] = "idle"
            bins[bin_name]["history"] = []
            bins[bin_name]["collections"] = bins[bin_name].get("collections", 0) + 1
            bins[bin_name]["last_emptied"] = ev["ts"]
        if rid:
            key = str(rid)
            if key in cc["inflight"]:
                inf = cc["inflight"][key]
                inf["stage"] = "awaiting_close"
                inf["bin"]   = bin_name or inf.get("bin", "")

    # -- Request fully closed -------------------------------------------------
    elif name == "request_closed" and rid:
        cc["inflight"].pop(str(rid), None)
        cc["completed"] += 1
        cc["req_times"].append(ev["ts"])
        if len(cc["req_times"]) > 100:
            cc["req_times"] = cc["req_times"][-100:]
        if bin_name in bins and bins[bin_name]["state"] != "idle":
            bins[bin_name]["state"] = "idle"

    # -- Truck refused, now free again ----------------------------------------
    elif name == "truck_refused" and truck:
        if truck in trucks:
            trucks[truck]["state"] = "idle"
        cc["failed"] += 1
        cc["failures"].append({"type": name, "bin": bin_name, "truck": truck, "ts": ev["ts"]})
        if len(cc["failures"]) > 100:
            cc["failures"] = cc["failures"][-100:]

    # -- Failure / warning events --------------------------------------------
    elif name in ("no_truck_available_retry", "completion_timeout", "reply_timeout"):
        cc["failed"] += 1
        cc["failures"].append({"type": name, "bin": bin_name, "truck": truck, "ts": ev["ts"]})
        if len(cc["failures"]) > 100:
            cc["failures"] = cc["failures"][-100:]

# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------
async def broadcast(msg: str) -> None:
    dead = set()
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)

# ---------------------------------------------------------------------------
# File tailer  — reads from start on startup, detects truncation
# ---------------------------------------------------------------------------
async def tail_log() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    while True:                      # outer loop: re-open after truncation
        if not LOG_FILE.exists():
            LOG_FILE.touch()

        with open(LOG_FILE, "r") as f:
            catching_up = True       # True while replaying existing content

            while True:
                line = f.readline()

                if line:
                    ev = parse_line(line)
                    if ev:
                        update_state(ev)
                        if not catching_up:
                            # Live event — push to all connected clients
                            await broadcast(json.dumps(
                                {"type": "update", "state": state, "event": ev}
                            ))
                else:
                    # EOF reached
                    if catching_up:
                        # Finished replaying history — notify connected clients
                        catching_up = False
                        await broadcast(json.dumps({"type": "init", "state": state}))

                    # Detect file truncation (startmas.sh clears the file)
                    cur = f.tell()
                    try:
                        file_size = LOG_FILE.stat().st_size
                    except FileNotFoundError:
                        break          # file removed — re-open outer loop

                    if cur > file_size:
                        # File was truncated → reset state and re-read from 0
                        state.clear()
                        state.update(fresh_state())  # sets fresh started_at
                        recent.clear()
                        await broadcast(json.dumps(
                            {"type": "reset", "state": state}
                        ))
                        break          # re-open file

                    await asyncio.sleep(0.05)

# ---------------------------------------------------------------------------
# Stale inflight cleanup  — removes entries stuck in terminal stages > TTL
# ---------------------------------------------------------------------------
async def cleanup_stale_inflight() -> None:
    TTL = 90  # seconds
    while True:
        await asyncio.sleep(30)
        now = time.time()
        cc = state["cc"]
        stale = [
            k for k, inf in list(cc["inflight"].items())
            if now - inf.get("ts", now) > TTL
            and inf.get("stage") in ("awaiting_close", "awaiting_reset")
        ]
        for k in stale:
            cc["inflight"].pop(k, None)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(tail_log())
    asyncio.create_task(cleanup_stale_inflight())

@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text())

@app.get("/state")
async def get_state() -> dict:
    return state

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    # Send current state immediately on connect
    await ws.send_text(json.dumps({"type": "init", "state": state}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
