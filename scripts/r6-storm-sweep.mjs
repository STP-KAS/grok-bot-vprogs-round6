// round6 (lead 12:50): sweep the stopped storm workers' pool (state-rw-P0..P7.json, locally tracked UTXOs incl. unconfirmed)
// -> faucet (desk key 0; KNS consumes 3/4 slice + runner-slice surplus). Multi-wallet batches of BATCH inputs, feerate = /tmp/r6-feerate
// (2x normal estimate rule). No keys involved (tag wallets are testnet anyone-can-spend P2SH, documented in round 4/5). Excludes the Grok Build wallet by address.
import { readFileSync, appendFileSync, existsSync } from "node:fs";
import { kaspa, connect, NET, deskKey, addrOf } from "./lib.mjs";
const DIR = "/workspace/tn10-break-test-2026-09-25"; const LOG = `${DIR}/logs/round6/storm-sweep.jsonl`;
const GB = "kaspatest:qzzkwgjh7mwranw998am5ztvqv25mqfqd7r2lpscd4tst9m2v9rfg553wtgzv";
const FA = addrOf(deskKey(0)); if (FA === GB) throw new Error("refuse");
const BATCH = Number(process.env.BATCH || 80); const SUB = Number(process.env.SUB || 10);
const fr = () => { try { const v = BigInt(readFileSync("/tmp/r6-feerate", "utf8").trim()); if (v >= 200n) return v; } catch {} return 400n; };
const log = (o) => appendFileSync(LOG, JSON.stringify({ t: new Date().toISOString(), ...o }) + "\n");
// storm-lite ran MODE=p2w: pool UTXOs sit in P2SH tag wallets id (redeem = push4(id) OP_DROP OP_TRUE, spent with sigScript "07"+redeem, no key)
const tagRedeem = (id) => "04" + Buffer.from(Uint32Array.of(id).buffer).toString("hex") + "7551";
const tagW = (id) => { const r = tagRedeem(id), spk = kaspa.payToScriptHashScript(r); return { id, sigScript: "07" + r, spk, address: kaspa.addressFromScriptPublicKey(spk, NET).toString() }; };
const rpc = await connect("n0");
const all = [];
for (let p = 0; p < 8; p++) {
  const f = `${DIR}/state-rw-P${p}.json`; if (!existsSync(f)) continue;
  const st = JSON.parse(readFileSync(f, "utf8"));
  for (const [i, us] of Object.entries(st)) { if (!(Number(i) >= 0)) continue; const k = tagW(Number(i)); if (k.address === GB) continue;
    for (const u of us) all.push({ k, txid: u[0], index: u[1], amount: BigInt(u[2]) }); }
}
log({ ev: "start", utxos: all.length, tkas: Number(all.reduce((a, u) => a + u.amount, 0n)) / 1e8 });
const PK = new Map(); const pk = (k) => { if (!PK.has(k.address)) PK.set(k.address, new kaspa.PrivateKey(k.key)); return PK.get(k.address); };
let swept = 0n, txs = 0, fails = 0, failIn = 0;
async function send(batch) {
  const ins = batch.map((u) => ({ address: u.k.address, outpoint: { transactionId: u.txid, index: u.index }, utxoEntry: { amount: u.amount, scriptPublicKey: u.k.spk, blockDaaScore: 0n, isCoinbase: false } }));
  const total = ins.reduce((a, x) => a + x.utxoEntry.amount, 0n);
  const mk = (amt) => { const tx = kaspa.createTransaction(ins, [{ address: FA, amount: amt }], 0n, null, 1); batch.forEach((u, j) => { tx.inputs[j].signatureScript = u.k.sigScript; }); return tx; };
  let tx = mk(total - 1n); const amt = total - BigInt(kaspa.calculateTransactionMass(NET, tx)) * fr(); if (amt < 20000000n) return false;
  tx = mk(amt);
  try { await rpc.submitTransaction({ transaction: tx, allowOrphan: true }); swept += amt; txs++; return true; }
  catch (e) { return String(e.message || e).slice(0, 400); }
}
for (let i = 0; i < all.length; i += BATCH) {
  const b = all.slice(i, i + BATCH); const r = await send(b);
  if (r !== true && r !== false) { // bad input somewhere -> split in singles-groups of 10 to salvage
    for (let j = 0; j < b.length; j += SUB) { const r2 = await send(b.slice(j, j + SUB)); if (r2 !== true) { fails++; failIn += Math.min(SUB, b.length - j); if (fails < 20) log({ ev: "fail", e: String(r2) }); } }
  }
  if (txs % 100 === 0) log({ ev: "prog", i, txs, swept_tkas: Number(swept) / 1e8 });
}
log({ ev: "done", txs, swept_tkas: +(Number(swept) / 1e8).toFixed(2), fail_groups: fails, fail_inputs: failIn });
appendFileSync(`${DIR}/logs/storm/ramp.log`, `${new Date().toISOString().slice(0, 19)}Z R6-STORM-SWEEP done: ${txs} txs, ${(Number(swept) / 1e8).toFixed(0)} TKAS -> faucet (failed input groups ${fails}/${failIn} inputs)\n`);
process.exit(0);
