import type { AthleteProfile, CompletedExercise, LiftType, PlannedTraining, WeekDay, WorkoutSession } from '../types';
import { normalizePlan, definition } from '../data/exercises';
import { strengthProgram, strengthSlots } from '../domain/program';

export const KEYS = { profile: 'ct_profile', sessions: 'ct_local_sessions_v1', draft: 'ct_workout_draft_v1', overrides: 'ct_week_overrides_v1', volumeTargets: 'ct_volume_targets_v1' };
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function readJson<T>(key: string, fallback: T, storage: StorageLike = localStorage): T {
  try { const raw = storage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
}

export function writeJson(key: string, value: unknown, storage: StorageLike = localStorage) {
  try { storage.setItem(key, JSON.stringify(value)); }
  catch { throw new Error('Opslaan op dit toestel lukt niet. Exporteer je gegevens of maak opslagruimte vrij; je invoer blijft open.'); }
}

export function localDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function readProfile(storage: StorageLike = localStorage): AthleteProfile | null {
  const p = readJson<AthleteProfile | null>(KEYS.profile, null, storage);
  return p && typeof p.name === 'string' && p.onboardingComplete && ['kracht', 'duur', 'balans'].includes(p.priority)
    && Array.isArray(p.availableDays) && p.availableDays.length > 0 && p.availableDays.every(d => Number.isInteger(d) && d >= 0 && d <= 6)
    && Number.isFinite(p.sessionDurationMinutes) && p.sessionDurationMinutes >= 15 && p.capacities ? p : null;
}

export function readSessions(storage: StorageLike = localStorage): WorkoutSession[] {
  const items = readJson<WorkoutSession[]>(KEYS.sessions, [], storage);
  return Array.isArray(items) ? items : [];
}

export function appendSession(session: WorkoutSession, storage: StorageLike = localStorage): WorkoutSession {
  const record = { ...session, id: session.id ?? crypto.randomUUID(), savedToServer: false };
  const sessions = readSessions(storage).filter(s => s.id !== record.id);
  writeJson(KEYS.sessions, [record, ...sessions], storage);
  return record;
}

export function parseVelocities(text: string, count: number): (number | null)[] {
  if (!Number.isInteger(count) || count < 1 || count > 100) throw new Error('Gebruik 1 tot 100 uitgevoerde reps.');
  if (!text.trim()) return Array(count).fill(null);
  const tokens = text.trim().split(';');
  if (tokens.length !== count) throw new Error(`Vul ${count} snelheden in, gescheiden door ;. Gebruik - voor een ontbrekende meting.`);
  return tokens.map(token => {
    if (!token.trim() || token.trim() === '-') return null;
    const value = Number(token.trim().replace(',', '.'));
    if (!Number.isFinite(value) || value <= 0 || value > 3) throw new Error('Snelheden moeten tussen 0 en 3 m/s liggen.');
    return value;
  });
}

export function planForDay(profile: AthleteProfile, date: string, index: number, sessions:WorkoutSession[]=[]): PlannedTraining {
  const slots = [...new Set(profile.availableDays)].length;
  const strengthCount = strengthSlots(profile);
  // Distribute emphasis across the chosen slots, without adding days or claiming model optimization.
  const strength = Math.floor((index + 1) * strengthCount / slots) > Math.floor(index * strengthCount / slots);
  const durationMinutes = profile.sessionDurationMinutes;
  if (!strength) return { date, type: 'duur', title: 'Rustige duurtraining', durationMinutes,
    reason: 'Voorlopige weekindeling binnen jouw gekozen dagen en tijd. Kies zelf een passende inspanning.',
    endurance: { sport: 'cycling', durationMinutes, intensityType: 'easy', description: 'Handmatig plan; geen berekende vermogensdoelstelling.' } };
  return strengthProgram(profile,date,index,sessions);
}

export function buildWeek(profile: AthleteProfile, now = new Date(), sessions: WorkoutSession[] = [], overrides: Record<string, PlannedTraining | null> = {}): WeekDay[] {
  const monday = new Date(now); monday.setHours(12, 0, 0, 0); monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  const days: WeekDay[] = []; let index = 0;
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday); d.setDate(d.getDate() + i); const date = localDate(d);
    const available = profile.availableDays.includes(d.getDay());
    const base = available ? planForDay(profile, date, index++,sessions) : undefined;
    const selected = Object.hasOwn(overrides, date) ? overrides[date] ?? undefined : base;
    const planned = selected ? normalizePlan(selected) : undefined;
    days.push({ date, dayLabel: d.toLocaleDateString('nl-BE', { weekday: 'long', day: 'numeric', month: 'numeric' }),
      dayName: ['zo', 'ma', 'di', 'wo', 'do', 'vr', 'za'][d.getDay()], planned,
      completed: sessions.find(s => s.date === date), isToday: date === localDate(now), isPast: date < localDate(now) });
  }
  return days;
}

export function measuredTrend(sessions: WorkoutSession[], lift: LiftType) {
  const byDate = new Map<string, number>();
  for (const s of sessions) for (const ex of s.exercises ?? []) if (ex.lift === lift)
    for (const set of ex.sets) if (set.completedReps > 0 && Number.isFinite(set.weight)) byDate.set(s.date, Math.max(byDate.get(s.date) ?? 0, set.weight));
  return [...byDate].sort(([a], [b]) => a.localeCompare(b)).map(([date, value]) => ({ date, value, isEstimate: false }));
}

export interface WorkoutDraft { plan: PlannedTraining; phase: 'start' | 'active'; startTime: string; completed: Record<string, import('../types').CompletedSet[]>; exerciseIndex: number; sessionId?: string }

export function saveEditedPlan(plan:PlannedTraining,draft:WorkoutDraft,storage:StorageLike=localStorage){
  const previousOverrides=storage.getItem(KEYS.overrides),previousDraft=storage.getItem(KEYS.draft);
  try{
    writeJson(KEYS.overrides,{...readJson<Record<string,PlannedTraining|null>>(KEYS.overrides,{},storage),[plan.date]:plan},storage);
    writeJson(KEYS.draft,draft,storage);
  }catch(e){
    // Restore the last complete snapshot when the second storage write fails.
    try{if(previousOverrides===null)storage.removeItem(KEYS.overrides);else storage.setItem(KEYS.overrides,previousOverrides);
      if(previousDraft===null)storage.removeItem(KEYS.draft);else storage.setItem(KEYS.draft,previousDraft);}catch{/* Keep the original actionable storage error. */}
    throw e;
  }
}

export function readDraft(storage: StorageLike = localStorage): WorkoutDraft | null {
  const d = readJson<WorkoutDraft | null>(KEYS.draft, null, storage);
  if(!d?.plan || !['start','active'].includes(d.phase) || !Number.isFinite(Date.parse(d.startTime)) || !d.completed)return null;
  const plan=normalizePlan(d.plan),completed:WorkoutDraft['completed']={};
  for(const [key,sets] of Object.entries(d.completed)){
    const id=plan.exercises?.find(e=>e.id===key)?.id ?? (/^\d+$/.test(key)?plan.exercises?.[Number(key)]?.id:undefined);
    if(id)completed[id]=sets;
  }
  return{...d,plan,completed};
}

export function exportLocal(storage: StorageLike = localStorage) {
  return { format: 'concurrent-training-local', version: 1, profile: readProfile(storage), sessions: readSessions(storage),
    overrides: readJson(KEYS.overrides, {}, storage), volumeTargets:readJson(KEYS.volumeTargets,undefined,storage) };
}

export function importLocal(text: string, storage: StorageLike = localStorage) {
  const data = JSON.parse(text);
  if (data.format !== 'concurrent-training-local' || data.version !== 1 || !Array.isArray(data.sessions)) throw new Error('Dit is geen ondersteund CT-exportbestand.');
  for (const s of data.sessions) {
    if (!['kracht', 'duur'].includes(s.type) || !/^\d{4}-\d{2}-\d{2}$/.test(s.date) || typeof s.title !== 'string'
      || !Number.isFinite(s.durationMinutes) || s.durationMinutes < 0) throw new Error('Het bestand bevat een ongeldige sessie.');
    if (s.exercises) for (const ex of s.exercises as CompletedExercise[]) for (const set of ex.sets) {
      if (!Number.isFinite(set.weight) || set.weight < 0 || set.weight > 500 || (set.weight===0 && !['bodyweight','assistance'].includes(definition(ex)?.load??'')) || !Number.isInteger(set.completedReps) || set.completedReps < 1
        || set.completedReps > 100 || !Array.isArray(set.velocities) || set.velocities.length !== set.completedReps
        || set.velocities.some(v => v !== null && (!Number.isFinite(v) || v <= 0 || v > 3))) throw new Error('Het bestand bevat ongeldige setgegevens.');
    }
  }
  const existing = readSessions(storage);
  const seen = new Set(existing.map(s => s.id));
  const added = data.sessions.filter((s: WorkoutSession) => {
    if (s.id != null && seen.has(s.id)) return false;
    if (s.id != null) seen.add(s.id);
    return true;
  }).map((s: WorkoutSession) => ({ ...s, id: s.id ?? crypto.randomUUID(), savedToServer: false }));
  writeJson(KEYS.sessions, [...existing, ...added], storage);
}
