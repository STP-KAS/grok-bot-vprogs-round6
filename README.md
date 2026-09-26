# grok-bot-vprogs round 6 — FINAL (10:35–13:16 CEST, 26 Sep 2026)

Private report by Grok, acting for stp. Kaspa **TN10 only**. Times are CEST.
Previous rounds: [round 5 final (09:22–10:35)](https://github.com/STP-KAS/grok-bot-vprogs-round5) · [round 4 final](https://github.com/STP-KAS/grok-bot-vprogs-round4).
Live notes + final addendum: [`findings/round6-notes.md`](findings/round6-notes.md).

## Brief
| time (CEST) | user direction |
|---|---|
| 10:33–10:34 | "fix the own vprog / tic-tac-toe, skip the originals, scale, TPS again", "use coins from all the wallets you have", "full gusto", "report in new github" |
| 12:19–12:22 | lower the storm and spend on our own vprog / ttt / **KNS** instead; reduce the miners to 2; drain every local wallet except Grok Build; stop when all TKAS is gone, backstop 20:00; pause for tonight's pruning; "keep transaction costs double the standard so we have priority" |
| 12:27 | KNS: fully random names, random throwaway owners |
| 12:28 | "report to github, keep going until all tkas is gone" |
| 12:50 | (lead) stop storm entirely; sweep remaining storm-pool TKAS into KNS funding |

**FINAL STOP 13:16:14 CEST** — funds 2,697 TKAS &lt; 3k for 15 min. Disk had paused senders since 13:06:29 (disk &lt; 13 G). Pruning pause at 18:30 was never reached. Recovery: mempool already ~0 at stop; drain to near-zero ≈ **0 s** (13 samples / 60 s in `logs/recovery.jsonl`).

## Headline metrics
| metric | value |
|---|---:|
| round window | **10:35–13:16 CEST** (~159 min) |
| own-runner txs submitted / accepted | **10,117,549 / 10,058,024** (ttt + vprog, tag E, 3 relaunches summed) |
| own-runner avg TPS (full gusto 10:38–12:25) | **~1,191 tx/s** sustained |
| own-runner avg TPS (whole round) | **~1,057 tx/s** |
| network accepted TPS (snapshots) | peak **~1,700/s** (10:41); steady **~1,620/s** (10:43). `nettps.jsonl` stale after 07:46 — these are from runner+storm+monitor snapshots in `ramp.log` |
| storm accepted (supervisor 10:35–12:20) | avg **~110 tx/s**, peak **1,229/s** (10:40); heavily mempool-tapered. Storm cut to ~100/s at 12:21, stopped 12:50 |
| tic-tac-toe games started / finished | **613,669 / 600,055** |
| vprog programs started / halted | **478,013 / 465,967** |
| moves / steps | **5,025,058 / 4,589,227** |
| illegal attempts / executed | **2,026,964 / 0** |
| runner rejects (R6 segments) | **0** |
| latency (full gusto end 12:25) | ttt p50 **1.0 s** / p95 **3.4 s**; vprog p50 **1.0 s** / p95 **3.6 s** |
| latency (late, post-12:35, high external backlog) | ttt p50 ~5–35 s / p95 ~116–124 s; vprog p50 ~2–35 s / p95 ~94–115 s |
| runner fee counter | **~685k TKAS** (ttt 334k + vprog 352k) |
| KNS creates | **A 771 + B 1,111 (+1 smoke) = 1,883** |
| KNS B success (created / created+commit_fail events) | **1,111 / 1,122 ≈ 99.0%** (reveal_fail events 0) |
| KNS fee burn | A ≈ **27.0k** (35 TKAS × 771) + B **107.1k** = **~134k TKAS** |
| storm fee counter delta (supervisor) | **~9.2k TKAS** (10:35–12:20) |
| mempool max (R6) | **78,319** at 10:39:29 |
| wallet sweeps → faucet | idle **84,418 TKAS** (81,923 + 2,495) + storm-pool **10,412 TKAS** |
| faucet net trend | grew under 5 miners (mature ~18k → **138k** by 12:20); after 2-miner cut + KNS, drained to stop threshold (**~2.7k** funds) |
| recovery drain time | **~0 s** (mempool 0 at stop) |
| disk free at stop / now | **~13.0 G** / ~13 G (floor 8 G; pause 13 G) |
| n0 | pid **2341090**, synced, mempool 0, no utxoindex |

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

- **Own runners: 7.71 M txs in 107 min, about 1,191 tx/s sustained.**
- Storm: about 110 tx/s avg accepted on top (peak 1,229); tapered by the external mempool backlog. Network accepted peaked around 1,700 tx/s (10:41); steady ~1,620 at 10:43.
- Mempool kept below 80k. Runners were set to 600+600/s after 800+800 pushed the mempool to 78.4k.

### Post-12:25 relaunches (same tag E; counters reset — summed into headline)
| segment | ttt accepted | vprog accepted | notes |
|---|---:|---:|---|
| 12:25–12:35 | 274,710 | 288,400 | 800 lanes → 650 → 550; feerate 2× normal |
| 12:35–13:16 | 898,153 | 887,255 | 450+450 after 12:46; disk pause 13:06 (rate 0) → final stop 13:16 |

## 2. Wallet sweep (10:36–10:39, then 12:35) — every local wallet except Grok Build
- `scripts/r6-wallet-scan.mjs` found 870 keys, 851 of them funded, holding 138,464 TKAS.
- `scripts/r6-sweeper.mjs` swept **81,923 TKAS from 451 wallets (464 txs)** to the faucet:

| group | TKAS |
|---|---:|
| storm keys 400–799 | 55,379 |
| desks L1–L8 | 20,570 |
| W1–W6 | 5,357 |
| round-3 issuers | 533 |
| round-4 ttt-g | 83 |

- Storm keys 0–399 swept after the storm cut: **2,495 TKAS from 125 wallets (148 txs)**. **Keyed-wallet swept total: 84,418 TKAS.**
- Storm-pool (P2SH anyone-can-spend tag wallets) swept 12:50–12:54 into the faucet for KNS: **10,412 TKAS** (5,995 + 299 + 4,118).
- The Grok Build wallet (`kaspatest:qzzkwg…553wtgzv`) is excluded in code and never spent.
- Per-wallet lines (short prefixes only): `logs/sweep.jsonl`. Totals: `logs/sweep-totals.json`.

## 3. The 12:20 direction change
- **Storm lowered to about 100 tx/s**, then **stopped at 12:50**.
  - Supervisor and H lane stopped at 12:21; P0–P7 ran storm-lite without supervisor until SIGTERM by exact pid at 12:50.
  - Why: storm fees mostly flowed back to our own mining address. Own vprog / ttt / KNS activity is the useful load.
- **Miners reduced to 2** (gb001 + knsbot). Stopped: storm keepalive, gb002, pool miner (restore cmds in `logs/ramp-r6-excerpt.log`).
- **Runners relaunched at 12:25 and 12:35** on tag E, resuming persisted chains.
  - Faucet UTXOs split by txid hash. From 12:35: KNS `h%4!=0` (¾) plus runner-slice surplus above 2k; ttt `h%8==0`; vprog `h%8==4`.
  - Rates 800 → 650 → 550 → **450+450/s** (mempool 72–74k, p50 20–38 s).
- **Faucet drained after the change.** Mature ~137.9k (12:20) → ~6.6k (12:37) → stop funds ~2.7k. Before the change it grew ~+2.8k to +4.3k per 10 min under 5 miners.

## 4. Fee rule (user 12:22: "double the standard so we have priority")
**feerate = max(2 × node `getFeeEstimate` normalBuckets[0], 2 × network minimum = 200) sompi/gram, recomputed every 30 s.**
- Applied to vprog, ttt, KNS commit/reveal, storm (via live `FEE_MULT = feerate/100`) and funding.
- Daemon: `scripts/r6-feerate.py`. Log: `logs/feerate.jsonl`.

| time | normal estimate | used |
|---|---:|---:|
| 12:23 | 864.6 | **1,729** |
| 12:25–12:48 | 188–194 | **377–388** |
| after stop | 100 | **200** (floor) |

- Normal estimate fell once the storm was cut, so per-tx cost dropped far below the old fixed 5,000 sompi/g game feerate.

## 5. KNS (TN10) bulk creates — 12:25–13:16
- Own node, no utxoindex. Commit/reveal against the public KNS TN10 indexer.
- **A (12:25–12:29), 40 workers, labels `stp-r6-…`:** **771 created.** Failures: 486 commit, 6 reveal, 2 funding, 2 check. Stopped for commit-fail loop on spent worker UTXO + Cloudflare 1015. Fee ≈ 35 TKAS × 771 = **~27.0k TKAS**.
- **B (`scripts/r6-kns2.mjs`, 12:33–13:16), random-name spec:**
  - Names from `[a-z0-9]`, length uniform 1–8 with ~10% chance of 15; random throwaway owners (keys owner-only on the box).
  - Price tiers: 1–2 chars 4,200; 3 chars 2,100; 4 chars 525; 5+ chars 35 TKAS.
  - **1,111 created, 107,135 TKAS** in KNS prices (sum of `price` on `created` events across 5 restarts).

  | length | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 15 |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|
  | created | 5 | 13 | 42 | 196 | 235 | 210 | 223 | 187 |

  - No 1-char creates (all 36 taken). Commit_fail events 11, reveal_fail 0. `unaffordable` rose as short tiers could not be funded from income.
- **Indexer lag:** ~235k DAA behind the DAG (`NG is lagging behind BlockDag`); ownership verify deferred (`owner_unk` in reps).
- **Loss note:** KNS instance 12:35:23–12:35:41 (restarted to add worker-key persistence) held an estimated **~26k TKAS** in unpersisted in-memory worker keys — effectively stranded. Worker keys persisted (owner-only) since 12:36.
- Summary JSON (no owner keys/addresses): `logs/kns-summary.json`.

## 6. Stop reason, disk pause, recovery
- **Stop rule:** mature faucet + storm pool &lt; 3k TKAS for 15 min, or 20:00 backstop. Watcher: `scripts/r6-final-watch.py` (`logs/final-watch.jsonl`).
- **13:06:29** — pause all senders (`disk&lt;13G`); saved rates ttt/vprog 450. KNS was exempt from the 13 G pause but was income-limited / winding down with the faucet.
- **13:16:14** — FINAL STOP: `funds 2697 < 3k TKAS for 15 min` → `r5-stop.sh` + `r6-recovery.py`. HALT files `/tmp/r5-games.HALT`, `/tmp/tps-storm.HALT`.
- **Recovery:** mempool already 0 at stop; &lt;500 after 0 s; 13 samples over 60 s (`logs/recovery.jsonl`).
- **Pruning pause at 18:30 never reached** (stopped ~5 h early). Hard floor 8 G never hit. Disk min in R6: **12.85 G** at 13:06:27.
- Left running (not senders): n0 kaspad, miners gb001 + knsbot, desk feeder, feerate daemon.

## 7. Node / disk health
| | |
|---|---|
| n0 pid | 2341090 (unchanged all round) |
| synced | yes |
| utxoindex | off (deleted in 07:10 disk emergency; runners are index-free) |
| mempool at stop | 0 (max 78,319 during R6) |
| disk free | ~18.9 G at 10:35 → ~13.0 G at stop (pause at 13 G) |
| appdir (n0) | grew ~80 → ~84 G during full gusto (monitor) |

## Hard rules
- **TN10 only.**
- Keys / mnemonics never printed or committed (`/home/box/secure` stays local). `tools/secret-scan.sh` before every push.
- Grok Build wallet never spent.
- Kill senders by exact pid only — never `pkill -f`.

## Log index (excerpts in this repo)
| path | content |
|---|---|
| `logs/runners-summary.json` | tag-E segment totals (ttt + vprog) |
| `logs/kns-summary.json` | KNS A/B aggregates (no keys) |
| `logs/sweep.jsonl` / `sweep-totals.json` | wallet + storm-pool sweep totals |
| `logs/feerate.jsonl` | 2×-normal fee daemon samples |
| `logs/final-watch.jsonl` | stop watcher |
| `logs/recovery.jsonl` | post-stop mempool samples |
| `logs/faucet-samples.json` | faucet mature/pool at key times |
| `logs/monitor-peaks.json` | mempool max / disk min / last n0 |
| `logs/ramp-r6-excerpt.log` | R6 lines from `ramp.log` |
| `scripts/` | runners, KNS, sweep, watcher, stop, secret-scan |
