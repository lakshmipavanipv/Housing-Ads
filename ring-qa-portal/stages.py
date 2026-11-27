"""Test stages and their PASS/FAIL rules."""
import asyncio
import statistics
import time

LIVE_VARS = ("count", "steps", "hr", "spo2", "hrv", "sleep")
MODE_KEYS = ("time", "counter", "steps", "hr", "spo2", "sleep", "battery", "off", "on")
DONE = ("PASS", "FAIL")


def is_done(status):
    return bool(status) and status.split(":")[0] in DONE


def battery_update(row, pct, t, rules, scale=1.0, grace_min=1.0):
    """Update one ring's battery row with a new reading. Pure function (unit-tested)."""
    spec = float(rules.get("spec_full_charge_min", 60))
    tol = float(rules.get("battery_variance_pct", 20))
    stall = float(rules.get("battery_stall_min", 10))
    samples = row.setdefault("samples", [])
    prev = samples[-1][1] if samples else None
    samples.append([t, pct])
    row["current"] = pct
    if "start_pct" not in row:
        row.update(start_pct=pct, start_t=t, last_rise_t=t, est_total_min=round((100 - pct) * spec / 100, 1))
    if prev is not None and pct > prev:
        row["last_rise_t"] = t
    elapsed = (t - row["start_t"]) / 60 * scale
    gained = pct - row["start_pct"]
    rate = gained / elapsed if elapsed >= 1 and gained > 0 else 100 / spec   # % per minute
    row["elapsed_min"] = round(elapsed, 1)
    row["eta_min"] = 0 if pct >= 100 else round((100 - pct) / rate, 1)
    est = row["est_total_min"]
    if pct >= 100:
        row["full_at"] = t
        row["actual_min"] = round(elapsed, 1)
        row["variance_min"] = round(elapsed - est, 1)
        row["variance_pct"] = round((elapsed - est) / est * 100, 1) if est > 0 else 0.0
        ok = elapsed <= est * (1 + tol / 100) + grace_min
        row["status"] = "PASS" if ok else f"FAIL: {row['variance_pct']}% slower than estimate"
    elif (t - row["last_rise_t"]) / 60 * scale > stall:
        row["status"] = f"FAIL: no charge rise for {stall:g} min"
    elif est > 0 and elapsed > est * 1.5 + grace_min:
        row["status"] = "FAIL: not full by 1.5x estimate"
    else:
        row["status"] = "PENDING"  # still charging; the result is only ever PASS or FAIL
    return row


def charge_state(row, ring_charging):
    """Battery tab Status column: FULLY CHARGED / CHARGING / NEEDS CHARGING (separate from the PASS/FAIL result)."""
    pct = row.get("current")
    if pct is None:
        return None
    if pct >= 100:
        return "FULLY CHARGED"
    s = row.get("samples", [])
    rising = len(s) >= 2 and s[-1][1] > s[0][1]
    return "CHARGING" if ring_charging or rising else "NEEDS CHARGING"


def live_eval(var, row, rules, now, final=False):
    vals = [v for _, v in row.get("samples", []) if v is not None]
    last = row.get("last_data_t")
    if last is None:
        last = row.get("start_t", now)
    # At the end, judge on what was collected: a late gap must not cancel enough good readings.
    if now - last > float(rules.get("live_no_data_s", 30)) and not (final and len(vals) >= 3):
        return "FAIL: no data"
    if not vals:
        return "FAIL: no data" if final else "WAITING"
    if var in ("hr", "spo2", "hrv"):
        lo, hi = rules.get(var, [float("-inf"), float("inf")])
        if len(vals) < 3 and not final:
            return "MEASURING"
        avg = statistics.mean(vals)
        if lo <= avg <= hi and all(lo <= v <= hi for v in vals[-3:]):
            return "PASS"
        return f"FAIL: avg {avg:.0f} outside {lo}-{hi}"
    if var in ("steps", "count"):
        if vals[-1] > vals[0]:
            return "PASS"
        return "FAIL: value did not increase" if final else "MOVE RING"
    return "PASS"  # sleep: data returned


class StageEngine:
    def __init__(self, mgr):
        self.mgr = mgr
        self.stages = {}
        self.tasks = {}
        self.bt_seen = {}
        self.time_scale = 1.0

    @property
    def rules(self):
        return self.mgr.rules

    def connected(self):
        # rings the watchdog is reconnecting stay in the test (their commands wait for the link to return)
        return [a for a, r in self.mgr.rings.items() if r.get("connected") or r.get("keep")]

    def reset(self):
        for t in self.tasks.values():
            t.cancel()
        self.tasks.clear()
        self.stages.clear()
        self.bt_seen.clear()

    async def _read(self, addr, var):
        try:
            return await self.mgr.read_var(addr, var), None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    # ---------- bluetooth ----------
    def bt_status(self, r):
        if not r.get("connected"):
            if r.get("error"):
                return "FAIL: " + r["error"]
            return "PENDING" if r.get("found") else "FAIL: not found"
        seen = self.bt_seen.get(r["addr"])
        return "PASS" if seen is True else "FAIL: buzz not seen" if seen is False else "PENDING"

    # ---------- start / stop ----------
    def start(self, stage, params=None):
        params = params or {}
        self.stop(stage, finalize=False)
        st = self.stages[stage] = {"running": True, "started_at": time.time(), "rows": {}, "params": params}
        if stage == "battery":
            coro = self._battery(st)
        elif stage == "time":
            coro = self._time(st, params)
        elif stage in LIVE_VARS:
            coro = self._live(st, stage)
        else:
            raise ValueError(f"stage '{stage}' cannot be run")
        self.tasks[stage] = asyncio.create_task(self._wrap(stage, coro))

    async def _wrap(self, stage, coro):
        try:
            await coro
        except asyncio.CancelledError:
            pass
        finally:
            self._finalize(stage)

    def stop(self, stage, finalize=True):
        t = self.tasks.pop(stage, None)
        if t:
            t.cancel()
        if finalize:
            self._finalize(stage)

    def _finalize(self, stage):
        st = self.stages.get(stage)
        if not st or not st.get("running"):
            return
        st["running"] = False
        st["finished_at"] = time.time()
        for row in st["rows"].values():
            if stage in LIVE_VARS:
                row["status"] = live_eval(stage, row, self.rules, time.time(), final=True)
            elif stage == "battery" and not is_done(row.get("status")):
                row["status"] = "STOPPED before 100%"

    # ---------- battery: poll every battery_interval_s ----------
    async def _battery(self, st):
        interval = float(self.rules.get("battery_interval_s", 60)) / self.time_scale
        st["interval_s"] = interval
        grace = interval * self.time_scale / 60
        while True:
            addrs = [a for a in self.connected() if not is_done(st["rows"].get(a, {}).get("status"))]
            res = await asyncio.gather(*(self._read(a, "battery") for a in addrs))
            now = time.time()
            for a, (pct, err) in zip(addrs, res):
                row = st["rows"].setdefault(a, {})
                if err:
                    row["error"] = err
                    row.setdefault("status", "PENDING")  # read error shows in the battery column; result stays PASS/FAIL
                    continue
                row.pop("error", None)
                battery_update(row, int(pct), now, self.rules, self.time_scale, grace)
                row["charge_state"] = charge_state(row, self.mgr.rings.get(a, {}).get("charging"))
            st["last_poll"] = now
            if st["rows"] and all(is_done(r.get("status")) for r in st["rows"].values()):
                break
            await asyncio.sleep(interval)

    # ---------- time zone / time shift ----------
    async def _time(self, st, p):
        tz = p.get("tz_min")
        shift = float(p.get("shift_min") or 0)
        read_only = bool(p.get("read_only"))
        tol = float(self.rules.get("time_tolerance_s", 2))
        has_tz = "timezone" in self.mgr.profile.get("vars", {})

        if self.mgr.profile.get("vars", {}).get("time", {}).get("op") == "jieli_clock":
            return await self._time_jieli(st, tz, shift, read_only)

        async def one(addr):
            row = st["rows"][addr] = {"status": "RUNNING"}
            try:
                row["before_time"] = await self.mgr.read_var(addr, "time")
                if has_tz:
                    row["before_tz"] = await self.mgr.read_var(addr, "timezone")
                if read_only:
                    row["status"] = "READ"
                    return
                if has_tz and tz is not None:
                    await self.mgr.write_var(addr, "timezone", int(tz))
                row["target"] = int(time.time() + shift * 60)
                await self.mgr.write_var(addr, "time", row["target"])
                row["after_time"] = await self.mgr.read_var(addr, "time")
                if has_tz:
                    row["after_tz"] = await self.mgr.read_var(addr, "timezone")
                drift = round(row["after_time"] - (time.time() + shift * 60), 1)
                row["drift_s"] = drift
                tz_ok = not has_tz or tz is None or row["after_tz"] == int(tz)
                if abs(drift) > tol:
                    row["status"] = f"FAIL: drift {drift}s"
                elif not tz_ok:
                    row["status"] = "FAIL: time zone not applied"
                else:
                    row["status"] = "PASS"
            except Exception as e:
                row["status"] = f"FAIL: {type(e).__name__}: {e}"

        await asyncio.gather(*(one(a) for a in self.connected()))

    async def _time_jieli(self, st, tz, shift, read_only):
        """SR16 has no clock getter (any HR-based read would switch the HR page on), so:
        Run  = set the wall clock ({2,1,0}) to UTC + time zone + shift, then wake the screen with a 'stop HR'
               frame so the ring shows its date/time page. PASS = the ring ACKed the set.
        Read = no ring commands: shows each ring's clock as kept since this portal last set it."""
        import datetime as _dt
        if tz is None:
            tz = -time.altzone // 60 if time.localtime().tm_isdst else -time.timezone // 60
        v = self.mgr.var("time")
        wake = v.get("wake")
        clock = self.mgr.__dict__.setdefault("_clock_set", {})   # addr -> (epoch set at, tz_min, shift_s)

        async def one(addr):
            row = st["rows"][addr] = {"status": "RUNNING"}
            if read_only:
                c = clock.get(addr)
                if not c:
                    row["status"] = "READ: not set in this session - press Apply to set it"
                    return
                set_at, ctz, cshift = c
                row["before_time"], row["before_tz"] = int(time.time() + cshift), ctz
                row["status"] = "READ: kept since set at " + _dt.datetime.fromtimestamp(set_at).strftime("%H:%M:%S")
                return
            try:
                target = time.time() + shift * 60
                wall = _dt.datetime.utcfromtimestamp(target) + _dt.timedelta(minutes=tz)
                body = bytes.fromhex(v["set"].replace("{now}", "")) + bytes(
                    [wall.year % 100, wall.month, wall.day, wall.hour, wall.minute, wall.second])
                await self.mgr.jieli_request(addr, v, body)
                clock[addr] = (time.time(), tz, shift * 60)
                row["target"], row["after_time"], row["after_tz"] = int(target), int(target), tz
                for i, w in enumerate([wake] if isinstance(wake, str) else (wake or [])):
                    try:
                        if i:
                            await asyncio.sleep(float(self.rules.get("time_wake_gap_s", 0.3)))
                        await self.mgr.jieli_request(addr, v, bytes.fromhex(w))
                    except Exception:
                        pass
                row["status"] = "PASS: clock set (ring ACKed) - date/time on screen"
            except Exception as e:
                row["status"] = f"FAIL: {type(e).__name__}: {e}"

        await asyncio.gather(*(one(a) for a in self.connected()))

    # ---------- modes (header click switches all rings) ----------
    async def apply_mode(self, mode):
        if mode not in MODE_KEYS:
            raise ValueError(f"unknown mode '{mode}'")
        st = self.stages.setdefault("modes", {"started_at": time.time(), "rows": {}, "running": False})
        st["last_mode"], st["last_at"] = mode, time.time()
        var = "power" if mode in ("off", "on") else "mode"

        def restatus(row):
            ms = row["modes"]
            if any(v.startswith("FAIL") for v in ms.values()):
                row["status"] = "FAIL"
            elif all(ms.get(k) == "OK" or str(ms.get(k)).startswith(("N/A", "OK:")) for k in MODE_KEYS):
                row["status"] = "PASS"
            else:
                row["status"] = "PENDING"

        tap_s = float(self.mgr.profile.get("vars", {}).get("mode", {}).get("tap_wait_s", 0) or 0)

        async def wait_tap(addr, row, live, t0):
            """Counter mode: PASS once the ring pushes a bead count ({2,0x53,0}) after the click."""
            loop = asyncio.get_running_loop()
            end = loop.time() + tap_s
            while loop.time() < end:
                if live.get("t") and live["t"] > t0 and live.get("value") is not None:
                    row["modes"]["counter"] = f"OK: count {live['value']}"
                    restatus(row)
                    return
                left = int(end - loop.time())
                row["modes"]["counter"] = f"WAITING: tap the ring ({left} s)"
                await asyncio.sleep(0.5)
            row["modes"]["counter"] = f"FAIL: no tap count within {int(tap_s)} s"
            restatus(row)

        async def one(addr):
            row = st["rows"].setdefault(addr, {"modes": {}})
            try:
                ok = await self.mgr.send_cmd(addr, var, mode, verify=True)
                row["modes"][mode] = "OK" if ok else "FAIL: read-back mismatch"
                show = (self.mgr.profile.get("vars", {}).get(var, {}).get("show_value") or {}).get(mode)
                if ok and show:
                    import datetime as _dt
                    cur = await self.mgr.stored_latest(addr, show)
                    if cur is None:
                        row["modes"][mode] = f"OK: 0 {show} (none stored)"
                    else:
                        at = _dt.datetime(2000, 1, 1) + _dt.timedelta(seconds=cur[0])
                        row["modes"][mode] = f"OK: {cur[1]:,} {show} (ring {at:%H:%M})"
                if ok and mode == "counter" and tap_s and "count" in self.mgr.profile.get("vars", {}):
                    loop = asyncio.get_running_loop()
                    live = self.mgr._live.setdefault((addr, "count"), {"armed": False, "value": None, "t": None})
                    old = self.tasks.pop(("tap", addr), None)
                    if old:
                        old.cancel()
                    row["modes"][mode] = f"WAITING: tap the ring ({int(tap_s)} s)"
                    self.tasks[("tap", addr)] = asyncio.create_task(wait_tap(addr, row, live, loop.time()))
            except NotImplementedError as e:
                row["modes"][mode] = f"N/A: {e}"
            except Exception as e:
                row["modes"][mode] = f"FAIL: {e}"
            restatus(row)
            return not row["modes"][mode].startswith("FAIL")

        addrs = self.connected()
        res = await asyncio.gather(*(one(a) for a in addrs))
        return {"ok": sum(res), "total": len(addrs)}

    # ---------- live data: poll every live_interval_s ----------
    async def _live(self, st, var):
        interval = float(self.rules.get("live_interval_s", 10))
        duration = float(self.rules.get("live_duration_s", 120))
        st["interval_s"], st["duration_s"] = interval, duration
        t0 = st["started_at"]
        try:
            await self._live_loop(st, var, interval, duration, t0)
        finally:
            await asyncio.gather(*(self.mgr.live_stop(a, var) for a in list(self.mgr.rings)),
                                 return_exceptions=True)

    async def _live_loop(self, st, var, interval, duration, t0):
        while True:
            addrs = self.connected()
            res = await asyncio.gather(*(self._read(a, var) for a in addrs))
            now = time.time()
            for a, (v, err) in zip(addrs, res):
                row = st["rows"].setdefault(a, {"samples": [], "start_t": t0})
                if err:
                    row["error"] = err
                else:
                    row.pop("error", None)
                    row["samples"].append([now, v])
                    row["current"] = v
                    row["last_data_t"] = now
                op = self.mgr.profile.get("vars", {}).get(var, {}).get("opcode")
                if op:
                    row["raw"] = self.mgr.rings.get(a, {}).get("raw", {}).get(f"{int(str(op), 16):02x}")
                vals = [x for _, x in row["samples"] if isinstance(x, (int, float))]
                if vals:
                    row.update(avg=round(statistics.mean(vals), 1), min=min(vals), max=max(vals))
                row["status"] = live_eval(var, row, self.rules, now)
            st["last_poll"] = now
            if duration and now - t0 >= duration:
                break
            await asyncio.sleep(interval)

    # ---------- snapshot / export ----------
    def snapshot(self):
        out = {}
        for k, st in self.stages.items():
            s = {kk: vv for kk, vv in st.items() if kk != "rows"}
            s["rows"] = {a: {kk: (vv[-60:] if kk == "samples" else vv) for kk, vv in r.items()}
                         for a, r in st["rows"].items()}
            out[k] = s
        out["bluetooth"] = {"rows": {a: {"seen": self.bt_seen.get(a), "status": self.bt_status(r)}
                                     for a, r in self.mgr.rings.items()}}
        return out

    def export(self, stage):
        rows = []
        st = self.stages.get(stage, {})
        for a, r in self.mgr.rings.items():
            base = {"addr": a, "name": r.get("name"), "unit_id": r.get("unit_id")}
            if stage == "bluetooth":
                rows.append({**base, "status": self.bt_status(r),
                             "values": {k: r.get(k) for k in ("found", "connected", "rssi", "error")} |
                             {"buzz_seen": self.bt_seen.get(a)}})
                continue
            row = st.get("rows", {}).get(a)
            if row is None:
                continue
            values = {k: v for k, v in row.items() if k != "samples"}
            rows.append({**base, "status": row.get("status") or "PENDING", "values": values,
                         "samples": row.get("samples", [])})
        return rows, st.get("started_at")
