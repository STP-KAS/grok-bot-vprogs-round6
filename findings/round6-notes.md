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
