#!/usr/bin/env python3
"""12h TPS storm supervisor (TN10 only). Detached; survives the agent session.
- Starts/keeps alive the sender workers (rwstorm.mjs, MODE=p2w, 8 procs) + the 0.5 TKAS lane (storm3.mjs, wallets 0-399)
  + the vprog game bot if present. A worker that exits before the end is restarted (it resumes from its state file).
- Guards every 10 s: free disk < 8 GB or free RAM < 1 GB -> concurrency 0 (pause) until recovered; a node that is down,
  not synced or sink_age > 30 s is removed from /tmp/tps-storm.nodes (workers stop sending to it); a kaspad process that
  died is restarted with its exact original flags (records the event).
- Mempool target: keeps the larger node mempool between LOW_MP and HIGH_MP by adjusting per-worker concurrency
  (/tmp/tps-storm.conc). ram-scale 0.1 caps the mempool at 100k txs, and kaspad 2.1.0 panicked at that cap on 2026-09-25.
- Logs a line every 10 s to logs/tps12h/supervisor.jsonl and an hourly summary line to logs/tps12h/hourly.jsonl.
- /tmp/tps-storm.HALT stops everything cleanly (workers save state and exit; supervisor exits).
usage: setsid nohup python3 tps-supervisor.py HOURS &"""
import json, os, subprocess, sys, time, re, shutil, glob, asyncio
import websockets
H = float(sys.argv[1]) if len(sys.argv) > 1 else 12
D = "/workspace/tn10-break-test-2026-09-25"; LOG = f"{D}/logs/tps12h"; os.makedirs(LOG, exist_ok=True)
HALT = "/tmp/tps-storm.HALT"; CONCF = "/tmp/tps-storm.conc"; NODESF = "/tmp/tps-storm.nodes"; PIDF = "/tmp/tps-storm.pid"
open(PIDF, "w").write(str(os.getpid()))
END = time.time() + H * 3600
LOW_MP, HIGH_MP, PANIC_MP, CMIN, CMAX = 40000, 60000, 72000, 2, 96
NODE_HI, NODE_LO = 70000, 50000; DISK_FULL, DISK_ZERO = 9.5, 8.4; dfac = 1.0; BYTES_PER_TX = 320; disk_cap = 0; FULL = os.environ.get('FULL', '1') == '1'; FULL_LO, FULL_HI = 40000, 60000; mtaper = 1.0; gated = set(); prev_mp = None; prev_t = 0; drain = None
# PANIC_MP: kaspad 2.1.0 panicked at the 100k mempool cap (assert in validate_and_insert_transaction.rs:123) during this test,
# so above 70k the fleet is cut to CMIN at once and the 0.5 lane pauses. Thresholds can be overridden live in /tmp/tps-storm.limits
# as "LOW HIGH PANIC RATE_MAX".
JP = {n: {"n0": 18210, "n1": 18220}[n] for n in os.environ.get("STORM_NODES", "n0 n1").split()}  # 2026-09-25 21:33: n0 only (n1 data wiped for disk)
NODE_CMD = {n: ["/workspace/artifacts/kaspa-tn10/bin/kaspad", "--testnet", "--netsuffix=10", f"--appdir=/tmp/kaspa-data-tn10-{n}", f"--logdir=/tmp/kaspa-logs-tn10-{n}",
               f"--listen=0.0.0.0:{p}1", f"--rpclisten=127.0.0.1:{p}0", f"--rpclisten-borsh=127.0.0.1:{b}", f"--rpclisten-json=127.0.0.1:{j}",
               "--ram-scale=0.1", "--async-threads=4", "--outpeers=6", "--maxinpeers=24", "--rpcmaxclients=64", "--disable-upnp"] + (["--utxoindex"] if os.path.isdir(f"/tmp/kaspa-data-tn10-{n}/kaspa-testnet-10/datadir/utxoindex") else []) + [f"--addpeer=127.0.0.1:{o}"]  # round4 07:15: utxoindex deleted in the disk emergency -> only pass it if the index exists
            for n, p, b, j, o in (("n0", "1621", 17210, 18210, 16221), ("n1", "1622", 17220, 18220, 16211)) if n in JP}
W = []  # (tag, argv, env)
for k in range(8):
    a = k * 500
    W.append((f"P{k}", ["node", f"{D}/scripts/rwstorm.mjs", f"P{k}", str(a), str(a + 500), str(k * 25000), str((k + 1) * 25000), str(k), "8"],
              {"MODE": "p2w", "AFFINITY": "0", "NODES": " ".join(JP), "COOL": "4000", "FEE_MULT": os.environ.get("FEE_MULT_P", "2.0"), "LOW": os.environ.get("LOW_P", "0"), "REFILL": os.environ.get("REFILL_P", "2000")}))  # r5: LOW_P>0 enables faucet top-up from /tmp/rw-desk-utxos.json
# 0.5 TKAS random lane: signed P2PK storm wallets 0-399, seeded from the last P2SH slice, PAY=0.5 TKAS, random pairs.
W.append(("H", ["node", f"{D}/scripts/rwstorm.mjs", "H", "0", "400", "200000", "207042", "0", "1"],
          {"MODE": "sig", "PAY": "50000000", "NODES": " ".join(JP), "AFFINITY": "1", "COOL": "3000", "FEE_MULT": os.environ.get("FEE_MULT_P", "2.0"), "LOW": "0", "CONC": "8", "CONCFILE": "/tmp/tps-storm-h.conc"}))
if os.path.exists(f"{D}/scripts/gamebot.mjs"):
    W.append(("G", ["node", f"{D}/scripts/gamebot.mjs"], {}))
procs = {}
def log(f, o): open(f"{LOG}/{f}", "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **o}) + "\n")
def start(tag, argv, env):
    e = dict(os.environ, **env, SECS=str(int(END - time.time())))
    out = open(f"{LOG}/worker-{tag}.jsonl", "a")
    procs[tag] = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=e, cwd=D, start_new_session=True)
    log("supervisor.jsonl", {"event": "start", "tag": tag, "pid": procs[tag].pid})
def kaspad_pid(n):
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        try: c = open(f"/proc/{p}/cmdline", "rb").read().split(b"\0")
        except Exception: continue
        if c and c[0].endswith(b"kaspad") and f"--appdir=/tmp/kaspa-data-tn10-{n}".encode() in c: return int(p)
    return None
async def nstat(n):
    try:
        async with websockets.connect(f"ws://127.0.0.1:{JP[n]}", open_timeout=3, max_size=2**24) as ws:
            async def c(i, m, p={}):
                await ws.send(json.dumps({"id": i, "method": m, "params": p}))
                while True:
                    r = json.loads(await asyncio.wait_for(ws.recv(), 8))
                    if r.get("id") == i: return r.get("params") or {}
            s = await c(1, "getSyncStatus"); i = await c(2, "getInfo"); d = await c(3, "getBlockDagInfo")
            b = await c(4, "getBlock", {"hash": d["sink"], "includeTransactions": False})
            return {"synced": bool(s.get("isSynced")), "mempool": int(i.get("mempoolSize", 0)), "daa": int(d["virtualDaaScore"]),
                    "sink_age_s": round(time.time() - int(b["block"]["header"]["timestamp"]) / 1000, 1)}
    except Exception as e:
        return {"err": type(e).__name__}
def appdir_gb(n):
    r = subprocess.run(["du", "-sm", f"/tmp/kaspa-data-tn10-{n}"], capture_output=True, text=True)
    try: return round(int(r.stdout.split()[0]) / 1024, 2)
    except Exception: return None
def last_worker_line(tag):
    try:
        with open(f"{LOG}/worker-{tag}.jsonl", "rb") as f:
            f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - 8000)); ls = f.read().decode(errors="ignore").strip().split("\n")
        for l in reversed(ls):
            if l.startswith("{") and ('"step":"rw"' in l or '"step":"storm"' in l):
                d = json.loads(l)
                # round4 06:50: a dead/exited worker leaves its last line behind -> stale TPS. Ignore lines older than 25 s (workers log every 10 s).
                try:
                    import calendar
                    ts = calendar.timegm(time.strptime(d["t"][:19], "%Y-%m-%dT%H:%M:%S"))
                    if time.time() - ts > 25: return None
                except Exception: pass
                return d
    except Exception: pass
    return None
conc = 96; RATEF = '/tmp/tps-storm.rate'; RMIN, RMAX = 500, 30000
rate = float(open(RATEF).read()) if os.path.exists(RATEF) else 3000
open(CONCF, "w").write(str(conc)); open(NODESF, "w").write(" ".join(JP))
open("/tmp/tps-storm-h.conc", "w").write("8")

for w in W: start(*w)
PERIOD = 3 if FULL else 10
hour0 = time.time(); hacc = []; paused = False; du_t = 0; du = {}
STOPF = "/tmp/tn10-break.STOP"; stop_logged = 0; DGF = "/tmp/tps-storm.diskguard"; dg_on = False
while True:
    now = time.time()
    if os.path.exists(HALT) or now > END:
        log("supervisor.jsonl", {"event": "stopping", "reason": "HALT" if os.path.exists(HALT) else "end"})
        open(HALT, "a").close()
        for t, p in procs.items():
            try: p.wait(60)
            except Exception: p.kill()
        log("supervisor.jsonl", {"event": "stopped"}); break
    # nodes
    st = {n: asyncio.run(nstat(n)) for n in JP}
    for n in JP:
        if kaspad_pid(n) is None:
            subprocess.Popen(NODE_CMD[n], stdout=open(f"/tmp/kaspa-logs-tn10-{n}/stdout.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd="/tmp", start_new_session=True)
            time.sleep(2); pid = kaspad_pid(n)
            if pid: open(f"/tmp/relqunch-fleet/tn10-{n}.pid", "w").write(str(pid))
            log("supervisor.jsonl", {"event": "node-restart", "node": n, "pid": pid})
    # per-node mempool gate (hysteresis): above NODE_HI a node gets no new traffic until it is back below NODE_LO.
    for n in JP:
        m = st[n].get("mempool", 0)
        if m > NODE_HI and n not in gated: gated.add(n); log("supervisor.jsonl", {"event": "gate-on", "node": n, "mempool": m})
        elif m < NODE_LO and n in gated: gated.discard(n); log("supervisor.jsonl", {"event": "gate-off", "node": n, "mempool": m})
    healthy = [n for n in JP if st[n].get("synced") and st[n].get("sink_age_s", 999) <= 30 and n not in gated]
    open(NODESF, "w").write(" ".join(healthy))
    # round4 06:50: the monitor's STOP file makes every worker exit at once and is never cleared -> say so loudly.
    if os.path.exists(STOPF):
        if now - stop_logged > 60:
            try: why = open(STOPF).read()[:300]
            except Exception: why = "?"
            log("supervisor.jsonl", {"event": "STOP-FILE-PRESENT", "file": STOPF, "note": "rwstorm workers exit instantly while it exists; remove it by hand after checking the cause", "content": why}); stop_logged = now
    # resources
    disk = shutil.disk_usage("/").free / 2**30
    mem = int(re.search(r"MemAvailable:\s+(\d+)", open("/proc/meminfo").read()).group(1)) / 1024
    mp = max([st[n].get("mempool", 0) for n in JP] or [0])
    if disk < 8 or mem < 1024:
        if not paused: log("supervisor.jsonl", {"event": "pause", "disk_gb": round(disk, 2), "mem_mb": int(mem)})
        paused = True; open(CONCF, "w").write("0"); open(RATEF, "w").write("0"); open("/tmp/tps-storm-h.conc", "w").write("0")
    else:
        if paused: log("supervisor.jsonl", {"event": "resume"}); paused = False; open("/tmp/tps-storm-h.conc", "w").write("8")
        try: LOW_MP, HIGH_MP, PANIC_MP, RMAX = map(int, open("/tmp/tps-storm.limits").read().split())
        except Exception: pass
        # 22:45 user safety: taper/gate live-tunable in /tmp/tps-storm.limits2 = "FULL_LO FULL_HI NODE_HI NODE_LO" (defaults 40000 60000 70000 50000)
        try: FULL_LO, FULL_HI, NODE_HI, NODE_LO = map(int, open("/tmp/tps-storm.limits2").read().split())
        except Exception: pass
        # rate control for the 8 TPS workers: estimate inclusion (drain) rate = accepted - d(mempool)/dt (EMA), then
        # offer drain + (TARGET_MP - mempool)/20 s, i.e. close the gap to the target backlog within ~20 s.
        acc_now = sum((last_worker_line(t) or {}).get("tps_accepted", 0) for t, _, _ in W)
        mpn = sum(st[n].get("mempool", 0) for n in JP) / len(JP)
        if prev_mp is not None:
            dr = acc_now - (mpn - prev_mp) / max(1, now - prev_t)
            drain = dr if drain is None else 0.7 * drain + 0.3 * dr
        prev_mp, prev_t = mpn, now
        TARGET_MP = (LOW_MP + HIGH_MP) / 2
        if drain is not None: rate = min(RMAX, max(RMIN, drain + (TARGET_MP - mp) / 20))
        if mp > PANIC_MP: rate = RMIN
        # disk budget: each accepted tx costs ~300 B per node (measured 21:25-21:29: ~9 GB/h at ~4k TPS on 2 nodes) and TN10
        # keeps block data for the whole pruning window (>1 day), so disk sets the sustainable rate, not the node.
        # Full rate above DISK_FULL GB free, linear taper to 0 at DISK_ZERO (> the hard 8 GB floor); resumes when pruning frees space.
        dfac = min(1.0, max(0.0, (disk - DISK_ZERO) / (DISK_FULL - DISK_ZERO)))
        # budget cap: spread the disk above DISK_ZERO evenly over the remaining run time at BYTES_PER_TX per tx on the node(s).
        disk_cap = max(0.0, (disk - DISK_ZERO) * 2**30 / max(1800, END - now) / (BYTES_PER_TX * len(JP)))
        # FULL THROTTLE (user 21:35): no rate target, no 12h disk rationing. The only brake is a mempool taper so the node never
        # nears the 100k assert: full RMAX below FULL_LO, linear down to 0 at FULL_HI (checked every 3 s), plus the 85k/70k gate.
        mtaper = min(1.0, max(0.0, (FULL_HI - mp) / (FULL_HI - FULL_LO)))
        eff = (max(0, rate - 150) if not FULL else RMAX * mtaper) * dfac
        open("/tmp/tps-storm-h.conc", "w").write("0" if (mp > PANIC_MP or dfac == 0) else "8")
        if mp > PANIC_MP: eff = 0  # 22:45 hard brake: nothing new above PANIC_MP (90k via limits)
        # round4 06:50: live disk guard (GB) in /tmp/tps-storm.diskguard: below it the storm offers 0 (logged once per crossing).
        try: dguard = float(open(DGF).read().split()[0])
        except Exception: dguard = 0.0
        if disk < dguard:
            eff = 0; open("/tmp/tps-storm-h.conc", "w").write("0")
            if not dg_on: log("supervisor.jsonl", {"event": "DISK-GUARD-ON", "disk_gb": round(disk, 2), "guard_gb": dguard}); dg_on = True
        elif dg_on and disk > dguard + 0.3: log("supervisor.jsonl", {"event": "DISK-GUARD-OFF", "disk_gb": round(disk, 2)}); dg_on = False
        open(RATEF, "w").write(str(int(eff))); open(CONCF, "w").write(str(CMAX))
    # workers
    for tag, argv, env in W:
        p = procs.get(tag)
        if p and p.poll() is not None and time.time() < END - 60 and not os.path.exists(HALT):
            log("supervisor.jsonl", {"event": "worker-exit", "tag": tag, "code": p.returncode}); time.sleep(1); start(tag, argv, env)
    ls = {t: last_worker_line(t) for t, _, _ in W}
    off = sum((l or {}).get("tps_submitted", 0) for t, l in ls.items() if t.startswith("P"))
    acc = sum((l or {}).get("tps_accepted", 0) for t, l in ls.items() if t.startswith("P"))
    half = (ls.get("H") or {})
    if now - du_t > 600: du = {n: appdir_gb(n) for n in JP}; du_t = now
    rec = {"offered_tps": round(off, 1), "accepted_tps": round(acc, 1), "half_lane_tps": half.get("tps_accepted"),
           "senders": sum((l or {}).get("distinct_senders", 0) for t, l in ls.items() if t.startswith("P")),
           "receivers": sum((l or {}).get("distinct_receivers", 0) for t, l in ls.items() if t.startswith("P")),
           "pool": sum((l or {}).get("pool", 0) for t, l in ls.items() if t.startswith("P")),
           "fees_tkas": round(sum(int((l or {}).get("fees_sompi", "0")) for l in ls.values()) / 1e8, 2),
           "rate_cap": int(((max(0, rate - 150)) if not FULL else RMAX * mtaper) * dfac) if not paused else 0, "disk_factor": round(dfac, 2), "disk_cap_tps": int(disk_cap), "full": FULL, "mempool_taper": round(mtaper, 2), "nodes": st, "healthy": healthy, "disk_free_gb": round(disk, 2), "mem_avail_mb": int(mem), "appdir_gb": du,
           "workers_alive": sum(1 for p in procs.values() if p.poll() is None), "workers_fresh": sum(1 for l in ls.values() if l), "stop_file": os.path.exists(STOPF), "disk_guard_on": dg_on}
    log("supervisor.jsonl", rec); hacc.append(rec)
    if now - hour0 >= 3600:
        a = [r["accepted_tps"] for r in hacc]
        log("hourly.jsonl", {"hour_start": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(hour0)), "samples": len(a), "accepted_tps_avg": round(sum(a) / max(1, len(a)), 1),
                              "accepted_tps_min": min(a or [0]), "accepted_tps_max": max(a or [0]), "disk_free_gb": round(disk, 2), "appdir_gb": du, "fees_tkas_workers": rec["fees_tkas"]})
        hour0 = now; hacc = []
    time.sleep(max(0.5, PERIOD - (time.time() - now)))
os.remove(PIDF)
