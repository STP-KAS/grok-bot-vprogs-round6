# grok-bot-vprogs round 6 — INTERIM report (live since 10:35 CEST, 26 Sep 2026; updated 12:35 CEST)

Private report by Grok, acting for stp. Kaspa **TN10 only**.
Previous rounds: [round 5 final (09:22–10:35)](https://github.com/STP-KAS/grok-bot-vprogs-round5) · [round 4 final](https://github.com/STP-KAS/grok-bot-vprogs-round4).
Live notes: [`findings/round6-notes.md`](findings/round6-notes.md). The final report replaces this README after the stop.

## Brief
| time (CEST) | user direction |
|---|---|
| 10:33–10:34 | "fix the own vprog / tic-tac-toe, skip the originals, scale, TPS again", "use coins from all the wallets you have", "full gusto", "report in new github" |
| 12:19–12:22 | lower the storm and spend on our own vprog / ttt / **KNS** instead; reduce the miners to 2; drain every local wallet except Grok Build; stop when all TKAS is gone, backstop 20:00; pause for tonight's pruning; "keep transaction costs double the standard so we have priority" |
| 12:27 | KNS: fully random names, random throwaway owners |
| 12:28 | "report to github, keep going until all tkas is gone" |

## 1. Full gusto, 10:35–12:25 (runner process E; own index-free vprog + tic-tac-toe)
Runner fixes at 10:38: orphan retry at funding, stale-resume classification, seed release on failed funding.

| 10:38 → 12:25 | tic-tac-toe | vprog |
|---|---:|---:|
| lanes | 600 | 600 |
| txs submitted / accepted | 3,842,503 / 3,841,174 | 3,869,642 / 3,868,332 |
| games started / finished | 467,891 / 456,892 | programs 364,897 / halted 354,294 |
| moves / steps | 3,831,564 | 3,493,076 |
| illegal attempts / executed | 843,210 / **0** | 701,379 / **0** |
| rejects | **0** | **0** |
| latency p50 / p95 at 12:25 | 1.0 / 3.4 s | 1.0 / 3.6 s |
| fees (runner counter) | 326k TKAS | 344k TKAS |

- **Own runners: 7.71 M txs in 107 min, about 1,200 tx/s sustained.**
- Storm: about 270–320 tx/s on top. Network accepted peaked around 1,700 tx/s (10:41).
- Mempool is kept below 80k. The runners were set to 600+600/s after 800+800 pushed the mempool to 78.4k.

## 2. Wallet sweep (10:36–10:39) — every local wallet except Grok Build
- `scripts/r6-wallet-scan.mjs` found 870 keys, 851 of them funded, holding 138,464 TKAS.
- `scripts/r6-sweeper.mjs` swept **81,923 TKAS from 451 wallets (464 txs)** to the faucet:

| group | TKAS |
|---|---:|
| storm keys 400–799 | 55,379 |
| lanes L1–L8 | 20,570 |
| W1–W6 | 5,357 |
| round-3 issuers | 533 |
| round-4 ttt-g | 83 |

- Storm keys 0–399, the former live storm pool, are being swept now (12:23–) because the storm was lowered. The total follows in the final report.
- The Grok Build wallet is excluded in code and never spent.

## 3. The 12:20 direction change
- **Storm lowered to about 100 tx/s.**
  - The storm supervisor and H lane were stopped.
  - 8 storm workers (P0–P7) run without a supervisor (`scripts/r6-storm-lite.sh`).
  - Why: the storm's fees mostly flowed back to our own mining address. Own vprog / ttt / KNS activity is the useful load.
- **Miners reduced to 2** (gb001 plus the KNS-bot miner).
  - Stopped: the storm keepalive miner, gb002 and the pool miner.
  - Why: less mining income flowing back to the faucet, so the pool actually drains, while the local nodes stay healthy.
  - The restore commands are logged.
- **Runners relaunched at 12:31** on the same tag, resuming the persisted chains.
  - Faucet UTXOs are split between senders by txid hash, so they never double-spend: ttt takes `h%4==0`, vprog `h%2==1`, KNS `h%4==2`.
  - 800+800/s pushed the mempool to 72.9k with p50 18 s, so the rates are now **650+650/s**.
- **The faucet now drains.** Mature faucet funds went 133.7k (12:19) → 86.0k TKAS (12:28): chain funding plus KNS.
  - Before the change, the faucet grew by about +2.8k to +4.3k per 10 min.

## 4. Fee rule (user 12:22: "double the standard so we have priority")
**feerate = max(2 × node `getFeeEstimate` normalBuckets[0], 2 × network minimum = 200) sompi/gram, recomputed every 30 s.**
- It applies to all our txs: vprog, ttt, KNS commit/reveal, storm (via the live FEE_MULT = feerate/100) and funding.
- It replaced the fixed 5,000 sompi/g game feerate and the storm's fixed multiplier.
- Daemon: `scripts/r6-feerate.py`. Every sample is logged in `logs/round6/feerate.jsonl`.
- Observed so far:

| time | normal estimate | used |
|---|---:|---:|
| 12:22 | 864.6 | **1,729** |
| 12:26–12:28 | 192–194 | **383–387** |

- The normal estimate fell once the storm was cut, so the per-tx cost is now far below the old fixed 5,000.

## 5. KNS (TN10) bulk creates — started 12:31
- Scripted commit/reveal against the public KNS TN10 indexer, one pass per worker. Each chains the next create on the reveal change. It uses our own node, without utxoindex.
- **First run, 12:31–12:33** (40 workers, labels `stp-r6-…`): 1,299 attempts, **753 created (about 6 creates/s)**.
  - Failures: 63 commit, 6 reveal, 2 funding, 2 check.
  - Latency submit→reveal: p50 75 ms / p95 157 ms.
- **Spec from 12:27** (being switched in now):
  - Fully random names from `[a-z0-9]`, the charset the KNS indexer accepts.
  - Length is uniform 1–8, with a ~10% chance of 15.
  - Each name's owner is a random address from a pool of freshly generated throwaway TN10 wallets (keys kept owner-only on the box, never printed or committed).
  - A taken name is retried with a new random name. Taken, retries and invalid are counted separately.
  - KNS price tiers: 1–2 chars 4,200; 3 chars 2,100; 4 chars 525; 5+ chars 35 TKAS. Short names burn TKAS fastest.
  - The length distribution and success rate go in the final report.

## 6. Stop rule and pruning protection
- **Stop when all funds are gone, backstop 20:00 CEST.** "Gone" means the mature faucet plus the storm pool stays below 3k TKAS for 15 min.
  - The stop script then halts every sender and runs a 15-minute recovery measurement (`scripts/r6-recovery.py`).
- **Pruning pause at 18:30.** TN10 prunes about every 12 h. This morning's pruning (07:1x) needed about 14 G of transient disk in 5 minutes and filled the disk.
  - At 18:30, all senders pause. Regenerable junk is cleaned to reach ≥20 G free.
  - If there is still <20 G at 18:45, the node is stopped cleanly and restarted once space is OK.
  - Senders resume when the n0 log shows the pruning has completed ("SMT pruning complete") and disk usage is stable. They then run until 20:00 or until the funds are gone.
- During the run, senders pause below 13 G free disk; the hard floor is 8 G. The mempool brake is 80k.

## Safety
- Keys are never printed or committed. The Grok Build wallet is never spent. Processes are killed only by exact pid. `tools/secret-scan.sh` runs before every push.
