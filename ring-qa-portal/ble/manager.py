"""RingManager: everything the portal does to a ring goes through here, driven by the active profile."""
import asyncio

from . import parsers


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
                                         self.profile.get("name_prefix", ""))
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
                await asyncio.wait_for(self._b().connect(addr), 20)
            r["connected"], r["error"] = True, None
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
        self._notify.clear()
        self._cmd_sub.clear()

    def ring_list(self):
        out = []
        for a, r in self.rings.items():
            if self.backend and r.get("connected") and not self.backend.is_connected(a):
                r["connected"], r["error"] = False, "connection lost"
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
            if r is not None:
                r.setdefault("raw", {})[f"{data[0]:02x}"] = data.hex()
            fut = self._cmd_wait.get((addr, data[0]))
            if fut and not fut.done():
                fut.set_result(data)

        async with self._lock(addr):
            await asyncio.wait_for(self._b().start_notify(addr, self.profile.get("service_uuid"), nch, cb), self._t())
        self._cmd_sub.add(addr)

    async def command(self, addr, v):
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
        async with self._lock(addr):
            await asyncio.wait_for(
                self._b().write(addr, self._svc(v), v.get("char") or self.profile.get("cmd_char"), data, v.get("write_response", True)), self._t())

    async def write_var(self, addr, name, value):
        v = self.var(name)
        await self._write(addr, v, parsers.encode(v["parser"], value))

    async def send_cmd(self, addr, name, cmd, verify=False):
        """Write a named command (e.g. mode 'sleep', vibration 'start'). Returns read-back match if verifiable."""
        v = self.var(name)
        cmds = v.get("commands") or {}
        if cmd not in cmds:
            raise KeyError(f"command '{cmd}' not defined for '{name}' in the ring profile")
        data = bytes.fromhex(cmds[cmd])
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

    async def _buzz_loop(self, addr):
        repeat = float(self.rules.get("buzz_repeat_s", 2))
        r = self.rings.get(addr, {})
        try:
            while True:
                errs = []
                for var, cmd in (("vibration", "start"), ("oled", "blink")):
                    try:
                        await self.send_cmd(addr, var, cmd)
                    except Exception as e:
                        errs.append(f"{var}: {e}")
                r["buzz_error"] = "; ".join(errs) or None
                await asyncio.sleep(repeat)
        finally:
            for var, cmd in (("vibration", "stop"), ("oled", "stop")):
                try:
                    await self.send_cmd(addr, var, cmd)
                except Exception:
                    pass
