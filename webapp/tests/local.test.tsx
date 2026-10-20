import test from 'node:test';
import assert from 'node:assert/strict';
import { appendSession, buildWeek, exportLocal, importLocal, KEYS, localDate, measuredTrend, parseVelocities, readDraft, readProfile, readSessions, writeJson } from '../src/api/local.ts';

function storage() {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => { data.set(k, v); }, removeItem: (k: string) => { data.delete(k); } };
}
const profile = { name: 'Test', priority: 'kracht' as const, experienceYears: 2, availableDays: [2, 4], sessionDurationMinutes: 30, hasVbt: false, hasStravaSync: false, capacities: { squat: 50, bench: 40 }, onboardingComplete: true };
const session = { id: 'test-session', date: '2026-10-20', type: 'kracht' as const, title: 'Training', durationMinutes: 20, savedToServer: false,
  exercises: [{ lift: 'squat' as const, displayName: 'Kniebuiging', sets: [{ setNum: 1, weight: 50, completedReps: 3, targetReps: 5, velocities: [null, null, null] }] }] };

test('no velocity measurements retain all performed repetitions', () => assert.deepEqual(parseVelocities('', 5), [null, null, null, null, null]));
test('partial velocity measurements retain their positions', () => assert.deepEqual(parseVelocities('0,5; -; 0.42', 3), [.5, null, .42]));
test('one average velocity is never copied to all repetitions', () => assert.throws(() => parseVelocities('.5', 5)));
test('invalid velocities and repetition counts are rejected', () => {
  for (const value of ['NaN', '-1', '0', 'Infinity', '4']) assert.throws(() => parseVelocities(value, 1));
  for (const value of [0, -1, 2.5, 101]) assert.throws(() => parseVelocities('', value));
});
test('profile can round trip and cleared capacity stays unknown', () => {
  const s = storage(); writeJson(KEYS.profile, profile, s); assert.deepEqual(readProfile(s), profile);
  assert.equal(readProfile(storage()), null);
});
test('week plan honors chosen days and session duration for every priority', () => {
  for (const priority of ['kracht', 'duur', 'balans'] as const) {
    const week = buildWeek({ ...profile, priority }, new Date(2026, 9, 20, 12));
    assert.equal(week.filter(d => d.planned).length, 2);
    assert.deepEqual(week.filter(d => d.planned).map(d => d.date), ['2026-10-20', '2026-10-22']);
    assert.ok(week.every(d => !d.planned || d.planned.durationMinutes <= 30));
  }
});
test('skipped sessions do not generate catch-up volume', () => {
  const week = buildWeek(profile, new Date(2026, 9, 20, 12), [], { '2026-10-20': null });
  assert.equal(week.filter(d => d.planned).length, 1);
});
test('week completion derives from actual locally logged sessions', () => {
  const week = buildWeek(profile, new Date(2026, 9, 20, 12), [session]);
  assert.equal(week.filter(d => d.completed).length, 1);
});
test('saving twice with the same session ID is idempotent', () => {
  const s = storage(); appendSession(session, s); appendSession(session, s);
  assert.equal(readSessions(s).length, 1); assert.deepEqual(readSessions(s)[0].exercises, session.exercises);
});
test('storage failure propagates instead of reporting successful save', () => {
  const s = { ...storage(), setItem: () => { throw new Error('full'); } };
  assert.throws(() => appendSession(session, s), /Opslaan op dit toestel lukt niet/);
});
test('export and import preserve measured data and skip duplicates', () => {
  const a = storage(), b = storage(); appendSession(session, a);
  const exported = exportLocal(a); exported.sessions.push({ ...session });
  const text = JSON.stringify(exported); importLocal(text, b); importLocal(text, b);
  assert.deepEqual(readSessions(b), readSessions(a));
});
test('invalid imported measurements do not overwrite saved data', () => {
  const s = storage(); appendSession(session, s);
  const bad = { ...session, id: 'bad', exercises: [{ ...session.exercises[0], sets: [{ ...session.exercises[0].sets[0], velocities: [.5] }] }] };
  assert.throws(() => importLocal(JSON.stringify({ format: 'concurrent-training-local', version: 1, sessions: [bad] }), s));
  assert.equal(readSessions(s).length, 1);
});
test('workout draft round trips across a reload', () => {
  const s = storage(); const draft = { plan: buildWeek(profile, new Date(2026, 9, 20, 12))[1].planned!, phase: 'active', startTime: '2026-10-20T12:00:00Z', completed: { 0: session.exercises[0].sets }, exerciseIndex: 0 };
  writeJson(KEYS.draft, draft, s); assert.deepEqual(readDraft(s), draft);
});
test('trends are measured work weights, with no invented history', () => {
  assert.deepEqual(measuredTrend([], 'squat'), []);
  assert.deepEqual(measuredTrend([session], 'squat'), [{ date: '2026-10-20', value: 50, isEstimate: false }]);
});
test('local date retains the calendar day', () => assert.equal(localDate(new Date(2026, 9, 20, 0, 5)), '2026-10-20'));
