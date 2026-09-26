#!/usr/bin/env python3
"""round6 recovery measurement after the final stop: every 5 s for up to 15 min (or until mempool < 500 for 60 s)
logs n0 mempool size, fee estimate, sink age, and processed-tx lines -> logs/round6/recovery.jsonl; summary to ramp.log."""
import json, time, asyncio, websockets, subprocess
D = "/workspace/tn10-break-test-2026-09-25"; L = f"{D}/logs/round6/recovery.jsonl"
async def q():
    async with websockets.connect("ws://127.0.0.1:18210", open_timeout=5, max_size=2**22) as ws:
        async def c(i, m):
            await ws.send(json.dumps({"id": i, "method": m, "params": {}}))
            while True:
                r = json.loads(await asyncio.wait_for(ws.recv(), 8))
                if r.get("id") == i: return r.get("params") or {}
        info = await c(1, "getInfo"); fe = await c(2, "getFeeEstimate")
        return int(info["mempoolSize"]), fe.get("estimate", {}).get("priorityBucket", {}).get("feerate")
t0 = time.time(); low = None; first = None; rows = []
while time.time() - t0 < 900:
    try: mp, pr = asyncio.run(q())
    except Exception as e: mp, pr = None, None
    r = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "s": round(time.time() - t0), "mempool": mp, "prio_feerate": pr}
    open(L, "a").write(json.dumps(r) + "\n"); rows.append(r); first = first or mp
    if mp is not None and mp < 500: low = low or time.time()
    else: low = None
    if low and time.time() - low > 60: break
    time.sleep(5)
drain = next((r["s"] for r in rows if r["mempool"] is not None and r["mempool"] < 500), None)
open(f"{D}/logs/storm/ramp.log", "a").write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + f" R6-RECOVERY mempool {first} -> {rows[-1]['mempool']} ; <500 after {drain} s ; samples {len(rows)} (logs/round6/recovery.jsonl)\n")
