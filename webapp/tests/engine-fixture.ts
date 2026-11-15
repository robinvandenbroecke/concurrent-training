/** Sessions as the webapp stores them; the request built from them is frozen in fixtures/contracts/client_request_v1.json. */
import type { AthleteProfile, WorkoutSession } from '../src/types.ts';

export const clientProfile: AthleteProfile = { name: 'Fixture', priority: 'balans', experienceYears: 3, availableDays: [1, 3], sessionDurationMinutes: 60,
  hasVbt: true, hasStravaSync: false, capacities: {}, enduranceThreshold: 250, onboardingComplete: true };
const meta = { metric: 'mean_concentric' as const, deviceId: 'encoder-1', source: 'manual' as const };
export const clientSessions: WorkoutSession[] = [
  { id: 'd1', date: '2026-11-10', type: 'duur', title: 'Duur — cycling', durationMinutes: 60, savedToServer: true, startTime: '2026-11-10T16:00:00.000Z',
    enduranceResult: { sport: 'cycling', durationMinutes: 60, intensityType: 'tempo', rpe: 6, averagePowerW: 210 } },
  { id: 'k1', date: '2026-11-10', type: 'kracht', title: 'Kracht A', durationMinutes: 55, savedToServer: true, startTime: '2026-11-10T17:30:00.000Z',
    exercises: [
      { exerciseId: 'power_clean', lift: 'power_clean', sets: [{ setNum: 1, weight: 60, targetReps: 2, completedReps: 2, velocities: [1.42, null], velocityMeta: meta }] },
      { exerciseId: 'back_squat', lift: 'squat', sets: [
        { setNum: 1, weight: 60, targetReps: 3, completedReps: 3, velocities: [0.82, 0.8, 0.79], kind: 'warmup', velocityMeta: meta },
        { setNum: 2, weight: 100, targetReps: 4, completedReps: 4, velocities: [0.52, 0.5, null, 0.44], rpe: 8, note: 'laatste zwaar', velocityMeta: meta }] },
      { exerciseId: 'bench_press', lift: 'bench', sets: [{ setNum: 1, weight: 70, targetReps: 4, completedReps: 4, velocities: [null, null, null, null], rpe: 7.5 }] }] },
  { id: 'old', date: '2026-11-07', type: 'duur', title: 'Duur — running', durationMinutes: 40, savedToServer: true,
    enduranceResult: { sport: 'running', durationMinutes: 40, intensityType: 'z2' } },
];

import type { PlannedTraining } from '../src/types.ts';
const set = (n: number, kind: 'work' | 'warmup' = 'work') => ({ setNum: n, weight: 50, targetReps: 5, restSec: 120, kind });
export const clientPlans: PlannedTraining[] = [
  { date: '2026-11-11', type: 'kracht', title: 'Benen', durationMinutes: 60, exercises: [
    { id: 'a', exerciseId: 'back_squat', lift: 'squat', displayName: 'Back squat', sets: [set(1, 'warmup'), set(2), set(3), set(4)] },
    { id: 'b', exerciseId: 'deadlift', lift: 'deadlift', displayName: 'Deadlift', sets: [set(1), set(2)] }] },
  { date: '2026-11-12', type: 'duur', title: 'Intervallen', durationMinutes: 50, endurance: { sport: 'cycling', durationMinutes: 50, intensityType: 'hiit', description: '' } },
  { date: '2026-11-14', type: 'kracht', title: 'Bovenlichaam', durationMinutes: 45, exercises: [
    { id: 'a', exerciseId: 'bench_press', lift: 'bench', displayName: 'Bankdrukken', sets: [set(1), set(2), set(3), set(4)] }] },
];
