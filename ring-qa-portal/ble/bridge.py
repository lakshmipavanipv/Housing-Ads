"""USB bridge backend: drives 1-3 (or more) ESP32 boards running firmware/rqa_bridge over serial.

Each board is an independent Bluetooth radio holding up to `max_conn` rings (9 with the supplied firmware),
so Windows' own Bluetooth stack is bypassed entirely. Rings are spread across the boards automatically.
"""
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .backends import BaseBackend

BAUD = 115200
# USB-serial chips used on ESP32 boards: Silicon Labs CP210x, WCH CH340/CH9102, FTDI, Espressif native USB
ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}


def norm_uuid(u):
    u = str(u).strip().lower()
    if u.startswith("0x"):
        u = u[2:]
    if len(u) == 4:
        return f"0000{u}-0000-1000-8000-00805f9b34fb"
    if len(u) == 8:
        return f"{u}-0000-1000-8000-00805f9b34fb"
    return u


def detect_ports():
    from serial.tools import list_ports
    return sorted(p.device for p in list_ports.comports() if p.vid in ESP32_VIDS)


class Bridge:
    """One ESP32 board on one COM port."""

    def __init__(self, port, loop):
        import serial
        self.port, self.loop = port, loop
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, BAUD, 0.2
        s.dtr = False
        s.rts = False
        s.open()
        self.ser = s
        self.info = self._handshake()
        self.max_conn = self.info["max_conn"]
        self.pending, self.next_id = {}, 1
        self.adv, self.ntf_cbs, self.connected = {}, {}, set()
        self.lock = asyncio.Lock()
        self.alive, self.error = True, None
        threading.Thread(target=self._reader, daemon=True).start()

    def _handshake(self):
        deadline, sent = time.time() + 8, 0.0
        while time.time() < deadline:
            if time.time() - sent > 1.5:
                self.ser.write(b"0 INFO\n")
                sent = time.time()
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("0 OK INFO"):
                p = line.split()
                return {"mac": p[3], "max_conn": int(p[4]), "fw": p[5] if len(p) > 5 else "?"}
        self.ser.close()
        raise RuntimeError("no answer from RQA bridge firmware - flash this board with flash_bridges.bat")

    def _reader(self):
        while self.alive:
            try:
                raw = self.ser.readline()
            except Exception as e:  # board unplugged
                self.alive, self.error = False, f"serial error: {e}"
                self.loop.call_soon_threadsafe(self._fail_all)
                break
            if raw:
                line = raw.decode(errors="replace").strip()
                if line:
                    self.loop.call_soon_threadsafe(self._on_line, line)

    def _fail_all(self):
        self.connected.clear()
        for fut in self.pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError(self.error))

    def _on_line(self, line):
        p = line.split(" ")
        tag = p[0]
        if tag == "ADV" and len(p) >= 4:
            addr = p[1].lower()
            name = bytes.fromhex(p[4]).decode(errors="replace") if len(p) > 4 and p[4] else ""
            self.adv[addr] = {"addr": addr, "type": int(p[2]), "rssi": int(p[3]), "name": name}
        elif tag == "NTF" and len(p) >= 3:
            cb = self.ntf_cbs.get((p[1].lower(), norm_uuid(p[2])))
            if cb:
                cb(bytes.fromhex(p[3]) if len(p) > 3 else b"")
        elif tag == "DISCONNECTED" and len(p) >= 2:
            self.connected.discard(p[1].lower())
        elif tag.isdigit():
            fut = self.pending.pop(int(tag), None)
            if fut and not fut.done():
                if len(p) > 1 and p[1] == "OK":
                    fut.set_result(p[2:])
                else:
                    fut.set_exception(RuntimeError(" ".join(p[2:]) or "bridge error"))

    async def cmd(self, text, timeout=6.0):
        if not self.alive:
            raise RuntimeError(f"{self.port}: {self.error or 'board offline'}")
        async with self.lock:  # the board handles one command at a time
            i = self.next_id
            self.next_id = self.next_id % 1_000_000 + 1
            fut = self.loop.create_future()
            self.pending[i] = fut
            self.ser.write(f"{i} {text}\n".encode())
            try:
                return await asyncio.wait_for(fut, timeout)
            finally:
                self.pending.pop(i, None)

    async def scan(self, timeout):
        self.adv = {}
        await self.cmd(f"SCAN {int(timeout * 1000)}", timeout + 10)
        return list(self.adv.values())

    def status(self):
        return {"port": self.port, "mac": self.info["mac"], "fw": self.info["fw"], "max_conn": self.max_conn,
                "rings": len(self.connected), "alive": self.alive, "error": self.error}

    def close(self):
        self.alive = False
        try:
            self.ser.close()
        except Exception:
            pass


class BridgeBackend(BaseBackend):
    name = "dongles"

    def __init__(self, ports=None):
        try:
            import serial  # noqa: F401
        except ImportError:
            raise RuntimeError("Python package 'pyserial' is not installed. Run: pip install pyserial")
        ports = ports or detect_ports()
        if not ports:
            raise RuntimeError("No ESP32 boards found on USB. Plug them in, check Device Manager > Ports (COM & LPT)")
        loop = asyncio.get_running_loop()
        self.bridges, self.errors = [], {}

        def try_open(p):
            try:
                return Bridge(p, loop)
            except Exception as e:
                self.errors[p] = f"{type(e).__name__}: {e}"

        with ThreadPoolExecutor(len(ports)) as ex:
            self.bridges = [b for b in ex.map(try_open, ports) if b]
        if not self.bridges:
            raise RuntimeError("; ".join(f"{p}: {e}" for p, e in self.errors.items()))
        self.route, self.types = {}, {}

    def status(self):
        return [b.status() for b in self.bridges] + [{"port": p, "error": e, "alive": False}
                                                     for p, e in self.errors.items()]

    def close(self):
        for b in self.bridges:
            b.close()

    async def scan(self, timeout=6.0, name_prefix=""):
        res = await asyncio.gather(*(b.scan(timeout) for b in self.bridges if b.alive), return_exceptions=True)
        best = {}
        for r in res:
            if isinstance(r, Exception):
                continue
            for d in r:
                cur = best.get(d["addr"])
                if not cur or d["rssi"] > cur["rssi"]:
                    best[d["addr"]] = {**d, "name": d["name"] or (cur or {}).get("name", "")}
        out = []
        for d in best.values():
            if name_prefix and not d["name"].startswith(name_prefix):
                continue
            self.types[d["addr"]] = d["type"]
            out.append({"addr": d["addr"], "name": d["name"], "rssi": d["rssi"]})
        return out

    async def connect(self, addr):
        if self.is_connected(addr):
            return True
        free = [b for b in self.bridges if b.alive and len(b.connected) < b.max_conn]
        if not free:
            cap = sum(b.max_conn for b in self.bridges if b.alive)
            raise RuntimeError(f"all boards are full ({cap} rings max) - add a board or test fewer rings")
        b = min(free, key=lambda x: len(x.connected))
        b.connected.add(addr)  # reserve the slot while connecting
        try:
            await b.cmd(f"CONN {addr} {self.types.get(addr, 0)}", 20)
        except Exception:
            b.connected.discard(addr)
            raise
        self.route[addr] = b
        return True

    def _b(self, addr):
        b = self.route.get(addr)
        if not b or addr not in b.connected:
            raise RuntimeError("ring not connected")
        return b

    async def disconnect(self, addr):
        b = self.route.pop(addr, None)
        if b:
            b.connected.discard(addr)
            for k in [k for k in b.ntf_cbs if k[0] == addr]:
                b.ntf_cbs.pop(k)
            await b.cmd(f"DISC {addr}")

    def is_connected(self, addr):
        b = self.route.get(addr)
        return bool(b and b.alive and addr in b.connected)

    async def read(self, addr, service, char):
        p = await self._b(addr).cmd(f"READ {addr} {service} {char}")
        return bytes.fromhex(p[0]) if p else b""

    async def write(self, addr, service, char, data, response=True):
        await self._b(addr).cmd(f"WRITE {addr} {service} {char} {data.hex() or '00'} {1 if response else 0}")

    async def start_notify(self, addr, service, char, cb):
        b = self._b(addr)
        b.ntf_cbs[(addr, norm_uuid(char))] = cb
        await b.cmd(f"SUB {addr} {service} {char}")
