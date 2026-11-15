/**
 * Structured cycle-ergometer workouts.
 *
 * Targets are fractions of ONE personal reference power. The reference and its
 * source are always shown: a fitted critical power, a critical power or
 * threshold the user entered, or - when nothing is known - a single easy power
 * the user chooses by feel. Interval sessions are not generated without a
 * measured reference.
 *
 * The W' balance check uses the differential model of Skiba et al. (2015). It
 * is a planning approximation with known individual variation
 * (Skiba & Clarke 2021, doi:10.1123/ijspp.2021-0205), not a guarantee.
 */
export type StepKind = 'warmup' | 'work' | 'recovery' | 'steady' | 'cooldown';
export interface Step { kind: StepKind; seconds: number; powerW: number; endPowerW?: number; label: string }
export type ReferenceSource = 'cp_fit_from_maximal_efforts' | 'user_entered_cp' | 'user_entered_threshold_not_cp' | 'manual_easy_power';
export interface Reference { powerW: number; source: ReferenceSource; wPrimeJ?: number | null }
export type WorkoutGoal = 'herstel' | 'duur' | 'tempo' | 'drempel' | 'vo2max' | 'kort';
export interface BikeWorkout {
  id: string; goal: WorkoutGoal; title: string; steps: Step[]; reference: Reference;
  assumptions: string[]; warnings: string[]; feasibility: Feasibility;
}
export interface Feasibility { status: 'ok' | 'hard' | 'not_feasible' | 'not_checked'; minBalanceJ?: number; minBalanceFraction?: number }

export const GOALS: Record<WorkoutGoal, { label: string; needsReference: boolean; aim: string }> = {
  herstel: { label: 'Herstelrit', needsReference: false, aim: 'Zeer rustig rijden.' },
  duur: { label: 'Rustige duur', needsReference: false, aim: 'Lang, gelijkmatig en rustig.' },
  tempo: { label: 'Tempo-blokken', needsReference: true, aim: 'Langere blokken onder je referentievermogen.' },
  drempel: { label: 'Drempelintervallen', needsReference: true, aim: 'Blokken net onder of rond je referentievermogen.' },
  vo2max: { label: 'Intervallen van 3–4 minuten', needsReference: true, aim: 'Zware blokken boven je referentievermogen.' },
  kort: { label: 'Korte intervallen van 1 minuut', needsReference: true, aim: 'Korte, zeer zware blokken met ruim herstel.' },
};
interface Plan { work?: [number, number, number]; reps?: [number, number]; steady?: number; warm: number; cool: number }
// [work seconds, work fraction, recovery seconds]; recovery is ridden at 50 % of the reference.
const PLANS: Record<WorkoutGoal, Plan> = {
  herstel: { steady: 0.55, warm: 300, cool: 300 },
  duur: { steady: 0.68, warm: 480, cool: 300 },
  tempo: { work: [720, 0.86, 300], reps: [2, 4], warm: 600, cool: 420 },
  drempel: { work: [480, 0.96, 240], reps: [2, 5], warm: 600, cool: 420 },
  vo2max: { work: [180, 1.12, 180], reps: [3, 6], warm: 720, cool: 480 },
  kort: { work: [60, 1.25, 120], reps: [4, 10], warm: 720, cool: 480 },
};
export const ABSOLUTE_MAX_W = 1500;
const round5 = (w: number) => Math.round(w / 5) * 5;

export function chooseReference(input: { cpFitW?: number | null; cpFitWPrimeJ?: number | null; criticalPowerW?: number; wPrimeJ?: number; thresholdPowerW?: number; manualEasyPowerW?: number }): Reference | null {
  if (input.cpFitW) return { powerW: input.cpFitW, source: 'cp_fit_from_maximal_efforts', wPrimeJ: input.cpFitWPrimeJ ?? null };
  if (input.criticalPowerW) return { powerW: input.criticalPowerW, source: 'user_entered_cp', wPrimeJ: input.wPrimeJ ?? null };
  if (input.thresholdPowerW) return { powerW: input.thresholdPowerW, source: 'user_entered_threshold_not_cp', wPrimeJ: null };
  if (input.manualEasyPowerW) return { powerW: input.manualEasyPowerW, source: 'manual_easy_power', wPrimeJ: null };
  return null;
}

/** Target power at a moment inside a step (linear ramp when endPowerW is set). */
export function powerAt(step: Step, elapsed: number): number {
  if (step.endPowerW === undefined || step.seconds <= 0) return step.powerW;
  const f = Math.min(1, Math.max(0, elapsed / step.seconds));
  return step.powerW + (step.endPowerW - step.powerW) * f;
}
export function totalSeconds(steps: Step[]): number { return steps.reduce((sum, s) => sum + s.seconds, 0); }
export function secondBySecond(steps: Step[]): number[] {
  const out: number[] = [];
  for (const step of steps) for (let t = 0; t < step.seconds; t++) out.push(powerAt(step, t + 0.5));
  return out;
}

/** Differential W' balance; identical to app/science/critical_power.py (shared fixture test). */
export function wPrimeBalance(power: (number | null)[], cpW: number, wPrimeJ: number, dt = 1): (number | null)[] {
  if (!(cpW > 0 && wPrimeJ > 0 && dt > 0)) throw new Error('CP, W′ en tijdstap moeten positief zijn.');
  let balance = wPrimeJ;
  return power.map(p => {
    if (p === null) return null;
    if (!Number.isFinite(p) || p < 0) throw new Error('Vermogen moet eindig en niet negatief zijn.');
    balance = p > cpW ? balance - (p - cpW) * dt : wPrimeJ - (wPrimeJ - balance) * Math.exp(-(cpW - p) * dt / wPrimeJ);
    return balance;
  });
}

export function checkFeasibility(steps: Step[], reference: Reference): Feasibility {
  const isCp = reference.source === 'cp_fit_from_maximal_efforts' || reference.source === 'user_entered_cp';
  if (!isCp || !reference.wPrimeJ) return { status: 'not_checked' };
  const trace = wPrimeBalance(secondBySecond(steps), reference.powerW, reference.wPrimeJ) as number[];
  const min = trace.length ? Math.min(...trace) : reference.wPrimeJ;
  const fraction = min / reference.wPrimeJ;
  return { status: min < 0 ? 'not_feasible' : fraction < 0.2 ? 'hard' : 'ok', minBalanceJ: Math.round(min), minBalanceFraction: Math.round(fraction * 100) / 100 };
}

export function validateSteps(steps: Step[], maxPowerW: number): void {
  if (!steps.length || steps.length > 200) throw new Error('Een workout heeft 1 tot 200 blokken.');
  if (!(maxPowerW > 0 && maxPowerW <= ABSOLUTE_MAX_W)) throw new Error(`Kies een maximumvermogen tot ${ABSOLUTE_MAX_W} W.`);
  for (const s of steps) {
    const powers = [s.powerW, s.endPowerW ?? s.powerW];
    if (!Number.isInteger(s.seconds) || s.seconds < 10 || s.seconds > 4 * 3600 || powers.some(p => !Number.isFinite(p) || p < 0 || p > maxPowerW))
      throw new Error(`Controleer duur en vermogen van elk blok (10 s tot 4 uur, 0 tot ${maxPowerW} W).`);
  }
  if (totalSeconds(steps) > 6 * 3600) throw new Error('Een workout duurt hoogstens 6 uur.');
}

export function describe(reference: Reference): string {
  const w = `${Math.round(reference.powerW)} W`;
  return { cp_fit_from_maximal_efforts: `Critical power uit je eigen maximale inspanningen: ${w}.`,
    user_entered_cp: `Door jou ingevoerde critical power: ${w}.`,
    user_entered_threshold_not_cp: `Door jou ingevoerd drempelvermogen: ${w}. Dit is geen critical power; W′ is onbekend.`,
    manual_easy_power: `Door jou op gevoel gekozen rustig vermogen: ${w}. Er is geen gemeten referentie.` }[reference.source];
}

export function generateWorkout(goal: WorkoutGoal, minutes: number, reference: Reference | null, options: { intensity?: number; maxPowerW?: number } = {}): BikeWorkout {
  if (!reference) throw new Error('Zonder referentievermogen kan geen vermogensdoel worden berekend. Voer een rustig vermogen op gevoel in voor een handmatige rit.');
  if (!Number.isFinite(minutes) || minutes < 20 || minutes > 300) throw new Error('Kies een duur van 20 tot 300 minuten.');
  const manual = reference.source === 'manual_easy_power';
  if (manual && GOALS[goal].needsReference) throw new Error('Intervallen vragen een gemeten referentie (critical power of drempelvermogen). Kies een rustige rit of vul je testgegevens in.');
  const intensity = options.intensity ?? 1;
  if (!(intensity >= 0.8 && intensity <= 1.1)) throw new Error('Pas de intensiteit aan tussen 80 % en 110 %.');
  const maxPowerW = options.maxPowerW ?? Math.min(ABSOLUTE_MAX_W, Math.round(reference.powerW * 2));
  const plan = PLANS[goal], total = Math.round(minutes * 60);
  // With a hand-picked easy power the chosen power IS the steady target; fractions apply to measured references only.
  const at = (fraction: number) => round5(manual ? reference.powerW * (fraction / 0.68) * intensity : reference.powerW * fraction * intensity);
  const low = at(0.45), steps: Step[] = [];
  const warm = Math.min(plan.warm, Math.round(total * 0.25)), cool = Math.min(plan.cool, Math.round(total * 0.15));
  const assumptions = [describe(reference)], warnings: string[] = [];
  if (plan.steady !== undefined) {
    const target = at(plan.steady);
    steps.push({ kind: 'warmup', seconds: warm, powerW: low, endPowerW: target, label: 'Warming-up' });
    steps.push({ kind: 'steady', seconds: Math.max(60, total - warm - cool), powerW: target, label: GOALS[goal].label });
    steps.push({ kind: 'cooldown', seconds: cool, powerW: target, endPowerW: low, label: 'Cooling-down' });
  } else {
    const [work, fraction, recovery] = plan.work!, [minReps, maxReps] = plan.reps!;
    const room = total - warm - cool + recovery;
    const reps = Math.min(maxReps, Math.floor(room / (work + recovery)));
    if (reps < minReps) throw new Error(`Voor ${GOALS[goal].label.toLowerCase()} zijn minstens ${Math.ceil((warm + cool + minReps * (work + recovery) - recovery) / 60)} minuten nodig.`);
    const workW = at(fraction), recoveryW = at(0.5), warmEnd = at(0.75);
    steps.push({ kind: 'warmup', seconds: warm, powerW: low, endPowerW: warmEnd, label: 'Warming-up' });
    for (let i = 0; i < reps; i++) {
      steps.push({ kind: 'work', seconds: work, powerW: workW, label: `Blok ${i + 1} van ${reps}` });
      if (i < reps - 1) steps.push({ kind: 'recovery', seconds: recovery, powerW: recoveryW, label: 'Herstel' });
    }
    const rest = total - warm - reps * work - (reps - 1) * recovery;
    steps.push({ kind: 'cooldown', seconds: Math.max(cool, rest), powerW: recoveryW, endPowerW: low, label: 'Cooling-down' });
    assumptions.push(`${reps} × ${work / 60 >= 1 ? `${work / 60} min` : `${work} s`} op ${Math.round(fraction * intensity * 100)} % van je referentie, herstel ${recovery / 60} min op 50 %.`);
    if (reference.source === 'user_entered_threshold_not_cp') warnings.push('De doelen zijn afgeleid van een ingevoerd drempelvermogen. De haalbaarheid is niet getoetst; verlaag de intensiteit als het eerste blok te zwaar aanvoelt.');
  }
  for (const s of steps) { s.powerW = Math.min(s.powerW, maxPowerW); if (s.endPowerW !== undefined) s.endPowerW = Math.min(s.endPowerW, maxPowerW); }
  validateSteps(steps, maxPowerW);
  const feasibility = checkFeasibility(steps, reference);
  if (feasibility.status === 'not_feasible') warnings.push('Volgens het critical-power-model raakt je W′ tijdens deze workout op. Verlaag de intensiteit, verkort de blokken of verleng het herstel.');
  if (feasibility.status === 'hard') warnings.push(`Volgens het model blijft op het zwaarste punt ongeveer ${Math.round((feasibility.minBalanceFraction ?? 0) * 100)} % van je W′ over. Dat is een benadering met individuele spreiding.`);
  if (manual) warnings.push('Zonder gemeten referentie is dit een rit op gevoel. Pas het vermogen aan zodat je vlot kunt blijven praten.');
  return { id: `${goal}-${minutes}-${Math.round(reference.powerW)}-${Math.round(intensity * 100)}`, goal, title: `${GOALS[goal].label} · ${minutes} min`, steps, reference, assumptions, warnings, feasibility };
}
