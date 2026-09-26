#!/usr/bin/env python3
"""round6 dynamic fee rule (user 12:22: 'keep transaction costs double the standard so we have priority').
Every 30 s: feerate = max(2 x getFeeEstimate normalBuckets[0].feerate, 2 x network minimum (100 sompi/g) = 200) sompi/gram.
Writes /tmp/r6-feerate (runners + KNS + funding read it), /tmp/r5-feerate (legacy name, same value), and the storm multiplier
/tmp/r6-storm-mult (= feerate/100, storm base is 100 sompi/g x FEE_MULT). Logs every sample to logs/round6/feerate.jsonl."""
import json, time, asyncio, websockets
D = "/workspace/tn10-break-test-2026-09-25"; L = f"{D}/logs/round6/feerate.jsonl"; FLOOR = 200
async def est():
    async with websockets.connect("ws://127.0.0.1:18210", open_timeout=5, max_size=2**22) as ws:
        await ws.send(json.dumps({"id": 1, "method": "getFeeEstimate", "params": {}}))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), 8))
            if r.get("id") == 1: return r["params"]["estimate"]
while True:
    try:
        e = est_ = asyncio.run(est()); normal = float(e["normalBuckets"][0]["feerate"]); prio = float(e["priorityBucket"]["feerate"])
        fr = max(FLOOR, int(round(2 * normal)))
        for f, v in (("/tmp/r6-feerate", fr), ("/tmp/r5-feerate", fr), ("/tmp/r6-storm-mult", round(fr / 100, 2))):
            open(f + ".tmp", "w").write(str(v)); __import__("os").replace(f + ".tmp", f)
        open(L, "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "normal": round(normal, 1), "priority": round(prio, 1), "feerate_used": fr}) + "\n")
    except Exception as x:
        open(L, "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "err": str(x)[:120]}) + "\n")
    time.sleep(30)
