"""Rings fill the ESP32 boards one after the other (board 1 full, then 2, then 3) and never land on two boards."""
import asyncio

from ble.bridge import BridgeBackend, _port_num


class FakeBridge:
    def __init__(self, port, cap=10):
        self.port, self.max_conn, self.alive, self.connected, self.ntf_cbs = port, cap, True, set(), {}

    async def cmd(self, text, timeout=6.0):
        await asyncio.sleep(0.001)
        return []


def make(boards):
    be = BridgeBackend.__new__(BridgeBackend)
    be.bridges, be.errors, be.route, be.types, be.svc, be.heard = boards, {}, {}, {}, {}, {}
    return be


def test_ports_sorted_naturally():
    assert sorted(["COM10", "COM6", "COM3"], key=_port_num) == ["COM3", "COM6", "COM10"]


def test_sequential_fill_no_duplicates():
    boards = [FakeBridge("COM3"), FakeBridge("COM6"), FakeBridge("COM10")]
    be = make(boards)
    rings = [f"aa:00:00:00:00:{i:02x}" for i in range(30)]

    async def run():
        sem = asyncio.Semaphore(3)  # same parallelism as connect_all

        async def one(a):
            async with sem:
                await be.connect(a)
        await asyncio.gather(*(one(a) for a in rings))
        await asyncio.gather(*(be.connect(a) for a in rings[:5]))  # reconnecting a connected ring is a no-op

    asyncio.run(run())
    assert [len(b.connected) for b in boards] == [10, 10, 10]
    assert set(rings[:10]) == boards[0].connected
    all_rings = [a for b in boards for a in b.connected]
    assert len(all_rings) == len(set(all_rings)) == 30


def test_failed_or_cancelled_connect_frees_the_slot():
    class Failing(FakeBridge):
        async def cmd(self, text, timeout=6.0):
            await asyncio.sleep(10)

    b = Failing("COM6")
    be = make([b])

    async def run():
        t = asyncio.ensure_future(be.connect("aa:bb"))
        await asyncio.sleep(0.01)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert b.connected == set()


def test_ring_goes_to_first_board_that_heard_it_then_falls_back():
    class Deaf(FakeBridge):
        async def cmd(self, text, timeout=6.0):
            raise RuntimeError("connect failed")

    b1, b2, b3 = Deaf("COM6"), FakeBridge("COM7"), FakeBridge("COM8")
    be = make([b1, b2, b3])
    be.heard = {"r1": {b3}, "r2": set()}
    asyncio.run(be.connect("r1"))
    assert be.route["r1"] is b3 and b1.connected == set() and b2.connected == set()
    asyncio.run(be.connect("r2"))  # heard by nobody: board 1 fails, board 2 takes it
    assert be.route["r2"] is b2 and b1.connected == set()


def test_connect_all_36_found_30_target_fills_boards_in_series():
    """36 rings advertising, target 30, 4 boards of 9: the 30 strongest connect, 9 + 9 + 9 + 3, in order."""
    from types import SimpleNamespace
    from ble.manager import RingManager

    boards = [FakeBridge("COM6", 9), FakeBridge("COM7", 9), FakeBridge("COM8", 9), FakeBridge("COM9", 9)]
    be = make(boards)
    mgr = RingManager(SimpleNamespace(active={"protocol": "plain", "rules": {"connect_parallel": 2}}))
    mgr.backend = be
    for i in range(36):  # ring i has rssi -40 - i: rings 0-29 are the strongest
        a = f"38:00:00:00:00:{i:02x}"
        mgr.rings[a] = {"addr": a, "name": "SR16", "unit_id": f"R{i + 1:03d}", "found": True, "rssi": -40 - i,
                        "connected": False}

    n = asyncio.run(mgr.connect_all(30))
    assert n == 30
    assert [len(b.connected) for b in boards] == [9, 9, 9, 3]
    strongest = [f"38:00:00:00:00:{i:02x}" for i in range(30)]
    assert {a for a, r in mgr.rings.items() if r["connected"]} == set(strongest)
    for k, b in enumerate(boards):  # in series: 1-9, 10-18, 19-27, 28-30
        assert b.connected == set(strongest[9 * k:9 * k + 9])
    on = [a for b in boards for a in b.connected]
    assert len(on) == len(set(on)) == 30  # never one ring on two boards
