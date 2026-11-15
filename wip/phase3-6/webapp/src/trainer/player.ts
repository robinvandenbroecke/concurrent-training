/**
 * Workout player: a pure state machine driven by wall-clock time, so it can be
 * tested without a browser or a trainer. It never talks to Bluetooth itself;
 * the screen forwards `target()` to the trainer while `status === 'playing'`.
 */
import type { PowerSummary } from '../types';
import { type BikeWorkout, powerAt, totalSeconds } from './workout';

export type PlayerStatus = 'idle' | 'playing' | 'paused' | 'finished';
export type PauseReason = 'user' | 'trainer_disconnected' | 'trainer_silent' | 'trainer_error' | 'clock_gap';
export interface Sample { t: number; powerW: number | null; cadenceRpm: number | null; targetW: number | null }
export const RESUME_RAMP_SECONDS = 5;      // after every start/resume the target climbs from 50 % to 100 %
export const MAX_TICK_GAP_MS = 5000;       // a suspended tab or phone must not jump the workout forward

export class WorkoutPlayer {
  status: PlayerStatus = 'idle';
  pauseReason: PauseReason | null = null;
  stepIndex = 0;
  stepElapsed = 0;       // seconds inside the current step
  elapsed = 0;           // active (non-paused) seconds
  intensity = 1;         // live manual adjustment, 0.5 - 1.2
  samples: Sample[] = [];
  private lastTick = 0;
  private sinceResume = 0;
  private latest: { powerW: number | null; cadenceRpm: number | null; at: number } = { powerW: null, cadenceRpm: null, at: 0 };

  constructor(readonly workout: BikeWorkout, private maxPowerW: number) {}

  get step() { return this.workout.steps[Math.min(this.stepIndex, this.workout.steps.length - 1)]; }
  get total() { return totalSeconds(this.workout.steps); }
  get remainingInStep() { return Math.max(0, this.step.seconds - this.stepElapsed); }

  /** Target for the trainer right now; null whenever the trainer must not be driven. */
  target(): number | null {
    if (this.status !== 'playing') return null;
    const ramp = Math.min(1, 0.5 + 0.5 * this.sinceResume / RESUME_RAMP_SECONDS);
    return Math.round(Math.min(this.maxPowerW, Math.max(0, powerAt(this.step, this.stepElapsed) * this.intensity * ramp)));
  }
  start(now: number) { if (this.status !== 'idle') return; this.status = 'playing'; this.lastTick = now; this.sinceResume = 0; }
  pause(reason: PauseReason = 'user') { if (this.status === 'playing') { this.status = 'paused'; this.pauseReason = reason; } }
  resume(now: number) { if (this.status === 'paused') { this.status = 'playing'; this.pauseReason = null; this.lastTick = now; this.sinceResume = 0; } }
  /** Jump to the next block (or finish). Allowed while playing or paused. */
  skip() {
    if (this.status === 'idle' || this.status === 'finished') return;
    this.elapsed += this.remainingInStep; this.stepIndex++; this.stepElapsed = 0; this.sinceResume = 0;
    if (this.stepIndex >= this.workout.steps.length) this.status = 'finished';
  }
  adjust(delta: number) { this.intensity = Math.round(Math.min(1.2, Math.max(0.5, this.intensity + delta)) * 100) / 100; }
  /** Latest measurement from the trainer or power meter. Missing values stay null. */
  measure(powerW: number | undefined, cadenceRpm: number | undefined, at: number) { this.latest = { powerW: powerW ?? null, cadenceRpm: cadenceRpm ?? null, at }; }

  /** Advance to wall-clock `now`. Whole seconds are consumed; one sample is recorded per active second. */
  tick(now: number) {
    if (this.status !== 'playing') return;
    const gap = now - this.lastTick;
    if (gap > MAX_TICK_GAP_MS) { this.lastTick = now; this.pause('clock_gap'); return; }
    let seconds = Math.floor(gap / 1000);
    this.lastTick += seconds * 1000;
    while (seconds-- > 0 && this.status === 'playing') {
      const fresh = now - this.latest.at <= 3000;      // a stale reading is not repeated as if it were measured
      this.samples.push({ t: this.elapsed, powerW: fresh ? this.latest.powerW : null, cadenceRpm: fresh ? this.latest.cadenceRpm : null, targetW: this.target() });
      this.elapsed++; this.stepElapsed++; this.sinceResume++;
      if (this.stepElapsed >= this.step.seconds) { this.stepIndex++; this.stepElapsed = 0; if (this.stepIndex >= this.workout.steps.length) this.status = 'finished'; }
    }
  }

  /** What was actually measured. Seconds without a reading are counted as missing, never as zero watts. */
  summary(): { activeSeconds: number; averagePowerW?: number; cadenceMeanRpm?: number; powerSummary?: PowerSummary } {
    const power = this.samples.map(s => s.powerW).filter((p): p is number => p !== null);
    const cadence = this.samples.map(s => s.cadenceRpm).filter((c): c is number => c !== null);
    if (!power.length) return { activeSeconds: this.samples.length };
    const mean = power.reduce((a, b) => a + b, 0) / power.length;
    return { activeSeconds: this.samples.length, averagePowerW: Math.round(mean * 10) / 10,
      cadenceMeanRpm: cadence.length ? Math.round(cadence.reduce((a, b) => a + b, 0) / cadence.length) : undefined,
      powerSummary: { recordedSeconds: power.length, missingSeconds: this.samples.length - power.length, meanW: Math.round(mean * 100) / 100,
        sumSquaresW2s: Math.round(power.reduce((a, b) => a + b * b, 0) * 10) / 10 } };
  }
}
