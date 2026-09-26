# Round 6 notes (live)

## Wallet sweep (10:36–10:39)
`scripts/r6-wallet-scan.mjs` scanned 870 local keys and found 851 funded, holding 138,464 TKAS. The Grok Build wallet is excluded in code.
`scripts/r6-sweeper.mjs` swept the idle set to the faucet: **81,923 TKAS from 451 wallets in 464 txs**. Per-wallet amounts (shortened addresses, no keys) are in `logs/sweep.jsonl`.

| group | wallets | TKAS |
|---|---:|---:|
| storm keys 400–799 | 400 | 55,379 |
| lanes L1–L8 | 8 | 20,570 |
| W1–W6 | 6 | 5,357 |
| round-3 issuers | 32 | 533 |
| round-4 ttt-g | 4 | 83 |

Storm keys 0–399 (56.4k TKAS) are the live H-lane working pool, so the storm keeps spending them in place.

## Runner fixes (10:38)
- Orphan at funding (parent not yet visible) → retry up to 3× after 400 ms.
- Stale persisted chain ends after a restart are classified as `resume_stale`, not rejects.
- Result since 10:38: **0 rejects**.
- Move feerate 60,000 → **5,000 sompi/g** (5x the storm), funding 2,000 → about 12x more moves per TKAS.

## Full gusto snapshot 10:41
| | ttt-E | vprog-E |
|---|---:|---:|
| lanes (concurrent games/programs) | 600 | 600 |
| submitted / accepted per s | 611 / 633 | 609 / 738 |
| latency p50 / p95 | 3.5 / 15.6 s | 5.6 / 91 s (backlog after the 800/s burst) |
| rejects | 0 | 0 |
| illegal attempts / executed | 22,883 / 0 | 24,052 / 0 |
| fee burn | ~3.2k TKAS/min | ~3.3k TKAS/min |

Storm 10x ~270 tx/s. **Network accepted ~1,700 tx/s**, which is about 3.7x the round-5 average. Mempool max 78.4k at 800+800/s → runner rates set to 600+600.

## Steady state 10:43
- ttt: 600 lanes, **600 moves/s** submitted, 595/s accepted, p50 1.7 s / p95 13.3 s. 23,022 games / 22,292 finished since 10:38.
- vprog: 600 lanes, **600 steps/s**, 601/s accepted, p50 2.2 s / p95 86 s. The p95 tail is chains that lost priority during the 800/s burst and are draining. 20,513 programs / 19,862 halted.
- 0 rejects. Illegal attempts 80,723, **0 executed**.
- Runner burn ~6.4k TKAS/min at 5,000 sompi/g. Storm 10x ~320 tx/s (165 TKAS/min; its pool is 81.6k, and the external mempool backlog keeps it tapered).
- **Our TPS ≈ 1,500/s; network accepted ≈ 1,620/s.** Mempool max 66k, disk 18.6 G, RAM available 6.3 G, load 11.5 on 8 cores (4 cores are busy with CPU miners).
- Mature faucet 21k TKAS (miners pay in ~1k/min plus ~57% of burned fees).

## Process E totals 10:38 → 12:25
- ttt: 3,842,503 submitted / 3,841,174 accepted, 467,891 games / 456,892 finished, 0 rejects, 843,210 illegal / 0 executed.
- vprog: 3,869,642 / 3,868,332, 364,897 programs / 354,294 halted, 0 rejects, 701,379 illegal / 0 executed.
- Combined: about 1,200 tx/s own. Fee counters: 326k + 344k TKAS.
- Faucet mature grew 107.9k → 133.7k from 11:19 to 12:19 (+2.8k to +4.3k per 10 min). Income from 5 miners plus fee flow-back exceeded the burn.

## 12:19–12:31 direction change (user)
- The storm supervisor and H lane were stopped, because storm fees largely returned to our own mining address.
  - Storm-lite P0–P7 run at 100 tx/s total, with FEE_MULT read live from `/tmp/r6-storm-mult`.
  - Storm keys 0–399 are queued for a sweep to the faucet.
- Miners 5 → 2, keeping gb001 and knsbot. Stopped: storm keepalive, gb002 and the pool miner (restore cmds in `ramp.log`). Why: less income flowing back to the faucet, while the nodes stay healthy.
- Fee rule: feerate = max(2 × getFeeEstimate normal, 200) sompi/g, every 30 s (`scripts/r6-feerate.py`, logged in `logs/round6/feerate.jsonl`).
  - 12:22 normal 864.6 → 1,729 used.
  - 12:26–12:28 normal ~193 → ~385 used, because the estimate dropped once the storm was cut.
- The 12:31 relaunch put ttt/vprog at 800 lanes each. The faucet split by txid hash is now ttt `h%4==0`, vprog `h%2==1`, KNS `h%4==2`, which removes an overlap between ttt and KNS.
  - At 800+800/s the mempool reached 72.9k and p50 was ~18 s, so the rates went to 650+650.
- KNS runner `r6-kns.mjs` A, 40 workers: 753 created of 1,299 attempts in the first ~2 min.
- Mature faucet 133.7k (12:19) → 86.0k (12:28): **now draining.**
- Stop rule: all funds < 3k for 15 min, or 20:00. Pruning pause from 18:30 (see README §6).

## 12:25–12:48 KNS, fee samples, rebalancing
- Fee rule samples (`logs/feerate.jsonl`):
  - 12:23 normal 864.6 → **1,729** sompi/g.
  - From 12:25, normal 188–194 → **377–388** (every 30 s).
  - The old fixed game feerate was 5,000.
- KNS A (12:25–12:29): 771 created at 35 TKAS. Stopped due to a commit-fail loop and the KNS API Cloudflare rate limit (error 1015).
- KNS B (random spec) 12:31–12:48: **401 created, 74,935 TKAS in KNS fees**.
  - By length: 2: 5, 3: 13, 4: 27, 5: 56, 6: 84, 7: 68, 8: 84, 15: 64.
  - All 36 1-char names are taken. 2-char names are mostly taken (48–59 taken hits per batch series).
- Faucet split rebalanced at 12:35: KNS ¾ plus the runner-slice surplus above 2k.
- At 12:36 KNS emptied its slice, so it is now income-limited.
- ~26k TKAS stranded in unpersisted keys of an 18 s KNS instance (see README §5).
- Runner rates 450+450 (mempool 72–74k, p50 20–38 s). The external mempool backlog persists: priority estimate ~790 vs our 387.
- Faucet mature: 133.7k (12:19) → 6.1k (12:36). It has held at 6–9k since, because KNS absorbs the income. Storm pool 12.1k.

## 12:48–12:56 Storm stopped, storm pool swept into KNS funding (lead 12:50: "all TKAS gone")
- Storm workers P0–P7 were stopped with SIGTERM by exact pid, and the storm rate set to 0.
- The storm pool sat in the storm's P2SH tag wallets. These are anyone-can-spend on testnet (`MODE=p2w`), so no keys were involved.
- It was swept to the faucet, which KNS draws from (¾ slice plus the runner-slice surplus above 2k), at the 2x-normal feerate:

  | pass | source | TKAS | txs |
  |---|---|---:|---:|
  | 1 | worker state files | 5,995 | 5,011 |
  | 2 | same, 10-input salvage | 299 | — |
  | 3 | live public-API UTXO list | 4,118 | 2,822 |
  | **total** | | **10,412** | |

  Pass-3 failures were "already spent in the mempool", i.e. inputs my earlier passes had already taken.
- The old storm state files (which included 2.5k of stale H-lane state) were archived, so the "storm pool" figure no longer inflates the watcher's funds total.
- Mempool 73k → 1.9k after the storm stop.
- **KNS after:** ~0.5 creates/s, ~20.8k TKAS of KNS fees per 10 min (the last 5 min: 159 created, 7.5k TKAS).
  - B total so far: 616 created, 85,890 TKAS in KNS fees. Commit failures 7, reveal failures 0.
  - The `unaffordable` count (1,838) rises because 2–4-char tiers can't be funded from income, so creates skew to 5+ chars.
- Funds left at 12:56: mature faucet ~3.3k plus KNS workers ~0.3k. Income from the 2 miners is absorbed by KNS above the runners' 2k reserve.

## FINAL addendum (13:16 CEST stop — report finalized)

**Stop:** 13:16:14 CEST — `funds 2697 < 3k TKAS for 15 min`. Disk pause since 13:06:29 (`disk<13G`). Pruning window (18:30) never reached. Recovery: mempool already 0; drain ≈ 0 s (`logs/recovery.jsonl`, 13 samples / 60 s).

**Own runners (tag E, R6 segments summed):**
| | submitted | accepted | games/programs | finished/halted | illegal exec | fee TKAS |
|---|---:|---:|---:|---:|---:|---:|
| ttt | 5,037,212 | 5,014,037 | 613,669 | 600,055 | 0 | 333,598 |
| vprog | 5,080,337 | 5,043,987 | 478,013 | 465,967 | 0 | 351,586 |
| **total** | **10,117,549** | **10,058,024** | | | **0** | **~685k** |

Full-gusto (10:38–12:25) alone: 7.71 M txs, ~1,191 tx/s, p50 ~1.0 s. Network peak ~1,700 tx/s (10:41). Mempool max 78,319.

**KNS final:** A 771 created (~27.0k TKAS at 35/name) + B 1,111 created (107.1k TKAS prices) = **1,883 creates**. B commit_fail events 11, reveal_fail 0. ~26k TKAS stranded in the 18 s unpersisted-worker restart (unchanged).

**Sweeps:** keyed wallets 84,418 TKAS + storm-pool 10,412 TKAS → faucet. Grok Build untouched.

**Faucet:** grew to mature ~138k by 12:20 under 5 miners; after 2-miner cut + KNS priority, drained to the &lt;3k/15 min stop. End-state mature faucet ~3.5–5k (mining income still arriving; senders halted).

**Left running:** n0 2341090, miners gb001 + knsbot, feeder, feerate daemon. All senders dead; HALT files present. Disk ~13 G free.
