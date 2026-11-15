import test from 'node:test';
import assert from 'node:assert/strict';
import { buildEngineRequest, configureEngineAuth, engineBase, evaluateEngine, planItem, planWeek, type EngineResponse, type PlanResponse } from '../src/engine/client.ts';
import { effortLine, modelLines, outcomeNotice } from '../src/engine/text.ts';
import { api, withVelocityMeta } from '../src/api/adapter.ts';
import { readSessions, selectStorage, writeJson, KEYS } from '../src/api/local.ts';
import type { AthleteProfile, PlannedTraining, WorkoutSession } from '../src/types.ts';

function storage() { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, removeItem: (k: string) => { m.delete(k); } }; }
const profile: AthleteProfile = { name: 'Geheime Naam', priority: 'balans', experienceYears: 3, availableDays: [1, 3], sessionDurationMinutes: 60, hasVbt: true,
  hasStravaSync: false, capacities: {}, enduranceThreshold: 250, velocitySetup: { metric: 'mean_concentric', deviceId: 'encoder-1' }, onboardingComplete: true };
const strength: WorkoutSession = { id: 'k1', date: '2026-11-10', type: 'kracht', title: 'Geheime titel', durationMinutes: 55, savedToServer: true, startTime: '2026-11-10T18:02:00.000Z',
  exercises: [{ exerciseId: 'back_squat', lift: 'squat', sets: [
    { setNum: 1, weight: 100, targetReps: 3, completedReps: 3, velocities: [0.61, null, 0.55], rpe: 8, note: 'geheime notitie', velocityMeta: { metric: 'mean_concentric', deviceId: 'encoder-1', source: 'manual' } }] }] };
const ride: WorkoutSession = { id: 'd1', date: '2026-11-10', type: 'duur', title: 'Duur — cycling', durationMinutes: 60, savedToServer: true,
  enduranceResult: { sport: 'cycling', durationMinutes: 60, intensityType: 'tempo', rpe: 6, averagePowerW: 210 } };
const fatigue = (total: number, cross = 0) => ({ own_fatigue_pct: total - cross, cross_fatigue_pct: cross, total_pct: total, low_pct: total - 2, high_pct: total + 2 });
const response = (overrides: Partial<EngineResponse['concurrent_model'] & object> = {}): EngineResponse => ({
  contract_version: '1', engine_version: 'ct-engine-3.2.0', as_of_date: '2026-11-10', input_digest: 'a'.repeat(64), sessions_used: 2, sessions_after_as_of_ignored: 0,
  strength: [], endurance: { cp_model: { status: 'insufficient_data', reasons: [], warnings: [], efforts_used: 0 }, reference: { source: 'none', power_w: null, w_prime_j: null } },
  load: { daily: [], last_7_days: { strength_work_sets: 1, strength_tonnage_kg: 300, endurance_minutes: 60, endurance_load: null, endurance_load_method: null },
    previous_28_days: { strength_work_sets: 0, strength_tonnage_kg: 0, endurance_minutes: 0, endurance_load: null, endurance_load_method: null }, previous_28_days_covered: false, note: '' },
  concurrent: [], limitations: [],
  concurrent_model: { model_version: 'ct-concurrent-1.0.0', strength: { status: 'prior_only', observations: 1, basis: 'group_level_priors_only' },
    endurance: { status: 'prior_only', observations: 0, basis: 'group_level_priors_only' },
    data: { sessions: 2, sessions_without_start_time: 1, same_day_pairs_with_unknown_gap: 1, strength_sets_region_unknown: 0 },
    expected_fatigue_effect: [{ at: '2026-11-11T00:00', strength_lower: fatigue(-1.8, -0.6), strength_upper: fatigue(0), endurance: fatigue(-0.9) },
      { at: '2026-11-12T00:00', strength_lower: fatigue(-1.1), strength_upper: fatigue(0), endurance: fatigue(-0.3) },
      { at: '2026-11-13T00:00', strength_lower: fatigue(-0.2), strength_upper: fatigue(0), endurance: fatigue(0) }], limitations: [], ...overrides } });

test('the engine request carries measurements and context but no name, title or note', () => {
  const request = buildEngineRequest([strength, ride], profile, '2026-11-10');
  const text = JSON.stringify(request);
  for (const secret of ['Geheime Naam', 'Geheime titel', 'geheime notitie']) assert.ok(!text.includes(secret), secret);
  assert.equal(request.contractVersion, '1');
  assert.deepEqual(request.endurance, { thresholdPowerW: 250, maximalEfforts: [] });
  const withEfforts = buildEngineRequest([], { ...profile, maximalEfforts: [{ date: '2026-11-01', durationSeconds: 300, powerW: 320 }] }, '2026-11-10');
  assert.deepEqual(withEfforts.endurance.maximalEfforts, [{ date: '2026-11-01', durationSeconds: 300, powerW: 320 }]);
  const [k, d] = request.sessions;
  assert.equal(k.startTime, '2026-11-10T18:02:00.000Z'); assert.equal(d.startTime, undefined);
  assert.deepEqual({ id: k.exercises[0].exerciseId, region: k.exercises[0].region, power: k.exercises[0].power, load: k.exercises[0].loadType }, { id: 'back_squat', region: 'lower', power: false, load: 'weight' });
  assert.deepEqual(k.exercises[0].sets[0].velocities, [0.61, null, 0.55]);               // a missing rep stays missing
  assert.deepEqual(k.exercises[0].sets[0].velocityMeta, { metric: 'mean_concentric', deviceId: 'encoder-1', source: 'manual' });
  assert.equal(d.enduranceResult!.averagePowerW, 210);
  const clean = buildEngineRequest([{ ...strength, exercises: [{ exerciseId: 'power_clean', lift: 'power_clean', sets: strength.exercises![0].sets }] }], null, '2026-11-10');
  assert.equal(clean.sessions[0].exercises[0].power, true); assert.equal(clean.endurance.thresholdPowerW, undefined);
});

test('velocity sets are stamped with the configured meter once, and sets without velocities are left alone', () => {
  const sets = [{ setNum: 1, weight: 100, targetReps: 3, completedReps: 3, velocities: [0.6, 0.58, null] },
    { setNum: 2, weight: 100, targetReps: 3, completedReps: 3, velocities: [null, null, null] },
    { setNum: 3, weight: 100, targetReps: 3, completedReps: 3, velocities: [0.5, 0.5, 0.5], velocityMeta: { metric: 'peak' as const, deviceId: 'old', source: 'manual' as const } }];
  const [ex] = withVelocityMeta([{ lift: 'squat', sets }], { metric: 'mean_propulsive', deviceId: '  mijn meter  ' });
  assert.deepEqual(ex.sets[0].velocityMeta, { metric: 'mean_propulsive', deviceId: 'mijn meter', source: 'manual' });
  assert.equal(ex.sets[1].velocityMeta, undefined); assert.equal(ex.sets[2].velocityMeta!.deviceId, 'old');
  assert.equal(withVelocityMeta([{ lift: 'squat', sets }], undefined)[0].sets[0].velocityMeta, undefined);
});

test('saving keeps the real start time and never invents one for a session logged afterwards', async () => {
  const s = storage(); selectStorage(s); writeJson(KEYS.profile, profile, s);
  try {
    await api.saveStrengthWorkout({ sessionId: 'new-k', athleteId: 1, startTime: '2026-11-12T17:30:00.000Z', endTime: '2026-11-12T18:30:00.000Z', durationMinutes: 60,
      completedExercises: [{ exerciseId: 'back_squat', lift: 'squat', sets: [{ setNum: 1, weight: 100, targetReps: 3, completedReps: 2, velocities: [0.6, 0.5] }] }], exercises: [] });
    await api.saveEnduranceSession({ sessionId: 'later', athleteId: 1, sport: 'cycling', startTime: '2026-11-12T06:00:00.000Z', durationMinutes: 45, intensityType: 'z2' });
    await api.saveEnduranceSession({ sessionId: 'timed', athleteId: 1, sport: 'cycling', startTime: '2026-11-13T06:00:00.000Z', startTimeKnown: true, durationMinutes: 45, intensityType: 'z2' });
    const saved = Object.fromEntries(readSessions(s).map(x => [x.id, x]));
    assert.equal(saved['new-k'].startTime, '2026-11-12T17:30:00.000Z');
    assert.deepEqual(saved['new-k'].exercises![0].sets[0].velocityMeta, { metric: 'mean_concentric', deviceId: 'encoder-1', source: 'manual' });
    assert.equal('startTime' in saved['later'], false); assert.equal(saved['timed'].startTime, '2026-11-13T06:00:00.000Z');
  } finally { selectStorage(); }
});

test('the engine is only called when signed in, caches by input, and reports failures without inventing a result', async () => {
  const s = storage();
  let calls: { url: string; auth: string; body: string }[] = [];
  let reply: () => Response = () => new Response(JSON.stringify(response()), { status: 200 });
  const fetcher = (async (url: string, init: RequestInit) => { calls.push({ url, auth: (init.headers as Record<string, string>).Authorization, body: init.body as string }); return reply(); }) as unknown as typeof fetch;
  const run = (sessions = [strength, ride]) => evaluateEngine(sessions, profile, '2026-11-10', { fetcher, base: 'https://engine.test', storage: s });
  configureEngineAuth(null);
  let out = await run();
  assert.deepEqual([out.state, out.state === 'unavailable' && out.reason, calls.length], ['unavailable', 'signed_out', 0]);
  assert.equal(outcomeNotice(out), 'Log in om berekeningen op te vragen.');
  configureEngineAuth(async () => 'user-token');
  try {
    out = await run();
    assert.equal(out.state, 'ok'); assert.equal(out.state === 'ok' && out.fromCache, false);
    assert.deepEqual([calls[0].url, calls[0].auth], ['https://engine.test/v3/engine/evaluate', 'Bearer user-token']);
    assert.ok(!calls[0].body.includes('Geheime'));
    out = await run();
    assert.equal(out.state === 'ok' && out.fromCache, true); assert.equal(calls.length, 1);
    out = await evaluateEngine([strength, ride], profile, '2026-11-10', { fetcher, base: 'https://engine.test', storage: s, force: true });
    assert.equal(out.state === 'ok' && out.fromCache, false); assert.equal(calls.length, 2);
    configureEngineAuth(null);
    out = await run();
    assert.equal(out.state === 'unavailable' && out.reason, 'signed_out');
    configureEngineAuth(async () => 'user-token');
    const cache = JSON.parse(s.getItem('ct_engine_cache_v1')!);
    cache.fetchedAt = '2020-01-01T00:00:00Z'; s.setItem('ct_engine_cache_v1', JSON.stringify(cache));
    out = await run();
    assert.equal(out.state === 'ok' && out.fromCache, false); assert.equal(calls.length, 3);
          // same input: no second call
    for (const [status, reason] of [[401, 'session_expired'], [409, 'version_mismatch'], [429, 'busy'], [503, 'not_configured'], [500, 'error']] as const) {
      reply = () => new Response('{}', { status });
      out = await run([strength]);
      assert.equal(out.state === 'unavailable' && out.reason, reason);
      assert.equal(out.state === 'unavailable' && out.cached?.response.engine_version, 'ct-engine-3.2.0');   // offered only as outdated context
    }
    reply = () => { throw new TypeError('network'); };
    out = await run([strength]);
    assert.equal(out.state === 'unavailable' && out.reason, 'offline');
    reply = () => new Response(JSON.stringify({ ...response(), contract_version: '2' }), { status: 200 });
    out = await run([strength]);
    assert.equal(out.state === 'unavailable' && out.reason, 'version_mismatch');
  } finally { configureEngineAuth(null); }
  assert.equal(engineBase({ hostname: 'robinvandenbroecke.github.io' }), 'https://concurrent-training.onrender.com');
  assert.equal(engineBase({ hostname: 'concurrent-training.onrender.com' }), '');
});

test('model text states the expected effect with its uncertainty and what it rests on', () => {
  const lines = modelLines(response()).join('\n');
  assert.match(lines, /Benenkracht: −1,8 % \(onzekerheid −3,8 % tot \+0,2 %\), waarvan −0,6 % door de andere trainingsvorm/);
  assert.match(lines, /Duurvermogen: −0,9 %/); assert.doesNotMatch(lines, /Bovenlichaamkracht/);
  assert.match(lines, /Over twee dagen is dat verwachte effect weggeëbd/);
  assert.match(lines, /voorlopige modelaannames, geïnspireerd op groepsonderzoek en niet op jouw metingen.*\(nu 1\)/);
  assert.match(lines, /1 training heeft geen starttijd/);
  assert.match(lines, /geen meting en geen uitspraak over blessurerisico.*niet op echte atleten gevalideerd/);
  const fresh = response({ expected_fatigue_effect: [{ at: 'x', strength_lower: fatigue(0), strength_upper: fatigue(0), endurance: fatigue(0.1) }],
    strength: { status: 'ok', observations: 40, basis: 'priors_updated_with_own_data', verdict: 'interaction_shown_in_own_data' },
    data: { sessions: 9, sessions_without_start_time: 0, same_day_pairs_with_unknown_gap: 0, strength_sets_region_unknown: 0 } });
  const text = modelLines(fresh).join('\n');
  assert.match(text, /geen merkbare restvermoeidheid/); assert.match(text, /In je eigen gegevens \(40 krachtmetingen\) past een model met wisselwerking/);
  assert.doesNotMatch(text, /starttijd/);
  assert.deepEqual(modelLines({ ...response(), concurrent_model: undefined }), []);
});

test('the request the webapp builds is exactly the frozen fixture that the Python contract test validates', async () => {
  const { readFileSync } = await import('node:fs');
  const { clientSessions, clientProfile } = await import('./engine-fixture.ts');
  const frozen = JSON.parse(readFileSync(new URL('./fixtures/contracts/client_request_v1.json', import.meta.url), 'utf8'));
  assert.deepEqual(JSON.parse(JSON.stringify(buildEngineRequest(clientSessions, clientProfile, '2026-11-10'))), { ...frozen, timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone });
});

test('the card renders the engine answer, and a server failure shows a notice instead of numbers', async () => {
  const React = (await import('react')).default; const { act } = await import('react');
  const { JSDOM } = await import('jsdom');
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test/concurrent-training/', pretendToBeVisual: true });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
  const { createRoot } = await import('react-dom/client');
  const { default: EngineCard } = await import('../src/components/EngineCard.tsx');
  const s = storage(); selectStorage(s); writeJson(KEYS.sessions, [strength, ride], s); writeJson(KEYS.profile, profile, s);
  const originalFetch = globalThis.fetch;
  let status = 200;
  globalThis.fetch = (async () => new Response(JSON.stringify(response()), { status })) as typeof fetch;
  configureEngineAuth(async () => 'user-token');
  const host = document.getElementById('root')!; const root = createRoot(host);
  const settle = async () => { for (let i = 0; i < 5; i++) await act(async () => { await new Promise(r => setTimeout(r, 5)); }); };
  try {
    await act(async () => { root.render(<EngineCard compact />); }); await settle();
    const text = host.textContent!;
    assert.match(text, /Verwachte restvermoeidheid \(experimenteel model\)/); assert.match(text, /Benenkracht: −1,8 %/);
    assert.match(text, /Laatste 7 dagen: 1 krachtwerksets, 60 min duurtraining/);
    assert.match(text, /zonder naam, titels of notities naar de rekenserver/); assert.match(text, /Rekenmotor ct-engine-3\.2\.0/);
    assert.match(text, /Er is geen gevalideerde belastbaarheidsscore/);
    writeJson(KEYS.sessions, [strength], s); status = 500;                       // input changed and the server now fails
    await act(async () => { [...host.querySelectorAll('button')].find(b => /Opnieuw/.test(b.textContent!))?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })); });
    await act(async () => { root.unmount(); });
    const second = createRoot(host);
    await act(async () => { second.render(<EngineCard compact />); }); await settle();
    assert.match(host.textContent!, /De rekenmotor gaf een fout\. Er wordt geen resultaat getoond\./);
    assert.match(host.textContent!, /laatst bekende berekening van \d{4}-\d{2}-\d{2}; je gegevens zijn sindsdien gewijzigd/);
    await act(async () => { second.unmount(); });
  } finally { configureEngineAuth(null); globalThis.fetch = originalFetch; selectStorage(); dom.window.close(); }
});

// ── week planner ────────────────────────────────────────────────────────────
const set = (n: number, kind: 'work' | 'warmup' = 'work') => ({ setNum: n, weight: 50, targetReps: 5, restSec: 120, kind });
const legs: PlannedTraining = { date: '2026-11-16', type: 'kracht', title: 'Benen', durationMinutes: 60, exercises: [
  { id: 'a', exerciseId: 'back_squat', lift: 'squat', displayName: 'Back squat', sets: [set(1, 'warmup'), set(2), set(3), set(4)] },
  { id: 'b', exerciseId: 'deadlift', lift: 'deadlift', displayName: 'Deadlift', sets: [set(1), set(2)] }] };
const mixed: PlannedTraining = { date: '2026-11-17', type: 'kracht', title: 'Gemengd', durationMinutes: 60, exercises: [
  { id: 'a', exerciseId: 'back_squat', lift: 'squat', displayName: 'Back squat', sets: [set(1), set(2), set(3)] },
  { id: 'b', exerciseId: 'bench_press', lift: 'bench', displayName: 'Bankdrukken', sets: [set(1), set(2), set(3)] }] };
const intervals: PlannedTraining = { date: '2026-11-19', type: 'duur', title: 'Intervallen', durationMinutes: 50,
  endurance: { sport: 'cycling', durationMinutes: 50, intensityType: 'hiit', description: '' } };
const planReply = (order: [string, string][]): PlanResponse => ({ model_version: 'ct-concurrent-1.0.0', method: 'exhaustive', arrangements_evaluated: 6, priority: 'balans',
  basis: { strength: 'group_level_priors_only', endurance: 'group_level_priors_only' }, difference_best_to_worst_pct: 1.4, limitations: [],
  options: [{ score: -0.01, end_of_horizon: {}, sessions: order.map(([label, day], i) => ({ label, start: `${day}T18:00`, domain: 'strength' as const, key: false,
    expected_fatigue_effect_pct: i ? -0.8 : 0, low_pct: i ? -2.6 : 0, high_pct: i ? 1.1 : 0, within_3h_of_endurance: false })) }] });

test('a planned training becomes a relative dose: work sets by region, minutes with a declared intensity', () => {
  assert.deepEqual(planItem(legs, true), { label: '2026-11-16', kind: 'strength_lower', workSets: 5, minutes: 0, relativeIntensity: 0.7, key: true });   // the warm-up set is not dose
  assert.deepEqual(planItem(mixed, false), { label: '2026-11-17', kind: 'strength_full', workSets: 3, minutes: 0, relativeIntensity: 0.7, key: false });
  assert.deepEqual(planItem(intervals, false), { label: '2026-11-19', kind: 'endurance', workSets: 0, minutes: 50, relativeIntensity: 1.1, key: false });
  assert.equal(planItem({ ...intervals, endurance: { ...intervals.endurance!, sport: 'swimming' } }, false)!.kind, 'endurance_swim');
  assert.equal(planItem({ date: '2026-11-20', type: 'rust', title: 'Rust', durationMinutes: 0 }, false), null);
  assert.equal(planItem({ ...legs, exercises: [] }, false), null);
});

test('the planner request reuses the engine request and adds only sessions, dates, one slot and the priority', async () => {
  let sent: Record<string, unknown> = {}, url = '';
  const fetcher = (async (u: string, init: RequestInit) => { url = u; sent = JSON.parse(init.body as string); return new Response(JSON.stringify(planReply([['2026-11-16', '2026-11-17'], ['2026-11-17', '2026-11-16']])), { status: 200 }); }) as unknown as typeof fetch;
  const items = [planItem(legs, true)!, planItem(mixed, false)!];
  configureEngineAuth(null);
  assert.deepEqual(await planWeek([strength], profile, '2026-11-15', items, ['2026-11-16', '2026-11-17'], 18, { fetcher, base: 'https://engine.test' }), { state: 'unavailable', reason: 'signed_out' });
  configureEngineAuth(async () => 'user-token');
  try {
    const out = await planWeek([strength], profile, '2026-11-15', items, ['2026-11-16', '2026-11-17'], 18, { fetcher, base: 'https://engine.test' });
    assert.equal(out.state, 'ok'); assert.equal(url, 'https://engine.test/v3/engine/plan');
    assert.deepEqual([sent.asOfDate, sent.availableDates, sent.slotHours, sent.priority], ['2026-11-15', ['2026-11-16', '2026-11-17'], [18], 'balans']);
    assert.deepEqual(sent.planSessions, items); assert.equal((sent.sessions as unknown[]).length, 1);
    assert.ok(!JSON.stringify(sent).includes('Geheime') && !JSON.stringify(sent).includes('Benen'));     // plan titles are not sent either
    const refused = (async () => new Response('{}', { status: 422 })) as unknown as typeof fetch;
    assert.deepEqual(await planWeek([], profile, '2026-11-15', items, ['2026-11-16', '2026-11-17'], 8, { fetcher: refused, base: '' }), { state: 'unavailable', reason: 'invalid_request' });
  } finally { configureEngineAuth(null); }
});

test('a suggested order is applied as one permutation of planned days, or not at all', async () => {
  const s = storage(); selectStorage(s);
  const now = new Date('2026-11-15T10:00:00');                                    // a Sunday: the coming days lie in the next calendar week
  writeJson(KEYS.profile, { ...profile, availableDays: [1, 2, 4] }, s);
  try {
    const before = await api.getUpcomingDays(now);
    assert.deepEqual(before.map(d => d.date), ['2026-11-16', '2026-11-17', '2026-11-19']);
    const titles = Object.fromEntries(before.map(d => [d.date, d.planned!.title]));
    await assert.rejects(api.applyArrangement([{ from: '2026-11-16', to: '2026-11-17' }], now), /Reken ze opnieuw door/);              // not a permutation
    await assert.rejects(api.applyArrangement([{ from: '2026-11-16', to: '2026-11-18' }, { from: '2026-11-18', to: '2026-11-16' }], now), /Reken ze opnieuw door/);   // not a planned day
    assert.deepEqual((await api.getUpcomingDays(now)).map(d => d.planned!.title), before.map(d => d.planned!.title));
    await api.applyArrangement([{ from: '2026-11-16', to: '2026-11-19' }, { from: '2026-11-19', to: '2026-11-16' }], now);
    const after = Object.fromEntries((await api.getUpcomingDays(now)).map(d => [d.date, d.planned!]));
    assert.equal(after['2026-11-19'].title, titles['2026-11-16']); assert.equal(after['2026-11-16'].title, titles['2026-11-19']);
    assert.equal(after['2026-11-17'].title, titles['2026-11-17']); assert.equal(after['2026-11-19'].date, '2026-11-19');
  } finally { selectStorage(); }
});

test('the planner card shows the suggestion with its uncertainty and basis, and applies it only on request', async () => {
  const React = (await import('react')).default; const { act } = await import('react');
  const { JSDOM } = await import('jsdom');
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test/concurrent-training/', pretendToBeVisual: true });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
  const { createRoot } = await import('react-dom/client');
  const { default: WeekPlanner } = await import('../src/components/WeekPlanner.tsx');
  const s = storage(); selectStorage(s); writeJson(KEYS.profile, { ...profile, availableDays: [0, 1, 2, 3, 4, 5, 6] }, s);
  const upcoming = await api.getUpcomingDays();
  const [first, second] = upcoming.map(d => d.date);
  const order: [string, string][] = upcoming.map((d, i) => [d.date, i === 0 ? second : i === 1 ? first : d.date]);
  const originalFetch = globalThis.fetch; let calls = 0;
  globalThis.fetch = (async () => { calls++; return new Response(JSON.stringify(planReply(order)), { status: 200 }); }) as typeof fetch;
  configureEngineAuth(async () => 'user-token');
  const host = document.getElementById('root')!; const root = createRoot(host); let changed = 0;
  const settle = async () => { for (let i = 0; i < 5; i++) await act(async () => { await new Promise(r => setTimeout(r, 5)); }); };
  const press = async (text: RegExp) => { const b = [...host.querySelectorAll('button')].find(x => text.test(x.textContent ?? '')); assert.ok(b, String(text)); await act(async () => { b.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })); }); await settle(); };
  try {
    await act(async () => { root.render(<WeekPlanner onChanged={() => { changed++; }} />); }); await settle();
    assert.equal(calls, 0);                                                    // nothing is sent before the user asks
    await press(/^Volgorde doorrekenen$/);
    const text = host.textContent!;
    assert.match(text, /Voorgestelde volgorde/); assert.match(text, /verwacht effect van eerdere trainingen −0,8 % \(onzekerheid −2,6 % tot \+1,1 %\)/);
    assert.match(text, /voorlopige modelaannames, geïnspireerd op groepsonderzoek, niet op jouw metingen/); assert.match(text, /niet op echte atleten gevalideerd/);
    assert.match(text, /nu gepland op/); assert.equal(changed, 0);
    const titleBefore = upcoming[0].planned!.title;
    await press(/^Deze volgorde overnemen$/);
    assert.equal(changed, 1); assert.match(host.textContent!, /De volgorde is overgenomen/);
    assert.equal((await api.getUpcomingDays()).find(d => d.date === second)!.planned!.title, titleBefore);
    await act(async () => { root.unmount(); });
  } finally { configureEngineAuth(null); globalThis.fetch = originalFetch; selectStorage(); dom.window.close(); }
});

test('critical power text explains a missing or doubtful fit in plain words', () => {
  const base = response();
  const none = { ...base, endurance: { ...base.endurance, cp_model: { status: 'insufficient_data' as const, reasons: ['need_three_maximal_efforts_2_to_20_min'], warnings: [], efforts_used: 2 } } };
  assert.match(effortLine(none)!, /minstens drie maximale inspanningen van verschillende duur/);
  const doubtful = { ...base, endurance: { ...base.endurance, cp_model: { status: 'ok' as const, reasons: [], warnings: ['no_effort_of_10_min_or_longer_cp_may_be_overestimated', 'only_three_efforts_one_degree_of_freedom'], efforts_used: 3, cp_w: 280, w_prime_j: 20000, se_cp_w: 3, se_w_prime_j: 900 } } };
  assert.match(effortLine(doubtful)!, /waarschijnlijk overschat; met drie inspanningen is de foutmarge zelf onzeker/);
  assert.equal(effortLine(base), null);
});

test('the planner request the webapp sends is exactly the frozen fixture that the Python test posts', async () => {
  const { readFileSync } = await import('node:fs');
  const { clientSessions, clientProfile, clientPlans } = await import('./engine-fixture.ts');
  let sent: unknown = null;
  const fetcher = (async (_u: string, init: RequestInit) => { sent = JSON.parse(init.body as string); return new Response(JSON.stringify(planReply([['2026-11-11', '2026-11-11']])), { status: 200 }); }) as unknown as typeof fetch;
  configureEngineAuth(async () => 'user-token');
  try {
    const items = clientPlans.map((p, i) => planItem(p, i === 0)!);
    await planWeek(clientSessions, clientProfile, '2026-11-10', items, items.map(i => i.label), 18, { fetcher, base: '' });
  } finally { configureEngineAuth(null); }
  assert.deepEqual(sent, { ...JSON.parse(readFileSync(new URL('./fixtures/contracts/client_plan_request_v1.json', import.meta.url), 'utf8')), timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone });
});
