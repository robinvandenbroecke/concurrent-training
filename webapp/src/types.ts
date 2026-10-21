// Canonical types matching backend schemas

export type LiftType = 'squat' | 'bench' | 'deadlift' | 'press' | 'power_clean' | 'clean' | 'other';
export type EnduranceSport = 'running' | 'cycling' | 'swimming' | 'other';
export type IntensityType = 'z2' | 'hiit' | 'tempo' | 'threshold' | 'long' | 'easy' | 'other';
export type Priority = 'kracht' | 'duur' | 'balans';

export interface RepData {
  weight: number;
  velocity?: number;
  rep_num: number;
  rest_before: number;
}

export interface SetData {
  weight: number;
  target_reps: number;
  reps: RepData[];
  rest_before_sec?: number;
  set_end_rpe?: number;
}

export interface PlannedSet {
  setNum: number;
  weight: number;
  targetReps: number;
  restSec: number;
  note?: string;
  targetRpe?: number;
  kind?: 'work' | 'warmup';
}

export interface PlannedExercise {
  id?: string;
  exerciseId?: string;
  lift: LiftType;
  displayName: string;
  sets: PlannedSet[];
}

export interface PlannedTraining {
  date: string;
  type: 'kracht' | 'duur' | 'rust';
  title: string;
  durationMinutes: number;
  reason?: string;
  exercises?: PlannedExercise[];
  endurance?: PlannedEndurance;
}

export interface PlannedEndurance {
  sport: EnduranceSport;
  durationMinutes: number;
  intensityType: IntensityType;
  description: string;
}

export interface WorkoutSession {
  id?: number | string;
  date: string;
  type: 'kracht' | 'duur';
  title: string;
  durationMinutes: number;
  savedToServer: boolean;
  // kracht
  exercises?: CompletedExercise[];
  // duur
  enduranceResult?: CompletedEndurance;
}

export interface CompletedExercise {
  id?: string;
  exerciseId?: string;
  lift: LiftType;
  displayName: string;
  sets: CompletedSet[];
}

export interface CompletedSet {
  setNum: number;
  weight: number;
  targetReps: number;
  completedReps: number;
  velocities: (number | null)[];
  rpe?: number;
  note?: string;
  kind?: 'work' | 'warmup';
}

export interface CompletedEndurance {
  sport: EnduranceSport;
  durationMinutes: number;
  intensityType: IntensityType;
  rpe?: number;
  averagePowerW?: number;
}

export interface ReadinessData {
  overall: number | null;
  per_lift: Record<string, number | null>;
  endurance: number | null;
  explanations: string[];
  assessment_status: string;
}

export interface WeekDay {
  date: string;
  dayLabel: string;
  dayName: string;
  planned?: PlannedTraining;
  completed?: WorkoutSession;
  isToday: boolean;
  isPast: boolean;
}

export interface TrendPoint {
  date: string;
  value: number;
  isEstimate: boolean;
}

export interface AthleteProfile {
  name: string;
  priority: Priority;
  experienceYears: number;
  availableDays: number[];  // 0=zo, 1=ma, ... 6=za
  sessionDurationMinutes: number;
  hasVbt: boolean;
  olympicExperience?: boolean;
  hasStravaSync: boolean;
  capacities: Partial<Record<LiftType, number>>;
  enduranceThreshold?: number;
  onboardingComplete: boolean;
}

export interface AppState {
  mode: 'demo' | 'backend';
  backendUrl: string;
  apiKey: string;
  athleteId: number | null;
  profile: AthleteProfile | null;
  activeTab: 'vandaag' | 'training' | 'week' | 'historie';
  onboardingStep: number;
}
