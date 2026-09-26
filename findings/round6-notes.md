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
