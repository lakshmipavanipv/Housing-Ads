"""Ring QA Portal - local web server.

Run:  python server.py                  (ESP32 USB bridge boards if any are plugged in, else laptop Bluetooth)
      python server.py --backend local  (force the laptop's own Bluetooth)
      python server.py --backend mock   (30 simulated rings, no hardware)
Then open http://localhost:8000
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import storage
from ble.backends import make_backend
from ble.manager import RingManager
from profiles_store import ProfileStore
from stages import LIVE_VARS, StageEngine

ROOT = Path(__file__).parent
CFG = {"backend": "auto", "mock_rings": 30, "speed": 1.0}
APP = {"backend": None, "backend_error": None, "ring_target": 30}

store = ProfileStore(ROOT / "profiles")
mgr = RingManager(store)
engine = StageEngine(mgr)
app = FastAPI(title="Ring QA Portal")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def auto_backend():
    """ESP32 bridge boards when any are on USB, otherwise the laptop's own Bluetooth."""
    try:
        from ble.bridge import detect_ports
        return "dongles" if detect_ports() else "local"
    except Exception:
        return "local"


def set_backend(mode):
    if mode == "auto":
        mode = auto_backend()
    engine.reset()
    try:
        mgr.set_backend(make_backend(mode, store, CFG["mock_rings"], CFG["speed"]))
        APP["backend_error"] = None
    except Exception as e:
        mgr.set_backend(None)
        APP["backend_error"] = f"{type(e).__name__}: {e}"
        if mode == "local" and isinstance(e, ImportError):
            APP["backend_error"] = "Python package 'bleak' is not installed. Run: pip install bleak"
    engine.time_scale = CFG["speed"] if mode == "mock" else 1.0
    APP["backend"] = mode


@app.on_event("startup")
async def _startup():
    storage.init()
    if APP["backend"] is None:
        set_backend(CFG["backend"])
    mgr.start_watchdog()  # keeps every connected ring connected (auto-reconnect + keep-alive)


def bad(e):
    return HTTPException(400, f"{e}")


def snapshot():
    return {"backend": APP["backend"], "backend_error": APP["backend_error"], "ring_target": APP["ring_target"],
            "profile_name": store.active_name, "scanning": mgr.scanning, "server_time": time.time(),
            "rings": mgr.ring_list(), "stages": engine.snapshot(),
            "dongles": mgr.backend.status() if hasattr(mgr.backend, "status") else []}


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            await sock.send_text(json.dumps(snapshot(), default=str))
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.get("/api/state")
async def state():
    return snapshot()


# ---------- connection ----------
@app.post("/api/backend")
async def api_backend(body: dict = Body(...)):
    if any(r.get("connected") for r in mgr.rings.values()):
        await mgr.disconnect_all()
    set_backend(body.get("mode", "local"))
    return {"backend": APP["backend"], "error": APP["backend_error"]}


@app.post("/api/ring_target")
async def api_target(body: dict = Body(...)):
    APP["ring_target"] = max(1, int(body.get("n", 30)))
    return {"ring_target": APP["ring_target"]}


@app.post("/api/scan")
async def api_scan():
    try:
        found = await mgr.scan()
    except Exception as e:
        raise bad(e)
    return {"found": len(found)}


@app.post("/api/connect")
async def api_connect(body: dict = Body(...)):
    addr = body.get("addr")
    if addr not in mgr.rings:
        raise HTTPException(404, "unknown ring - search first")
    ok = await mgr.connect(addr)
    if not ok:
        raise bad(mgr.rings[addr]["error"])
    return {"connected": True}


@app.post("/api/connect_all")
async def api_connect_all():
    if not mgr.rings:
        raise bad("No rings found yet - click Search first")
    n = await mgr.connect_all()
    return {"connected": n, "total": len(mgr.rings)}


@app.post("/api/disconnect_all")
async def api_disconnect_all():
    await mgr.disconnect_all()
    return {"ok": True}


@app.post("/api/buzz")
async def api_buzz(body: dict = Body(...)):
    on = bool(body.get("on", True))
    addrs = [a for a, r in mgr.rings.items() if r.get("connected")] if body.get("all") else [body.get("addr")]
    if body.get("all") and not addrs:
        raise bad("No connected rings")
    for a in addrs:
        if a not in mgr.rings:
            raise HTTPException(404, "unknown ring")
        if on and not mgr.rings[a].get("connected"):
            raise bad(f"{mgr.rings[a]['unit_id']} is not connected")
        mgr.start_buzz(a) if on else mgr.stop_buzz(a)
    return {"count": len(addrs)}


@app.post("/api/raw")
async def api_raw(body: dict = Body(...)):
    """Debug: send one Jieli body (hex: CMD Key KeyFlag + payload) to one ring or all connected rings; returns reply payloads."""
    data = bytes.fromhex(body["hex"])
    addrs = [a for a, r in mgr.rings.items() if r.get("connected")] if body.get("all") else [body.get("addr")]

    async def one(a):
        try:
            return a, (await mgr.jieli_request(a, {}, data)).hex()
        except Exception as e:
            return a, f"ERR {e}"
    return {mgr.rings[a]["unit_id"]: v for a, v in await asyncio.gather(*(one(a) for a in addrs))}


@app.post("/api/bt/seen")
async def api_seen(body: dict = Body(...)):
    engine.bt_seen[body["addr"]] = bool(body.get("ok"))
    return {"ok": True}


# ---------- stages ----------
@app.post("/api/stage/{stage}/start")
async def api_stage_start(stage: str, body: dict = Body(default={})):
    if not engine.connected():
        raise bad("No connected rings - connect rings on the Bluetooth tab first")
    try:
        engine.start(stage, body)
    except Exception as e:
        raise bad(e)
    return {"started": stage}


@app.post("/api/stage/{stage}/stop")
async def api_stage_stop(stage: str):
    engine.stop(stage)
    return {"stopped": stage}


@app.post("/api/mode")
async def api_mode(body: dict = Body(...)):
    if not engine.connected():
        raise bad("No connected rings")
    try:
        return await engine.apply_mode(body.get("mode"))
    except Exception as e:
        raise bad(e)


@app.post("/api/save")
async def api_save(body: dict = Body(...)):
    stage, batch, tester = body.get("stage"), (body.get("batch") or "").strip(), (body.get("tester") or "").strip()
    if not batch or not tester:
        raise bad("Enter Batch name and Tester name at the top before saving")
    rows, started = engine.export(stage)
    if not rows:
        raise bad(f"No {stage} results to save yet - run the stage first")
    bid = storage.save_stage(batch, tester, APP["ring_target"], stage, started, rows)
    return {"batch_id": bid, "saved": len(rows)}


# ---------- reports ----------
@app.get("/api/batches")
async def api_batches():
    return storage.list_batches()


@app.get("/api/batches/{bid}")
async def api_batch(bid: int):
    d = storage.batch_detail(bid)
    if not d:
        raise HTTPException(404, "batch not found")
    return d


@app.get("/api/batches/{bid}/csv")
async def api_batch_csv(bid: int):
    data = storage.batch_csv(bid)
    if data is None:
        raise HTTPException(404, "batch not found")
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="batch_{bid}.csv"'})


# ---------- profiles ----------
@app.get("/api/profile")
async def api_profile():
    return {"name": store.active_name, "profile": store.active, "profiles": store.list(),
            "live_vars": LIVE_VARS}


@app.put("/api/profile")
async def api_profile_save(body: dict = Body(...)):
    try:
        store.save(body["profile"], body.get("name"))
    except Exception as e:
        raise bad(e)
    return {"name": store.active_name}


@app.post("/api/profile/load")
async def api_profile_load(body: dict = Body(...)):
    try:
        store.load(body["name"])
    except Exception as e:
        raise bad(e)
    return {"name": store.active_name}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ring QA Portal")
    ap.add_argument("--backend", choices=["auto", "local", "mock", "dongles"], default="auto",
                    help="auto (default) = ESP32 boards if plugged in, else laptop Bluetooth; "
                         "local = laptop Bluetooth, dongles = ESP32 USB bridge boards, mock = simulator")
    ap.add_argument("--rings", type=int, default=30, help="number of simulated rings (mock only)")
    ap.add_argument("--speed", type=float, default=1.0, help="mock time speed-up, e.g. 30 = 1 h in 2 min")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    CFG.update(backend=a.backend, mock_rings=a.rings, speed=a.speed)
    import uvicorn
    uvicorn.run(app, host=a.host, port=a.port)
