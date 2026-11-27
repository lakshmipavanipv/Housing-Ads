"""USB bridge backend: drives 1-3 (or more) ESP32 boards running firmware/rqa_bridge over serial.

Each board is an independent Bluetooth radio holding up to `max_conn` rings (9 with the supplied firmware),
so Windows' own Bluetooth stack is bypassed entirely. Rings are spread across the boards automatically.
"""
import asyncio
import re
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


def _port_num(port):
    m = re.search(r"(\d+)$", port)
    return (int(m.group(1)) if m else 0, port)


def detect_ports():
    """ESP32 COM ports in board order: COM3 = board 1, COM6 = board 2, COM10 = board 3 ..."""
    from serial.tools import list_ports
    return sorted((p.device for p in list_ports.comports() if p.vid in ESP32_VIDS), key=_port_num)


class Bridge:
    """One ESP32 board on one COM port."""

    def __init__(self, port, loop):
        import serial
        self.port, self.loop = port, loop
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, BAUD, 0.2
        s.write_timeout = 1.0  # a board without the bridge firmware never reads, so a plain write would hang forever
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
                sent = time.time()
                try:
                    self.ser.write(b"0 INFO\n")
                except Exception:  # serial write timeout: nothing on the board is reading USB
                    pass
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("0 OK INFO"):
                p = line.split()
                return {"mac": p[3], "max_conn": int(p[4]), "fw": p[5] if len(p) > 5 else "?"}
        self.ser.close()
        raise RuntimeError("board has no Ring QA bridge firmware yet - run flash_bridges.bat once for this board")

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
    own_timeouts = True  # each board command has its own timeout; queue time on a busy board must not count

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
        self.bridges.sort(key=lambda b: _port_num(b.port))  # board 1 = lowest COM port, filled first
        # Even if no board answers, keep the backend so the Connection page lists each board and its problem.
        self.route, self.types, self.svc, self.heard = {}, {}, {}, {}

    def status(self):
        return [b.status() for b in self.bridges] + [{"port": p, "error": e, "alive": False}
                                                     for p, e in self.errors.items()]

    def close(self):
        for b in self.bridges:
            b.close()

    async def scan(self, timeout=6.0, name_prefix="", service=""):
        res = await asyncio.gather(*(b.scan(timeout) for b in self.bridges if b.alive), return_exceptions=True)
        # which boards heard each ring in this scan (boards hear differently: antenna, distance, hub position)
        live = [b for b in self.bridges if b.alive]
        best, heard = {}, {}
        for b, r in zip(live, res):
            if isinstance(r, Exception):
                continue
            for d in r:
                heard.setdefault(d["addr"], set()).add(b)
                cur = best.get(d["addr"])
                if not cur or d["rssi"] > cur["rssi"]:
                    best[d["addr"]] = {**d, "name": d["name"] or (cur or {}).get("name", "")}
        # name_prefix may be a comma list ("SR16,VELVUE"); match case-insensitively like the local backend
        prefixes = tuple(p.strip().upper() for p in (name_prefix or "").split(",") if p.strip())
        out = []
        for d in best.values():
            if prefixes and not d["name"].upper().startswith(prefixes):
                continue
            self.types[d["addr"]] = d["type"]
            self.heard[d["addr"]] = heard.get(d["addr"], set())
            out.append({"addr": d["addr"], "name": d["name"], "rssi": d["rssi"]})
        return out

    async def connect(self, addr):
        if self.is_connected(addr):
            return True
        # Fill the boards one after the other: board 1 takes rings until it is full, then board 2, then board 3.
        # Only boards that heard the ring in the last scan are tried first (a board that cannot hear a ring cannot
        # connect to it); if those fail, the remaining boards are tried in order.
        # A ring is only ever routed to ONE board, and the slot is reserved before any await, so two connects
        # running at once can never land the same ring on two boards or overfill a board.
        heard = self.heard.get(addr) or set()
        order = [b for b in self.bridges if b in heard] + [b for b in self.bridges if b not in heard]
        last = None
        for b in order:
            if not b.alive or len(b.connected) >= b.max_conn:
                continue
            b.connected.add(addr)  # reserve the slot while connecting
            try:
                # the board's own connect timeout is 10 s; this limit only starts once the board takes the command,
                # so rings queued behind others on the same board are not failed for waiting their turn
                await b.cmd(f"CONN {addr} {self.types.get(addr, 0)}", 15)
            except asyncio.CancelledError:
                b.connected.discard(addr)  # never leave a slot reserved for a ring that is not there
                raise
            except Exception as e:
                b.connected.discard(addr)
                last = RuntimeError(f"{b.port}: {e}")
                continue
            self.route[addr] = b
            return True
        if last:
            raise last
        cap = sum(b.max_conn for b in self.bridges if b.alive)
        raise RuntimeError(f"all boards are full ({cap} rings max) - add a board or test fewer rings")

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

    def _s(self, addr, service):
        if service:
            self.svc[addr] = service
        return service or self.svc.get(addr) or ""

    async def read(self, addr, service, char):
        p = await self._b(addr).cmd(f"READ {addr} {self._s(addr, service)} {char}")
        return bytes.fromhex(p[0]) if p else b""

    async def write(self, addr, service, char, data, response=True):
        await self._b(addr).cmd(f"WRITE {addr} {self._s(addr, service)} {char} {data.hex() or '00'} {1 if response else 0}")

    async def start_notify(self, addr, service, char, cb):
        b = self._b(addr)
        b.ntf_cbs[(addr, norm_uuid(char))] = cb
        await b.cmd(f"SUB {addr} {self._s(addr, service)} {char}")
