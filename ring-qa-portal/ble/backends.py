"""Bluetooth backends. All share one interface so the portal does not care which is used.

- local : the laptop's own Bluetooth via `bleak` (Windows WinRT / Linux BlueZ / macOS)
- mock  : simulated rings, for demos and testing without hardware
- dongles: reserved for multi-dongle support (not enabled yet)
"""
import asyncio
import math
import random
import time

from . import parsers


class BaseBackend:
    name = "base"

    async def scan(self, timeout=5.0, name_prefix=""):
        raise NotImplementedError

    async def connect(self, addr):
        raise NotImplementedError

    async def disconnect(self, addr):
        raise NotImplementedError

    def is_connected(self, addr):
        raise NotImplementedError

    async def read(self, addr, service, char) -> bytes:
        raise NotImplementedError

    async def write(self, addr, service, char, data: bytes, response=True):
        raise NotImplementedError

    async def start_notify(self, addr, service, char, cb):
        raise NotImplementedError


class BleakBackend(BaseBackend):
    """Local laptop Bluetooth adapter."""
    name = "local"

    def __init__(self):
        import bleak  # noqa: raises ImportError if not installed
        self._bleak = bleak
        self.clients = {}
        self.devices = {}

    async def scan(self, timeout=5.0, name_prefix=""):
        found = await self._bleak.BleakScanner.discover(timeout=timeout, return_adv=True)
        out = []
        for dev, adv in found.values():
            name = adv.local_name or dev.name or ""
            if name_prefix and not name.startswith(name_prefix):
                continue
            self.devices[dev.address] = dev
            out.append({"addr": dev.address, "name": name, "rssi": adv.rssi})
        return out

    async def connect(self, addr):
        c = self.clients.get(addr)
        if c and c.is_connected:
            return True
        c = self._bleak.BleakClient(self.devices.get(addr, addr), timeout=15.0)
        await c.connect()
        self.clients[addr] = c
        return c.is_connected

    async def disconnect(self, addr):
        c = self.clients.pop(addr, None)
        if c:
            await c.disconnect()

    def is_connected(self, addr):
        c = self.clients.get(addr)
        return bool(c and c.is_connected)

    def _client(self, addr):
        c = self.clients.get(addr)
        if not c or not c.is_connected:
            raise RuntimeError("ring not connected")
        return c

    async def read(self, addr, service, char):
        return bytes(await self._client(addr).read_gatt_char(char))

    async def write(self, addr, service, char, data, response=True):
        await self._client(addr).write_gatt_char(char, data, response=response)

    async def start_notify(self, addr, service, char, cb):
        await self._client(addr).start_notify(char, lambda _s, d: cb(bytes(d)))


class MockRing:
    def __init__(self, i):
        rnd = random.Random(i)
        self.addr = f"C0:DE:00:00:{i // 256:02X}:{i % 256:02X}"
        self.name = f"BS-RING-{i:03d}"
        self.t0 = time.time()
        self.batt0 = rnd.randint(25, 70)
        self.rate = (100 / 3600) * rnd.uniform(0.85, 1.25)  # % per second -> ~60 min full charge
        self.no_charge = i == 7      # simulated defect: battery does not charge
        self.hr_dead = i == 13       # simulated defect: HR sensor returns 0
        self.no_connect = i == 21    # simulated defect: will not connect
        self.offset = rnd.randint(-40, 40)
        self.tz = 330
        self.mode = "time"
        self.on = True
        self.steps0 = rnd.randint(0, 800)
        self.base_rssi = rnd.randint(-75, -50)

    def value(self, name, speed):
        now = time.time()
        if name == "battery":
            gain = 0 if self.no_charge else self.rate * (now - self.t0) * speed
            return int(min(100, self.batt0 + gain))
        if name == "time":
            return int(now + self.offset)
        if name == "timezone":
            return self.tz
        if name == "hr":
            return 0 if self.hr_dead else int(72 + 8 * math.sin(now / 20) + random.uniform(-3, 3))
        if name == "spo2":
            return int(97 + random.uniform(-1.5, 1.5))
        if name == "hrv":
            return int(45 + random.uniform(-10, 10))
        if name == "steps":
            return self.steps0 + int((now - self.t0) * 0.6)
        if name == "count":
            return int((now - self.t0) * 0.25)
        if name == "sleep":
            return 420 + random.randint(-30, 30)
        return 0

    def set_value(self, name, val):
        if name == "time":
            self.offset = int(val) - time.time()
        elif name == "timezone":
            self.tz = int(val)


class MockBackend(BaseBackend):
    name = "mock"

    def __init__(self, store, n=30, speed=1.0):
        self.store = store
        self.speed = speed
        self.rings = {r.addr: r for r in (MockRing(i + 1) for i in range(n))}
        self.connected = set()
        self.cmd_cbs = {}

    def _p(self):
        return self.store.active

    def _apply_cmd(self, r, name, cmd):
        if name == "mode" and cmd:
            r.mode = cmd
        elif name == "power":
            r.on = cmd != "off"

    def _var_for(self, char):
        for k, v in self.store.active["vars"].items():
            if v.get("char", "").lower() == char.lower():
                return k, v
        raise RuntimeError(f"unknown characteristic {char}")

    def _ring(self, addr):
        if addr not in self.connected:
            raise RuntimeError("ring not connected")
        return self.rings[addr]

    async def scan(self, timeout=5.0, name_prefix=""):
        await asyncio.sleep(min(timeout, 1.5))
        return [{"addr": r.addr, "name": r.name, "rssi": r.base_rssi + random.randint(-4, 4)}
                for r in self.rings.values() if r.name.startswith(name_prefix or "")]

    async def connect(self, addr):
        await asyncio.sleep(0.2)
        if self.rings[addr].no_connect:
            raise ConnectionError("simulated: ring did not respond")
        self.connected.add(addr)
        return True

    async def disconnect(self, addr):
        self.connected.discard(addr)

    def is_connected(self, addr):
        return addr in self.connected

    async def read(self, addr, service, char):
        r = self._ring(addr)
        name, v = self._var_for(char)
        await asyncio.sleep(0.02)
        if name == "mode":
            return bytes.fromhex(v.get("commands", {}).get(r.mode, "00"))
        if not r.on:
            raise RuntimeError("simulated: ring is switched off")
        return parsers.encode(v["parser"], r.value(name, self.speed))

    async def write(self, addr, service, char, data, response=True):
        r = self._ring(addr)
        if char.lower() == (self._p().get("cmd_char") or "").lower():
            await asyncio.sleep(0.02)
            for k, v in self._p()["vars"].items():
                if v.get("op") == "command" and data and int(str(v["opcode"]), 16) == data[0]:
                    cb = self.cmd_cbs.get(addr)
                    if cb and r.on:
                        off = int(v.get("resp_offset", 1))
                        resp = bytes([data[0]]) + b"\x00" * (off - 1) + parsers.encode(v["parser"], r.value(k, self.speed))
                        asyncio.get_running_loop().call_later(0.05, cb, resp)
                    return
            for k, v in self._p()["vars"].items():
                for cname, h in (v.get("commands") or {}).items():
                    if bytes.fromhex(h) == data:
                        self._apply_cmd(r, k, cname)
                        return
            return
        name, v = self._var_for(char)
        await asyncio.sleep(0.02)
        cmds = v.get("commands") or {}
        if cmds:
            self._apply_cmd(r, name, next((k for k, h in cmds.items() if bytes.fromhex(h) == data), None))
            return
        r.set_value(name, parsers.decode(v["parser"], data))

    async def start_notify(self, addr, service, char, cb):
        r = self._ring(addr)
        nch = self._p().get("notify_char") or self._p().get("cmd_char") or ""
        if char.lower() == nch.lower():
            self.cmd_cbs[addr] = cb
            return
        name, v = self._var_for(char)

        async def loop():
            while addr in self.connected:
                try:
                    cb(parsers.encode(v["parser"], r.value(name, self.speed)))
                except Exception:
                    pass
                await asyncio.sleep(1)

        asyncio.create_task(loop())


def make_backend(mode, store, mock_rings=30, speed=1.0):
    if mode == "local":
        return BleakBackend()
    if mode == "mock":
        return MockBackend(store, mock_rings, speed)
    if mode == "dongles":
        raise RuntimeError("USB dongle mode is not enabled yet - use Local laptop Bluetooth")
    raise ValueError(f"unknown backend '{mode}'")
