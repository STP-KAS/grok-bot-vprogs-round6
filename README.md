# grok-bot-vprogs round 6 — INTERIM report (live since 10:35 CEST, 26 Sep 2026; updated 12:50 CEST)

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

- Storm keys 0–399 were swept after the storm cut: **2,495 TKAS from 125 wallets (148 txs)**, because the storm had already spent most of that pool. **Swept total: 84,418 TKAS.**
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
- **Runners relaunched at 12:25 and 12:35** on the same tag, resuming the persisted chains.
  - Faucet UTXOs are split between senders by txid hash, so they never double-spend. Since 12:35, KNS takes `h%4!=0` (¾, because KNS is the biggest burner per byte of disk) plus the surplus of the runner slice above a 2k reserve; ttt takes `h%8==0` and vprog `h%8==4`.
  - Rates stepped 800 → 650 → 550 → **450+450/s** because the mempool sat at 72–74k and p50 latency rose to 20–38 s.
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
| 12:25–12:48 | 188–194 | **377–388** |

- The normal estimate fell once the storm was cut, so the per-tx cost is now far below the old fixed 5,000.

## 5. KNS (TN10) bulk creates — started 12:25
- Scripted commit/reveal against the public KNS TN10 indexer, one pass per worker. Each chains the next create on the reveal change. It uses our own node, without utxoindex.
- **First run (A), 12:25–12:29** (40 workers, labels `stp-r6-…`): 1,299 attempts, **753 created (about 6 creates/s)**.
  - Failures: 63 commit, 6 reveal, 2 funding, 2 check.
  - Latency submit→reveal: p50 75 ms / p95 157 ms.
  - A was stopped because failed commits looped on an already-spent worker UTXO, and 40 unthrottled workers triggered the KNS API's Cloudflare rate limit (error 1015). A total: **771 created**.
- **Random-name runner (B, `scripts/r6-kns2.mjs`) from 12:31**, per the 12:27 spec:
  - Fully random names from `[a-z0-9]`, the charset the KNS indexer accepts.
  - Length is uniform 1–8, with a ~10% chance of 15.
  - Each name's owner is a random address from a pool of freshly generated throwaway TN10 wallets (keys kept owner-only on the box, never printed or committed).
  - A taken name is retried with a new random name. Taken, retries and invalid are counted separately.
  - KNS price tiers: 1–2 chars 4,200; 3 chars 2,100; 4 chars 525; 5+ chars 35 TKAS. Short names burn TKAS fastest.
  - The owner key is the only signer of the reveal. Each name's check is batched (50 names per call) and throttled.
  - If the faucet can't fund the drawn length, the worker redraws among lengths it can afford; this is counted as `unaffordable`.
- **B so far (12:31–12:48): 401 created, 74,935 TKAS in KNS fees.**

  | length | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 15 |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|
  | created | 5 | 13 | 27 | 56 | 84 | 68 | 84 | 64 |

  - No 1-char names: all 36 are taken. 2-char names are mostly taken.
  - Short names are under-represented because the faucet can't fund 2,100–4,200 TKAS names from income.
  - Commit/reveal failures ≈0 since v2.
- **KNS indexer lag:** the indexer lags the DAG by about 235k DAA (`NG is lagging behind BlockDag`), so ownership can't be verified yet. The runner samples `GET /{domain}/owner`, and the final report re-checks.
- **Loss note:** a KNS worker instance that ran for only 18 s (12:35:23–12:35:41) was restarted to add worker-key persistence. It held an estimated **~26k TKAS** of top-ups in in-memory worker keys, now unrecoverable, so those coins are effectively burned.
  - Estimate: faucet drop 77.8k minus 51.3k KNS fees in 12:35:20–12:36:24.
  - Worker keys are persisted (owner-only) since 12:36, and a restart now adopts their coins.

## 6. Stop rule and pruning protection
- **Stop when all funds are gone, backstop 20:00 CEST.** "Gone" means the mature faucet plus the storm pool stays below 3k TKAS for 15 min.
  - The stop script then halts every sender and runs a 15-minute recovery measurement (`scripts/r6-recovery.py`).
- **Pruning pause at 18:30.** TN10 prunes about every 12 h. This morning's pruning (07:1x) needed about 14 G of transient disk in 5 minutes and filled the disk.
  - At 18:30, all senders pause. Regenerable junk is cleaned to reach ≥20 G free.
  - If there is still <20 G at 18:45, the node is stopped cleanly and restarted once space is OK.
  - Senders resume when the n0 log shows the pruning has completed ("SMT pruning complete") and disk usage is stable. They then run until 20:00 or until the funds are gone.
- During the run, ttt/vprog/storm pause below 13 G free disk (resume above 14 G); the hard floor is 8 G, which triggers the final stop.
  - KNS is exempt from the 13 G pause because it writes almost nothing to disk per TKAS burned. It pauses only for pruning.
- Storm guard: mempool >80k sets the storm to 0; it resumes below 40k.
- Watcher: `scripts/r6-final-watch.py` (log `logs/round6/final-watch.jsonl`).
- **Outlook:** disk was 13.7 G at 12:46 and falling about 1 G per 15 min, so ttt/vprog/storm will hit the 13 G pause around 13:00 and stay paused until disk frees up (the pruning around 19:00). KNS keeps draining.
  - Mining income (2 miners) keeps arriving and KNS burns it continuously. The storm pool (12k) drains slowly.
  - The "all funds < 3k" stop may therefore not trigger before the 20:00 backstop.

## Safety
- Keys are never printed or committed. The Grok Build wallet is never spent. Processes are killed only by exact pid. `tools/secret-scan.sh` runs before every push.
