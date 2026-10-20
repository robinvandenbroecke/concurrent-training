/**
 * Data adapter – demo mode vs backend mode.
 * Alle backend-aanroepen via dit bestand; nooit direct uit de UI.
 */
import type {
  AthleteProfile, ReadinessData, PlannedTraining, WorkoutSession, WeekDay, TrendPoint,
  LiftType, EnduranceSport, IntensityType, CompletedExercise
} from '../types';
import {
  DEMO_READINESS, DEMO_TODAY, DEMO_WEEK_DAYS, getDemoHistory, getDemoTrend, DEMO_PROFILE
} from '../data/demoData';
import { KEYS, readJson, writeJson, readProfile, readSessions, appendSession, buildWeek, measuredTrend, localDate } from './local';

export interface ApiConfig {
  mode: 'demo' | 'backend';
  baseUrl: string;
  apiKey: string;
  athleteId: number | null;
}

export interface SaveStrengthWorkout {
  title?: string;
  durationMinutes?: number;
  completedExercises?: CompletedExercise[];
  sessionId?: string;
  athleteId: number;
  startTime: string;
  endTime: string;
  exercises: Array<{
    lift: LiftType;
    sets: Array<{
      weight: number;
      target_reps: number;
      reps: Array<{ weight: number; velocity?: number; rep_num: number; rest_before: number }>;
      rest_before_sec?: number;
      set_end_rpe?: number;
    }>;
  }>;
}

export interface SaveEnduranceSession {
  sessionId?: string;
  athleteId: number;
  sport: EnduranceSport;
  startTime: string;
  endTime?: string;
  durationMinutes: number;
  intensityType: IntensityType;
  rpe?: number;
  averagePowerW?: number;
}

class ApiAdapter {
  private config: ApiConfig = {
    mode: 'demo',
    baseUrl: '',
    apiKey: '',
    athleteId: null,
  };

  configure(config: Partial<ApiConfig>) {
    this.config = { ...this.config, ...config };
  }

  get isDemo(): boolean {
    return this.config.mode === 'demo';
  }

  private async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;
    const res = await window.fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.config.apiKey,
        ...(options?.headers ?? {}),
      },
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `HTTP ${res.status}`);
    }
    return res.json();
  }

  async getReadiness(): Promise<ReadinessData> {
    if (this.isDemo) return { overall: null, per_lift: {}, endurance: null,
      explanations: ['Het onderzoeksmodel is niet gekoppeld. Lokale sessies worden niet omgezet in een belastbaarheidsscore.'], assessment_status: 'insufficient_data' };
    const id = this.config.athleteId;
    if (!id) throw new Error('Geen atleet geselecteerd');
    const r = await this.fetch<ReadinessData>(`/readiness/today?athlete_id=${id}`);
    return { ...r, overall: r.overall === null ? null : r.overall / 100,
      endurance: r.endurance === null ? null : r.endurance / 100,
      per_lift: Object.fromEntries(Object.entries(r.per_lift).map(([k, v]) => [k, v === null ? null : v / 100])) };
  }

  async getTodayPlan(): Promise<PlannedTraining | null> {
    if (this.isDemo) return (await this.getWeekDays()).find(d => d.isToday)?.planned ?? null;
    // Backend heeft geen dedicated planning-endpoint; gebruik readiness + autoregulate als proxy
    return Promise.resolve(null);
  }

  async getWeekDays(): Promise<WeekDay[]> {
    if (this.isDemo) {
      const profile = readProfile();
      return profile ? buildWeek(profile, new Date(), readSessions(), readJson(KEYS.overrides, {})) : [];
    }
    // Combineer recent sessions + planning
    return Promise.resolve([]);
  }

  async getHistory(days = 30): Promise<WorkoutSession[]> {
    if (this.isDemo) return readSessions().sort((a, b) => b.date.localeCompare(a.date));
    const id = this.config.athleteId;
    if (!id) throw new Error('Geen atleet geselecteerd');
    const data = await this.fetch<{ strength: unknown[]; endurance: unknown[] }>(
      `/sessions/recent?athlete_id=${id}&days=${days}`
    );
    // Map to WorkoutSession[]
    const result: WorkoutSession[] = [];
    for (const s of (data.strength as Array<Record<string, unknown>>)) {
      result.push({
        date: String(s.start_time).slice(0, 10),
        type: 'kracht',
        title: `Kracht – ${s.lift}`,
        durationMinutes: 0,
        savedToServer: true,
      });
    }
    for (const s of (data.endurance as Array<Record<string, unknown>>)) {
      result.push({
        date: String(s.start_time).slice(0, 10),
        type: 'duur',
        title: `Duur – ${s.sport}`,
        durationMinutes: Number(s.duration_minutes),
        savedToServer: true,
      });
    }
    return result.sort((a, b) => b.date.localeCompare(a.date));
  }

  async getLiftTrend(lift: LiftType, days = 30): Promise<TrendPoint[]> {
    if (this.isDemo) return measuredTrend(readSessions(), lift);
    const id = this.config.athleteId;
    if (!id) throw new Error('Geen atleet geselecteerd');
    const data = await this.fetch<{ data: Array<{ date: string; C_l: number }> }>(
      `/trends/lift?athlete_id=${id}&lift=${lift}&days=${days}`
    );
    return data.data.map(p => ({ date: p.date, value: p.C_l, isEstimate: false }));
  }

  async saveStrengthWorkout(workout: SaveStrengthWorkout): Promise<{ sessionIds: (number | string)[] }> {
    if (this.isDemo) {
      // Demo: opslaan in localStorage
      const record = appendSession({ id: workout.sessionId, date: localDate(new Date(workout.startTime)), type: 'kracht',
        title: workout.title ?? 'Krachttraining', durationMinutes: workout.durationMinutes ?? 0, savedToServer: false,
        exercises: workout.completedExercises ?? [] });
      return { sessionIds: [record.id!] };
    }
    const payload = {
      athlete_id: workout.athleteId,
      start_time: workout.startTime,
      end_time: workout.endTime,
      exercises: workout.exercises.map(e => ({
        lift: e.lift,
        sets: e.sets,
      })),
    };
    const data = await this.fetch<{ session_ids: number[] }>('/sessions/strength-workout', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return { sessionIds: data.session_ids };
  }

  async saveEnduranceSession(session: SaveEnduranceSession): Promise<{ id: number | string }> {
    if (this.isDemo) {
      const record = appendSession({ id: session.sessionId, date: localDate(new Date(session.startTime)), type: 'duur',
        title: `Duur — ${session.sport}`, durationMinutes: session.durationMinutes, savedToServer: false,
        enduranceResult: { sport: session.sport, durationMinutes: session.durationMinutes, intensityType: session.intensityType,
          rpe: session.rpe, averagePowerW: session.averagePowerW } });
      return { id: record.id! };
    }
    const payload = {
      athlete_id: session.athleteId,
      sport: session.sport,
      start_time: session.startTime,
      end_time: session.endTime,
      duration_minutes: session.durationMinutes,
      intensity_type: session.intensityType,
      rpe: session.rpe,
      average_power_w: session.averagePowerW,
    };
    return this.fetch('/sessions/endurance', { method: 'POST', body: JSON.stringify(payload) });
  }

  async getProfile(): Promise<AthleteProfile> {
    if (this.isDemo) {
      const stored = readProfile();
      if (stored) return stored;
      return { ...DEMO_PROFILE };
    }
    throw new Error('Backend profiel ophalen nog niet geïmplementeerd');
  }

  async saveProfile(profile: AthleteProfile): Promise<void> {
    writeJson(KEYS.profile, profile);
    if (!this.isDemo) {
      // TODO: sync met backend via athlete endpoint
    }
  }

  async skipDay(date: string): Promise<void> {
    const overrides = readJson<Record<string, PlannedTraining | null>>(KEYS.overrides, {});
    writeJson(KEYS.overrides, { ...overrides, [date]: null });
  }

  async moveDay(from: string, to: string): Promise<void> {
    const week = await this.getWeekDays();
    const source = week.find(d => d.date === from), target = week.find(d => d.date === to);
    const profile = readProfile();
    if (!source?.planned || !target || target.planned || target.completed || target.isPast
      || !profile?.availableDays.includes(new Date(`${to}T12:00:00`).getDay())) throw new Error('Kies een vrije, beschikbare dag in deze week.');
    const overrides = readJson<Record<string, PlannedTraining | null>>(KEYS.overrides, {});
    writeJson(KEYS.overrides, { ...overrides, [from]: null, [to]: { ...source.planned, date: to } });
  }
}

export const api = new ApiAdapter();
