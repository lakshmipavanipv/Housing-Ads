"""SQLite storage: batches, rings, per-stage results (with timestamp + tester) and sample series."""
import csv
import io
import json
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "qa.db"
STAGE_ORDER = ["bluetooth", "battery", "time", "modes", "count", "steps", "hr", "spo2", "hrv", "sleep"]

SCHEMA = """
create table if not exists batches(id integer primary key, name text unique, tester text, created_at real, ring_target integer);
create table if not exists rings(mac text, ble_name text, unit_id text, size text, colour text, batch_id integer,
                                 primary key(mac, batch_id));
create table if not exists results(id integer primary key, batch_id integer, mac text, stage text, status text,
                                   values_json text, tester text, started_at real, saved_at real);
create table if not exists samples(batch_id integer, mac text, stage text, ts real, value real);
"""


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.executescript(SCHEMA)


def save_stage(batch, tester, target, stage, started_at, rows):
    now = time.time()
    with _conn() as c:
        b = c.execute("select id from batches where name=?", (batch,)).fetchone()
        if b:
            bid = b["id"]
            c.execute("update batches set tester=?, ring_target=? where id=?", (tester, target, bid))
        else:
            bid = c.execute("insert into batches(name, tester, created_at, ring_target) values(?,?,?,?)",
                            (batch, tester, now, target)).lastrowid
        for r in rows:
            c.execute("insert or replace into rings(mac, ble_name, unit_id, batch_id) values(?,?,?,?)",
                      (r["addr"], r.get("name"), r.get("unit_id"), bid))
            c.execute("insert into results(batch_id, mac, stage, status, values_json, tester, started_at, saved_at)"
                      " values(?,?,?,?,?,?,?,?)",
                      (bid, r["addr"], stage, r["status"], json.dumps(r.get("values", {}), default=str),
                       tester, started_at, now))
            samples = [(bid, r["addr"], stage, t, v) for t, v in r.get("samples", []) if isinstance(v, (int, float))]
            if samples:
                c.execute("delete from samples where batch_id=? and mac=? and stage=?", (bid, r["addr"], stage))
                c.executemany("insert into samples values(?,?,?,?,?)", samples)
    return bid


def _latest(c, bid):
    latest = {}
    for row in c.execute("select * from results where batch_id=? order by saved_at", (bid,)):
        latest[(row["mac"], row["stage"])] = row
    return latest


def _bucket(status):
    return "pass" if status == "PASS" else "fail" if status.startswith("FAIL") else "other"


def list_batches():
    with _conn() as c:
        out = []
        for b in c.execute("select * from batches order by created_at desc").fetchall():
            stages, last = {}, None
            for (_, st), r in _latest(c, b["id"]).items():
                s = stages.setdefault(st, {"pass": 0, "fail": 0, "other": 0})
                s[_bucket(r["status"])] += 1
                last = max(last or 0, r["saved_at"])
            n = c.execute("select count(*) from rings where batch_id=?", (b["id"],)).fetchone()[0]
            out.append({**dict(b), "rings": n, "stages": stages, "last_saved": last})
        return out


def batch_detail(bid):
    with _conn() as c:
        b = c.execute("select * from batches where id=?", (bid,)).fetchone()
        if not b:
            return None
        rings = {r["mac"]: {**dict(r), "results": {}} for r in
                 c.execute("select * from rings where batch_id=? order by unit_id", (bid,))}
        seen = set()
        for (mac, st), r in _latest(c, bid).items():
            seen.add(st)
            if mac in rings:
                rings[mac]["results"][st] = {"status": r["status"], "values": json.loads(r["values_json"] or "{}"),
                                             "saved_at": r["saved_at"], "tester": r["tester"]}
        stages = [s for s in STAGE_ORDER if s in seen] + sorted(seen - set(STAGE_ORDER))
        return {"batch": dict(b), "stages": stages, "rings": list(rings.values())}


def batch_csv(bid):
    d = batch_detail(bid)
    if not d:
        return None
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["batch", "unit_id", "ble_name", "mac"] + [f"{s}_{k}" for s in d["stages"] for k in ("status", "values")])
    for r in d["rings"]:
        row = [d["batch"]["name"], r["unit_id"], r["ble_name"], r["mac"]]
        for s in d["stages"]:
            res = r["results"].get(s, {})
            row += [res.get("status", ""), json.dumps(res.get("values", ""))]
        w.writerow(row)
    return buf.getvalue()
