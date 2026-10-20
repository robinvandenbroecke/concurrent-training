// Demo data – fictiefe gegevens voor preview zonder backend
import type {
  AthleteProfile, WeekDay, WorkoutSession, ReadinessData, PlannedTraining, TrendPoint
} from '../types';

export const DEMO_PROFILE: AthleteProfile = {
  name: 'Demo Atleet',
  priority: 'balans',
  experienceYears: 3,
  availableDays: [1, 3, 5, 6], // ma, wo, vr, za
  sessionDurationMinutes: 60,
  hasVbt: false,
  hasStravaSync: false,
  capacities: {
    squat: 100,
    bench: 75,
    deadlift: 130,
    press: 55,
  },
  onboardingComplete: true,
};

export const LIFT_NAMES: Record<string, string> = {
  squat: 'Kniebuiging',
  bench: 'Bankdrukken',
  deadlift: 'Deadlift',
  press: 'Schouderdrukken',
  power_clean: 'Power Clean',
  clean: 'Clean',
  other: 'Overig',
};

export const SPORT_NAMES: Record<string, string> = {
  running: 'Hardlopen',
  cycling: 'Fietsen',
  swimming: 'Zwemmen',
  other: 'Overig',
};

export const INTENSITY_NAMES: Record<string, string> = {
  z2: 'Zone 2',
  hiit: 'HIIT',
  tempo: 'Tempo',
  threshold: 'Drempel',
  long: 'Lang duur',
  easy: 'Rustig',
  other: 'Overig',
};

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function dateStr(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export const DEMO_READINESS: ReadinessData = {
  overall: 0.82,
  per_lift: {
    squat: 0.85,
    bench: 0.90,
    deadlift: 0.78,
    press: 0.88,
  },
  endurance: 0.80,
  explanations: [
    'Lokale vermoeidheid kniebuiging: licht verhoogd (2 dagen geleden zware sessie)',
    'Systemische vermoeidheid: normaal',
    'Structurele belasting benen: laag',
  ],
  assessment_status: 'demo_schatting',
};

export const DEMO_TODAY: PlannedTraining = {
  date: todayStr(),
  type: 'kracht',
  title: 'Kracht – bovenkant',
  durationMinutes: 55,
  reason: 'Kniebuiging heeft nog herstel nodig na woensdag.',
  exercises: [
    {
      lift: 'bench',
      displayName: 'Bankdrukken',
      sets: [
        { setNum: 1, weight: 60, targetReps: 5, restSec: 120 },
        { setNum: 2, weight: 65, targetReps: 5, restSec: 180 },
        { setNum: 3, weight: 70, targetReps: 4, restSec: 180 },
        { setNum: 4, weight: 70, targetReps: 4, restSec: 180 },
      ],
    },
    {
      lift: 'press',
      displayName: 'Schouderdrukken',
      sets: [
        { setNum: 1, weight: 40, targetReps: 8, restSec: 90 },
        { setNum: 2, weight: 42.5, targetReps: 8, restSec: 90 },
        { setNum: 3, weight: 42.5, targetReps: 8, restSec: 90 },
      ],
    },
  ],
};

export const DEMO_WEEK_DAYS: WeekDay[] = (() => {
  const today = new Date();
  const dayOfWeek = today.getDay();
  // Start from Monday of this week
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));

  const DAY_NAMES = ['zo', 'ma', 'di', 'wo', 'do', 'vr', 'za'];
  const days: WeekDay[] = [];

  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const ds = d.toISOString().slice(0, 10);
    const dow = d.getDay();
    const isToday = ds === todayStr();
    const isPast = d < today && !isToday;

    let planned: PlannedTraining | undefined;
    let completed: WorkoutSession | undefined;

    if (dow === 1) { // maandag
      planned = { date: ds, type: 'kracht', title: 'Kracht – bovenkant', durationMinutes: 55 };
      if (isPast) completed = {
        date: ds, type: 'kracht', title: 'Kracht – bovenkant', durationMinutes: 52,
        savedToServer: false,
        exercises: [{
          lift: 'bench', displayName: 'Bankdrukken',
          sets: [
            { setNum: 1, weight: 65, targetReps: 5, completedReps: 5, velocities: [null, null, null, null, null] },
            { setNum: 2, weight: 67.5, targetReps: 5, completedReps: 5, velocities: [] },
          ]
        }],
      };
    }
    if (dow === 3) { // woensdag
      planned = { date: ds, type: 'duur', title: 'Zone 2 hardlopen', durationMinutes: 45,
        endurance: { sport: 'running', durationMinutes: 45, intensityType: 'z2', description: '45 min rustig hardlopen' }
      };
      if (isPast) completed = { date: ds, type: 'duur', title: 'Zone 2 hardlopen', durationMinutes: 45, savedToServer: false };
    }
    if (dow === 5) { // vrijdag
      if (isToday) {
        planned = DEMO_TODAY;
      } else if (isPast) {
        planned = { date: ds, type: 'kracht', title: 'Kracht – onderkant', durationMinutes: 60 };
        completed = {
          date: ds, type: 'kracht', title: 'Kracht – onderkant', durationMinutes: 58, savedToServer: false,
          exercises: [{
            lift: 'squat', displayName: 'Kniebuiging',
            sets: [
              { setNum: 1, weight: 80, targetReps: 5, completedReps: 5, velocities: [] },
              { setNum: 2, weight: 85, targetReps: 5, completedReps: 5, velocities: [] },
              { setNum: 3, weight: 90, targetReps: 4, completedReps: 3, velocities: [], note: 'Moe' },
            ]
          }],
        };
      } else {
        planned = DEMO_TODAY;
      }
    }
    if (dow === 6) { // zaterdag
      planned = { date: ds, type: 'duur', title: 'Lange duurrit', durationMinutes: 90,
        endurance: { sport: 'cycling', durationMinutes: 90, intensityType: 'long', description: '90 min fietsen, rustig tempo' }
      };
    }

    days.push({
      date: ds,
      dayLabel: `${DAY_NAMES[dow]} ${d.getDate()}/${d.getMonth() + 1}`,
      dayName: DAY_NAMES[dow],
      planned,
      completed,
      isToday,
      isPast,
    });
  }
  return days;
})();

export function getDemoHistory(): WorkoutSession[] {
  const sessions: WorkoutSession[] = [];
  for (let i = 1; i <= 21; i++) {
    const dow = new Date(dateStr(-i)).getDay();
    if (dow === 1 && i <= 14) {
      sessions.push({
        date: dateStr(-i), type: 'kracht', title: 'Kracht – bovenkant',
        durationMinutes: 50 + Math.round(Math.random() * 15), savedToServer: false,
        exercises: [{
          lift: 'bench', displayName: 'Bankdrukken',
          sets: [
            { setNum: 1, weight: 62.5 + (i > 7 ? 0 : 2.5), targetReps: 5, completedReps: 5, velocities: [] },
            { setNum: 2, weight: 67.5 + (i > 7 ? 0 : 2.5), targetReps: 5, completedReps: 5, velocities: [] },
          ],
        }],
      });
    }
    if (dow === 5 && i <= 14) {
      sessions.push({
        date: dateStr(-i), type: 'kracht', title: 'Kracht – onderkant',
        durationMinutes: 55 + Math.round(Math.random() * 10), savedToServer: false,
        exercises: [{
          lift: 'squat', displayName: 'Kniebuiging',
          sets: [
            { setNum: 1, weight: 82.5 + (i > 7 ? 0 : 5), targetReps: 5, completedReps: 5, velocities: [] },
            { setNum: 2, weight: 87.5 + (i > 7 ? 0 : 5), targetReps: 4, completedReps: 4, velocities: [] },
          ],
        }],
      });
    }
    if ((dow === 3 || dow === 6) && i <= 14) {
      sessions.push({
        date: dateStr(-i), type: 'duur', title: dow === 3 ? 'Zone 2' : 'Lange duurrit',
        durationMinutes: dow === 3 ? 45 : 90, savedToServer: false,
      });
    }
  }
  return sessions.sort((a, b) => b.date.localeCompare(a.date));
}

export function getDemoTrend(lift: string, days: number = 30): TrendPoint[] {
  const baseCapacity: Record<string, number> = {
    squat: 100, bench: 75, deadlift: 130, press: 55,
  };
  const base = baseCapacity[lift] || 80;
  const points: TrendPoint[] = [];
  for (let i = days; i >= 0; i -= 3) {
    const progress = (days - i) / days;
    const noise = (Math.random() - 0.5) * 3;
    points.push({
      date: dateStr(-i),
      value: Math.round((base + progress * 8 + noise) * 10) / 10,
      isEstimate: i < 7,
    });
  }
  return points;
}
