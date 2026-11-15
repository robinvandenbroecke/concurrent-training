/**
 * Strength programme generator.
 *
 * Every number here is a transparent, editable coaching starting point. The
 * choices follow published group-level findings (see docs/strength_programs.md):
 * the 2026 ACSM overview of reviews found that few prescription variables
 * change the outcome. For strength: loads of about 80 % 1RM or more, 2-3 sets
 * per exercise, full range of motion, the lift early in the session, at least
 * two sessions a week. For hypertrophy: about ten or more weekly sets per
 * muscle group. For power: moderate loads moved fast, low volume, and
 * weightlifting-style or other explosive work. Training to failure, the type of
 * equipment and complex periodisation did not consistently matter. The
 * generator is therefore deliberately simple. None of its numbers is an
 * individually measured optimum, and it makes no claim about a personal minimum
 * or maximum recoverable volume.
 *
 * Invariants (tested):
 *  - only exercises possible with the stated equipment are selected;
 *  - catch/overhead weightlifting variants need confirmed technique experience;
 *  - a weight comes only from the SAME exercise's last logged work set, or (sets of six or fewer) from the
 *    working weight the athlete entered for that exact lift; otherwise it stays empty;
 *  - a missed session never adds catch-up volume;
 *  - anything removed to fit the available time is listed, never dropped silently.
 */
import type { AthleteProfile, EquipmentTag, ExperienceLevel, PlannedExercise, PlannedTraining, ProgramGoal, ProgramSettings, WorkoutSession } from '../types';
import { EXERCISES, available, createExercise, definition, type ExerciseDefinition, type Pattern } from '../data/exercises';
import { estimatedMinutes } from './volume';
import { countPlan, MUSCLE_LABELS } from './volume';
import { strengthSlots } from './program';
import type { Muscle } from '../data/exercises';

export const GOAL_LABELS: Record<ProgramGoal, string> = {
  algemeen: 'Algemene kracht', powerlifting: 'Powerlifting / maximale kracht', hypertrofie: 'Spiergroei',
  power: 'Atletische power', concurrent: 'Kracht naast duursport',
};
export const EXPERIENCE_LABELS: Record<ExperienceLevel, string> = { beginner: 'Beginner (minder dan ± 1 jaar gestructureerd)', gevorderd: 'Gevorderd', ervaren: 'Ervaren' };
export const FULL_GYM: EquipmentTag[] = ['halter', 'rek', 'bank', 'dumbbells', 'kettlebell', 'machines', 'kabel', 'optrekstang', 'bumpers', 'trapbar'];
export const EQUIPMENT_PRESETS: Record<string, { label: string; tags: EquipmentTag[] }> = {
  gym: { label: 'Volledige gym', tags: FULL_GYM },
  thuis: { label: 'Thuisgym: halter, rek en bank', tags: ['halter', 'rek', 'bank', 'optrekstang'] },
  dumbbells: { label: 'Dumbbells en/of kettlebell', tags: ['dumbbells', 'kettlebell', 'bank'] },
  machines: { label: 'Machines en kabels', tags: ['machines', 'kabel'] },
  lichaam: { label: 'Alleen lichaamsgewicht', tags: [] },
  eigen: { label: 'Eigen keuze', tags: [] },
};

type Role = 'main' | 'secondary' | 'accessory' | 'power';
interface Slot { pattern: Pattern[]; role: Role; prefer?: string[] }
interface Scheme { sets: number; reps: number; rpe: number; rest: number }

/** Set/rep/effort starting points per goal and role. RPE is a target the lifter reports, not a measurement. */
const SCHEMES: Record<ProgramGoal, Record<Role, Scheme>> = {
  powerlifting: { main: { sets: 4, reps: 4, rpe: 7.5, rest: 210 }, secondary: { sets: 3, reps: 5, rpe: 7, rest: 180 }, accessory: { sets: 2, reps: 8, rpe: 7.5, rest: 120 }, power: { sets: 3, reps: 2, rpe: 6, rest: 150 } },
  algemeen: { main: { sets: 3, reps: 6, rpe: 7.5, rest: 180 }, secondary: { sets: 3, reps: 8, rpe: 7.5, rest: 150 }, accessory: { sets: 2, reps: 10, rpe: 7.5, rest: 90 }, power: { sets: 3, reps: 3, rpe: 6, rest: 120 } },
  hypertrofie: { main: { sets: 3, reps: 8, rpe: 8, rest: 150 }, secondary: { sets: 3, reps: 10, rpe: 8, rest: 120 }, accessory: { sets: 3, reps: 12, rpe: 8.5, rest: 90 }, power: { sets: 2, reps: 3, rpe: 6, rest: 120 } },
  power: { main: { sets: 3, reps: 4, rpe: 7, rest: 180 }, secondary: { sets: 2, reps: 5, rpe: 7, rest: 150 }, accessory: { sets: 2, reps: 8, rpe: 7, rest: 90 }, power: { sets: 4, reps: 3, rpe: 6, rest: 180 } },
  concurrent: { main: { sets: 3, reps: 4, rpe: 7.5, rest: 180 }, secondary: { sets: 2, reps: 6, rpe: 7, rest: 150 }, accessory: { sets: 2, reps: 8, rpe: 7, rest: 90 }, power: { sets: 3, reps: 3, rpe: 6, rest: 150 } },
};

const POWER: Slot = { pattern: ['power_catch', 'power_pull', 'jump', 'power_overhead'], role: 'power' };
/** A second explosive slot for the power goal: jumps did as well as weightlifting in pooled comparisons. */
const JUMP: Slot = { pattern: ['jump', 'power_overhead', 'power_pull'], role: 'power' };
const LOWER: Pattern[] = ['squat', 'hinge', 'single_leg'];
const S = (role: Role, prefer: string[], ...pattern: Pattern[]): Slot => ({ pattern, role, prefer });
/** Session templates. Order = execution order: explosive work first, then the heaviest multi-joint lifts. */
const TEMPLATES: Record<string, Slot[][]> = {
  full2: [
    [POWER, S('main', ['back_squat'], 'squat'), S('main', ['bench_press'], 'push_h'), S('secondary', ['barbell_row'], 'pull_h'), S('accessory', [], 'hinge'), S('accessory', [], 'push_v')],
    [POWER, S('main', ['deadlift'], 'hinge'), S('main', ['bench_press', 'overhead_press'], 'push_h', 'push_v'), S('secondary', ['pull_up', 'lat_pulldown'], 'pull_v'), S('accessory', ['front_squat'], 'squat', 'single_leg'), S('accessory', [], 'pull_h')],
  ],
  full3: [
    [POWER, S('main', ['back_squat'], 'squat'), S('main', ['bench_press'], 'push_h'), S('secondary', [], 'pull_h'), S('accessory', [], 'hinge')],
    [POWER, S('main', ['deadlift'], 'hinge'), S('main', ['overhead_press'], 'push_v'), S('secondary', [], 'pull_v'), S('accessory', [], 'single_leg')],
    [POWER, S('main', ['bench_press'], 'push_h'), S('secondary', ['front_squat', 'paused_squat'], 'squat'), S('secondary', [], 'pull_h'), S('accessory', ['romanian_deadlift'], 'hinge'), S('accessory', [], 'isolation')],
  ],
  split4: [
    [POWER, S('main', ['back_squat'], 'squat'), S('secondary', ['romanian_deadlift'], 'hinge'), S('accessory', [], 'single_leg'), S('accessory', ['leg_curl'], 'isolation', 'hinge')],
    [S('main', ['bench_press'], 'push_h'), S('main', [], 'pull_h'), S('secondary', ['overhead_press'], 'push_v'), S('secondary', [], 'pull_v'), S('accessory', ['lateral_raise', 'face_pull'], 'isolation')],
    [POWER, S('main', ['deadlift'], 'hinge'), S('secondary', ['front_squat', 'paused_squat'], 'squat'), S('accessory', [], 'single_leg'), S('accessory', [], 'hinge')],
    [S('main', ['bench_press', 'close_grip_bench'], 'push_h'), S('main', [], 'pull_v'), S('secondary', [], 'push_v', 'push_h'), S('secondary', [], 'pull_h'), S('accessory', ['face_pull', 'lateral_raise'], 'isolation')],
  ],
};
// With one session per week all three powerlifts fit in one visit.
TEMPLATES.full1 = [[POWER, S('main', ['back_squat'], 'squat'), S('main', ['bench_press'], 'push_h'), S('main', ['deadlift'], 'hinge'), S('secondary', [], 'pull_h', 'pull_v')]];

export const CYCLE_WEEKS = 4;
export interface WeekRule { label: string; setDelta: number; repDelta: number; rpeDelta: number; setFactor: number }
/**
 * Week rule. The default is a constant schedule with load progression: the
 * pooled evidence shows no consistent benefit of complex periodisation, and the
 * one controlled trial of a mid-programme week off found slightly less strength
 * gain and no other difference. A lighter fourth week is therefore optional and
 * presented as a convention for managing fatigue, not as a requirement.
 */
export function weekRule(settings: ProgramSettings, week: number): WeekRule {
  const index = ((week % CYCLE_WEEKS) + CYCLE_WEEKS) % CYCLE_WEEKS;
  if (settings.returning && week < 2) return { label: `Herstart, week ${week + 1} van 2: één set minder op de hoofdoefeningen en lagere inspanning`, setDelta: -1, repDelta: 0, rpeDelta: -1, setFactor: 1 };
  if (settings.lighterWeek && index === CYCLE_WEEKS - 1) return { label: 'Lichtere week (elke vierde week, eigen keuze): ongeveer 40 % minder sets en lagere inspanning', setDelta: 0, repDelta: 0, rpeDelta: -1.5, setFactor: 0.6 };
  return { label: 'Vast schema: verhoog het gewicht met de kleinste stap wanneer alle sets binnen de doel-RPE lukken', setDelta: 0, repDelta: 0, rpeDelta: 0, setFactor: 1 };
}

export function cycleWeek(settings: ProgramSettings, date: string): number {
  const days = Math.round((Date.parse(`${date}T12:00:00Z`) - Date.parse(`${settings.cycleStart}T12:00:00Z`)) / 86400000);
  return Number.isFinite(days) ? Math.max(0, Math.floor(days / 7)) : 0;
}

/** Catch and jerk variants always need confirmed weightlifting experience; pulls and jumps do not. */
export function maxTechnique(profile: AthleteProfile): 2 | 3 {
  return profile.olympicExperience ? 3 : 2;
}

function pick(slot: Slot, profile: AthleteProfile, settings: ProgramSettings, used: Set<string>): ExerciseDefinition | undefined {
  const limit = maxTechnique(profile);
  const usable = (d: ExerciseDefinition) => !used.has(d.id) && d.technique <= limit && available(d, settings.equipment)
    && (slot.role === 'power') === !!d.power;
  for (const id of slot.prefer ?? []) {
    const d = EXERCISES.find(e => e.id === id);
    if (d && slot.pattern.includes(d.pattern) && usable(d)) return d;
  }
  for (const pattern of slot.pattern) {
    // Catalogue order is the tie-break: barbell basics first, then simpler or machine variants.
    const candidates = EXERCISES.filter(e => e.pattern === pattern && usable(e));
    // Externally loaded first: it can progress in small steps. Supporting work does not repeat a competition lift
    // at high repetitions when another exercise of the same pattern is available.
    const support = slot.role === 'accessory' || slot.role === 'secondary';
    const ranked = [...candidates].sort((a, b) => Number(support && !!a.powerlift) - Number(support && !!b.powerlift) || Number(a.load !== 'weight') - Number(b.load !== 'weight'));
    if (ranked[0]) return ranked[0];
  }
  return undefined;
}

function lastWorkSet(sessions: WorkoutSession[], exerciseId: string, date: string) {
  const recent = [...sessions].filter(s => s.date <= date).sort((a, b) => b.date.localeCompare(a.date))
    .flatMap(s => (s.exercises ?? []).map(e => ({ e, date: s.date }))).filter(({ e }) => definition(e)?.id === exerciseId)
    .map(({ e, date: d }) => ({ date: d, sets: e.sets.filter(s => s.kind !== 'warmup' && s.completedReps > 0) })).filter(r => r.sets.length > 0);
  return recent;
}

/** A suggestion only: both last exposures completed every target rep at or below RPE 8. Never applied automatically. */
export function progressionHint(sessions: WorkoutSession[], exerciseId: string, date: string): string | undefined {
  const [last, previous] = lastWorkSet(sessions, exerciseId, date);
  if (!last || !previous) return undefined;
  const ok = (sets: typeof last.sets) => sets.every(s => s.completedReps >= s.targetReps && s.rpe !== undefined && s.rpe <= 8);
  const top = (sets: typeof last.sets) => Math.max(...sets.map(s => s.weight));
  if (ok(last.sets) && ok(previous.sets) && top(last.sets) === top(previous.sets) && top(last.sets) > 0)
    return `Twee trainingen op ${top(last.sets)} kg volledig gehaald met RPE 8 of lager: je kunt de kleinste gewichtsprong overwegen.`;
  if (last.sets.some(s => s.completedReps < s.targetReps || (s.rpe ?? 0) >= 9.5)) return 'Vorige keer niet alle reps gehaald of bijna maximaal: houd het gewicht gelijk of verlaag het.';
  return undefined;
}

export interface Generated { plan: PlannedTraining; removed: string[]; unfilled: string[] }

export function generateStrength(profile: AthleteProfile, date: string, ordinal: number, sessions: WorkoutSession[] = []): Generated {
  return build(profile, date, ordinal, sessions, true);
}

function build(profile: AthleteProfile, date: string, ordinal: number, sessions: WorkoutSession[], withWeeklyNote: boolean): Generated {
  const settings = profile.program!;
  const slots = strengthSlots(profile);
  const key = slots <= 1 ? 'full1' : slots === 2 ? 'full2' : slots === 3 ? 'full3' : 'split4';
  const sessionIndex = ((ordinal % TEMPLATES[key].length) + TEMPLATES[key].length) % TEMPLATES[key].length;
  const week = cycleWeek(settings, date), rule = weekRule(settings, week);
  const scheme = SCHEMES[settings.goal];
  const used = new Set<string>(), unfilled: string[] = [];
  let template = TEMPLATES[key][sessionIndex];
  if (settings.goal === 'power') template = [POWER, JUMP, ...template.filter(s => s !== POWER)];
  // For muscle growth: no explosive block, and two extra supporting slots that are the first to go when time is short.
  if (settings.goal === 'hypertrofie') template = [...template.filter(s => s !== POWER), S('accessory', ['leg_extension', 'leg_curl', 'lateral_raise'], 'isolation', 'single_leg'), S('accessory', [], 'push_v', 'pull_v', 'push_h', 'pull_h')];
  // Beside endurance sport the legs already carry the endurance load: lower-body accessory work is left out, the main lifts stay.
  if (settings.goal === 'concurrent') template = template.filter(s => !(s.role === 'accessory' && s.pattern.every(p => LOWER.includes(p))));
  const levelSets = settings.experience === 'beginner' ? -1 : settings.experience === 'ervaren' ? 1 : 0;
  const rpeCap = settings.experience === 'beginner' ? 8 : 9;
  const exercises: (PlannedExercise & { role: Role })[] = [];
  for (const slot of template) {
    const d = pick(slot, profile, settings, used);
    if (!d) { unfilled.push(slot.pattern[0]); continue; }
    used.add(d.id);
    const base = scheme[slot.role];
    const mainBonus = slot.role === 'main' ? levelSets + rule.setDelta : slot.role === 'power' ? 0 : Math.min(0, levelSets + Math.min(0, rule.setDelta));
    const floor = slot.role === 'main' ? 2 : 1;                       // two sets on a main lift is the lower end of what the evidence supports for strength
    const sets = Math.max(floor, Math.ceil(Math.max(floor, base.sets + mainBonus) * rule.setFactor));
    const ex = createExercise(d.id, profile, `${date}:${d.id}`, sets);
    const logged = lastWorkSet(sessions, d.id, date)[0]?.sets.at(-1);
    const hint = progressionHint(sessions, d.id, date);
    const bodyweightReps = d.load === 'bodyweight' && !d.power ? Math.max(base.reps, d.reps) : base.reps;
    const reps = d.power ? Math.min(d.reps, 5) : bodyweightReps + rule.repDelta;
    // The onboarding weight is a working weight for about five repetitions: it is not reused for clearly longer sets.
    const entered = reps <= 6 ? ex.sets[0]?.weight ?? 0 : 0;
    ex.sets = ex.sets.map(s => ({ ...s, weight: logged ? logged.weight : entered, targetReps: reps,
      targetRpe: Math.max(5, Math.min(d.power ? 6.5 : rpeCap, base.rpe + (d.power ? 0 : rule.rpeDelta))), restSec: base.rest,
      note: hint ? `${d.cue} ${hint}` : d.cue }));
    exercises.push({ ...ex, role: slot.role });
  }
  const plan: PlannedTraining = { date, type: 'kracht', durationMinutes: profile.sessionDurationMinutes,
    title: `${GOAL_LABELS[settings.goal]} — sessie ${'ABCD'[sessionIndex]}`, exercises: exercises.map(({ role: _role, ...e }) => e),
    reason: '' };
  // Fit the available time: accessories go first, then secondary work, then extra sets. Main lifts and rest periods stay.
  const removed: string[] = [];
  const order: Role[] = ['accessory', 'secondary'];
  for (const role of order) {
    for (let i = exercises.length - 1; i >= 0 && estimatedMinutes(plan) > plan.durationMinutes; i--) {
      if (exercises[i].role !== role) continue;
      removed.push(exercises[i].displayName);
      exercises.splice(i, 1);
      plan.exercises = exercises.map(({ role: _role, ...e }) => e);
    }
  }
  while (estimatedMinutes(plan) > plan.durationMinutes && plan.exercises!.some(e => e.sets.length > 2)) {
    const longest = [...plan.exercises!].sort((a, b) => b.sets.length - a.sets.length)[0];
    longest.sets = longest.sets.slice(0, -1);
    if (!removed.includes('één set per oefening')) removed.push('één set per oefening');
  }
  // Volume is the variable that matters for muscle growth: unused session time goes to extra sets, never beyond four per exercise.
  let added = 0;
  if (settings.goal === 'hypertrofie' && rule.setFactor === 1 && !(settings.returning && week < 2)) {
    for (let guard = 0; guard < 40; guard++) {
      const target = [...plan.exercises!].filter(e => e.sets.length < 4 && !definition(e)?.power).sort((a, b) => a.sets.length - b.sets.length)[0];
      if (!target) break;
      const last = target.sets[target.sets.length - 1];
      target.sets = [...target.sets, { ...last, setNum: last.setNum + 1 }];
      if (estimatedMinutes(plan) > plan.durationMinutes) { target.sets = target.sets.slice(0, -1); break; }
      added++;
    }
  }
  const notes = [rule.label + '.'];
  if (added) notes.push(`De beschikbare tijd is gevuld met ${added} extra ${added === 1 ? 'set' : 'sets'}; voor spiergroei telt het weekvolume.`);
  if (settings.goal === 'concurrent') notes.push('Naast duursport: de hoofdoefeningen voor de benen blijven, het extra beenwerk vervalt. Plan explosief en zwaar beenwerk bij voorkeur niet in dezelfde sessie als duurtraining; in groepsonderzoek verdwijnt het nadeel bij enkele uren tussentijd.');
  if (settings.goal === 'hypertrofie' && withWeeklyNote) { const low = weeklyShortfall(profile); if (low.length) notes.push(`Met dit aantal trainingen en deze sessieduur kom je per week onder ongeveer tien sets voor ${low.join(', ')}. Dat is het niveau waarboven groepsonderzoek meer spiergroei ziet; een extra trainingsdag of langere sessie brengt je erboven.`); }
  if (settings.goal === 'power' || exercises.some(e => e.role === 'power')) notes.push('Explosieve sets: korte sets met maximale intentie; stop zodra de snelheid of techniek zichtbaar afneemt.');
  if (removed.length) notes.push(`Ingekort om binnen ${plan.durationMinutes} min te blijven: ${removed.join(', ')}.`);
  if (unfilled.length) notes.push('Voor een deel van het schema is met jouw materiaal geen passende oefening beschikbaar; voeg zelf een alternatief toe.');
  notes.push('Controleer elk werkgewicht: het komt uit je laatst gelogde set van dezelfde oefening, uit het werkgewicht dat je zelf hebt ingevuld, of is nog leeg.');
  plan.reason = notes.join(' ');
  return { plan, removed, unfilled };
}

/** Muscle groups that stay under about ten weekly sets (direct = 1, indirect = 0.5) with the generated week. */
export function weeklyShortfall(profile: AthleteProfile, threshold = 10): string[] {
  if (!profile.program) return [];
  const totals: Record<Muscle, number> = { quadriceps: 0, posterior: 0, chest: 0, back: 0, shoulders: 0 };
  const slots = strengthSlots(profile);
  for (let ordinal = 0; ordinal < slots; ordinal++) {
    const count = countPlan(build(profile, profile.program.cycleStart, ordinal, [], false).plan);
    for (const muscle of Object.keys(totals) as Muscle[]) totals[muscle] += count.muscles[muscle];
  }
  return (Object.keys(totals) as Muscle[]).filter(m => totals[m] < threshold).map(m => MUSCLE_LABELS[m].toLowerCase());
}

export function defaultProgram(profile: AthleteProfile, cycleStart: string): ProgramSettings {
  return { goal: profile.priority === 'duur' ? 'concurrent' : profile.priority === 'kracht' ? 'powerlifting' : 'algemeen',
    experience: profile.experienceYears < 1 ? 'beginner' : profile.experienceYears < 4 ? 'gevorderd' : 'ervaren', equipment: FULL_GYM, returning: false, lighterWeek: false, cycleStart };
}
