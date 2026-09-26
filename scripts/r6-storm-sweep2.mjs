// round6 (lead 12:50) pass 3: sweep storm tag wallets (P2SH anyone-can-spend ids 0..3999) from the LIVE public-API UTXO list -> faucet.
// state files were partly stale. feerate = /tmp/r6-feerate (2x normal). No keys involved. Excludes Grok Build by address.
import { readFileSync, appendFileSync } from "node:fs";
import { kaspa, connect, NET, deskKey, addrOf } from "./lib.mjs";
const DIR = "/workspace/tn10-break-test-2026-09-25"; const LOG = `${DIR}/logs/round6/storm-sweep2.jsonl`;
const GB = "kaspatest:qzzkwgjh7mwranw998am5ztvqv25mqfqd7r2lpscd4tst9m2v9rfg553wtgzv"; const FA = addrOf(deskKey(0)); if (FA === GB) throw new Error("refuse");
const fr = () => { try { const v = BigInt(readFileSync("/tmp/r6-feerate", "utf8").trim()); if (v >= 200n) return v; } catch {} return 400n; };
const log = (o) => appendFileSync(LOG, JSON.stringify({ t: new Date().toISOString(), ...o }) + "\n");
const tagRedeem = (id) => "04" + Buffer.from(Uint32Array.of(id).buffer).toString("hex") + "7551";
const W = Array.from({ length: 4000 }, (_, id) => { const r = tagRedeem(id), spk = kaspa.payToScriptHashScript(r); return { sigScript: "07" + r, spk, address: kaspa.addressFromScriptPublicKey(spk, NET).toString() }; });
const byA = new Map(W.map((w) => [w.address, w]));
const rpc = await connect("n0");
let swept = 0n, txs = 0, fails = 0; const errs = {};
async function send(b) {
  const ins = b.map((u) => ({ address: u.w.address, outpoint: u.op, utxoEntry: { amount: u.amount, scriptPublicKey: u.w.spk, blockDaaScore: u.daa, isCoinbase: false } }));
  const total = ins.reduce((a, x) => a + x.utxoEntry.amount, 0n);
  const mk = (amt) => { const tx = kaspa.createTransaction(ins, [{ address: FA, amount: amt }], 0n, null, 1); b.forEach((u, j) => { tx.inputs[j].signatureScript = u.w.sigScript; }); return tx; };
  let tx = mk(total - 1n); const amt = total - BigInt(kaspa.calculateTransactionMass(NET, tx)) * fr(); if (amt < 20000000n) return "small";
  tx = mk(amt);
  try { await rpc.submitTransaction({ transaction: tx, allowOrphan: false }); swept += amt; txs++; return true; }
  catch (e) { const m = String(e.message || e); const k = m.replace(/[0-9a-f]{64}/g, "#").slice(0, 140); errs[k] = (errs[k] || 0) + 1; return k; }
}
for (let i = 0; i < W.length; i += 100) {
  let us = [];
  try { const r = await fetch("https://api-tn10.kaspa.org/addresses/utxos", { method: "POST", headers: { "content-type": "application/json", "User-Agent": "grok-r6" }, body: JSON.stringify({ addresses: W.slice(i, i + 100).map((w) => w.address) }) }); us = await r.json(); } catch { continue; }
  const items = us.map((u) => ({ w: byA.get(u.address), op: { transactionId: u.outpoint.transactionId, index: u.outpoint.index }, amount: BigInt(u.utxoEntry.amount), daa: BigInt(u.utxoEntry.blockDaaScore) })).filter((x) => x.w);
  for (let j = 0; j < items.length; j += 40) { const b = items.slice(j, j + 40); const r = await send(b);
    if (r !== true) for (let k = 0; k < b.length; k += 8) { const r2 = await send(b.slice(k, k + 8)); if (r2 !== true) fails++; } }
  log({ ev: "prog", addr_i: i, txs, swept_tkas: +(Number(swept) / 1e8).toFixed(2), fails });
}
log({ ev: "done", txs, swept_tkas: +(Number(swept) / 1e8).toFixed(2), fails, errs });
appendFileSync(`${DIR}/logs/storm/ramp.log`, `${new Date().toISOString().slice(0, 19)}Z R6-STORM-SWEEP2 (live API list) done: ${txs} txs, ${(Number(swept) / 1e8).toFixed(0)} TKAS -> faucet, failed 8-groups ${fails}\n`);
process.exit(0);
