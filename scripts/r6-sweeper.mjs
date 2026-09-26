// round6: sweep idle local TN10 wallets -> faucet (desk key 0), so the runners/feeder consume them. Never prints keys.
// EXCLUDES the Grok Build wallet (already absent from the set) and storm wallets 0-399 (the live H-lane pool).
// Reads /home/box/secure/r6-sweep-set.json [{src,k,a,sompi,n}]. Batches up to BATCH inputs/tx, one output to faucet.
import { readFileSync, appendFileSync } from "node:fs";
import { kaspa, connect, NET, deskKey, addrOf } from "./lib.mjs";
const DIR = "/workspace/tn10-break-test-2026-09-25"; const RAMP = `${DIR}/logs/storm/ramp.log`; const LOG = `${DIR}/logs/round6/sweep.jsonl`;
const FA = addrOf(deskKey(0)); const FSPK = kaspa.payToAddressScript(FA);
const BATCH = Number(process.env.BATCH || 60); const FR = BigInt(process.env.SWEEP_FEERATE || 2000);
const set = JSON.parse(readFileSync("/home/box/secure/r6-sweep-set.json", "utf8"))
  .filter((w) => !(w.src.startsWith("storm") && Number(w.src.slice(5)) < 400)); // keep H-lane pool (0-399) alone
const rpc = await connect("n0");
const ramp = (s) => appendFileSync(RAMP, new Date().toISOString().replace("T", "T").slice(0, 19) + "+0200 R6-SWEEP " + s + "\n");
const log = (o) => appendFileSync(LOG, JSON.stringify({ t: new Date().toISOString(), ...o }) + "\n");
async function utxos(addr) { try { const r = await fetch("https://api-tn10.kaspa.org/addresses/utxos", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ addresses: [addr] }) }); return await r.json(); } catch { return []; } }
let totalSwept = 0n, txs = 0, walletsDone = 0; const perGroup = {};
for (const w of set) {
  const key = new kaspa.PrivateKey(w.k); const spk = kaspa.payToAddressScript(w.a);
  let us = await utxos(w.a); if (!us.length) continue;
  us = us.filter((u) => !u.utxoEntry.isCoinbase || (Number(u.utxoEntry.blockDaaScore) + 1200 < 9e18)); // normal or mature
  let swept = 0n;
  for (let i = 0; i < us.length; i += BATCH) {
    const batch = us.slice(i, i + BATCH);
    const ins = batch.map((u) => ({ address: w.a, outpoint: { transactionId: u.outpoint.transactionId, index: u.outpoint.index }, utxoEntry: { amount: BigInt(u.utxoEntry.amount), scriptPublicKey: spk, blockDaaScore: BigInt(u.utxoEntry.blockDaaScore), isCoinbase: u.utxoEntry.isCoinbase } }));
    const total = ins.reduce((a, x) => a + x.utxoEntry.amount, 0n);
    let tx = kaspa.createTransaction(ins, [{ address: FA, amount: total - 1n }], 0n, null, 1); kaspa.signTransaction(tx, [key], false);
    const fee = BigInt(kaspa.calculateTransactionMass(NET, tx)) * FR; const amt = total - fee;
    if (amt < 20000000n) continue;
    tx = kaspa.createTransaction(ins, [{ address: FA, amount: amt }], 0n, null, 1); kaspa.signTransaction(tx, [key], false);
    try { await rpc.submitTransaction({ transaction: tx, allowOrphan: false }); swept += amt; txs++; }
    catch (e) { const m = String(e.message || e).slice(0, 80); if (/spent|orphan|already/.test(m)) {} else log({ src: w.src, err: m }); }
  }
  if (swept > 0n) { totalSwept += swept; walletsDone++; const g = w.src.replace(/[0-9#].*$/, ""); perGroup[g] = (perGroup[g] || 0) + Number(swept) / 1e8;
    log({ src: w.src, addr: w.a.slice(0, 12) + "…" + w.a.slice(-6), swept_tkas: +(Number(swept) / 1e8).toFixed(2) }); }
}
ramp(`done: ${walletsDone} wallets, ${txs} txs, swept ${(Number(totalSwept) / 1e8).toFixed(0)} TKAS to faucet. groups ${JSON.stringify(Object.fromEntries(Object.entries(perGroup).map(([k, v]) => [k, Math.round(v)])))}`);
log({ ev: "done", wallets: walletsDone, txs, total_tkas: +(Number(totalSwept) / 1e8).toFixed(2), groups: perGroup });
console.log("SWEEP DONE", walletsDone, "wallets", txs, "txs", (Number(totalSwept) / 1e8).toFixed(0), "TKAS");
process.exit(0);
