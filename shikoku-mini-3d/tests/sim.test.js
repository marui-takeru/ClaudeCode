// 運行シミュレーションのテスト:  node --test tests/
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(network) {
  const ctx = { window: {} };
  vm.createContext(ctx);
  const root = path.join(__dirname, '..');
  if (network) ctx.window.NETWORK = network;
  else vm.runInContext(fs.readFileSync(path.join(root, 'data/network.js'), 'utf8'), ctx);
  vm.runInContext(fs.readFileSync(path.join(root, 'js/sim.js'), 'utf8'), ctx);
  return ctx.window;
}

const W = load();
const { Simulator, easeTrapezoid, parseTime } = W.Sim;
const sim = new Simulator(W.NETWORK);
const pattern = id => sim.patterns.find(p => p.service.id === id);
const H = h => h * 3600;

test('台形速度の位置関数は 0→1 で単調増加', () => {
  let prev = -1;
  for (let u = 0; u <= 1.0001; u += 0.01) {
    const e = easeTrapezoid(Math.min(u, 1), 0.2);
    assert.ok(e >= prev - 1e-12);
    prev = e;
  }
  assert.equal(easeTrapezoid(0, 0.2), 0);
  assert.ok(Math.abs(easeTrapezoid(1, 0.2) - 1) < 1e-9);
});

test('主な系統の所要時間が実際の値に近い', () => {
  const minutes = id => pattern(id).durationOf(0) / 60;
  assert.ok(minutes('iyo3') > 15 && minutes('iyo3') < 25, `3系統 ${minutes('iyo3')}`);
  // 高浜〜横河原の直通 (実際はおよそ 50 分)
  assert.ok(minutes('takahama') > 45 && minutes('takahama') < 60, `高浜・横河原線 ${minutes('takahama')}`);
  assert.ok(minutes('gunchu') > 20 && minutes('gunchu') < 30, `郡中線 ${minutes('gunchu')}`);
  assert.ok(minutes('shiokaze') > 120 && minutes('shiokaze') < 170, `しおかぜ 児島→松山 ${minutes('shiokaze')}`);
});

test('深夜は運行せず、昼は多くの列車が走る', () => {
  // 深夜も走るのは夜行・深夜便の船だけ
  assert.equal(sim.trainsAt(H(3)).filter(t => t.service.kind !== 'ship').length, 0);
  assert.ok(sim.trainsAt(H(3)).some(t => t.service.id === 'ferry_orange'));
  assert.ok(sim.trainsAt(H(12)).length > 80);
});

test('日付をまたぐ列車も数える', () => {
  // 23:50 発・所要約 30 分の便だけを持つ系統で、0:10 にも走っていることを確かめる
  const base = W.NETWORK.services.find(s => s.id === 'takahama');
  const stops = base.path.filter(p => p[2]).length;
  const t = Array.from({ length: stops }, (_, k) => [k * 200, k * 200]);
  const net = { ...W.NETWORK, services: [{ ...base, id: 'late', both: false, bands: undefined, trips: [{ dep: H(23) + 50 * 60, t }] }] };
  const W2 = load(net);
  const s2 = new W2.Sim.Simulator(W2.NETWORK);
  assert.equal(s2.trainsAt(H(23) + 55 * 60).length, 1);
  const after = s2.trainsAt(10 * 60);
  assert.equal(after.length, 1);
  assert.equal(after[0].dep, H(23) + 50 * 60);
  assert.equal(s2.trainsAt(H(3)).length, 0);
});

test('発車待ちの列車は始発駅に停車している', () => {
  const trains = sim.trainsAt(H(10) + 123);
  const waiting = trains.filter(t => t.waiting);
  assert.ok(waiting.length > 0);
  for (const t of waiting) {
    assert.equal(t.dist, 0);
    assert.ok(t.elapsed < 0 && t.elapsed >= -t.pattern.layover);
  }
});

test('列車の位置は経路上にあり、時間とともに進む', () => {
  const p = pattern('gunchu');
  let prev = -1;
  for (let e = 0; e <= p.durationOf(0); e += 15) {
    const st = p.stateAt(e);
    assert.ok(st.dist >= prev - 1e-6 && st.dist <= p.length + 1e-6);
    prev = st.dist;
  }
});

test('発車案内は近い順で、その駅を発車する列車だけ', () => {
  const line = W.NETWORK.lines.find(l => l.id === 'iyo_shieki');
  const [name, c] = line.stations.find(s => s[0] === '大街道');
  const deps = sim.departuresAt(name, c, H(8), { limit: 20 });
  assert.ok(deps.length === 20);
  for (let i = 1; i < deps.length; i++) assert.ok(deps[i].wait >= deps[i - 1].wait);
  for (const d of deps) assert.ok(d.pattern.path.some(q => q[0] === '大街道' && q[2]));
});

test('到達圏: 出発駅は 0 分、遠い駅ほど時間がかかり、上限を超えない', () => {
  const line = W.NETWORK.lines.find(l => l.id === 'iyo_takahama');
  const [name, c] = line.stations.find(st => st[0] === '松山市');
  const r = sim.reachFrom(name, c, H(8), { maxMinutes: 60 });
  const byName = n => r.find(x => x.name === n);
  assert.equal(byName(name).minutes, 0);
  assert.ok(byName('高浜').minutes < 40);
  assert.ok(byName('古町').minutes < byName('高浜').minutes);
  for (const x of r) assert.ok(x.minutes >= 0 && x.minutes <= 60);
  // 物理的な下限: 直線距離を時速 100km で割った時間より短くはならない
  for (const x of r) {
    const d = W.Sim.haversine(c, x.c);
    assert.ok(x.minutes * 60 + 1 >= d / (100 / 3.6) - 60, `${x.name} ${x.minutes}`);
  }
});

test('便ごとの時刻 (trips) を持つ系統は、その時刻どおりに走る', () => {
  const base = W.NETWORK.services.find(s => s.id === 'takahama');
  const stops = base.path.filter(p => p[2]).length;
  const mk = (dep, run) => {
    const t = [];
    let x = 0;
    for (let k = 0; k < stops; k++) {
      // 始発駅は発車時刻 = 0 (import_gtfs.py と同じ)、途中駅は 30 秒停車
      const d = k === 0 || k === stops - 1 ? x : x + 30;
      t.push([x, d]);
      x = d + run;
    }
    return { dep, t };
  };
  const net = { ...W.NETWORK, services: [{ ...base, id: 'g', both: false, bands: undefined, trips: [mk(H(8), 120), mk(H(9), 240)] }] };
  const W2 = load(net);
  const s2 = new W2.Sim.Simulator(W2.NETWORK);
  const p = s2.patterns[0];
  assert.equal(p.durationOf(0), (stops - 1) * 120 + (stops - 2) * 30);
  assert.equal(p.durationOf(1), (stops - 1) * 240 + (stops - 2) * 30);
  const tr = s2.trainsAt(H(9) + 240 + 15).find(x => x.dep === H(9));
  assert.equal(tr.stopped, true); // 2 駅目に停車中 (240 秒で到着、30 秒停車)
  assert.equal(p.path[tr.at][0], p.path.filter(q => q[2])[1][0]);
});

test('parseTime は HH:MM を秒に変換する', () => {
  assert.equal(parseTime('07:45'), 7 * 3600 + 45 * 60);
});

test('平日 / 土休日ダイヤ: 日付の判定と便の切り替え', () => {
  const base = W.NETWORK.services.find(s => s.id === 'takahama');
  const stops = base.path.filter(p => p[2]).length;
  const t = Array.from({ length: stops }, (_, k) => [k * 120, k * 120]);
  const net = {
    ...W.NETWORK,
    calendar: { holidays: ['20261012'] },
    services: [{ ...base, id: 'd', both: false, bands: undefined, trips: [
      { dep: H(8), t, days: ['weekday'] },
      { dep: H(8) + 600, t, days: ['weekday', 'holiday'] },
    ] }],
  };
  const W2 = load(net);
  const s2 = new W2.Sim.Simulator(W2.NETWORK);
  assert.equal(s2.dayTypeOf('20261005'), 'weekday'); // 月曜
  assert.equal(s2.dayTypeOf('20261010'), 'holiday'); // 土曜
  assert.equal(s2.dayTypeOf('20261012'), 'holiday'); // 祝日 (スポーツの日)
  assert.equal(s2.trainsAt(H(8) + 900).length, 2);
  s2.setDayType('holiday');
  assert.equal(s2.trainsAt(H(8) + 900).length, 1);
});

test('平日と土休日で推計ダイヤの本数が変わる (伊予鉄 郊外電車の朝)', () => {
  const W2 = load();
  const s2 = new W2.Sim.Simulator(W2.NETWORK);
  const count = () => s2.patterns.filter(p => p.service.id === 'takahama')
    .reduce((n, p) => n + p.departures.filter(d => d >= H(7) + 1800 && d < H(8) + 1800).length, 0);
  const weekday = count();
  s2.setDayType('holiday');
  assert.ok(weekday > count(), `平日 ${weekday} 本`);
});

test('瀬戸大橋線: 列車は線路の点列の上を走る (児島〜宇多津は約 18.1km)', () => {
  const line = W.NETWORK.lines.find(l => l.id === 'jr_seto_ohashi');
  assert.ok(line && line.shape && line.shape.length > 20, '国土数値情報の線形がある');
  const p = pattern('nanpu');
  const kojima = p.path.findIndex(q => q[0] === '児島');
  const utazu = p.path.findIndex(q => q[0] === '宇多津');
  const km = (p.cum[utazu] - p.cum[kojima]) / 1000;
  assert.ok(km > 17.8 && km < 18.4, `児島〜宇多津 ${km.toFixed(2)} km`);
  // 橋の途中の位置が、線路の点列から 1m 以内にある
  const d = (p.cum[kojima] + p.cum[utazu]) / 2;
  const pt = p.pointAt(d).c;
  const near = Math.min(...line.shape.map((c, i) => i && W.Sim.haversine(pt, c)).filter(Boolean));
  const seg = line.shape.findIndex((c, i) => i > 0 && W.Sim.haversine(line.shape[i - 1], pt) + W.Sim.haversine(pt, c)
    - W.Sim.haversine(line.shape[i - 1], c) < 1);
  assert.ok(seg > 0, `線路から外れていない (最寄りの点まで ${near.toFixed(0)} m)`);
});
