// round6: enumerate every local TN10 key we control (never prints keys), query live balances via public API POST /addresses/utxos.
// EXCLUDES the Grok Build wallet. Writes /home/box/secure/r6-sweep-set.json (mode 600: key+address per wallet, for the sweeper)
// and prints per-wallet shortened address + balance only.
import { readFileSync, writeFileSync, chmodSync } from "node:fs";
import { kaspa, NET, deskKey, addrOf } from "./lib.mjs";
const GROK = "kaspatest:qzzkwgjh7mwranw998am5ztvqv25mqfqd7r2lpscd4tst9m2v9rfg553wtgzv";
const S = "/home/box/secure"; const W = [];
const add = (src, hex, addr) => { try { const k = new kaspa.PrivateKey(hex); const a = addrOf(k); if (addr && addr !== a) return; if (a === GROK) return; W.push({ src, k: hex, a }); } catch {} };
for (const x of JSON.parse(readFileSync(`${S}/tn10-storm-keys.json`, "utf8"))) add(`storm${x.i}`, x.key, x.address);
for (const [n, x] of Object.entries(JSON.parse(readFileSync(`${S}/tn10-break-wallets.json`, "utf8")))) add(n, x.key, x.address);
for (const f of ["round3-issuers", "round3-ttt-workers-b", "round3-ttt-workers", "round4-ttt-fresh", "round4-ttt-g"])
  JSON.parse(readFileSync(`${S}/${f}.json`, "utf8")).keys.forEach((h, i) => add(`${f}#${i}`, typeof h === "string" ? h : h.key));
for (let i = 1; i <= 20; i++) { const k = deskKey(i); W.push({ src: `desk${i}`, k: k.toString(), a: addrOf(k) }); }
// dedupe
const seen = new Set(); const U = W.filter((w) => !seen.has(w.a) && seen.add(w.a));
const bal = {}; const utx = {};
for (let i = 0; i < U.length; i += 200) {
  const r = await fetch("https://api-tn10.kaspa.org/addresses/utxos", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ addresses: U.slice(i, i + 200).map((w) => w.a) }) });
  for (const u of await r.json()) { bal[u.address] = (bal[u.address] || 0) + Number(u.utxoEntry.amount); (utx[u.address] ||= []).push(u); }
}
const out = U.filter((w) => bal[w.a] > 0).map((w) => ({ ...w, sompi: bal[w.a], n: utx[w.a].length }));
writeFileSync(`${S}/r6-sweep-set.json`, JSON.stringify(out), { mode: 0o600 }); chmodSync(`${S}/r6-sweep-set.json`, 0o600);
const grp = {}; for (const w of out) { const g = w.src.replace(/\d+$/, "").replace(/#$/, ""); grp[g] ||= { wallets: 0, utxos: 0, tkas: 0 }; grp[g].wallets++; grp[g].utxos += w.n; grp[g].tkas += w.sompi / 1e8; }
console.log(JSON.stringify({ scanned: U.length, funded: out.length, total_tkas: out.reduce((a, w) => a + w.sompi, 0) / 1e8, groups: grp }));
for (const w of out.sort((a, b) => b.sompi - a.sompi).slice(0, 15)) console.log(w.src, w.a.slice(0, 16) + "…" + w.a.slice(-6), (w.sompi / 1e8).toFixed(2), w.n);
process.exit(0);
