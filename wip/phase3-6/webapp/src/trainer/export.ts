/**
 * Workout files for external players when direct trainer control is not available.
 *  - ZWO: targets as a fraction of the FTP configured in the player (set it to the reference shown in the file).
 *  - ERG: absolute watts against minutes.  - MRC: percent of the reference against minutes.
 * These are text formats read by common indoor-training players; compatibility with a specific player is not guaranteed.
 */
import { type BikeWorkout, type Step } from './workout';

const esc = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const frac = (w: number, ref: number) => (w / ref).toFixed(3);

export function toZwo(workout: BikeWorkout): string {
  const ref = workout.reference.powerW;
  const element = (s: Step) => s.endPowerW === undefined
    ? `    <SteadyState Duration="${s.seconds}" Power="${frac(s.powerW, ref)}"/>`
    : `    <${s.kind === 'cooldown' ? 'Cooldown' : s.kind === 'warmup' ? 'Warmup' : 'Ramp'} Duration="${s.seconds}" PowerLow="${frac(s.powerW, ref)}" PowerHigh="${frac(s.endPowerW, ref)}"/>`;
  return ['<?xml version="1.0" encoding="UTF-8"?>', '<workout_file>', '  <author>Concurrent Training</author>',
    `  <name>${esc(workout.title)}</name>`,
    `  <description>${esc(`Referentievermogen ${Math.round(ref)} W: stel dit in als FTP in je speler. ${workout.assumptions.join(' ')}`)}</description>`,
    '  <sportType>bike</sportType>', '  <workout>', ...workout.steps.map(element), '  </workout>', '</workout_file>', ''].join('\n');
}

function course(workout: BikeWorkout, percent: boolean): string {
  const ref = workout.reference.powerW, rows: string[] = [];
  let minute = 0;
  const value = (w: number) => percent ? (100 * w / ref).toFixed(1) : String(Math.round(w));
  for (const s of workout.steps) {
    rows.push(`${minute.toFixed(2)}\t${value(s.powerW)}`);
    minute += s.seconds / 60;
    rows.push(`${minute.toFixed(2)}\t${value(s.endPowerW ?? s.powerW)}`);
  }
  return ['[COURSE HEADER]', 'VERSION = 2', 'UNITS = ENGLISH', `DESCRIPTION = ${workout.title.replace(/[\r\n]/g, ' ')}`,
    `FILE NAME = ${workout.id}`, ...(percent ? [] : [`FTP = ${Math.round(ref)}`]), `MINUTES ${percent ? 'PERCENT' : 'WATTS'}`,
    '[END COURSE HEADER]', '[COURSE DATA]', ...rows, '[END COURSE DATA]', ''].join('\r\n');
}
export const toErg = (workout: BikeWorkout) => course(workout, false);
export const toMrc = (workout: BikeWorkout) => course(workout, true);
