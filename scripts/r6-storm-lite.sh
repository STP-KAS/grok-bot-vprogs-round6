#!/bin/bash
# round6 low storm: P0-P7 only (H lane retired, its keys swept), total /tmp/tps-storm.rate tx/s, dynamic fee via /tmp/r6-storm-mult.
# No supervisor (it would respawn H). Workers exit on /tmp/tps-storm.HALT. Prints pids.
D=/workspace/tn10-break-test-2026-09-25; cd $D
for k in 0 1 2 3 4 5 6 7; do a=$((k*500))
  MODE=p2w AFFINITY=0 NODES=n0 COOL=4000 FEE_MULT=$(cat /tmp/r6-storm-mult) LOW=0 MIN_SOMPI=2000000 SECS=30000 CONCFILE=/tmp/tps-storm.conc RATEFILE=/tmp/tps-storm.rate \
  setsid nohup node $D/scripts/rwstorm.mjs P$k $a $((a+500)) $((k*25000)) $(((k+1)*25000)) $k 8 >> $D/logs/tps12h/worker-P$k.jsonl 2>&1 < /dev/null &
  echo -n "$! "
done; echo
