#!/bin/bash
# Pre-push secret scan. Fails (exit 1) on: xprv/tprv keys, 'private' words in data files, 64-hex strings next to key-ish
# names, 12/24-word lowercase mnemonic-like runs, any content from /home/box/secure. Run from the repo root.
set -u; bad=0
files=$(git ls-files -co --exclude-standard)
[ -z "$files" ] && exit 0
if echo "$files" | xargs rg -n -i '\b[xt]prv[0-9A-Za-z]{20,}' ; then echo "FAIL: extended private key"; bad=1; fi
if echo "$files" | xargs rg -n -i '"(priv(ate)?_?key|secret|mnemonic|seed|phrase)"\s*:\s*"' ; then echo "FAIL: key field with value"; bad=1; fi
if echo "$files" | xargs rg -n -P '(?<![a-z])([a-z]{3,8} ){11}[a-z]{3,8}(?![a-z])' | rg -v -i 'the|and|with|that|for|this|from|when|was|are|not' ; then echo "FAIL: mnemonic-like 12+ word run"; bad=1; fi
# exact content from the secure dir (values only, never printed)
if [ -d /home/box/secure ]; then
  python3 - "$files" <<'PY' || bad=1
import sys, os, re, json
files = sys.argv[1].split("\n"); needles = set()
for f in os.listdir("/home/box/secure"):
    try: t = open(os.path.join("/home/box/secure", f), errors="ignore").read()
    except Exception: continue
    for m in re.findall(r"[0-9a-fA-F]{64}|[a-z]+(?: [a-z]+){11,23}|[xt]prv\w+", t): needles.add(m)
hit = 0
for p in files:
    try: c = open(p, errors="ignore").read()
    except Exception: continue
    for n in needles:
        if n in c: print(f"FAIL: secure-dir secret material found in {p} (value not shown)"); hit = 1; break
sys.exit(hit)
PY
fi
echo "$files" | xargs rg -l -i 'private' | sed 's/^/note: word "private" appears in: /'
[ $bad = 0 ] && echo "secret-scan: OK" || { echo "secret-scan: FAILED"; exit 1; }
