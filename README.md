# grok-bot-vprogs round 6 — INTERIM (live, full gusto from 10:35 CEST, 26 Sep 2026)

Private report by Grok (acting for stp). Kaspa TN10 only.
Previous: [round 5 final (09:22–10:35)](https://github.com/STP-KAS/grok-bot-vprogs-round5) · [round 4 final](https://github.com/STP-KAS/grok-bot-vprogs-round4).

**Brief (user 10:33–10:34):** "fix the own vprog / tic-tac-toe, skip the originals, scale, TPS again", "use coins from all the wallets you have", "full gusto", "report in new github".

- Only our own index-free runners (`r5-ttt.mjs`, `r5-vprog.mjs`) plus the storm. The upstream vprogs/ttloop originals stay off.
- All local TN10 wallets were swept into the faucet, **excluding the Grok Build wallet**.
- Only safety guards remain: mempool brake 80k (runners pause at 79k), disk 12 G + 3 G/2 min drop guard, n0 crash latch, RAM floor 1 G.
- **Stop rule:** when the mature faucet stays below 3k TKAS, the runners continue in *income-only* mode on fresh mining rewards. The final stop comes at min(income-only + 30 min, 12:30 CEST), via `scripts/r6-final-watch.sh`. It then runs a 15-minute recovery measurement (`scripts/r6-recovery.py`).

Live notes: `findings/round6-notes.md`. The final report will replace this README after the stop.
