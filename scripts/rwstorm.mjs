// Random wallet-to-wallet storm (12h TPS run). One worker of the supervised fleet.
// Each tx: take a ready UTXO from the pool -> send 1-in-1-out to a RANDOM wallet of this worker's set (random
// sender = owner of the taken UTXO, random receiver). New output re-enters the pool after COOL ms, so funds keep
// circulating wallet-to-wallet. Senders/receivers are counted per report interval and logged as a distribution metric.
// Pool is seeded from (a) a slice of the anyone-can-spend P2SH(OP_TRUE) UTXOs [P2A,P2B) (spent with no signature, this
//   also recovers those funds into normal wallets) and (b) any saved state. It refills from the faucet ONLY when the
//   pool runs low (occasional top-up), pulling desk coinbase UTXOs [DA,DB).
// Guards live in the supervisor; this worker also stops on /tmp/tps-storm.HALT.
// usage: MODE=sig|p2w node rwstorm.mjs <tag> <wfrom> <wto> <p2from> <p2to> <workerIndex> <workerCount>
import { readFileSync, writeFileSync, existsSync, appendFileSync, statSync } from "node:fs";
import { kaspa, connect, log, sleep, NET, deskKey, addrOf } from "./lib.mjs";
const [TAG, WF, WT, P2F, P2T, DF, DT] = process.argv.slice(2).map((x, i) => i === 0 ? x : Number(x));
const COOL = Number(process.env.COOL || 4000); let FEE_MULT = Number(process.env.FEE_MULT || 1);
// r6: dynamic fee (2x normal estimate) via /tmp/r6-storm-mult; cached per-tx fees are reset when it changes
setInterval(() => { try { const m = Number(readFileSync("/tmp/r6-storm-mult", "utf8").trim()); if (m >= 2 && m !== FEE_MULT) { FEE_MULT = m; MASS1 = null; TAGFEE = null; FEE2 = null; P2FEE = BigInt(Math.ceil(571 * 100 * FEE_MULT)); } } catch {} }, 30000);
const MIN = BigInt(process.env.MIN_SOMPI || 10000000); // drop leftovers < MIN (default 0.1 TKAS; r5 env MIN_SOMPI)
const LOW = Number(process.env.LOW || 4000), REFILL = Number(process.env.REFILL || 2000);
const DIR = "/workspace/tn10-break-test-2026-09-25";
const STATE = `${DIR}/state-rw-${TAG}.json`;
const keys = JSON.parse(readFileSync("/home/box/secure/tn10-storm-keys.json", "utf8"));
// MODE=sig: wallets are the storm key wallets [WF,WT) (P2PK, Schnorr-signed spends, compute mass ~1624).
// MODE=p2w: wallets are labelled P2SH "tag wallets" id in [WF,WT): redeem = push4(id) OP_DROP OP_TRUE. Each id is a distinct
//   address, so traffic is still random wallet-to-wallet, but spends need no signature (mass ~600): ~2.7x more txs per
//   500k-mass block. They are ANYONE-CAN-SPEND (testnet only, throwaway funds) - documented in the README.
const MODE = process.env.MODE || "sig";
const tagRedeem = (id) => "04" + Buffer.from(Uint32Array.of(id).buffer).toString("hex") + "7551";
const W = MODE === "sig" ? keys.slice(WF, WT).map((k) => ({ i: k.i, key: new kaspa.PrivateKey(k.key), address: k.address, spk: kaspa.payToAddressScript(k.address) }))
  : Array.from({ length: WT - WF }, (_, j) => { const id = WF + j, r = tagRedeem(id), spk = kaspa.payToScriptHashScript(r); return { i: id, tagw: true, sigScript: "07" + r, address: kaspa.addressFromScriptPublicKey(spk, NET).toString(), spk }; });
const byI = new Map(W.map((w) => [w.i, w]));
const ent = (w, txid, index, amount) => ({ address: w.address, outpoint: { transactionId: txid, index }, utxoEntry: { amount: BigInt(amount), scriptPublicKey: w.spk, blockDaaScore: 0n, isCoinbase: false } });
// desk + p2sh pseudo-wallets
const dk = deskKey(0), da = addrOf(dk); const DW = { i: -1, key: dk, address: da, spk: kaspa.payToAddressScript(da) };
const P2SPK = kaspa.payToScriptHashScript("51"); const P2ADDR = kaspa.addressFromScriptPublicKey(P2SPK, NET).toString();
const P2 = { i: -2, p2sh: true, address: P2ADDR, spk: P2SPK };
const nodes = (process.env.NODES || "n0 n1").split(/\s+/).filter(Boolean); // NODES="n0" after the n1 wipe
// Auto-reconnect: a node whose socket failed is set to null and reconnected by one in-flight task (retry every 2 s).
let RPC = {}; const reconnecting = {};
async function reconnectNode(n) { if (reconnecting[n]) return; reconnecting[n] = true; RPC[n] = null;
  for (;;) { try { RPC[n] = await connect(n); S.reconnects = (S.reconnects || 0) + 1; break; } catch { await sleep(2000); } } reconnecting[n] = false; }
async function reconnect() { for (const n of nodes) { try { RPC[n] = await connect(n); } catch (e) { RPC[n] = null; reconnectNode(n); } } }
await reconnect();
const S = { sub: 0, ok: 0, err: 0, errs: {}, fees: 0n, lat: [], orphan: 0, pay: 0, dropped: 0, full: 0, refills: 0 };
let senders = new Set(), receivers = new Set();
const feeFor = (tx) => { const m = BigInt(kaspa.calculateTransactionMass(NET, tx)); return { m, fee: (m * BigInt(Math.round(100 * FEE_MULT))) }; };
let MASS1 = null, TAGFEE = null, FEE2 = null; const PAY = BigInt(process.env.PAY || 0); let P2FEE = BigInt(Math.ceil(571 * 100 * FEE_MULT));
const q = []; let head = 0;
// r5: PERTX_FEE=1 -> fee = actual mass (incl. KIP-9 storage mass) x feerate per tx (fixed TAGFEE underpays small UTXOs at high multipliers)
const PERTX = process.env.PERTX_FEE === "1";
const leftover = (it) => { S.dropped++; try { appendFileSync(`${DIR}/state-leftover-${TAG}.jsonl`, JSON.stringify([it.w.p2sh ? "p2sh" : it.w.i, it.e.outpoint.transactionId, it.e.outpoint.index, String(it.e.utxoEntry.amount)]) + "\n"); } catch {} };
const key = (u) => u.outpoint.transactionId + ":" + u.outpoint.index;
// seed: saved state
if (existsSync(STATE)) { const s = JSON.parse(readFileSync(STATE, "utf8")); for (const [i, list] of Object.entries(s)) { const w = i === "p2sh" ? P2 : byI.get(Number(i)); if (w) for (const [t, x, a, n] of list) q.push({ w, e: i === "p2sh" ? { address: P2ADDR, outpoint: { transactionId: t, index: x }, utxoEntry: { amount: BigInt(a), scriptPublicKey: P2SPK, blockDaaScore: 0n, isCoinbase: false } } : ent(w, t, x, a), node: n && n !== "any" ? n : null, readyAt: 0 }); } }
// seed: our P2SH slice
const hadState = existsSync(STATE);
// the P2SH seed is used only on the very first start; restarts resume from STATE
if (P2T > P2F && !hadState) { const all = JSON.parse(readFileSync("/tmp/p2sh-utxos.json", "utf8")).slice(P2F, P2T); for (const u of all) q.push({ w: P2, e: { address: P2ADDR, outpoint: u.outpoint, utxoEntry: { amount: BigInt(u.utxoEntry.amount), scriptPublicKey: P2SPK, blockDaaScore: 0n, isCoinbase: false } }, node: null, readyAt: 0 }); }
// Faucet top-up: the supervisor keeps /tmp/rw-desk-utxos.json (mature desk coinbase UTXOs) fresh; worker DF of DT takes
// entries with index % DT == DF, so workers never share an input. Only used when this worker's pool drops below LOW.
const DESKF = "/tmp/rw-desk-utxos.json"; let deskList = [], deskCur = 0, deskStamp = 0; const deskUsed = new Set();
function loadDesk() { try { const m = statSync(DESKF).mtimeMs; if (m === deskStamp) return; deskStamp = m; deskList = JSON.parse(readFileSync(DESKF, "utf8")).filter((u) => parseInt(u.outpoint.transactionId.slice(0, 8), 16) % DT === DF); /* r5: partition by txid hash (stable across feeder refreshes) */ deskCur = 0; } catch {} }
function refill() { loadDesk(); let n = 0; while (n < REFILL && deskCur < deskList.length) { const u = deskList[deskCur++]; const kk = u.outpoint.transactionId + ":" + u.outpoint.index; if (deskUsed.has(kk)) continue; deskUsed.add(kk); q.push({ w: DW, desk: true, e: { address: DW.address, outpoint: u.outpoint, utxoEntry: { amount: BigInt(u.utxoEntry.amount), scriptPublicKey: DW.spk, blockDaaScore: BigInt(u.utxoEntry.blockDaaScore), isCoinbase: true } }, node: null, readyAt: 0 }); n++; } S.refills += n; return n; }
const bump = (e) => { const m = String(e?.message || e).replace(/[0-9a-f]{64}/g, "<h>").replace(/\d{4,}/g, "<n>").slice(0, 140); S.errs[m] = (S.errs[m] || 0) + 1; S.err++; };
const PREF = process.env.PREF || "any"; const AFF = process.env.AFFINITY !== "0";
// /tmp/tps-storm.nodes (written by the supervisor) lists the nodes that are healthy; others get no traffic.
let OK = nodes; const readNodes = () => { try { const v = readFileSync("/tmp/tps-storm.nodes", "utf8").trim().split(/\s+/).filter((n) => nodes.includes(n)); OK = v; } catch { OK = nodes; } };
const pickNode = (it) => { if (!OK.length) return null; if (AFF && it.node && OK.includes(it.node)) return it.node; if (PREF !== "any" && OK.includes(PREF)) return PREF; return OK[(Math.random() * OK.length) | 0]; };
let CONC = Number(process.env.CONC || 64);
const readConc = () => { try { CONC = Number(readFileSync(process.env.CONCFILE || "/tmp/tps-storm.conc", "utf8").trim()); if (!Number.isFinite(CONC)) CONC = 0; } catch {} };
readConc();
const t0 = Date.now(), SECS = Number(process.env.SECS || 43200);
const stop = () => Date.now() - t0 > SECS * 1000 || existsSync("/tmp/tps-storm.HALT") || existsSync("/tmp/tn10-break.STOP");
function take() { const now = Date.now(); for (let t = 0; t < 128 && head < q.length; t++) { const it = q[head++]; if (it.readyAt <= now) return it; q.push(it); } return null; }
async function submit(node, tx) { const t = Date.now(); const r = await RPC[node].submitTransaction({ transaction: tx, allowOrphan: false }); S.lat.push(Date.now() - t); return r.transactionId; }
async function one() {
  if (LOW > 0 && q.length - head < LOW) refill();
  const it = take(); if (!it) { await sleep(20); return; }
  const to = W[(Math.random() * W.length) | 0];
  let tx, fee;
  if (it.w.p2sh || it.w.tagw) { const ss = it.w.p2sh ? "0151" : it.w.sigScript;
    if (!it.w.p2sh && !TAGFEE) { const t = kaspa.createTransaction([it.e], [{ address: to.address, amount: it.e.utxoEntry.amount - 1n }], 0n, null, 0); t.inputs[0].signatureScript = ss; TAGFEE = feeFor(t).fee; }
    fee = it.w.p2sh ? P2FEE : TAGFEE;
    if (PERTX) { const t = kaspa.createTransaction([it.e], [{ address: to.address, amount: it.e.utxoEntry.amount - fee }], 0n, null, 0); t.inputs[0].signatureScript = ss; fee = feeFor(t).fee;
      const t2 = kaspa.createTransaction([it.e], [{ address: to.address, amount: it.e.utxoEntry.amount - fee }], 0n, null, 0); t2.inputs[0].signatureScript = ss; fee = feeFor(t2).fee * 105n / 100n; }
    const amt = it.e.utxoEntry.amount - fee; if (amt < MIN) { leftover(it); return; }
    tx = kaspa.createTransaction([it.e], [{ address: to.address, amount: amt }], 0n, null, 0); tx.inputs[0].signatureScript = ss;
  } else { tx = kaspa.createTransaction([it.e], [{ address: to.address, amount: it.e.utxoEntry.amount - 1n }], 0n, null, 1);
    if (!MASS1) MASS1 = feeFor(tx); fee = MASS1.fee; const amt = it.e.utxoEntry.amount - fee; if (amt < MIN) return;
    tx = kaspa.createTransaction([it.e], [{ address: to.address, amount: amt }], 0n, null, 1); kaspa.signTransaction(tx, [it.w.key], false); }
  // PAY lane (the user's 0.5 TKAS random transfers): a big input pays exactly PAY to the random receiver and returns
  // change to the sender (1-in-2-out; the PAY output carries KIP-9 storage mass ~C/PAY = 20000 grams at 0.5 TKAS).
  let split = false;
  if (PAY && !it.w.p2sh && it.e.utxoEntry.amount > PAY + 100000000n && to.i !== it.w.i) {
    const mk = (f) => { const t = kaspa.createTransaction([it.e], [{ address: to.address, amount: PAY }, { address: it.w.address, amount: it.e.utxoEntry.amount - PAY - f }], 0n, null, it.w.tagw ? 0 : 1); if (it.w.tagw) t.inputs[0].signatureScript = it.w.sigScript; else kaspa.signTransaction(t, [it.w.key], false); return t; };
    if (!FEE2) FEE2 = feeFor(mk(0n)).fee;
    if (it.e.utxoEntry.amount > PAY + FEE2 + MIN) { fee = FEE2; tx = mk(fee); split = true; S.pay++; } // r5: at 150x FEE2 (~20k storage-mass grams) can exceed the input -> negative change crashed H
  }
  const amt = tx.outputs[0].value; const node = pickNode(it);
  if (!node || !RPC[node]) { it.readyAt = Date.now() + 500; q.push(it); return; }
  S.sub++; senders.add(it.w.i); receivers.add(to.i);
  try { const id = await submit(node, tx); S.ok++; S.fees += fee; q.push({ w: to, e: ent(to, id, 0, amt), node, readyAt: Date.now() + COOL });
    if (split) q.push({ w: it.w, e: ent(it.w, id, 1, tx.outputs[1].value), node, readyAt: Date.now() + COOL }); }
  catch (e) { bump(e); const m = String(e);
    if (/orphan/.test(m)) { S.orphan++; it.tries = (it.tries || 0) + 1; if (!it.desk && it.tries < 4) { it.readyAt = Date.now() + 800; q.push(it); } else S.dropped++; }
    else if (/full/.test(m)) { S.full++; it.node = node === "n0" ? "n1" : "n0"; it.readyAt = Date.now() + 800; q.push(it); }
    else if (/connect|closed|timeout|not currently available|websocket/i.test(m)) { reconnectNode(node); it.readyAt = Date.now() + 500; q.push(it); }
    else if (/already spent|double spend|already in the mempool/i.test(m)) { S.dropped++; } }
}
// Token bucket: this process may submit at most RATE tx/s; RATE = total rate in RATEFILE / worker count (DT).
let RATE = 1e9, tokens = 0, lastTok = Date.now();
// a worker with its own CONCFILE (the 0.5 TKAS lane) also has its own rate file next to it (<name>.rate, per-process value)
const RF = process.env.RATEFILE || (process.env.CONCFILE ? process.env.CONCFILE.replace(/\.conc$/, ".rate") : "/tmp/tps-storm.rate");
const readRate = () => { try { const v = Number(readFileSync(RF, "utf8").trim()); if (Number.isFinite(v)) RATE = v / (RF === "/tmp/tps-storm.rate" ? DT : 1); } catch { RATE = 1e9; } };
readRate(); setInterval(readRate, 2000);
async function token() { for (;;) { if (stop()) return; const now = Date.now(); tokens = Math.min(RATE, tokens + (now - lastTok) * RATE / 1000); lastTok = now; if (tokens >= 1) { tokens -= 1; return; } await sleep(Math.max(5, 1000 / Math.max(RATE, 1))); } }
async function worker(k) { while (!stop()) { if (k >= CONC) { await sleep(300); continue; } await token(); await one(); } }
const cc = setInterval(() => { readConc(); readNodes(); }, 2000); readNodes();
const cmp = setInterval(() => { if (head > 200000) { q.splice(0, head); head = 0; } }, 5000);
let last = { t: Date.now(), ok: 0, sub: 0 };
const rep = setInterval(async () => {
  const now = Date.now(), dt = (now - last.t) / 1000; const l = S.lat.sort((a, b) => a - b); const mp = {};
  for (const n of nodes) { try { mp[n] = RPC[n] ? (await RPC[n].getInfo()).mempoolSize : null; } catch { mp[n] = null; } }
  log({ step: "rw", tag: TAG, conc: CONC, elapsed_s: Math.round((now - t0) / 1000), submitted: S.sub, accepted: S.ok, rejected: S.err,
    tps_submitted: +((S.sub - last.sub) / dt).toFixed(1), tps_accepted: +((S.ok - last.ok) / dt).toFixed(1),
    submit_ms_p50: l[l.length >> 1] ?? null, submit_ms_p99: l[Math.floor(l.length * 0.99)] ?? null, mempool: mp,
    pool: q.length - head, distinct_senders: senders.size, distinct_receivers: receivers.size, orphan_retries: S.orphan, full_requeues: S.full,
    dropped: S.dropped, refills: S.refills, reconnects: S.reconnects || 0, pay_txs: S.pay, fee_pay: FEE2 && String(FEE2), desk_cur: deskCur, mode: MODE, rate_cap: Math.round(RATE), fee1: MASS1 && String(MASS1.fee), fee_tag: TAGFEE && String(TAGFEE), fees_sompi: String(S.fees), errs: S.errs });
  S.lat = []; last = { t: now, ok: S.ok, sub: S.sub }; senders = new Set(); receivers = new Set();
}, 10000);
const save = () => { const o = {}; for (let k = head; k < q.length; k++) { const it = q[k]; if (it.desk) continue; (o[it.w.p2sh ? "p2sh" : it.w.i] ||= []).push([it.e.outpoint.transactionId, it.e.outpoint.index, it.e.utxoEntry.amount.toString(), it.node || "any"]); } writeFileSync(STATE + ".tmp", JSON.stringify(o)); try { writeFileSync(STATE, readFileSync(STATE + ".tmp")); } catch {} };
const sv = setInterval(save, 30000);
await Promise.all(Array.from({ length: 512 }, (_, k) => worker(k)));
[cc, cmp, rep, sv].forEach(clearInterval); save();
log({ step: "rw-done", tag: TAG, submitted: S.sub, accepted: S.ok, rejected: S.err, fees_sompi: String(S.fees), secs: Math.round((Date.now() - t0) / 1000) });
process.exit(0);
