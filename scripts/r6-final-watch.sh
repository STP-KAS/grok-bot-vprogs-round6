#!/bin/bash
# round6 final-stop rule (replaces r5-empty-watch.sh):
#  INCOME-ONLY mode starts when the mature faucet stays < 3000 TKAS (feeder writes /tmp/r5-faucet-empty after 15 min < 3k;
#  here we detect it directly from logs/round5/faucet.jsonl: mature_tkas < 3000 on 3 consecutive samples). Runners keep going on
#  incoming mining rewards (feeder keeps handing over newly matured coinbase UTXOs).
#  FINAL STOP = income-only mode has lasted 30 min OR 12:30 CEST, whichever first -> r5-stop.sh + r6-recovery.py (15 min).
D=/workspace/tn10-break-test-2026-09-25; F=$D/logs/round5/faucet.jsonl; R=$D/logs/storm/ramp.log
DEADLINE=$(date -d '2026-09-26 12:30:00' +%s); inc=""; low=0
while true; do
  now=$(date +%s)
  m=$(tail -1 $F | python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("mature_tkas", 1e9))' 2>/dev/null || echo 1e9)
  if python3 -c "import sys; sys.exit(0 if float('$m') < 3000 else 1)"; then low=$((low+1)); else low=0; fi
  if [ -z "$inc" ] && [ $low -ge 3 ]; then inc=$now; echo "$(date +%FT%T%z) R6 INCOME-ONLY mode start (mature faucet $m TKAS < 3000); final stop at min(+30 min, 12:30)" >> $R; fi
  if [ $now -ge $DEADLINE ]; then why="12:30 deadline"; break; fi
  if [ -n "$inc" ] && [ $((now-inc)) -ge 1800 ]; then why="income-only 30 min"; break; fi
  sleep 30
done
echo "$(date +%FT%T%z) R6 FINAL STOP trigger: $why" >> $R
bash $D/scripts/r5-stop.sh "$why"
cd $D && python3 scripts/r6-recovery.py
