#!/bin/bash
# round5 clean stop of ALL our senders (TN10). Exact-pid kills only (no pkill -f). Leaves n0, miners, KNS, watchdog, monitor alone.
# usage: scripts/r5-stop.sh [reason]
D=/workspace/tn10-break-test-2026-09-25; R="${1:-manual}"
rm -f /tmp/r6-kns.PAUSE; touch /tmp/r5-games.HALT /tmp/tps-storm.HALT        # runners + storm workers/supervisor exit on these (workers save state)
sleep 8
PIDS=""
for p in $(ls /proc | grep -E '^[0-9]+$'); do
  c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null) || continue
  case "$c" in
    "node scripts/r5-ttt.mjs "*|"node scripts/r6-kns.mjs "*|"node scripts/r6-kns2.mjs "*|"node scripts/r5-vprog.mjs "*|"python3 scripts/tps-supervisor.py "*|"python3 scripts/r5-pacer.py"*|"node $D/scripts/rwstorm.mjs "*) PIDS="$PIDS $p";;
  esac
done
[ -n "$PIDS" ] && kill -TERM $PIDS 2>/dev/null
sleep 3
echo 0 > /dev/null; python3 - <<'PY'
a=open('/tmp/tps-storm.limits').read().split(); a[3]='0'; open('/tmp/tps-storm.limits','w').write(' '.join(a))
PY
echo "$(date +%FT%T%z) R5-STOP ($R): senders stopped, pids TERM'd:${PIDS:- none}; limits RATE_MAX=0. Feeder left running for final balance log (kill \$(cat /tmp/r5-feeder.pid) to stop)." >> $D/logs/storm/ramp.log
echo "stopped:$PIDS"
