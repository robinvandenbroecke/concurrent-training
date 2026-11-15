import type { AthleteProfile, EquipmentTag, LiftType, PlannedExercise, PlannedTraining } from '../types';

export type Powerlift = 'squat' | 'bench' | 'deadlift';
export type Muscle = 'quadriceps' | 'posterior' | 'chest' | 'back' | 'shoulders';
export type Pattern = 'squat' | 'hinge' | 'single_leg' | 'push_h' | 'push_v' | 'pull_h' | 'pull_v' | 'isolation' | 'power_catch' | 'power_pull' | 'power_overhead' | 'jump';
export const PATTERN_LABELS: Record<Pattern, string> = { squat: 'Kniebuiging', hinge: 'Heupscharnier', single_leg: 'Eenbenig', push_h: 'Horizontaal drukken', push_v: 'Verticaal drukken',
  pull_h: 'Horizontaal trekken', pull_v: 'Verticaal trekken', isolation: 'Geïsoleerd', power_catch: 'Olympisch met opvang', power_pull: 'Explosieve trek', power_overhead: 'Explosief boven het hoofd', jump: 'Sprong' };
export const EQUIPMENT_LABELS: Record<EquipmentTag, string> = { halter: 'Halter met schijven', rek: 'Squatrek', bank: 'Bank', dumbbells: 'Dumbbells', kettlebell: 'Kettlebell',
  machines: 'Machines', kabel: 'Kabelstation', optrekstang: 'Optrekstang', bumpers: 'Bumperschijven en hefvloer', trapbar: 'Trap bar' };
export interface ExerciseDefinition {
  /** Movement pattern: the basis for alternatives and for programme slots. */
  pattern: Pattern;
  /** Equipment: any ONE of these sets is enough. An empty set means no equipment. */
  needs: EquipmentTag[][];
  /** 1 = basic, 2 = needs practice or instruction, 3 = catch or jerk: only with confirmed weightlifting experience. */
  technique: 1 | 2 | 3;
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
  // Variants for limited equipment (November 2026). A logged weight never carries over from another variant.
  ['goblet_squat','Goblet squat','Accessoires','Dumbbells','other',['quadriceps'],['posterior'],{reps:8,cue:'Eén dumbbell of kettlebell voor de borst; noteer dat gewicht.'}],
  ['db_romanian_deadlift','Dumbbell Romanian deadlift','Accessoires','Dumbbells','other',['posterior'],['back'],{reps:8,cue:'Noteer het gewicht per dumbbell.'}],
  ['db_bench_press','Dumbbell bankdrukken','Accessoires','Dumbbells','other',['chest'],['shoulders'],{reps:8,cue:'Noteer het gewicht per dumbbell.'}],
  ['db_floor_press','Dumbbell floor press','Accessoires','Dumbbells','other',['chest'],['shoulders'],{reps:8,cue:'Liggend op de vloer; noteer het gewicht per dumbbell.'}],
  ['db_shoulder_press','Dumbbell schouderdrukken','Accessoires','Dumbbells','other',['shoulders'],[],{reps:8,cue:'Noteer het gewicht per dumbbell.'}],
  ['machine_chest_press','Chest press (machine)','Accessoires','Machine/kabel','other',['chest'],['shoulders']],
  ['machine_shoulder_press','Shoulder press (machine)','Accessoires','Machine/kabel','other',['shoulders'],[]],
  ['leg_extension','Leg extension','Accessoires','Machine/kabel','other',['quadriceps'],[],{reps:10,rest:90}],
  ['back_extension','Back extension','Accessoires','Machine/kabel','other',['posterior'],['back'],{load:'bodyweight',reps:10,rest:90}],
  ['inverted_row','Inverted row','Accessoires','Lichaamsgewicht','other',['back'],[],{load:'bodyweight',reps:8,cue:'Onder een lage stang in het rek; maak het zwaarder door de voeten hoger te zetten.'}],
  ['pike_push_up','Pike push-up','Accessoires','Lichaamsgewicht','other',['shoulders'],['chest'],{load:'bodyweight',reps:8}],
  ['bodyweight_squat','Squat zonder gewicht','Accessoires','Lichaamsgewicht','other',['quadriceps'],['posterior'],{load:'bodyweight',reps:15,rest:90}],
  ['bodyweight_split_squat','Split squat zonder gewicht','Accessoires','Lichaamsgewicht','other',['quadriceps'],['posterior'],{load:'bodyweight',reps:10,rest:90,cue:'Reps per been; verhoog de achterste voet om het zwaarder te maken.'}],
  ['single_leg_rdl','Eenbenige Romanian deadlift','Accessoires','Lichaamsgewicht','other',['posterior'],[],{load:'bodyweight',reps:10,rest:90,cue:'Reps per been; beheerst, heup recht houden.'}],
  ['single_leg_glute_bridge','Eenbenige glute bridge','Accessoires','Lichaamsgewicht','other',['posterior'],[],{load:'bodyweight',reps:12,rest:90,cue:'Reps per been.'}],
  ['kettlebell_swing','Kettlebell swing','Accessoires','Dumbbells','other',[],[],{power:true,reps:8,cue:'Explosief vanuit de heup; stop zodra de snelheid afneemt.'}],
];
type Meta = [Pattern, EquipmentTag[][], 1 | 2 | 3];
const BAR: EquipmentTag[][] = [['halter']], RACK: EquipmentTag[][] = [['halter', 'rek']], BENCH: EquipmentTag[][] = [['halter', 'rek', 'bank']];
const FREE: EquipmentTag[][] = [['dumbbells'], ['kettlebell']], NONE: EquipmentTag[][] = [[]], LIFTING: EquipmentTag[][] = [['halter', 'bumpers']];
const META: Record<string, Meta> = {
  back_squat: ['squat', RACK, 1], bench_press: ['push_h', BENCH, 1], deadlift: ['hinge', BAR, 1], sumo_deadlift: ['hinge', BAR, 1], paused_bench: ['push_h', BENCH, 1],
  paused_squat: ['squat', RACK, 1], front_squat: ['squat', RACK, 2], romanian_deadlift: ['hinge', BAR, 1], trap_bar_deadlift: ['hinge', [['trapbar']], 1], close_grip_bench: ['push_h', BENCH, 1],
  incline_db_press: ['push_h', [['dumbbells', 'bank']], 1], overhead_press: ['push_v', BAR, 1], barbell_row: ['pull_h', BAR, 1], db_row: ['pull_h', FREE, 1],
  chest_supported_row: ['pull_h', [['machines']], 1], cable_row: ['pull_h', [['kabel']], 1], pull_up: ['pull_v', [['optrekstang']], 1], assisted_pull_up: ['pull_v', [['machines']], 1],
  lat_pulldown: ['pull_v', [['kabel'], ['machines']], 1], split_squat: ['single_leg', FREE, 1], step_up: ['single_leg', FREE, 1], leg_press: ['squat', [['machines']], 1],
  leg_curl: ['isolation', [['machines']], 1], hip_thrust: ['hinge', [['halter', 'bank']], 1], push_up: ['push_h', NONE, 1], lateral_raise: ['isolation', [['dumbbells'], ['kabel']], 1],
  face_pull: ['isolation', [['kabel']], 1], power_clean: ['power_catch', LIFTING, 3], hang_power_clean: ['power_catch', LIFTING, 3], clean: ['power_catch', LIFTING, 3],
  clean_pull: ['power_pull', BAR, 2], hang_clean_pull: ['power_pull', BAR, 2], clean_high_pull: ['power_pull', BAR, 2], jump_shrug: ['power_pull', BAR, 2],
  power_snatch: ['power_catch', LIFTING, 3], hang_power_snatch: ['power_catch', LIFTING, 3], snatch_pull: ['power_pull', BAR, 2], push_press: ['power_overhead', BAR, 2],
  push_jerk: ['power_overhead', LIFTING, 3], split_jerk: ['power_overhead', LIFTING, 3], countermovement_jump: ['jump', NONE, 1], broad_jump: ['jump', NONE, 1],
  goblet_squat: ['squat', FREE, 1], db_romanian_deadlift: ['hinge', FREE, 1], db_bench_press: ['push_h', [['dumbbells', 'bank']], 1], db_floor_press: ['push_h', FREE, 1],
  db_shoulder_press: ['push_v', FREE, 1], machine_chest_press: ['push_h', [['machines']], 1], machine_shoulder_press: ['push_v', [['machines']], 1], leg_extension: ['isolation', [['machines']], 1],
  back_extension: ['hinge', [['machines']], 1], inverted_row: ['pull_h', RACK, 1], pike_push_up: ['push_v', NONE, 1], bodyweight_squat: ['squat', NONE, 1],
  bodyweight_split_squat: ['single_leg', NONE, 1], single_leg_rdl: ['hinge', NONE, 1], single_leg_glute_bridge: ['hinge', NONE, 1], kettlebell_swing: ['power_pull', [['kettlebell']], 2],
};
export const EXERCISES: ExerciseDefinition[] = entries.map(([id,name,category,equipment,lift,primary,secondary,extra]) => ({
  id,name,category,equipment,lift,primary,secondary,pattern:META[id][0],needs:META[id][1],technique:META[id][2],load:'weight',reps:extra?.power?2:8,rest:extra?.power?120:180,rpe:extra?.power?6:7,
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

/** Can this exercise be done with the stated equipment? */
export function available(d: ExerciseDefinition, equipment: EquipmentTag[]): boolean {
  return d.needs.some(set => set.every(tag => equipment.includes(tag)));
}
/** Same movement pattern, possible with the equipment, within the technique level. The original is excluded. */
export function alternatives(id: string, equipment: EquipmentTag[], maxTechnique: 1 | 2 | 3 = 2): ExerciseDefinition[] {
  const d = EXERCISES.find(e => e.id === id);
  if (!d) return [];
  return EXERCISES.filter(e => e.id !== id && e.pattern === d.pattern && !!e.power === !!d.power && e.technique <= maxTechnique && available(e, equipment));
}
