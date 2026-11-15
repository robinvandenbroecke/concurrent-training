/**
 * Client for the stateless calculation engine (contract version 1).
 *
 * The request is built from the user's own stored sessions; the response is a
 * versioned, reproducible summary. Authentication is the user's own session
 * token. When the engine cannot be reached the app says so and shows nothing
 * calculated: there is no local imitation of the model.
 */
import type { AthleteProfile, LiftType, PlannedTraining, WorkoutSession } from '../types';
import { definition } from '../data/exercises';
import { getLocalStore, readJson, type StorageLike } from '../api/local';

export const CONTRACT_VERSION = '1';
const CACHE_KEY = 'ct_engine_cache_v1';
const RENDER_ORIGIN = 'https://concurrent-training.onrender.com';

export type Status = 'ok' | 'insufficient_data' | 'rejected' | 'not_applicable';
export interface EngineVelocityGroup {
  metric: string; device: string; sessions_with_velocity: number; warnings: string[];
  profile: { status: Status; reasons: string[]; points: number; distinct_loads: number; load_range_kg?: [number, number]; intercept_ms?: number; slope_ms_per_kg?: number; r2?: number; residual_sd_ms?: number };
  latest_deviation: { status: Status; reason?: string; date?: string; points?: number; deviation_pct?: number; z?: number; interpretation?: 'within_noise' | 'slower' | 'faster'; calibration_points?: number };
  forecast_check: { status: Status; reason?: string; test_sessions?: number; models?: { model: string; mae_log: number }[]; best?: string; dynamic_model_beats_simple_baselines?: boolean };
}
export interface EngineStrength {
  exercise: string; sessions: number; last_date: string;
  history: { date: string; top_work_weight_kg: number; reps: number }[];
  e1rm_estimate: { status: Status; reason?: string; value_kg?: number; low_kg?: number; high_kg?: number; basis?: { date: string; weight_kg: number; reps: number; rpe: number } };
  velocity: EngineVelocityGroup[];
  last_session_velocity_loss: { set: number; velocity_loss: number | null; measured_reps: number; reps: number }[];
}
export interface FatigueEffect { own_fatigue_pct: number; cross_fatigue_pct: number; total_pct: number; low_pct: number; high_pct: number }
export interface ModelDomain {
  status: 'ok' | 'prior_only'; observations: number; basis: 'group_level_priors_only' | 'priors_updated_with_own_data';
  verdict?: 'interaction_shown_in_own_data' | 'own_dynamics_shown_in_own_data' | 'not_enough_tests' | 'not_shown_in_own_data';
  beats_last_observation?: boolean;
}
export interface ConcurrentModel {
  model_version: string; strength: ModelDomain; endurance: ModelDomain;
  data: { sessions: number; sessions_without_start_time: number; same_day_pairs_with_unknown_gap: number; strength_sets_region_unknown: number };
  expected_fatigue_effect: { at: string; strength_lower: FatigueEffect; strength_upper: FatigueEffect; endurance: FatigueEffect }[];
  limitations: string[];
}
export interface EngineWindow { strength_work_sets: number; strength_tonnage_kg: number; endurance_minutes: number; endurance_load: number | null; endurance_load_method: string | null }
export interface EngineResponse {
  contract_version: string; engine_version: string; as_of_date: string; input_digest: string;
  sessions_used: number; sessions_after_as_of_ignored: number;
  strength: EngineStrength[];
  endurance: {
    cp_model: { status: Status; reasons: string[]; warnings: string[]; efforts_used: number; cp_w?: number; w_prime_j?: number; se_cp_w?: number; se_w_prime_j?: number; r2?: number };
    reference: { source: 'cp_fit_from_maximal_efforts' | 'user_entered_cp' | 'user_entered_threshold_not_cp' | 'none'; power_w: number | null; w_prime_j: number | null };
  };
  load: { daily: unknown[]; last_7_days: EngineWindow; previous_28_days: EngineWindow; previous_28_days_covered: boolean; note: string };
  concurrent: { date: string; code: string; gap_hours: number | null; order: string | null; explosive_work: boolean; evidence: string }[];
  concurrent_model?: ConcurrentModel;
  limitations: string[];
}
export type EngineOutcome =
  | { state: 'ok'; response: EngineResponse; fetchedAt: string; fromCache: boolean }
  | { state: 'unavailable'; reason: 'signed_out' | 'offline' | 'not_configured' | 'session_expired' | 'busy' | 'version_mismatch' | 'invalid_request' | 'error'; cached?: { response: EngineResponse; fetchedAt: string } };

const LOWER = new Set(['quadriceps', 'posterior']);
export function region(ex: { exerciseId?: string; lift: LiftType }): 'lower' | 'upper' | 'full' | 'unknown' {
  const d = definition(ex);
  if (!d) return 'unknown';
  const lower = d.primary.some(m => LOWER.has(m)), upper = d.primary.some(m => !LOWER.has(m));
  return lower && upper ? 'full' : lower ? 'lower' : upper ? 'upper' : 'unknown';
}

/** Data minimisation: titles, notes and names are not sent. Measurements are sent unchanged. */
export function buildEngineRequest(sessions: WorkoutSession[], profile: AthleteProfile | null, asOfDate: string) {
  return {
    contractVersion: CONTRACT_VERSION, asOfDate, timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    // The profile holds one self-entered threshold power; it is sent as such, never as critical power.
    endurance: { thresholdPowerW: profile?.enduranceThreshold && profile.enduranceThreshold > 0 ? profile.enduranceThreshold : undefined,
      maximalEfforts: (profile?.maximalEfforts ?? []).slice(-20).map(e => ({ date: e.date, durationSeconds: e.durationSeconds, powerW: e.powerW })) },
    sessions: sessions.map(s => ({
      id: String(s.id), date: s.date, type: s.type, durationMinutes: s.durationMinutes, startTime: s.startTime,
      exercises: (s.exercises ?? []).map(ex => {
        const d = definition(ex);
        return { exerciseId: ex.exerciseId ?? d?.id, lift: ex.lift, power: !!d?.power, loadType: d?.load ?? 'weight', region: region(ex),
          sets: ex.sets.map(set => ({ setNum: set.setNum, weight: set.weight, completedReps: set.completedReps, velocities: set.velocities,
            rpe: set.rpe, kind: set.kind ?? 'work', velocityMeta: set.velocityMeta ? { metric: set.velocityMeta.metric, deviceId: set.velocityMeta.deviceId, source: set.velocityMeta.source } : undefined })) };
      }),
      enduranceResult: s.enduranceResult ? { sport: s.enduranceResult.sport, durationMinutes: s.enduranceResult.durationMinutes,
        intensityType: s.enduranceResult.intensityType, rpe: s.enduranceResult.rpe, averagePowerW: s.enduranceResult.averagePowerW } : undefined,
    })),
  };
}

export function engineBase(location: { hostname: string } = typeof window === 'undefined' ? { hostname: '' } : window.location): string {
  const configured = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_ENGINE_URL;
  if (configured) return configured.replace(/\/$/, '');
  return location.hostname.endsWith('github.io') ? RENDER_ORIGIN : '';
}

type TokenSource = () => Promise<string | null>;
let tokenSource: TokenSource | null = null;
/** Set by the account gate. Without it the engine reports "signed_out" and nothing is sent. */
export function configureEngineAuth(source: TokenSource | null) { tokenSource = source; }
export async function accessToken(): Promise<string | null> { return tokenSource ? tokenSource() : null; }

async function fingerprint(text: string): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  return [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
}

interface Cached { key: string; response: EngineResponse; fetchedAt: string }

export async function evaluateEngine(sessions: WorkoutSession[], profile: AthleteProfile | null, asOfDate: string,
  options: CallOptions & { storage?: StorageLike; force?: boolean } = {}): Promise<EngineOutcome> {
  const storage = options.storage ?? getLocalStore();
  const body = JSON.stringify(buildEngineRequest(sessions, profile, asOfDate));
  const key = await fingerprint(body);
  const cached = readJson<Cached | null>(CACHE_KEY, null, storage);
  const usable = cached && cached.response?.contract_version === CONTRACT_VERSION ? cached : null;
  if (usable && usable.key === key && !options.force && Date.now() - Date.parse(usable.fetchedAt) >= 0 && Date.now() - Date.parse(usable.fetchedAt) < 15 * 60_000 && await accessToken()) return { state: 'ok', response: usable.response, fetchedAt: usable.fetchedAt, fromCache: true };
  // A cached result for OTHER input is offered only as explicitly outdated context.
  const stale = usable ? { response: usable.response, fetchedAt: usable.fetchedAt } : undefined;
  const result = await post<EngineResponse>('/v3/engine/evaluate', body, options);
  if (result.state === 'unavailable') return { state: 'unavailable', reason: result.reason, cached: stale };
  const data = result.data;
  if (data.contract_version !== CONTRACT_VERSION || typeof data.engine_version !== 'string' || !Array.isArray(data.strength)) return { state: 'unavailable', reason: 'version_mismatch', cached: stale };
  const fetchedAt = new Date().toISOString();
  try { storage.setItem(CACHE_KEY, JSON.stringify({ key, response: data, fetchedAt } satisfies Cached)); } catch { /* the cache is optional */ }
  return { state: 'ok', response: data, fetchedAt, fromCache: false };
}

type Unavailable = 'signed_out' | 'offline' | 'not_configured' | 'session_expired' | 'busy' | 'version_mismatch' | 'invalid_request' | 'error';
type PostResult<T> = { state: 'ok'; data: T } | { state: 'unavailable'; reason: Unavailable };
interface CallOptions { fetcher?: typeof fetch; base?: string; timeoutMs?: number }

async function post<T>(path: string, body: string, options: CallOptions): Promise<PostResult<T>> {
  const token = await accessToken();
  if (!token) return { state: 'unavailable', reason: 'signed_out' };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 75000);   // a sleeping free instance needs up to a minute
  try {
    const response = await (options.fetcher ?? fetch)(`${options.base ?? engineBase()}${path}`, {
      method: 'POST', body, signal: controller.signal, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } });
    const reason: Unavailable | null = response.status === 401 ? 'session_expired' : response.status === 409 ? 'version_mismatch' : response.status === 429 ? 'busy'
      : response.status === 503 ? 'not_configured' : response.status === 422 ? 'invalid_request' : response.ok ? null : 'error';
    if (reason) return { state: 'unavailable', reason };
    return { state: 'ok', data: await response.json() as T };
  } catch {
    return { state: 'unavailable', reason: 'offline' };
  } finally { clearTimeout(timer); }
}

// ── week planner ────────────────────────────────────────────────────────────

/** Declared intensity as a share of the reference power; the same assumed scale the engine uses for past sessions. */
const RELATIVE_INTENSITY: Record<string, number> = { easy: 0.6, z2: 0.65, long: 0.65, tempo: 0.85, threshold: 1.0, hiit: 1.1, other: 0.7 };
export interface PlanItem { label: string; kind: 'strength_lower' | 'strength_upper' | 'strength_full' | 'endurance' | 'endurance_swim'; workSets: number; minutes: number; relativeIntensity: number; key: boolean }
export interface PlanOptionSession { label: string; start: string; domain: 'strength' | 'endurance'; key: boolean; expected_fatigue_effect_pct: number; low_pct: number; high_pct: number; within_3h_of_endurance: boolean }
export interface PlanOption { score: number; sessions: PlanOptionSession[]; end_of_horizon: Record<string, { adaptation_change_pct: number; fatigue_pct: number }> }
export interface PlanResponse { model_version: string; method: 'exhaustive' | 'heuristic'; arrangements_evaluated: number; priority: string;
  basis: { strength: string; endurance: string }; difference_best_to_worst_pct: number | null; options: PlanOption[]; limitations: string[] }
export type PlanOutcome = { state: 'ok'; response: PlanResponse } | { state: 'unavailable'; reason: Unavailable };

/** A planned training as a relative dose. The label is the training's current date, so an answer can be mapped back. */
export function planItem(plan: PlannedTraining, key: boolean): PlanItem | null {
  if (plan.type === 'duur' && plan.endurance) {
    return { label: plan.date, kind: plan.endurance.sport === 'swimming' ? 'endurance_swim' : 'endurance', workSets: 0,
      minutes: plan.endurance.durationMinutes, relativeIntensity: RELATIVE_INTENSITY[plan.endurance.intensityType] ?? 0.7, key };
  }
  if (plan.type !== 'kracht') return null;
  let lower = 0, upper = 0;
  for (const ex of plan.exercises ?? []) {
    const sets = ex.sets.filter(set => (set.kind ?? 'work') === 'work').length, where = region(ex);
    if (where === 'lower') lower += sets; else if (where === 'upper') upper += sets; else { lower += sets / 2; upper += sets / 2; }
  }
  const total = Math.round(lower + upper);
  if (total < 1) return null;
  const kind = upper === 0 ? 'strength_lower' : lower === 0 ? 'strength_upper' : lower >= 2 * upper ? 'strength_lower' : upper >= 2 * lower ? 'strength_upper' : 'strength_full';
  // Sets for the dominant region carry the dose; a mixed session is sent as "full".
  return { label: plan.date, kind, workSets: Math.min(60, kind === 'strength_full' ? Math.round(Math.max(lower, upper)) : total), minutes: 0, relativeIntensity: 0.7, key };
}

export async function planWeek(sessions: WorkoutSession[], profile: AthleteProfile | null, asOfDate: string, items: PlanItem[], availableDates: string[],
  slotHour: number, options: CallOptions = {}): Promise<PlanOutcome> {
  const body = JSON.stringify({ ...buildEngineRequest(sessions, profile, asOfDate), planSessions: items, availableDates, slotHours: [slotHour], priority: profile?.priority ?? 'balans' });
  const result = await post<PlanResponse>('/v3/engine/plan', body, options);
  if (result.state === 'unavailable') return result;
  if (!Array.isArray(result.data.options) || !result.data.options.length) return { state: 'unavailable', reason: 'version_mismatch' };
  return { state: 'ok', response: result.data };
}
