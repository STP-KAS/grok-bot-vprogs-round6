#!/usr/bin/env python3
"""round6 final-stop + guard + pruning watcher (user 12:19-12:28). Every 15 s:
 GUARD  mempool > 80k -> storm rate 0 (resume < 40k). disk < 13 G -> pause ttt/vprog/storm (rate 0); KNS exempt (negligible disk per TKAS),
        resume > 14 G. disk < 8 G (hard floor) -> final stop.
 PRUNE  18:30 pause all senders; clean regenerable junk (npm/pip caches) to aim >= 20 G free; if still < 20 G at 18:45 -> SIGINT n0
        (exact pid), wait for exit, restart it (tps-supervisor NODE_CMD, no --utxoindex) once free >= 20 G (or after 15 min if >= 13 G).
        Resume when the n0 log shows pruning finished after 18:25 ('SMT pruning complete' / 'Header and Block pruning completed')
        + 5 min quiet + disk drop < 0.3 G / 2 min + free > 13 G. Fallback: no pruning seen by 19:30 and free >= 15 G -> resume.
 STOP   earliest of: all funds (mature faucet + storm pool, from faucet.jsonl) < 3,000 TKAS for 15 min, 20:00 CEST, disk < 8 G.
        -> scripts/r5-stop.sh r6-final, then scripts/r6-recovery.py (15-min drain measurement). Exact-pid only; never touches miners/KNS keepalive."""
import json, time, os, shutil, subprocess, asyncio, re, signal, datetime as dt
import websockets
D = "/workspace/tn10-break-test-2026-09-25"; LOG = f"{D}/logs/round6/final-watch.jsonl"; RAMP = f"{D}/logs/storm/ramp.log"
NLOG = "/tmp/kaspa-logs-tn10-n0/stdout.log"
RATES = {"/tmp/r5-ttt.rate": None, "/tmp/r5-vprog.rate": None, "/tmp/tps-storm.rate": None}
NODE_CMD = ["/workspace/artifacts/kaspa-tn10/bin/kaspad", "--testnet", "--netsuffix=10", "--appdir=/tmp/kaspa-data-tn10-n0", "--logdir=/tmp/kaspa-logs-tn10-n0",
            "--listen=0.0.0.0:16211", "--rpclisten=127.0.0.1:16210", "--rpclisten-borsh=127.0.0.1:17210", "--rpclisten-json=127.0.0.1:18210",
            "--ram-scale=0.1", "--async-threads=4", "--outpeers=6", "--maxinpeers=24", "--rpcmaxclients=64", "--disable-upnp", "--addpeer=127.0.0.1:16221"]
def now(): return dt.datetime.now()
def at(h, m): return now().replace(hour=h, minute=m, second=0, microsecond=0)
def ramp(s): open(RAMP, "a").write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} R6-WATCH {s}\n")
def log(o): open(LOG, "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **o}) + "\n")
def rd(f):
    try: return open(f).read().strip()
    except Exception: return None
def wr(f, v): open(f + ".tmp", "w").write(str(v)); os.replace(f + ".tmp", f)
async def _mp():
    async with websockets.connect("ws://127.0.0.1:18210", open_timeout=5, max_size=2**22) as ws:
        await ws.send(json.dumps({"id": 1, "method": "getInfo", "params": {}}))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), 8))
            if r.get("id") == 1: return int(r["params"]["mempoolSize"])
def mempool():
    try: return asyncio.run(_mp())
    except Exception: return None
def funds():
    try:
        with open(f"{D}/logs/round5/faucet.jsonl", "rb") as f:
            f.seek(max(0, os.path.getsize(f.name) - 20000)); ls = f.read().decode(errors="ignore").strip().split("\n")[1:]
        js = [json.loads(x) for x in ls if '"mature_tkas"' in x]
        if not js: return None
        j = js[-1]
        if time.time() - dt.datetime.strptime(j["t"], "%Y-%m-%dT%H:%M:%S%z").timestamp() > 600: return None  # stale feeder -> unknown, never "empty"
        k = 0.0
        try:
            if time.time() - os.path.getmtime("/tmp/r6-kns-balance") < 120: k = float(open("/tmp/r6-kns-balance").read())
        except Exception: pass
        return float(j.get("mature_tkas", 0)) + float(j.get("storm_pool_tkas", 0)) + k  # + KNS worker balances
    except Exception: return None
def n0_pid():
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        try: c = open(f"/proc/{p}/cmdline", "rb").read().split(b"\0")
        except Exception: continue
        if c and c[0].endswith(b"/kaspad") and b"--appdir=/tmp/kaspa-data-tn10-n0" in c: return int(p)
    return None
pause_reasons = set()
def kns_sync():  # KNS writes ~nothing to disk per TKAS burned -> exempt from the disk<13G pause; paused only for pruning
    rs = [r for r in pause_reasons if not r.startswith("disk")]
    if rs: open("/tmp/r6-kns.PAUSE", "w").write(",".join(rs))
    else:
        try: os.remove("/tmp/r6-kns.PAUSE")
        except FileNotFoundError: pass
def pause(reason):
    if reason in pause_reasons: return
    first = not pause_reasons; pause_reasons.add(reason)
    if first:
        for f in RATES:
            v = rd(f)
            if v not in (None, "0"): RATES[f] = v
            wr(f, 0)
    kns_sync()
    ramp(f"PAUSE all senders ({reason}); saved rates {RATES}")
def unpause(reason):
    if reason not in pause_reasons: return
    pause_reasons.discard(reason)
    if not pause_reasons:
        for f, v in RATES.items():
            if v is not None: wr(f, v)
        ramp(f"RESUME all senders (cleared {reason}); rates restored {RATES}")
    else: ramp(f"cleared {reason}, still paused by {pause_reasons}")
    kns_sync()
storm_held = False; low_since = None; hist = []
prune_state = "none"  # none -> paused -> (node_stopped) -> resumed
node_stopped_at = None; prune_seen_at = None
def prune_done_since(t0):
    try:
        with open(NLOG, "rb") as f:
            f.seek(max(0, os.path.getsize(NLOG) - 30_000_000)); data = f.read().decode(errors="ignore")
    except Exception: return None
    last = None
    for m in re.finditer(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+\S* \[\w+ *\] (SMT pruning complete|Header and Block pruning completed|Header and Block pruning)", data, re.M):
        ts = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        if ts >= t0: last = (ts, m.group(2))
    return last
def final_stop(why):
    ramp(f"FINAL STOP ({why}) -> r5-stop.sh + r6-recovery.py")
    try: os.remove("/tmp/r6-kns.PAUSE")
    except FileNotFoundError: pass
    subprocess.run(["bash", f"{D}/scripts/r5-stop.sh", f"r6-final: {why}"], cwd=D)
    try: pids = open("/tmp/r6-storm-pids").read().split()
    except Exception: pids = []
    for p in pids:
        try:
            c = open(f"/proc/{p}/cmdline", "rb").read()
            if b"rwstorm.mjs" in c: os.kill(int(p), signal.SIGTERM)
        except Exception: pass
    subprocess.run(["python3", f"{D}/scripts/r6-recovery.py"], cwd=D)
    ramp("FINAL: recovery measurement done (logs/round6/recovery.jsonl)"); log({"ev": "final", "why": why})
ramp(f"started pid {os.getpid()}: stop at funds<3k/15min or 20:00, pruning pause 18:30, disk pause <13G, floor 8G, storm mempool guard 80k/40k")
while True:
    t = now(); free = shutil.disk_usage("/").free / 2**30; mp = mempool(); fu = funds()
    hist.append((time.time(), free)); hist[:] = [h for h in hist if time.time() - h[0] <= 130]; drop = hist[0][1] - free
    # STOP conditions
    if fu is not None and fu < 3000: low_since = low_since or time.time()
    else: low_since = None
    why = None
    if t >= at(20, 0): why = "20:00 backstop"
    elif low_since and time.time() - low_since >= 900: why = f"funds {fu:.0f} < 3k TKAS for 15 min"
    elif free < 8: why = f"disk {free:.2f} G < 8 G hard floor"
    if why: final_stop(why); break
    # storm mempool guard
    if mp is not None and mp > 80000 and not storm_held:
        storm_held = True; v = rd("/tmp/tps-storm.rate")
        if v not in (None, "0"): RATES["/tmp/tps-storm.rate"] = v
        wr("/tmp/tps-storm.rate", 0); ramp(f"mempool {mp} > 80k -> storm rate 0")
    if storm_held and mp is not None and mp < 40000:
        storm_held = False
        if not pause_reasons and RATES["/tmp/tps-storm.rate"]: wr("/tmp/tps-storm.rate", RATES["/tmp/tps-storm.rate"])
        ramp(f"mempool {mp} < 40k -> storm resumed")
    # disk pause
    if free < 13: pause("disk<13G")
    elif free > 14: unpause("disk<13G")
    # pruning protection
    if prune_state == "none" and t >= at(18, 30) and t < at(20, 0):
        pause("pruning-18:30"); prune_state = "paused"
        for c in (["npm", "cache", "clean", "--force"], ["rm", "-rf", "/home/box/.cache/pip"]):
            try: subprocess.run(c, timeout=120, capture_output=True)
            except Exception: pass
        ramp(f"18:30 pruning pause; caches cleaned; free {shutil.disk_usage('/').free/2**30:.2f} G")
    if prune_state == "paused" and t >= at(18, 45) and free < 20 and node_stopped_at is None:
        pid = n0_pid()
        if pid:
            ramp(f"18:45 free {free:.2f} G < 20 G -> SIGINT n0 pid {pid}")
            os.kill(pid, signal.SIGINT)
            for _ in range(120):
                if not os.path.exists(f"/proc/{pid}"): break
                time.sleep(1)
            node_stopped_at = time.time(); ramp(f"n0 exited={not os.path.exists(f'/proc/{pid}')}, free {shutil.disk_usage('/').free/2**30:.2f} G")
    if node_stopped_at and n0_pid() is None and (free >= 20 or (time.time() - node_stopped_at > 900 and free >= 13)):
        subprocess.Popen(NODE_CMD, stdout=open(NLOG, "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd="/tmp", start_new_session=True)
        time.sleep(5); ramp(f"n0 restarted pid {n0_pid()} (free {free:.2f} G)"); node_stopped_at = -1
    if prune_state == "paused" and (node_stopped_at in (None, -1)):
        pd = prune_done_since(at(18, 25))
        if pd:
            if prune_seen_at != pd[0]: prune_seen_at = pd[0]; ramp(f"pruning activity seen in n0 log: {pd[1]} at {pd[0]}")
            quiet = (t - pd[0]).total_seconds()
            if "complete" in pd[1] and quiet >= 300 and drop < 0.3 and free > 13 and mp is not None:
                prune_state = "resumed"; ramp(f"pruning settled ({pd[1]} {pd[0]}), free {free:.2f} G, drop {drop:.2f} G/2min -> resume"); unpause("pruning-18:30")
        elif t >= at(19, 30) and free >= 15 and mp is not None:
            prune_state = "resumed"; ramp(f"no pruning seen by 19:30, free {free:.2f} G -> resume"); unpause("pruning-18:30")
    log({"free_gb": round(free, 2), "drop_2m": round(drop, 2), "mp": mp, "funds_tkas": None if fu is None else round(fu), "low_for_s": int(time.time() - low_since) if low_since else 0,
         "paused": sorted(pause_reasons), "storm_held": storm_held, "prune": prune_state, "n0": n0_pid()})
    time.sleep(15)
