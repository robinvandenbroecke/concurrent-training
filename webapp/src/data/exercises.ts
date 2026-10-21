import type { AthleteProfile, LiftType, PlannedExercise, PlannedTraining } from '../types';

export type Powerlift = 'squat' | 'bench' | 'deadlift';
export type Muscle = 'quadriceps' | 'posterior' | 'chest' | 'back' | 'shoulders';
export interface ExerciseDefinition {
  id: string; name: string; category: 'Powerlifting' | 'Olympisch' | 'Accessoires' | 'Sprongen';
  equipment: 'Halter' | 'Dumbbells' | 'Machine/kabel' | 'Lichaamsgewicht';
  lift: LiftType; powerlift?: Powerlift; power?: boolean; catch?: boolean;
  load: 'weight' | 'bodyweight' | 'assistance';
  primary: Muscle[]; secondary: Muscle[];
  reps: number; rest: number; rpe: number; cue: string;
}
type Entry = [string, string, ExerciseDefinition['category'], ExerciseDefinition['equipment'], LiftType, Muscle[], Muscle[], Partial<ExerciseDefinition>?];
const entries: Entry[] = [
  ['back_squat','Back squat','Powerlifting','Halter','squat',['quadriceps'],['posterior'],{powerlift:'squat',reps:4}],
  ['bench_press','Bankdrukken','Powerlifting','Halter','bench',['chest'],['shoulders'],{powerlift:'bench',reps:5}],
  ['deadlift','Deadlift','Powerlifting','Halter','deadlift',['posterior'],['back'],{powerlift:'deadlift',reps:3}],
  ['sumo_deadlift','Sumo deadlift','Powerlifting','Halter','other',['posterior'],['quadriceps'],{powerlift:'deadlift',reps:3}],
  ['paused_bench','Bankdrukken met pauze','Powerlifting','Halter','other',['chest'],['shoulders'],{powerlift:'bench',reps:4}],
  ['paused_squat','Squat met pauze','Accessoires','Halter','other',['quadriceps'],['posterior'],{reps:4}],
  ['front_squat','Front squat','Accessoires','Halter','other',['quadriceps'],['posterior'],{reps:5}],
  ['romanian_deadlift','Romanian deadlift','Accessoires','Halter','other',['posterior'],['back'],{reps:6}],
  ['trap_bar_deadlift','Trap-bar deadlift','Accessoires','Halter','other',['posterior','quadriceps'],[],{reps:5}],
  ['close_grip_bench','Smal bankdrukken','Accessoires','Halter','other',['chest'],['shoulders'],{reps:6}],
  ['incline_db_press','Schuin dumbbell drukken','Accessoires','Dumbbells','other',['chest'],['shoulders']],
  ['overhead_press','Schouderdrukken','Accessoires','Halter','press',['shoulders'],['chest'],{reps:5}],
  ['barbell_row','Halterroeien','Accessoires','Halter','other',['back'],['posterior']],
  ['db_row','Dumbbell roeien','Accessoires','Dumbbells','other',['back'],[],{cue:'Reps per zijde; noteer het gewicht per dumbbell.'}],
  ['chest_supported_row','Borstgesteund roeien','Accessoires','Machine/kabel','other',['back'],[]],
  ['cable_row','Kabelroeien','Accessoires','Machine/kabel','other',['back'],[]],
  ['pull_up','Pull-up','Accessoires','Lichaamsgewicht','other',['back'],[],{load:'bodyweight',reps:6}],
  ['assisted_pull_up','Ondersteunde pull-up','Accessoires','Machine/kabel','other',['back'],[],{load:'assistance',reps:6,cue:'Voer ondersteuning positief in. Meer ondersteuning maakt de oefening lichter.'}],
  ['lat_pulldown','Lat pulldown','Accessoires','Machine/kabel','other',['back'],[]],
  ['split_squat','Split squat','Accessoires','Dumbbells','other',['quadriceps'],['posterior'],{cue:'Reps per been; gebruik steeds dezelfde gewichtsconventie.'}],
  ['step_up','Step-up','Accessoires','Dumbbells','other',['quadriceps'],['posterior'],{cue:'Reps per been; kies een hoogte met controle.'}],
  ['leg_press','Leg press','Accessoires','Machine/kabel','other',['quadriceps'],['posterior']],
  ['leg_curl','Leg curl','Accessoires','Machine/kabel','other',['posterior'],[]],
  ['hip_thrust','Hip thrust','Accessoires','Halter','other',['posterior'],[]],
  ['push_up','Push-up','Accessoires','Lichaamsgewicht','other',['chest'],['shoulders'],{load:'bodyweight'}],
  ['lateral_raise','Zijwaarts heffen','Accessoires','Dumbbells','other',['shoulders'],[],{reps:10,rest:90}],
  ['face_pull','Face pull','Accessoires','Machine/kabel','other',['shoulders'],['back'],{reps:10,rest:90}],
  ['power_clean','Power clean','Olympisch','Halter','power_clean',[],[],{power:true,catch:true}],
  ['hang_power_clean','Hang power clean','Olympisch','Halter','other',[],[],{power:true,catch:true}],
  ['clean','Clean','Olympisch','Halter','clean',[],[],{power:true,catch:true}],
  ['clean_pull','Clean pull','Olympisch','Halter','other',[],[],{power:true,cue:'Geen opvang. Leer de posities en versnel de halter; stop bij techniekverlies.'}],
  ['hang_clean_pull','Hang clean pull','Olympisch','Halter','other',[],[],{power:true,cue:'Trek vanuit de hang, zonder opvang; technische instructie blijft nodig.'}],
  ['clean_high_pull','Clean high pull','Olympisch','Halter','other',[],[],{power:true}],
  ['jump_shrug','Jump shrug','Olympisch','Halter','other',[],[],{power:true}],
  ['power_snatch','Power snatch','Olympisch','Halter','other',[],[],{power:true,catch:true}],
  ['hang_power_snatch','Hang power snatch','Olympisch','Halter','other',[],[],{power:true,catch:true}],
  ['snatch_pull','Snatch pull','Olympisch','Halter','other',[],[],{power:true}],
  ['push_press','Push press','Olympisch','Halter','other',[],[],{power:true}],
  ['push_jerk','Push jerk','Olympisch','Halter','other',[],[],{power:true,catch:true}],
  ['split_jerk','Split jerk','Olympisch','Halter','other',[],[],{power:true,catch:true}],
  ['countermovement_jump','Countermovement jump','Sprongen','Lichaamsgewicht','other',[],[],{power:true,load:'bodyweight',cue:'Elke sprong apart. Land gecontroleerd en stop als hoogte of landing verslechtert.'}],
  ['broad_jump','Standver springen','Sprongen','Lichaamsgewicht','other',[],[],{power:true,load:'bodyweight',cue:'Volledig herstel tussen sprongen; stabiele landing.'}],
];
export const EXERCISES: ExerciseDefinition[] = entries.map(([id,name,category,equipment,lift,primary,secondary,extra]) => ({
  id,name,category,equipment,lift,primary,secondary,load:'weight',reps:extra?.power?2:8,rest:extra?.power?120:180,rpe:extra?.power?6:7,
  cue:extra?.power?'Korte, snelle sets. Stop bij techniek- of snelheidsverlies; geen geforceerde reps.':'Gebruik een volledige, beheerste bewegingsuitslag en houd herhalingen over.',...extra,
}));
export const LEGACY_EXERCISES: Partial<Record<LiftType,string>> = {squat:'back_squat',bench:'bench_press',deadlift:'deadlift',press:'overhead_press',power_clean:'power_clean',clean:'clean'};
export function definition(ex: {exerciseId?:string;lift:LiftType}): ExerciseDefinition | undefined {
  return EXERCISES.find(d => d.id === (ex.exerciseId ?? LEGACY_EXERCISES[ex.lift]));
}
export function normalizePlan(plan: PlannedTraining): PlannedTraining {
  return {...plan,exercises:plan.exercises?.map((ex,i)=>({...ex,id:ex.id ?? `${plan.date}:${i}:${ex.exerciseId ?? ex.lift}`,exerciseId:ex.exerciseId ?? LEGACY_EXERCISES[ex.lift]}))};
}
export function createExercise(exerciseId:string, profile?:AthleteProfile, id:string=crypto.randomUUID(), sets=3): PlannedExercise {
  const d=EXERCISES.find(d=>d.id===exerciseId);
  if(!d) throw new Error('Onbekende oefening.');
  const weight=LEGACY_EXERCISES[d.lift]===d.id ? profile?.capacities[d.lift] ?? 0 : 0;
  return {id,exerciseId,lift:d.lift,displayName:d.name,sets:Array.from({length:sets},(_,i)=>({setNum:i+1,weight,targetReps:d.reps,restSec:d.rest,targetRpe:d.rpe,kind:'work',note:d.cue}))};
}
