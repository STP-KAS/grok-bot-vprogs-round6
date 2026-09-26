#!/usr/bin/env python3
"""round5 faucet feeder + faucet-empty detector (TN10 only).
Every 60 s: fetch the faucet (desk key 0) UTXOs from the public TN10 API (live kaspad utxoindex; our n0 has no index),
keep mature coinbase/normal UTXOs (daa + 1200 < virtual DAA from n0), and write them to /tmp/rw-desk-utxos.json for the
storm workers (LOW_P>0 refill). UTXOs whose int(txid[8:16],16) % 2 == 1 (independent of the storm worker split on txid[0:8]) (50%, r5 09:43) are RESERVED (ttt: % 4 == 1, vprog: % 4 == 3) for the round5 game/vprog funders and are
never given to the storm. Logs faucet balance to logs/round5/faucet.jsonl.
Faucet-empty rule: API balance < EMPTY_TKAS (default 5000) AND storm pool (state files) < POOL_TKAS (5000) for 15 min in a row
-> writes /tmp/r5-faucet-empty (JSON with time); r5-stop.sh then stops all senders by exact pid."""
import json, time, os, glob, urllib.request, asyncio, websockets
D = "/workspace/tn10-break-test-2026-09-25"; L = f"{D}/logs/round5/faucet.jsonl"
A = "kaspatest:qzffl5xy9np46gkttyuftqnv2w04pr8g3wsp7c3vv8se3txtelx6q7c0v0ldx"; API = "https://api-tn10.kaspa.org"
OUT = "/tmp/rw-desk-utxos.json"; RES = "/tmp/r5-reserved-utxos.json"; EMPTY = "/tmp/r5-faucet-empty"
EMPTY_TKAS = float(os.environ.get("EMPTY_TKAS", 3000)); POOL_TKAS = float(os.environ.get("POOL_TKAS", 5000))
def get(u, t=60): return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "grok-r5", "Cache-Control": "no-cache"}), timeout=t).read())
def post_utxos(t=90):  # r5 09:40: GET /addresses/<a>/utxos is CDN-cached (stale ~minutes); POST /addresses/utxos is live
    r = urllib.request.Request(f"{API}/addresses/utxos", data=json.dumps({"addresses": [A]}).encode(), headers={"User-Agent": "grok-r5", "content-type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read())
async def vdaa():
    async with websockets.connect("ws://127.0.0.1:18210", open_timeout=5, max_size=2**22) as ws:
        await ws.send(json.dumps({"id": 1, "method": "getBlockDagInfo", "params": {}}))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), 8))
            if r.get("id") == 1: return int(r["params"]["virtualDaaScore"])
def pool():
    t = 0
    for f in glob.glob(f"{D}/state-rw-*.json"):
        try: t += sum(int(u[2]) for us in json.load(open(f)).values() for u in us)
        except Exception: pass
    return t / 1e8
low_since = None
while True:
    try:
        bal = get(f"{API}/addresses/{A}/balance", 20)["balance"] / 1e8
        us = post_utxos(); v = asyncio.run(vdaa())
        mat = [u for u in us if int(u["utxoEntry"]["blockDaaScore"]) + 1200 < v]
        storm = []  # r5 10:02: storm keeps its own pool; ALL mature faucet UTXOs go to the game/vprog runners
        res = mat
        for f, x in ((OUT, storm), (RES, res)):
            open(f + ".tmp", "w").write(json.dumps(x)); os.replace(f + ".tmp", f)
        p = pool(); now = time.time()
        if sum(int(u["utxoEntry"]["amount"]) for u in mat) / 1e8 < EMPTY_TKAS: low_since = low_since or now  # r5 10:14: "effectively empty" = spendable (mature) faucet < EMPTY_TKAS for 15 min; the balance never hits 0 while miners keep paying it (immature coinbase + fee return)  # r5 10:08: faucet-only rule (storm pool is separate); our miners refill the faucet (~1k TKAS/min + ~57% of fees), so "empty" = balance AND mature < EMPTY_TKAS for 15 min
        else: low_since = None
        o = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "faucet_tkas": round(bal, 1), "utxos": len(us), "mature": len(mat),
             "mature_tkas": round(sum(int(u["utxoEntry"]["amount"]) for u in mat) / 1e8, 1), "storm_list": len(storm), "reserved": len(res),
             "reserved_tkas": round(sum(int(u["utxoEntry"]["amount"]) for u in res) / 1e8, 1), "storm_pool_tkas": round(p), "vdaa": v,
             "low_for_s": round(now - low_since) if low_since else 0}
        open(L, "a").write(json.dumps(o) + "\n")
        # r6: no hard stop here any more; r6-final-watch.sh owns the stop rule (income-only 30 min or 12:30)
    except Exception as e:
        open(L, "a").write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "err": str(e)[:200]}) + "\n")
    time.sleep(30)
