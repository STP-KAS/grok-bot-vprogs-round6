#!/usr/bin/env python3
"""round5 (derived from r4-pacer.py): NO end time; RATE_MAX = TARGET tapered by a soft disk reserve for the ~18:50 pruning:
  factor = clamp((free - SOFT_LO)/(SOFT_HI - SOFT_LO), 0, 1)  (default 18 G -> full, 16 G -> 0), plus all r4 guards below.
Original r4 doc: round4 8-hour storm pacer + guard (TN10 only). Standalone daemon; replaces r4-guard.py. Every 10 s it writes RATE_MAX
(4th field of /tmp/tps-storm.limits; the supervisor re-reads it every 3 s):
  RATE_MAX = clamp(min(disk_rate, fund_rate), 0, CAP)
    disk_rate = (free_GB - DISK_FLOOR) * 2^30 / BYTES_PER_TX / seconds_left        (spread the disk over the run)
    fund_rate = pool_TKAS / FEE_TKAS_PER_TX / seconds_left                          (spread the storm funds over the run)
Guards (override the pacing):
  - mempool > MP_BRAKE (80k)            -> RATE_MAX=0, auto-resume after 60 s once mempool < 40k
  - free disk < DISK_GUARD (12 G)       -> RATE_MAX=0, auto-resume only when free > DISK_RESUME (15 G)
  - free disk drop > 3 G within 120 s   -> RATE_MAX=0 for 10 min, then resume only if the drop has stopped (< 0.5 G/120 s)
  - n0 crash (kaspad pid changed/missing, RPC down 60 s, or not synced 120 s) -> RATE_MAX=0 and LATCH (/tmp/r4-pacer.LATCH);
    never auto-resumes; a human must check n0 and delete the latch file.
  - at END (15:32 CEST) -> RATE_MAX=0 and exit.
Config: /tmp/r4-pacer.conf (JSON, re-read each loop) keys END, CAP, DISK_FLOOR, BYTES_PER_TX, FEE_TKAS_PER_TX, MP_BRAKE,
DISK_GUARD, DISK_RESUME. Logs: logs/round4/pacer.jsonl (every 10 s) and major events to logs/storm/ramp.log."""
import json, os, time, glob, shutil, asyncio, websockets
D = "/workspace/tn10-break-test-2026-09-25"; L = f"{D}/logs/round5/pacer.jsonl"; R = f"{D}/logs/storm/ramp.log"
LIM = "/tmp/tps-storm.limits"; LATCH = "/tmp/r4-pacer.LATCH"; CONF = "/tmp/r5-pacer.conf"
DEF = {"TARGET": 1500, "SOFT_HI": 18.0, "SOFT_LO": 16.0, "END": time.mktime(time.strptime("2026-09-26 15:32:00", "%Y-%m-%d %H:%M:%S")), "CAP": 25000, "DISK_FLOOR": 12.5,
       "BYTES_PER_TX": 600, "FEE_TKAS_PER_TX": 0.00643, "MP_BRAKE": 80000, "DISK_GUARD": 12.0, "DISK_RESUME": 15.0}
def conf():
    c = dict(DEF)
    try: c.update(json.load(open(CONF)))
    except Exception: pass
    return c
def log(o): open(L, "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **o}) + "\n")
def ramp(s): open(R, "a").write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + " R5-PACER " + s + "\n")
def set_rmax(v):
    a = open(LIM).read().split(); a[3] = str(int(v)); open(LIM, "w").write(" ".join(a))
def kaspad_pid():
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                a = open(f"/proc/{p}/cmdline").read().split("\0")
                if a and a[0].endswith("/kaspad") and "--appdir=/tmp/kaspa-data-tn10-n0" in a: return int(p)
            except Exception: pass
    return None
async def n0():
    try:
        async with websockets.connect("ws://127.0.0.1:18210", open_timeout=3, max_size=2**22) as ws:
            async def c(i, m):
                await ws.send(json.dumps({"id": i, "method": m, "params": {}}))
                while True:
                    r = json.loads(await asyncio.wait_for(ws.recv(), 6))
                    if r.get("id") == i: return r.get("params") or {}
            info = await c(1, "getInfo"); s = await c(2, "getSyncStatus")
            return int(info["mempoolSize"]), bool(s.get("isSynced"))
    except Exception: return None, None
def pool_tkas():
    t = 0
    for f in glob.glob(f"{D}/state-rw-*.json"):
        try: t += sum(int(u[2]) for us in json.load(open(f)).values() for u in us)
        except Exception: pass
    return t / 1e8
pid0 = kaspad_pid(); was_latched = False; hist = []; mp_hold = 0; disk_hold = False; drop_hold = 0; down_since = None; unsync_since = None; pool = pool_tkas(); pool_t = time.time()
ramp(f"start: n0 pid {pid0}, pool {pool:.0f} TKAS, conf {json.dumps(conf())}")
while True:
    c = conf(); now = time.time(); left = 0
    free = shutil.disk_usage("/").free / 2**30; mp, synced = asyncio.run(n0()); pid = kaspad_pid()
    if now - pool_t > 120: pool = pool_tkas(); pool_t = now
    hist.append((now, free)); hist[:] = [x for x in hist if now - x[0] <= 120]; drop = max(x[1] for x in hist) - free
    reason = None
    if was_latched and not os.path.exists(LATCH):  # a human cleared the latch: adopt the current n0 pid
        pid0 = pid; down_since = unsync_since = None; was_latched = False; ramp(f"latch cleared by hand -> n0 pid {pid}, resume")
    if mp is None: down_since = down_since or now
    else: down_since = None
    if synced is False: unsync_since = unsync_since or now
    else: unsync_since = None
    crash = (pid != pid0) or (down_since and now - down_since > 60) or (unsync_since and now - unsync_since > 120)
    if crash and not os.path.exists(LATCH):
        open(LATCH, "w").write(json.dumps({"t": time.ctime(), "pid0": pid0, "pid": pid, "mp": mp, "synced": synced}))
        ramp(f"n0 CRASH/unhealthy (pid {pid0}->{pid}, rpc_ok={mp is not None}, synced={synced}) -> RATE_MAX=0 LATCHED; check n0, then delete {LATCH} to resume")
    if os.path.exists(LATCH): reason = "latched"; was_latched = True
    if mp is not None and mp > c["MP_BRAKE"]:
        if not mp_hold: ramp(f"mempool {mp} > {c['MP_BRAKE']} -> RATE_MAX=0 (>=60 s, resume when < 40k)")
        mp_hold = now + 60
    if mp_hold and (now < mp_hold or mp is None or mp >= 40000):
        reason = reason or "mp-brake"
    elif mp_hold: mp_hold = 0; ramp(f"mempool {mp} < 40k -> resume")
    if free < c["DISK_GUARD"] and not disk_hold: disk_hold = True; ramp(f"disk {free:.2f}G < {c['DISK_GUARD']}G -> RATE_MAX=0 until > {c['DISK_RESUME']}G")
    if disk_hold and free > c["DISK_RESUME"]: disk_hold = False; ramp(f"disk {free:.2f}G > {c['DISK_RESUME']}G -> resume")
    if disk_hold and not reason: reason = "disk-guard"
    if drop > 3.0 and not drop_hold: drop_hold = now + 600; ramp(f"disk drop {drop:.2f}G in 120 s -> RATE_MAX=0 for 10 min")
    if drop_hold and now >= drop_hold and drop < 0.5: drop_hold = 0; ramp("disk drop stopped -> resume")
    if drop_hold and not reason: reason = "disk-drop"
    fac = max(0.0, min(1.0, (free - c["SOFT_LO"]) / (c["SOFT_HI"] - c["SOFT_LO"])))
    disk_rate = c["TARGET"] * fac; fund_rate = -1
    target = 0 if reason else int(min(c["CAP"], disk_rate))
    set_rmax(target)
    log({"free_gb": round(free, 2), "drop_120s": round(drop, 2), "mp": mp, "synced": synced, "pid": pid, "pool_tkas": round(pool), "disk_rate": int(disk_rate), "fund_rate": int(fund_rate), "rate_max": target, "reason": reason, "soft_fac": round(fac, 3)})
    time.sleep(10)
