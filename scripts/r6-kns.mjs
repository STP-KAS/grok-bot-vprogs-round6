// round6 KNS bulk create on TN10 (public KNS API + scripted commit/reveal), index-free, many concurrent workers.
// Each worker has its own funding key (created + funded from the faucet by fundWorkers()). One worker does, per label:
//   check available -> commit (P2SH lock 1 TKAS) -> reveal (pays fee to KNS fee sink) -> record. Fee dynamic (2x normal).
// Labels: stp-r6-<worker>-<seq> (>=5 chars => 35 TKAS KNS price). Skips taken labels. NEVER prints keys.
// Uses our own n0 via wRPC borsh (no utxoindex needed: we track each worker's UTXOs from its own txs / getUtxosByAddresses
// is served from mempool+our submitted outputs — but n0 has no utxoindex, so we track locally like the other runners).
import crypto from "node:crypto";
import { appendFileSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { kaspa, connect, NET, deskKey, addrOf } from "./lib.mjs";
const DIR = "/workspace/tn10-break-test-2026-09-25"; const LOG = `${DIR}/logs/round6/kns-${process.argv[2] || "A"}.jsonl`;
const API = "https://api.knsdomains.org/tn10/api/v1";
const FEE = "kaspatest:qq9h47etjv6x8jgcla0ecnp8mgrkfxm70ch3k60es5a50ypsf4h6sak3g0lru";
const TAG = process.argv[2] || "A"; const CONC = Number(process.env.KNS_CONC || 20);
const FKEY = deskKey(0); const FADDR = addrOf(FKEY); const FSPK = kaspa.payToAddressScript(FADDR);
const RESF = "/tmp/r5-reserved-utxos.json"; // faucet UTXOs (feeder). We take a distinct slice (txid[8:16]%4==2) for KNS.
const log = (o) => appendFileSync(LOG, JSON.stringify({ t: new Date().toISOString(), ...o }) + "\n");
const feerate = () => { try { const v = BigInt(readFileSync("/tmp/r6-feerate", "utf8").trim()); if (v >= 200n) return v; } catch {} return 2000n; };
const halted = () => existsSync("/tmp/r5-games.HALT") || existsSync("/tmp/tps-storm.HALT");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rpc = await connect("n0");

// local UTXO tracking per worker (n0 has no utxoindex). Seed each worker with one faucet UTXO (>= 60 TKAS: covers 1 TKAS
// commit lock + 35 TKAS reveal fee + priorities + chaining several creates before refunding).
const USEDF = "/workspace/tmp/r6-kns-used.txt";
const USED = new Set(existsSync(USEDF) ? readFileSync(USEDF, "utf8").split("\n").filter(Boolean) : []);
function takeFaucet(minSompi) {
  let raw = []; try { raw = JSON.parse(readFileSync(RESF, "utf8")); } catch { return null; }
  const cands = raw.filter((u) => parseInt(u.outpoint.transactionId.slice(8, 16), 16) % 4 === 2 && !USED.has(u.outpoint.transactionId + ":" + u.outpoint.index))
    .sort((a, b) => Number(BigInt(b.utxoEntry.amount) - BigInt(a.utxoEntry.amount)));
  const out = []; let sum = 0n;
  for (const u of cands) { out.push(u); sum += BigInt(u.utxoEntry.amount); if (sum >= minSompi) break; if (out.length >= 20) break; }
  if (sum < minSompi) return null;
  for (const u of out) { USED.add(u.outpoint.transactionId + ":" + u.outpoint.index); appendFileSync(USEDF, u.outpoint.transactionId + ":" + u.outpoint.index + "\n"); }
  return out;
}
// fund a fresh worker key from faucet UTXOs; returns { key, addr, utxo:{outpoint,amount} } tracked locally
async function fundWorker() {
  const need = kaspa.kaspaToSompi("70");
  const seeds = takeFaucet(BigInt(need)); if (!seeds) return null;
  const key = new kaspa.PrivateKey(crypto.randomBytes(32).toString("hex")); const addr = addrOf(key); const spk = kaspa.payToAddressScript(addr);
  const ins = seeds.map((u) => ({ address: FADDR, outpoint: u.outpoint, utxoEntry: { amount: BigInt(u.utxoEntry.amount), scriptPublicKey: FSPK, blockDaaScore: BigInt(u.utxoEntry.blockDaaScore), isCoinbase: u.utxoEntry.isCoinbase } }));
  const total = ins.reduce((a, x) => a + x.utxoEntry.amount, 0n);
  let tx = kaspa.createTransaction(ins, [{ address: addr, amount: total - 1n }], 0n, null, 1); kaspa.signTransaction(tx, [FKEY], false);
  const fee = BigInt(kaspa.calculateTransactionMass(NET, tx)) * feerate(); const amt = total - fee;
  tx = kaspa.createTransaction(ins, [{ address: addr, amount: amt }], 0n, null, 1); kaspa.signTransaction(tx, [FKEY], false);
  try { await rpc.submitTransaction({ transaction: tx, allowOrphan: false }); } catch (e) { S.fund_fail++; return null; }
  return { key, addr, spk, utxo: { outpoint: { transactionId: tx.id, index: 0 }, amount: amt } };
}

const S = { attempts: 0, created: 0, unavailable: 0, commit_fail: 0, reveal_fail: 0, fund_fail: 0, check_fail: 0, lat: [] };
async function check(domain, payer) {
  for (let a = 0; a < 4; a++) { try {
    const r = await fetch(`${API}/domains/check`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ domainNames: [domain], address: payer }) });
    const j = JSON.parse(await r.text()); const d = j?.data?.domains?.[0]; return d?.available === true && d?.isReservedDomain === false;
  } catch { await sleep(2000 * (a + 1)); } } return null;
}
// build commit + reveal spending only our locally-tracked worker UTXO (no getUtxosByAddresses; n0 has no utxoindex)
async function createOne(w, label) {
  const domain = `${label}.kas`; S.attempts++;
  const av = await check(domain, w.addr); if (av === null) { S.check_fail++; return w; } if (!av) { S.unavailable++; return w; }
  const payload = JSON.stringify({ op: "create", p: "domain", v: label });
  const script = new kaspa.ScriptBuilder().addData(w.key.toKeypair().xOnlyPublicKey).addOp(kaspa.Opcodes.OpCheckSig).addOp(kaspa.Opcodes.OpFalse).addOp(kaspa.Opcodes.OpIf).addData(Buffer.from("kns")).addI64(0n).addData(Buffer.from(payload)).addOp(kaspa.Opcodes.OpEndIf);
  const p2shSpk = script.createPayToScriptHashScript(); const p2shAddr = kaspa.addressFromScriptPublicKey(p2shSpk, NET).toString();
  const fr = feerate();
  const lock = kaspa.kaspaToSompi("1"); const feeSompi = kaspa.kaspaToSompi("35");
  // commit: worker UTXO -> [p2sh lock, change]
  const inC = [{ address: w.addr, outpoint: w.utxo.outpoint, utxoEntry: { amount: BigInt(w.utxo.amount), scriptPublicKey: w.spk, blockDaaScore: 0n, isCoinbase: false } }];
  let cfee = 2000n * fr; let change = BigInt(w.utxo.amount) - BigInt(lock) - cfee;
  if (change < kaspa.kaspaToSompi("40")) return null; // not enough for the reveal fee -> retire worker
  let commit = kaspa.createTransaction(inC, [{ address: p2shAddr, amount: BigInt(lock) }, { address: w.addr, amount: change }], 0n, null, 1); kaspa.signTransaction(commit, [w.key], false);
  cfee = BigInt(kaspa.calculateTransactionMass(NET, commit)) * fr; change = BigInt(w.utxo.amount) - BigInt(lock) - cfee;
  commit = kaspa.createTransaction(inC, [{ address: p2shAddr, amount: BigInt(lock) }, { address: w.addr, amount: change }], 0n, null, 1); kaspa.signTransaction(commit, [w.key], false);
  const t0 = Date.now();
  try { await rpc.submitTransaction({ transaction: commit, allowOrphan: false }); } catch (e) { S.commit_fail++; log({ ev: "commit_fail", label, e: String(e.message || e).slice(0, 80) }); return w; }
  // reveal: [p2sh input (script sig), change input] -> [fee sink], change back to worker
  const p2shEntry = { address: p2shAddr, outpoint: { transactionId: commit.id, index: 0 }, utxoEntry: { amount: BigInt(lock), scriptPublicKey: p2shSpk, blockDaaScore: 0n, isCoinbase: false } };
  const changeEntry = { address: w.addr, outpoint: { transactionId: commit.id, index: 1 }, utxoEntry: { amount: change, scriptPublicKey: w.spk, blockDaaScore: 0n, isCoinbase: false } };
  let rfee = 3000n * fr; let rback = BigInt(lock) + change - BigInt(feeSompi) - rfee;
  if (rback < 0n) { S.reveal_fail++; return null; }
  const mkReveal = (rb) => kaspa.createTransaction([p2shEntry, changeEntry], [{ address: FEE, amount: BigInt(feeSompi) }, { address: w.addr, amount: rb }], 0n, null, 1);
  let reveal = mkReveal(rback); kaspa.signTransaction(reveal, [w.key], false);
  rfee = BigInt(kaspa.calculateTransactionMass(NET, reveal)) * fr; rback = BigInt(lock) + change - BigInt(feeSompi) - rfee;
  reveal = mkReveal(rback); kaspa.signTransaction(reveal, [w.key], false);
  // fill P2SH input signature
  const idx = reveal.inputs.findIndex((i) => !i.signatureScript || i.signatureScript === "");
  const sig = kaspa.createInputSignature(reveal, idx, w.key);
  reveal.inputs[idx].signatureScript = script.encodePayToScriptHashSignatureScript(sig);
  let revealId;
  try { revealId = await rpc.submitTransaction({ transaction: reveal, allowOrphan: false }); } catch (e) { S.reveal_fail++; log({ ev: "reveal_fail", label, e: String(e.message || e).slice(0, 80) }); return w; }
  S.created++; S.lat.push(Date.now() - t0);
  log({ ev: "created", label, commit: commit.id, reveal: revealId, feerate: Number(fr) });
  return { ...w, utxo: { outpoint: { transactionId: reveal.id, index: 1 }, amount: rback } }; // chain next create on the reveal change
}
let seq = 0;
async function worker(i) {
  let w = null;
  while (!halted()) {
    if (!w) { w = await fundWorker(); if (!w) { await sleep(3000); continue; } }
    const label = `stp-r6-${TAG.toLowerCase()}${i}-${(seq++).toString(36)}${crypto.randomBytes(2).toString("hex")}`;
    const nw = await createOne(w, label);
    w = nw; // null => refund a new worker next loop
  }
}
log({ ev: "start", tag: TAG, conc: CONC });
const rep = setInterval(() => { const l = [...S.lat].sort((a, b) => a - b); const p = (q) => l.length ? l[Math.min(l.length - 1, Math.floor(l.length * q))] : null;
  log({ ev: "rep", ...S, lat_p50: p(0.5), lat_p95: p(0.95), lat_n: l.length, feerate_now: Number(feerate()) }); S.lat = []; }, 15000);
await Promise.all(Array.from({ length: CONC }, (_, i) => worker(i)));
clearInterval(rep); log({ ev: "done", ...S }); process.exit(0);
