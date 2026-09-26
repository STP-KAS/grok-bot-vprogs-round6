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
