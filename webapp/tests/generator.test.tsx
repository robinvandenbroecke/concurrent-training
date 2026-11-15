import test from 'node:test';
import assert from 'node:assert/strict';
import { EXERCISES, alternatives, available, definition } from '../src/data/exercises.ts';
import { EQUIPMENT_PRESETS, FULL_GYM, cycleWeek, defaultProgram, generateStrength, progressionHint, weekRule, weeklyShortfall } from '../src/domain/generator.ts';
import { estimatedMinutes, countPlan } from '../src/domain/volume.ts';
import { strengthSlots } from '../src/domain/program.ts';
import { buildWeek } from '../src/api/local.ts';
import { validatePlan } from '../src/domain/editing.ts';
import type { AthleteProfile, EquipmentTag, ExperienceLevel, ProgramGoal, ProgramSettings, WorkoutSession } from '../src/types.ts';

const START = '2026-11-02';
const settings = (patch: Partial<ProgramSettings> = {}): ProgramSettings => ({ goal: 'algemeen', experience: 'gevorderd', equipment: FULL_GYM, returning: false, lighterWeek: false, cycleStart: START, ...patch });
const athlete = (patch: Partial<AthleteProfile> = {}, program: Partial<ProgramSettings> = {}): AthleteProfile => ({ name: 'Test', priority: 'kracht', experienceYears: 3, availableDays: [1, 3, 5],
  sessionDurationMinutes: 75, hasVbt: false, hasStravaSync: false, capacities: { squat: 100, bench: 70, deadlift: 130 }, onboardingComplete: true, program: settings(program), ...patch });
const GOALS: ProgramGoal[] = ['algemeen', 'powerlifting', 'hypertrofie', 'power', 'concurrent'];
const LEVELS: ExperienceLevel[] = ['beginner', 'gevorderd', 'ervaren'];
const ids = (p: AthleteProfile, ordinal = 0, date = START) => generateStrength(p, date, ordinal).plan.exercises!.map(e => e.exerciseId!);
const logged = (date: string, exerciseId: string, weight: number, reps: number, target: number, rpe: number): WorkoutSession => ({ id: `${date}-${exerciseId}`, date, type: 'kracht',
  exercises: [{ id: 'x', exerciseId, lift: EXERCISES.find(d => d.id === exerciseId)!.lift, displayName: exerciseId, sets: [1, 2].map(n => ({ setNum: n, weight, targetReps: target, completedReps: reps, velocities: [], rpe })) }] } as unknown as WorkoutSession);

test('every goal, level, equipment preset, day count and duration gives a valid plan with only possible exercises', () => {
  let plans = 0;
  for (const goal of GOALS) for (const experience of LEVELS) for (const [key, preset] of Object.entries(EQUIPMENT_PRESETS)) for (const days of [[1], [1, 4], [1, 3, 5], [1, 2, 4, 5], [1, 2, 3, 4, 5, 6]])
    for (const minutes of [30, 45, 60, 90]) for (const olympicExperience of [false, true]) {
      const p = athlete({ availableDays: days, sessionDurationMinutes: minutes, olympicExperience }, { goal, experience, equipment: preset.tags });
      for (let ordinal = 0; ordinal < Math.max(1, strengthSlots(p)); ordinal++) {
        const g = generateStrength(p, START, ordinal); plans++;
        const label = `${goal}/${experience}/${key}/${days.length}d/${minutes}min`;
        if (g.plan.exercises!.length) validatePlan(g.plan);
        for (const e of g.plan.exercises!) {
          const d = definition(e)!;
          assert.ok(available(d, preset.tags), `${label}: ${d.id} needs equipment that is not there`);
          assert.ok(olympicExperience || d.technique <= 2, `${label}: ${d.id} needs technique experience`);
          assert.ok(olympicExperience || !d.catch, `${label}: catch variant ${d.id} without experience`);
          assert.ok(e.sets.length >= 1 && e.sets.length <= 6, `${label}: ${d.id} has ${e.sets.length} sets`);
          for (const s of e.sets) { assert.ok(s.targetReps >= 1 && s.targetReps <= 20); assert.ok((s.targetRpe ?? 0) >= 5 && (s.targetRpe ?? 0) <= 9); assert.ok((s.restSec ?? 0) >= 60); }
        }
        assert.equal(new Set(g.plan.exercises!.map(e => e.exerciseId)).size, g.plan.exercises!.length, `${label}: duplicate exercise`);
        assert.ok(g.plan.reason && g.plan.reason.length > 20);
      }
    }
  assert.ok(plans > 2000);
});

test('the plan fits the session time or says exactly what was shortened', () => {
  for (const goal of GOALS) for (const minutes of [30, 45, 60, 75, 90]) for (let ordinal = 0; ordinal < 3; ordinal++) {
    const g = generateStrength(athlete({ sessionDurationMinutes: minutes }, { goal }), START, ordinal);
    const fits = estimatedMinutes(g.plan) <= minutes;
    // What cannot be shortened further: main lifts with two sets each and their rest periods.
    assert.ok(fits || g.plan.exercises!.every(e => e.sets.length <= 2), `${goal} ${minutes} min: ${estimatedMinutes(g.plan)} min without reaching the floor`);
    if (g.removed.length) { assert.match(g.plan.reason!, /Ingekort om binnen/); for (const name of g.removed) assert.ok(g.plan.reason!.includes(name)); }
  }
  const long = generateStrength(athlete({ sessionDurationMinutes: 120 }), START, 0), short = generateStrength(athlete({ sessionDurationMinutes: 30 }), START, 0);
  assert.deepEqual(long.removed, []); assert.ok(short.removed.length > 0);
  assert.ok(short.plan.exercises!.length < long.plan.exercises!.length);
  // Rest periods are never shortened to save time.
  const rest = (g: typeof long) => Object.fromEntries(g.plan.exercises!.map(e => [e.exerciseId, e.sets[0].restSec]));
  for (const [id, sec] of Object.entries(rest(short))) assert.equal(sec, rest(long)[id]);
});

test('missing equipment leads to another exercise of the same movement or an explicit gap', () => {
  const home = ids(athlete({}, { equipment: EQUIPMENT_PRESETS.dumbbells.tags }));
  assert.ok(!home.includes('back_squat') && !home.includes('bench_press'));
  assert.ok(home.includes('goblet_squat'));
  assert.ok(home.some(id => EXERCISES.find(d => d.id === id)!.pattern === 'push_h') && home.some(id => EXERCISES.find(d => d.id === id)!.pattern === 'pull_h'));
  const none = generateStrength(athlete({}, { equipment: [] }), START, 0);
  assert.ok(none.plan.exercises!.length >= 3);
  assert.ok(none.plan.exercises!.every(e => definition(e)!.load === 'bodyweight' || definition(e)!.needs.some(n => n.length === 0)));
  // Without a bar there is no horizontal pull possible: reported, not silently skipped.
  assert.ok(none.unfilled.includes('pull_h')); assert.match(none.plan.reason!, /geen passende oefening beschikbaar/);
  const machines = ids(athlete({}, { equipment: EQUIPMENT_PRESETS.machines.tags }));
  assert.ok(machines.includes('leg_press') && machines.includes('machine_chest_press'));
});

test('alternatives stay within movement pattern, equipment and technique level', () => {
  const alt = alternatives('back_squat', EQUIPMENT_PRESETS.dumbbells.tags);
  assert.ok(alt.length > 0 && alt.every(d => d.pattern === 'squat' && available(d, EQUIPMENT_PRESETS.dumbbells.tags)));
  assert.ok(alternatives('clean_pull', FULL_GYM, 2).every(d => d.technique <= 2 && d.power));
  assert.ok(alternatives('power_clean', FULL_GYM, 3).some(d => d.catch));
  assert.deepEqual(alternatives('bestaat_niet', FULL_GYM), []);
});

test('catch variants need confirmed technique experience; pulls and jumps do not', () => {
  const novice = ids(athlete({}, { goal: 'power' })), expert = ids(athlete({ olympicExperience: true }, { goal: 'power' }));
  assert.ok(novice.every(id => !EXERCISES.find(d => d.id === id)!.catch));
  assert.ok(novice.some(id => EXERCISES.find(d => d.id === id)!.power));
  assert.ok(expert.some(id => EXERCISES.find(d => d.id === id)!.catch));
});

test('goals differ where the evidence says they should', () => {
  const plan = (goal: ProgramGoal, ordinal = 0) => generateStrength(athlete({ sessionDurationMinutes: 90 }, { goal }), START, ordinal).plan.exercises!;
  const main = (goal: ProgramGoal) => plan(goal).find(e => e.exerciseId === 'back_squat')!;
  // Maximal strength: heavy and few repetitions, the competition lift before all supporting work.
  assert.ok(main('powerlifting').sets[0].targetReps <= 5 && main('powerlifting').sets.length >= 3);
  const pl = plan('powerlifting'), firstHeavy = pl.findIndex(e => !definition(e)!.power);
  assert.equal(pl[firstHeavy].exerciseId, 'back_squat');
  // Explosive work always comes first.
  for (const goal of ['algemeen', 'powerlifting', 'power', 'concurrent'] as ProgramGoal[]) { const p = plan(goal), last = p.map(e => !!definition(e)!.power).lastIndexOf(true); assert.ok(p.slice(0, last + 1).every(e => definition(e)!.power), goal); }
  // Muscle growth: no explosive block, more sets and more repetitions.
  assert.ok(plan('hypertrofie').every(e => !definition(e)!.power));
  assert.ok(main('hypertrofie').sets[0].targetReps > main('powerlifting').sets[0].targetReps);
  const sets = (goal: ProgramGoal) => plan(goal).filter(e => !definition(e)!.power).reduce((n, e) => n + e.sets.length, 0);
  assert.ok(sets('hypertrofie') > sets('powerlifting'));
  // Power: two explosive exercises, low repetitions, far from failure.
  const explosive = plan('power').filter(e => definition(e)!.power);
  assert.equal(explosive.length, 2); assert.ok(explosive.every(e => e.sets.every(s => s.targetReps <= 5 && (s.targetRpe ?? 0) <= 6.5)));
  // Beside endurance sport: main leg lifts stay, lower-body accessory work goes.
  const lower = (goal: ProgramGoal) => [0, 1, 2].flatMap(o => plan(goal, o)).filter(e => ['squat', 'hinge', 'single_leg'].includes(definition(e)!.pattern)).length;
  assert.ok(lower('concurrent') < lower('algemeen'));
  assert.ok([0, 1, 2].flatMap(o => plan('concurrent', o)).some(e => e.exerciseId === 'back_squat'));
  assert.match(generateStrength(athlete({}, { goal: 'concurrent' }), START, 0).plan.reason!, /Naast duursport/);
});

test('experience changes sets on main lifts and caps effort for beginners', () => {
  const squat = (experience: ExperienceLevel) => generateStrength(athlete({ sessionDurationMinutes: 120 }, { experience }), START, 0).plan.exercises!.find(e => e.exerciseId === 'back_squat')!;
  assert.ok(squat('beginner').sets.length < squat('ervaren').sets.length);
  assert.ok(squat('beginner').sets.length >= 2);
  const all = generateStrength(athlete({ sessionDurationMinutes: 120 }, { experience: 'beginner', goal: 'hypertrofie' }), START, 0).plan.exercises!;
  assert.ok(all.every(e => e.sets.every(s => (s.targetRpe ?? 0) <= 8)));
});

test('a weight comes only from the same exercise or the entered working weight, never from another lift', () => {
  const fresh = generateStrength(athlete({}, { goal: 'powerlifting' }), START, 0).plan.exercises!;
  assert.equal(fresh.find(e => e.exerciseId === 'back_squat')!.sets[0].weight, 100);
  for (const e of fresh) if (!['back_squat', 'bench_press', 'deadlift', 'overhead_press', 'power_clean', 'clean'].includes(e.exerciseId!)) assert.ok(e.sets.every(s => s.weight === 0), e.exerciseId);
  // Eight repetitions is not the entered five-repetition weight: left empty.
  const growth = generateStrength(athlete({}, { goal: 'hypertrofie' }), START, 0).plan.exercises!.find(e => e.exerciseId === 'back_squat')!;
  assert.ok(growth.sets[0].targetReps > 6 && growth.sets.every(s => s.weight === 0));
  // A logged front squat does not set the back squat; a logged back squat does.
  const history = [logged('2026-10-28', 'front_squat', 80, 5, 5, 7), logged('2026-10-29', 'back_squat', 112.5, 4, 4, 7)];
  const next = generateStrength(athlete({}, { goal: 'powerlifting' }), START, 0, history).plan.exercises!;
  assert.ok(next.find(e => e.exerciseId === 'back_squat')!.sets.every(s => s.weight === 112.5));
  // Sessions dated after the plan are ignored.
  const future = generateStrength(athlete({}, { goal: 'powerlifting' }), START, 0, [logged('2026-11-20', 'back_squat', 140, 4, 4, 7)]).plan.exercises!;
  assert.equal(future.find(e => e.exerciseId === 'back_squat')!.sets[0].weight, 100);
});

test('progression is a suggestion after two full sessions and never an automatic jump', () => {
  const two = [logged('2026-10-20', 'back_squat', 100, 4, 4, 7.5), logged('2026-10-27', 'back_squat', 100, 4, 4, 8)];
  assert.match(progressionHint(two, 'back_squat', START)!, /kleinste gewichtsprong overwegen/);
  assert.equal(progressionHint(two.slice(1), 'back_squat', START), undefined);
  assert.equal(progressionHint([two[0], logged('2026-10-27', 'back_squat', 100, 4, 4, 9)], 'back_squat', START), undefined);
  assert.match(progressionHint([two[0], logged('2026-10-27', 'back_squat', 100, 3, 4, 9)], 'back_squat', START)!, /gelijk of verlaag/);
  // No RPE logged: missing stays missing, no advice to add load.
  const blank = [0, 1].map(i => { const s = logged(`2026-10-2${i}`, 'back_squat', 100, 4, 4, 7); for (const set of s.exercises![0].sets) delete (set as { rpe?: number }).rpe; return s; });
  assert.equal(progressionHint(blank, 'back_squat', START), undefined);
  const plan = generateStrength(athlete({}, { goal: 'powerlifting' }), START, 0, two).plan.exercises!.find(e => e.exerciseId === 'back_squat')!;
  assert.ok(plan.sets.every(s => s.weight === 100)); assert.match(plan.sets[0].note!, /overwegen/);
});

test('missed sessions never add catch-up volume', () => {
  const p = athlete();
  const base = generateStrength(p, '2026-11-16', 0), afterGap = generateStrength(p, '2026-11-16', 0, [logged('2026-09-01', 'back_squat', 100, 4, 4, 7)]);
  const total = (g: typeof base) => g.plan.exercises!.reduce((n, e) => n + e.sets.length, 0);
  assert.equal(total(afterGap), total(base));
  assert.deepEqual(afterGap.plan.exercises!.map(e => e.exerciseId), base.plan.exercises!.map(e => e.exerciseId));
});

test('week rule: constant by default, optional lighter fourth week, two-week restart', () => {
  const s = settings();
  assert.equal(cycleWeek(s, START), 0); assert.equal(cycleWeek(s, '2026-11-08'), 0); assert.equal(cycleWeek(s, '2026-11-09'), 1); assert.equal(cycleWeek(s, '2026-10-01'), 0);
  assert.equal(cycleWeek({ ...s, cycleStart: 'geen datum' }, START), 0);
  for (let w = 0; w < 8; w++) assert.equal(weekRule(s, w).setFactor, 1);
  assert.equal(weekRule({ ...s, lighterWeek: true }, 3).setFactor, 0.6); assert.equal(weekRule({ ...s, lighterWeek: true }, 7).setFactor, 0.6); assert.equal(weekRule({ ...s, lighterWeek: true }, 2).setFactor, 1);
  const sets = (p: AthleteProfile, date: string) => generateStrength(p, date, 0).plan.exercises!.reduce((n, e) => n + e.sets.length, 0);
  const rpe = (p: AthleteProfile, date: string) => generateStrength(p, date, 0).plan.exercises!.find(e => e.exerciseId === 'back_squat')!.sets[0].targetRpe!;
  const normal = athlete({ sessionDurationMinutes: 120 }), light = athlete({ sessionDurationMinutes: 120 }, { lighterWeek: true }), back = athlete({ sessionDurationMinutes: 120 }, { returning: true });
  assert.equal(sets(normal, '2026-11-23'), sets(normal, START));
  assert.ok(sets(light, '2026-11-23') < sets(light, START)); assert.ok(rpe(light, '2026-11-23') < rpe(light, START));
  assert.ok(sets(back, START) < sets(normal, START)); assert.ok(rpe(back, START) < rpe(normal, START));
  assert.equal(sets(back, '2026-11-16'), sets(normal, '2026-11-16'));
  assert.match(generateStrength(back, START, 0).plan.reason!, /Herstart/);
});

test('muscle growth: spare time goes to sets, at most four per exercise, and a weekly shortfall is named', () => {
  const roomy = athlete({ sessionDurationMinutes: 75 }, { goal: 'hypertrofie' });
  const slots = strengthSlots(roomy); assert.ok(slots >= 2);
  for (let o = 0; o < slots; o++) { const g = generateStrength(roomy, START, o); assert.ok(g.plan.exercises!.every(e => e.sets.length <= 4)); assert.ok(estimatedMinutes(g.plan) <= 75); }
  assert.deepEqual(weeklyShortfall(roomy), []);
  const tight = athlete({ availableDays: [1], sessionDurationMinutes: 30 }, { goal: 'hypertrofie' });
  assert.ok(weeklyShortfall(tight).length > 0);
  assert.match(generateStrength(tight, START, 0).plan.reason!, /onder ongeveer tien sets/);
  assert.deepEqual(weeklyShortfall({ ...roomy, program: undefined }), []);
  const week = Array.from({ length: slots }, (_, o) => o).map(o => countPlan(generateStrength(roomy, START, o).plan).muscles);
  for (const m of ['quadriceps', 'posterior', 'chest', 'back', 'shoulders'] as const) assert.ok(week.reduce((n, c) => n + c[m], 0) >= 10, m);
});

test('accounts without programme settings keep the original schedule; with settings the week uses the generator', () => {
  const { program: _program, ...old } = athlete({ availableDays: [1, 4], sessionDurationMinutes: 60 });
  const before = buildWeek(old as AthleteProfile, new Date(2026, 10, 4));
  assert.ok(before.every(d => !d.planned?.title?.includes('sessie')));
  const withProgram = buildWeek(athlete({ availableDays: [1, 4], sessionDurationMinutes: 60 }), new Date(2026, 10, 4));
  const strength = withProgram.filter(d => d.planned?.type === 'kracht');
  assert.equal(strength.length, 2); assert.match(strength[0].planned!.title!, /sessie A/); assert.match(strength[1].planned!.title!, /sessie B/);
  // An endurance-first athlete with settings still gets one strength session when two days are available.
  assert.equal(strengthSlots(athlete({ priority: 'duur', availableDays: [1, 4] })), 1);
  // An athlete's own edit of a day wins over the generator.
  const edited = { ...strength[0].planned!, title: 'Eigen plan' };
  assert.equal(buildWeek(athlete({ availableDays: [1, 4] }), new Date(2026, 10, 4), [], { [strength[0].date]: edited }).find(d => d.date === strength[0].date)!.planned!.title, 'Eigen plan');
});

test('default settings follow the profile and never assume missing equipment or technique', () => {
  assert.equal(defaultProgram(athlete({ priority: 'duur' }), START).goal, 'concurrent');
  assert.equal(defaultProgram(athlete({ experienceYears: 0.5 }), START).experience, 'beginner');
  const d = defaultProgram(athlete(), START); assert.equal(d.returning, false); assert.equal(d.lighterWeek, false); assert.equal(d.cycleStart, START);
  const tags: EquipmentTag[] = ['dumbbells'];
  assert.ok(ids(athlete({}, { equipment: tags })).every(id => available(EXERCISES.find(e => e.id === id)!, tags)));
});

test('the settings card saves nothing until asked, then stores the programme and can revert to the original schedule', async () => {
  const React = (await import('react')).default; const { act } = await import('react');
  const { JSDOM } = await import('jsdom');
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test/concurrent-training/', pretendToBeVisual: true });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
  const { createRoot } = await import('react-dom/client');
  const { default: ProgramSettingsCard } = await import('../src/components/ProgramSettingsCard.tsx');
  const { selectStorage, writeJson, readProfile, KEYS } = await import('../src/api/local.ts');
  const data = new Map<string, string>();
  const store = { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => { data.set(k, v); }, removeItem: (k: string) => { data.delete(k); } };
  selectStorage(store);
  const { program: _program, ...plain } = athlete({ availableDays: [1, 4] });
  writeJson(KEYS.profile, plain, store);
  let saved: AthleteProfile | undefined;
  const host = document.getElementById('root')!; const root = createRoot(host);
  const click = async (label: RegExp) => { const b = [...host.querySelectorAll('button')].find(x => label.test(x.textContent ?? ''))!; await act(async () => { b.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })); await new Promise(r => setTimeout(r, 5)); }); };
  try {
    await act(async () => { root.render(<ProgramSettingsCard profile={plain as AthleteProfile} onSaved={p => { saved = p; }} />); });
    assert.match(host.textContent!, /Krachtprogramma instellen/); assert.match(host.textContent!, /geen persoonlijk gemeten grens/);
    assert.match(host.textContent!, /2 krachttrainingen per week van 75 minuten/);
    assert.match(host.textContent!, /Olympische varianten met opvang worden niet ingepland/);
    assert.equal(readProfile()!.program, undefined);
    const goal = host.querySelector('select[aria-label="Doel van het krachtprogramma"]') as HTMLSelectElement;
    await act(async () => { const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype, 'value')!.set!; setter.call(goal, 'hypertrofie'); goal.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
    assert.equal(readProfile()!.program, undefined);
    await click(/Programma bewaren/);
    assert.equal(readProfile()!.program!.goal, 'hypertrofie'); assert.equal(saved!.program!.goal, 'hypertrofie');
    assert.deepEqual(readProfile()!.capacities, plain.capacities);
    assert.match(host.textContent!, /Programma bewaard/);
    await act(async () => { root.render(<ProgramSettingsCard profile={saved!} onSaved={p => { saved = p; }} />); });
    await click(/Terug naar het oorspronkelijke startschema/);
    assert.equal(readProfile()!.program, undefined); assert.ok(!('program' in saved!));
  } finally { await act(async () => { root.unmount(); }); selectStorage(undefined); }
});
