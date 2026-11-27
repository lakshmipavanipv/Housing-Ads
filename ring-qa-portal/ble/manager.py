"""RingManager: everything the portal does to a ring goes through here, driven by the active profile."""
import asyncio
import time

from . import jieli, parsers


class RingManager:
    def __init__(self, store):
        self.store = store
        self.backend = None
        self.rings = {}       # addr -> {addr, name, unit_id, rssi, found, connected, error}
        self._locks = {}
        self._buzz = {}       # addr -> asyncio.Task
        self._notify = {}     # (addr, var) -> latest value
        self._cmd_sub = set()  # rings subscribed to the command-response notify characteristic
        self._cmd_wait = {}    # (addr, opcode) -> Future waiting for the response
        self.scanning = False
        self._rx = {}          # addr -> [header(flag, n), bytes] for multi-packet Jieli frames
        self._live = {}        # (addr, var) -> {"armed": bool, "value", "t"}
        self._stored = {}      # (addr, var) -> (ring_ts, value)
        self._pull = {}        # (addr, cmd, key) -> [bytes collected, Future]
        self._clock_wait = {}  # addr -> Future for the next {2,36,0} push (ring clock read)

    # ---------- profile helpers ----------
    @property
    def profile(self):
        return self.store.active

    @property
    def rules(self):
        return self.profile.get("rules", {})

    def var(self, name):
        v = self.profile.get("vars", {}).get(name)
        if not v:
            raise KeyError(f"variable '{name}' is not defined in the ring profile")
        return v

    def _svc(self, v):
        return v.get("service") or self.profile.get("service_uuid")

    def _jieli(self):
        return self.profile.get("protocol") == "jieli"

    def _lock(self, addr):
        return self._locks.setdefault(addr, asyncio.Lock())

    def _t(self):
        return float(self.rules.get("op_timeout_s", 10))

    def _b(self):
        if not self.backend:
            raise RuntimeError("No Bluetooth adapter available - check the Connection page")
        return self.backend

    def set_backend(self, backend):
        for t in self._buzz.values():
            t.cancel()
        self._buzz.clear()
        self._notify.clear()
        self._cmd_sub.clear()
        self.rings.clear()
        if self.backend and hasattr(self.backend, "close"):
            self.backend.close()
        self.backend = backend

    # ---------- discovery / connection ----------
    async def scan(self):
        self.scanning = True
        try:
            found = await self._b().scan(float(self.rules.get("scan_timeout_s", 6)),
                                         self.profile.get("name_prefix", ""),
                                         self.profile.get("scan_service", ""))
        finally:
            self.scanning = False
        for r in self.rings.values():
            r["found"] = False
        for f in sorted(found, key=lambda x: x["name"] or x["addr"]):
            r = self.rings.get(f["addr"])
            if not r:
                r = self.rings[f["addr"]] = {"addr": f["addr"], "name": f["name"],
                                             "unit_id": f"R{len(self.rings) + 1:03d}", "connected": False}
            r.update(found=True, rssi=f["rssi"], name=f["name"] or r["name"])
        return found

    async def connect(self, addr):
        r = self.rings[addr]
        try:
            async with self._lock(addr):
                b = self._b()
                if getattr(b, "own_timeouts", False):
                    await b.connect(addr)
                else:
                    await asyncio.wait_for(b.connect(addr), 20)
            self._cmd_sub.discard(addr)
            if self._jieli():
                await self._ensure_cmd_notify(addr)  # ring frames must be ACKed from the start
            r["connected"], r["error"], r["keep"] = True, None, True
            r["last_io"] = time.time()
        except Exception as e:
            r["connected"], r["error"] = False, f"{type(e).__name__}: {e}"
        return r["connected"]

    async def connect_all(self):
        sem = asyncio.Semaphore(int(self.rules.get("connect_parallel", 3)))

        async def one(a):
            async with sem:
                return await self.connect(a)

        todo = [a for a, r in self.rings.items() if not r.get("connected")]
        await asyncio.gather(*(one(a) for a in todo))
        return sum(1 for r in self.rings.values() if r.get("connected"))

    async def disconnect_all(self):
        for a in list(self.rings):
            self.stop_buzz(a)
            try:
                await self._b().disconnect(a)
            except Exception:
                pass
            self.rings[a]["connected"] = False
            self.rings[a]["keep"] = False  # user let go: the watchdog must not reconnect it
        self._notify.clear()
        self._cmd_sub.clear()

    # ---------- keep every ring connected ----------
    def start_watchdog(self):
        if not getattr(self, "_watchdog", None) or self._watchdog.done():
            self._watchdog = asyncio.create_task(self._watch_loop())

    async def _watch_loop(self):
        """Every watchdog_s: reconnect rings that dropped (unless the user disconnected them) and ping idle
        rings with a battery read so neither the ring nor Windows closes an idle link."""
        while True:
            await asyncio.sleep(float(self.rules.get("watchdog_s", 5)))
            if not self.backend or self.scanning:
                continue
            try:
                lost = []
                for a, r in list(self.rings.items()):
                    if not r.get("keep"):
                        continue
                    if not self.backend.is_connected(a):
                        if r.get("connected"):
                            r["connected"], r["error"] = False, "connection lost - reconnecting"
                        self._cmd_sub.discard(a)
                        self._rx.pop(a, None)
                        lost.append(a)
                sem = asyncio.Semaphore(int(self.rules.get("connect_parallel", 3)))

                async def again(a):
                    async with sem:
                        if await self.connect(a):
                            self.rings[a]["reconnects"] = self.rings[a].get("reconnects", 0) + 1
                        else:
                            self.rings[a]["keep"] = True  # keep trying next round
                await asyncio.gather(*(again(a) for a in lost))
                ka = float(self.rules.get("keepalive_s", 20))
                if ka > 0 and self._jieli():
                    bt = float(self.rules.get("battery_check_s", 10))  # feeds charging detection
                    idle = [a for a, r in self.rings.items() if r.get("connected") and r.get("keep")
                            and not self._lock(a).locked()
                            and (time.time() - r.get("last_io", 0) > ka
                                 or time.time() - (r.get("batt_hist") or [(0,)])[-1][0] > bt)]
                    await asyncio.gather(*(self._ping(a) for a in idle), return_exceptions=True)
            except Exception:
                pass

    async def wait_link(self, addr, timeout=45):
        """If the watchdog is reconnecting this ring, wait for the link to come back before sending."""
        r = self.rings.get(addr, {})
        end = time.time() + timeout
        while r.get("keep") and self.backend and not self.backend.is_connected(addr) and time.time() < end:
            await asyncio.sleep(0.5)

    async def _ping(self, addr):
        # The watchdog itself runs this, so it must never wait for a reconnect (only the watchdog reconnects -
        # waiting here would stall every reconnect for up to ~90 s). One quick attempt, hard-capped.
        if not self.backend or not self.backend.is_connected(addr):
            return
        v = self.var("battery")
        try:
            await asyncio.wait_for(
                self._jieli_request_once(addr, v, bytes.fromhex(v["frame"] + v.get("args", "")), timeout=5), 7)
        except Exception:
            pass

    def ring_list(self):
        out = []
        for a, r in self.rings.items():
            if self.backend and r.get("connected") and not self.backend.is_connected(a):
                r["connected"] = False
                r["error"] = "connection lost - reconnecting" if r.get("keep") else "connection lost"
            out.append({**r, "buzzing": self.buzzing(a)})
        return sorted(out, key=lambda r: r["unit_id"])

    # ---------- read / write ----------
    async def read_raw(self, addr, name):
        v = self.var(name)
        async with self._lock(addr):
            return await asyncio.wait_for(self._b().read(addr, self._svc(v), v["char"]), self._t())

    # ---------- opcode command channel (e.g. write 0xB9 to FF01, response arrives as notification) ----------
    async def _ensure_cmd_notify(self, addr):
        if addr in self._cmd_sub:
            return
        nch = self.profile.get("notify_char") or self.profile.get("cmd_char")

        def cb(data, addr=addr):
            if not data:
                return
            r = self.rings.get(addr)
            if self._jieli():
                acc = self._rx.get(addr)
                if acc is None:
                    if len(data) < 9 or data[0] != jieli.MAGIC:
                        return
                    acc = self._rx[addr] = [(data[1], (data[2] << 8) | data[3]), bytes(data[6:])]
                else:
                    acc[1] += bytes(data)
                (flag, n), body = acc
                if len(body) < n:
                    return  # wait for continuation packets
                self._rx.pop(addr, None)
                c, k, kf, payload = body[0], body[1], body[2], bytes(body[3:n])
                self._on_jieli_frame(addr, c, k, kf, payload)
                if r is not None:
                    r.setdefault("raw", {})[f"{c:02x}{k:02x}{kf:02x}"] = data.hex()
                if flag != jieli.FLAG_REPLY:
                    asyncio.ensure_future(self._b().write(addr, self.profile.get("service_uuid"), self.profile.get("cmd_char"),
                                                          jieli.ack(c, k, kf), True))
                fut = self._cmd_wait.get((addr, (c, k)))
                if fut and not fut.done():
                    fut.set_result(payload)
                return
            if r is not None:
                r.setdefault("raw", {})[f"{data[0]:02x}"] = data.hex()
            fut = self._cmd_wait.get((addr, data[0]))
            if fut and not fut.done():
                fut.set_result(data)

        async with self._lock(addr):
            await asyncio.wait_for(self._b().start_notify(addr, self.profile.get("service_uuid"), nch, cb), self._t())
        self._cmd_sub.add(addr)

    # ---------- SR16 live push (HR) and stored history (SpO2 / HRV) ----------
    def _on_jieli_frame(self, addr, c, k, kf, payload):
        """Route pushes the portal understands without a pending request."""
        if (c, k, kf) == (2, 3, 16) and len(payload) >= 3:
            self._battery_trend(addr, payload[0], (payload[1] << 8) | payload[2])
        if (c, k, kf) == (6, 9, 0) and len(payload) >= 3 and payload[2] == 0:
            # the ring switched a live sensor off by itself (it does so after ~30 s) - re-arm on next read
            for (a, var), st in self._live.items():
                arm = self.profile.get("vars", {}).get(var, {}).get("arm", "")
                if a == addr and len(arm) >= 8 and int(arm[6:8], 16) == payload[0]:
                    st["armed"] = False
        for (a, var), st in self._live.items():
            if a != addr:
                continue
            v = self.profile.get("vars", {}).get(var, {})
            if v.get("push") and bytes.fromhex(v["push"]) == bytes([c, k, kf]):
                val = self._push_value(v, payload)
                if val is not None:
                    st.update(value=val, t=asyncio.get_running_loop().time())
        cw = self._clock_wait.get(addr)
        if cw is not None and (c, k, kf) == (2, 36, 0) and len(payload) >= 4 and not cw.done():
            cw.set_result(payload)
        p = self._pull.get((addr, c, k))
        if p is not None and kf == 0x10:
            p[0] += payload
            if not p[1].done():
                p[1].set_result(True)

    def _battery_trend(self, addr, pct, mv):
        """No charging flag exists in the SR16 battery reply ([%, mV]); a ring on the charger shows a rising
        voltage/percentage, so flag it as charging when that trend holds over ~20-90 s."""
        r = self.rings.get(addr)
        if r is None:
            return
        now = time.time()
        h = [x for x in r.setdefault("batt_hist", []) if now - x[0] <= 90] + [(now, pct, mv)]
        r["batt_hist"] = h
        r["battery_pct"], r["battery_mv"] = pct, mv
        # resting voltage measured on SR16 rings off the charger: ~3.69 V at 9 %, ~3.80 V at 25 %, ~3.96 V at 88 %
        rest_mv = 3680 + 3.3 * pct
        above = mv - rest_mv >= float(self.rules.get("charge_mv_above_rest", 150))
        old = [x for x in h if now - x[0] >= 20]
        rose = bool(old) and pct > old[0][1]
        r["charging"] = above or rose

    @staticmethod
    def _push_value(v, payload):
        """Value from a push: a byte at value_offset, or (record_len set) a BE int in the LAST record."""
        rl = int(v.get("record_len", 0))
        if rl:
            if len(payload) < rl:
                return None
            o = (len(payload) // rl - 1) * rl + int(v.get("value_offset", 0))
            return int.from_bytes(payload[o:o + int(v.get("value_len", 1))], "big")
        off = int(v.get("value_offset", 0))
        return payload[off] if len(payload) > off else None

    async def _live_read(self, addr, name, v):
        key = (addr, name)
        st = self._live.setdefault(key, {"armed": False, "value": None, "t": None})
        if not v.get("arm"):
            # passive push (e.g. bead count): nothing to switch on; None until the ring sends one
            await self._ensure_cmd_notify(addr)
            return st["value"]
        now = asyncio.get_running_loop().time()
        if st["armed"] and st["t"] is not None and now - st["t"] > float(v.get("stale_s", 15)) / 2:
            st["armed"] = False  # pushes stopped without an 'off' frame - re-arm
        if not st["armed"]:
            await self._ensure_cmd_notify(addr)
            await self._write(addr, v, jieli.build(bytes.fromhex(v["arm"])))
            st["armed"] = True
            st.setdefault("armed_at", now)
            if st["t"] is None or now - st["t"] > float(v.get("stale_s", 15)):
                await asyncio.sleep(3)  # first push arrives ~2 s after arming
            now = asyncio.get_running_loop().time()
        if st["t"] is None:
            if self.rings.get(addr, {}).get("charging"):
                raise RuntimeError("ring is charging - take it off the charger and put it on a finger")
            raise RuntimeError("no reading yet - put the ring on a finger")
        if now - st["t"] > float(v.get("stale_s", 15)):
            raise RuntimeError(f"no new reading for {now - st['t']:.0f} s")
        return st["value"]

    async def live_stop(self, addr, name):
        """Always switch a live sensor off again - a sensor left on freezes the ring."""
        st = self._live.pop((addr, name), None)
        v = self.profile.get("vars", {}).get(name, {})
        if st and st.get("armed") and v.get("disarm") and self.rings.get(addr, {}).get("connected"):
            for _ in range(2):
                try:
                    await self._write(addr, v, jieli.build(bytes.fromhex(v["disarm"])))
                    return
                except Exception:
                    await asyncio.sleep(0.5)

    async def _stored_read(self, addr, name, v):
        """Pull the ring's stored records {5,X,16} (+ACK {5,X,0x30}) and return the newest recent value.
        NOTE: the ring deletes each page once it is ACKed."""
        import datetime as _dt
        await self._ensure_cmd_notify(addr)
        pulls = v["pull"] if isinstance(v["pull"], list) else [v["pull"]]
        for pull in pulls:
            await self._pull_channel(addr, name, v, bytes.fromhex(pull))
        cur = self._stored.get((addr, name))
        if cur is None:
            if self.rings.get(addr, {}).get("charging"):
                raise RuntimeError("ring is charging - no new readings while on the charger")
            raise RuntimeError(v.get("empty_msg") or "no stored reading - wear the ring ~10 min first")
        # ring time = local wall clock as seconds since 2000-01-01
        now_ring = int(_dt.datetime.now().replace(tzinfo=_dt.timezone.utc).timestamp()) - 946684800
        age_min = (now_ring - cur[0]) / 60
        max_age = float(v.get("max_age_min", 20))
        if age_min > max_age:
            raise RuntimeError(f"newest stored reading is {age_min:.0f} min old (limit {max_age:g})")
        return cur[1]

    async def stored_latest(self, addr, name):
        """Pull a stored channel and return the newest (ring_ts, value) seen this session, or None. No age limit."""
        v = self.var(name)
        await self._ensure_cmd_notify(addr)
        for pull in (v["pull"] if isinstance(v["pull"], list) else [v["pull"]]):
            await self._pull_channel(addr, name, v, bytes.fromhex(pull))
        return self._stored.get((addr, name))

    async def _pull_channel(self, addr, name, v, body):
        cmd, key = body[0], body[1]
        for _ in range(int(v.get("max_pages", 20))):
            fut = asyncio.get_running_loop().create_future()
            self._pull[(addr, cmd, key)] = [b"", fut]
            try:
                await self._write(addr, v, jieli.build(body))
                try:
                    await asyncio.wait_for(fut, self._t())
                except asyncio.TimeoutError:
                    break
                data = self._pull[(addr, cmd, key)][0]
            finally:
                self._pull.pop((addr, cmd, key), None)
            await self._write(addr, v, jieli.build(bytes([cmd, key, 0x30])))
            stride = int(v.get("record_len", 6))
            vo, vl = int(v.get("value_offset", 4)), int(v.get("value_len", 1))
            recs = [(int.from_bytes(data[o:o + 4], "big"), int.from_bytes(data[o + vo:o + vo + vl], "big"))
                    for o in range(0, len(data) - vo - vl + 1, stride)]
            recs = [(ts, val) for ts, val in recs if val or v.get("keep_zero")]
            if v.get("skip_hour_aligned"):
                recs = [(ts, val) for ts, val in recs if ts % 3600]  # hourly buckets; keep the running total
            for ts, val in recs:
                cur = self._stored.get((addr, name))
                if cur is None or ts >= cur[0]:
                    self._stored[(addr, name)] = (ts, val)
            if not data:
                break

    async def command(self, addr, v):
        if self._jieli():
            if not v.get("frame"):
                raise ValueError("no Jieli 'frame' (CMD Key KeyFlag) set for this variable in the ring profile")
            body = bytes.fromhex(v["frame"]) + bytes.fromhex(v.get("args") or "")
            await self._ensure_cmd_notify(addr)
            fut = asyncio.get_running_loop().create_future()
            self._cmd_wait[(addr, (body[0], body[1]))] = fut
            try:
                await self._write(addr, v, jieli.build(body))
                return await asyncio.wait_for(fut, self._t())  # reply payload (after CMD/Key/KeyFlag)
            finally:
                self._cmd_wait.pop((addr, (body[0], body[1])), None)
        op = int(str(v["opcode"]), 16)
        await self._ensure_cmd_notify(addr)
        fut = asyncio.get_running_loop().create_future()
        self._cmd_wait[(addr, op)] = fut
        try:
            await self._write(addr, v, bytes([op]) + bytes.fromhex(v.get("args") or ""))
            return await asyncio.wait_for(fut, self._t())
        finally:
            self._cmd_wait.pop((addr, op), None)

    async def read_var(self, addr, name):
        v = self.var(name)
        if v.get("op") == "jieli_live":
            return await self._live_read(addr, name, v)
        if v.get("op") == "jieli_stored":
            return await self._stored_read(addr, name, v)
        if v.get("op") == "command":
            data = await self.command(addr, v)
            return parsers.decode(v["parser"], data[int(v.get("resp_offset", 1)):])
        if v.get("op") == "notify":
            key = (addr, name)
            if key not in self._notify:
                self._notify[key] = None

                def cb(data, key=key, parser=v["parser"]):
                    try:
                        self._notify[key] = parsers.decode(parser, data)
                    except Exception:
                        pass
                try:
                    async with self._lock(addr):
                        await asyncio.wait_for(self._b().start_notify(addr, self._svc(v), v["char"], cb), self._t())
                except Exception:
                    self._notify.pop(key, None)
                    raise
            return self._notify[key]
        return parsers.decode(v["parser"], await self.read_raw(addr, name))

    async def _write(self, addr, v, data):
        if addr in self.rings:
            self.rings[addr]["last_io"] = time.time()
        async with self._lock(addr):
            await asyncio.wait_for(
                self._b().write(addr, self._svc(v), self._write_char(v), data, v.get("write_response", True)), self._t())

    def _write_char(self, v):
        if self._jieli():
            return self.profile.get("cmd_char")  # every Jieli frame goes to the data write char (b002)
        return v.get("char") or self.profile.get("cmd_char")

    async def _call_alert(self, addr, v, state):
        """Show the ring's Unit ID on its OLED as an incoming 'call' (Jieli {6,4,16})."""
        import datetime as _dt
        code = {"ringing": 0, "answered": 1, "ended": 2}[state]
        num = self.rings.get(addr, {}).get("unit_id", "RING").encode()[:32]
        # local wall-clock seconds dressed as epoch, as the ring expects (same as setDateTime)
        secs = int(_dt.datetime.now().replace(tzinfo=_dt.timezone.utc).timestamp())
        payload = bytes([code]) + secs.to_bytes(4, "little") + bytes([len(num)]) + num
        await self._ensure_cmd_notify(addr)
        await self._write(addr, v, jieli.build(bytes.fromhex(v.get("frame", "060410")) + payload))

    @staticmethod
    def _expand(body):
        """Hex frame body; '{now}' becomes the local clock [yy mm dd hh mi ss] (Jieli setDate layout)."""
        import datetime as _dt
        if "{now}" in body:
            t = _dt.datetime.now()
            body = body.replace("{now}", bytes([t.year % 100, t.month, t.day, t.hour, t.minute, t.second]).hex())
        return bytes.fromhex(body.replace(" ", ""))

    async def jieli_request(self, addr, v, body, timeout=None):
        """Send one Jieli frame; if the link drops mid-command, wait for the watchdog's reconnect and retry (twice)."""
        for attempt in range(3):
            try:
                return await self._jieli_request_once(addr, v, body, timeout)
            except Exception:
                r = self.rings.get(addr, {})
                if attempt == 2 or not (r.get("keep") and self.backend):
                    raise
                await asyncio.sleep(1)
                if self.backend.is_connected(addr):
                    raise  # link is fine: the ring really did not answer
                await self.wait_link(addr)

    async def _jieli_request_once(self, addr, v, body, timeout=None):
        """Send one Jieli frame and wait for the ring's answer with the same CMD/Key. Returns the reply payload."""
        await self.wait_link(addr)
        await self._ensure_cmd_notify(addr)
        fut = asyncio.get_running_loop().create_future()
        self._cmd_wait[(addr, (body[0], body[1]))] = fut
        try:
            await self._write(addr, v, jieli.build(body))
            try:
                return await asyncio.wait_for(fut, timeout or self._t())
            except asyncio.TimeoutError:
                raise RuntimeError(f"ring did not answer {{{body[0]},{body[1]},{body[2]}}}")
        finally:
            self._cmd_wait.pop((addr, (body[0], body[1])), None)

    async def ring_clock(self, addr):
        """Read the ring's clock: briefly switch live HR on and take the timestamp from its push
        ({2,36,0} payload [ts32 BE = local seconds since 2000, bpm, 0]); HR is always switched off again."""
        import datetime as _dt
        v = self.var("hr")
        got = asyncio.get_running_loop().create_future()
        self._clock_wait[addr] = got
        try:
            await self.jieli_request(addr, v, bytes.fromhex(v["arm"]))
            payload = await asyncio.wait_for(got, 20)
        except asyncio.TimeoutError:
            raise RuntimeError("ring sent no timestamped reading within 20 s")
        finally:
            self._clock_wait.pop(addr, None)
            try:
                await self._write(addr, v, jieli.build(bytes.fromhex(v["disarm"])))
            except Exception:
                pass
        ring_local = int.from_bytes(payload[0:4], "big") + 946684800
        # convert ring local wall-clock to a real epoch using this laptop's UTC offset
        offset = _dt.datetime.now().astimezone().utcoffset().total_seconds()
        return ring_local - offset

    async def write_var(self, addr, name, value):
        v = self.var(name)
        await self._write(addr, v, parsers.encode(v["parser"], value))

    async def send_cmd(self, addr, name, cmd, verify=False):
        """Write a named command (e.g. mode 'sleep', vibration 'start'). Returns read-back match if verifiable."""
        v = self.var(name)
        cmds = v.get("commands") or {}
        if cmd not in cmds:
            raise KeyError(f"command '{cmd}' not defined for '{name}' in the ring profile")
        if cmds[cmd] is None:
            raise NotImplementedError(f"this ring has no command for '{cmd}'")
        if v.get("op") == "call_alert":
            await self._call_alert(addr, v, cmds[cmd])
            return True
        if self._jieli() and isinstance(cmds[cmd], list):
            for body in cmds[cmd]:
                if body.startswith("wait:"):  # pause between frames, e.g. HR on -> off to wake the screen
                    await asyncio.sleep(float(body[5:]))
                    continue
                await self.jieli_request(addr, v, self._expand(body))
            return True
        data = bytes.fromhex(cmds[cmd])
        if self._jieli():
            if not data:
                return True  # nothing to send (e.g. vibration has no stop command)
            await self.jieli_request(addr, v, data)  # wait for the ring's answer so failures are visible
            return True
        await self._write(addr, v, data)
        if verify and "read" in v.get("op", ""):
            return (await self.read_raw(addr, name)) == data
        return True

    # ---------- buzz: continuous vibration + screen blink until stopped ----------
    def buzzing(self, addr):
        t = self._buzz.get(addr)
        return bool(t and not t.done())

    def start_buzz(self, addr):
        if not self.buzzing(addr):
            self._buzz[addr] = asyncio.create_task(self._buzz_loop(addr))

    def stop_buzz(self, addr):
        t = self._buzz.pop(addr, None)
        if t:
            t.cancel()

    async def _blink_until(self, addr, seconds, errs, r):
        """Flash the screen (oled 'blink' / 'stop' alternately) for `seconds`; plain wait if the model can't."""
        cmds = self.profile.get("vars", {}).get("oled", {}).get("commands", {})
        step = float(self.rules.get("blink_s", 0) or 0)
        if not (step and "blink" in cmds and "stop" in cmds):
            await asyncio.sleep(seconds)
            return
        loop = asyncio.get_running_loop()
        end, on = loop.time() + seconds, True  # the buzz loop has just sent 'blink'
        while loop.time() < end:
            try:
                await self.send_cmd(addr, "oled", "stop" if on else "blink")
                on = not on
            except Exception as e:
                r["buzz_error"] = "; ".join(errs + [f"oled: {e}"])
            await asyncio.sleep(step)

    async def _buzz_loop(self, addr):
        repeat = float(self.rules.get("buzz_repeat_s", 2))
        r = self.rings.get(addr, {})
        try:
            while True:
                errs = []
                for var, cmd in (("vibration", "start"), ("oled", "blink")):
                    if var not in self.profile.get("vars", {}):
                        continue
                    try:
                        await self.send_cmd(addr, var, cmd)
                    except Exception as e:
                        errs.append(f"{var}: {e}")
                r["buzz_error"] = "; ".join(errs) or None
                await self._blink_until(addr, repeat, errs, r)
        finally:
            for var, cmd in (("vibration", "stop"), ("oled", "stop")):
                if var not in self.profile.get("vars", {}):
                    continue
                try:
                    await self.send_cmd(addr, var, cmd)
                except Exception:
                    pass
