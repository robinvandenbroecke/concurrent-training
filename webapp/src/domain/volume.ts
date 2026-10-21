import type { AthleteProfile, CompletedExercise, CompletedSet, PlannedExercise, PlannedTraining, WeekDay, WorkoutSession } from '../types';
import { definition, type Muscle, type Powerlift } from '../data/exercises';
export type CompletedMap=Record<string,CompletedSet[]>;
export type VolumeTargets=Record<Powerlift,{min:number;max:number}>;
// Adjustable coaching starting points, NOT validated personal minimum/maximum recoverable volumes.
export const DEFAULT_TARGETS:VolumeTargets={squat:{min:3,max:8},bench:{min:4,max:10},deadlift:{min:2,max:6}};
export const LIFT_LABELS:Record<Powerlift,string>={squat:'Squat',bench:'Bankdrukken',deadlift:'Deadlift'};
export const MUSCLE_LABELS:Record<Muscle,string>={quadriceps:'Quadriceps',posterior:'Heupstrekkers/hamstrings',chest:'Borst',back:'Rug',shoulders:'Schouders'};
export interface VolumeCount { lifts:Record<Powerlift,number>; muscles:Record<Muscle,number>; workSets:number;powerReps:number;unknownRpe:number;lightSets:number;unknownExercises:number; }
function empty():VolumeCount{return{lifts:{squat:0,bench:0,deadlift:0},muscles:{quadriceps:0,posterior:0,chest:0,back:0,shoulders:0},workSets:0,powerReps:0,unknownRpe:0,lightSets:0,unknownExercises:0};}
type SetDose={reps:number;rpe?:number;kind?:'work'|'warmup'};
function countSet(result:VolumeCount,ex:PlannedExercise|CompletedExercise,s:SetDose) {
  if(s.kind==='warmup'||s.reps<=0)return;
  const d=definition(ex);
  if(d?.power){result.powerReps+=s.reps;return;}
  result.workSets++;
  if(s.rpe===undefined)result.unknownRpe++;
  if(!d){result.unknownExercises++;return;}
  if(d.powerlift)result.lifts[d.powerlift]++;
  // Low-effort specific practice still counts as powerlift work, but not as a harder muscle-set proxy.
  if(s.rpe!==undefined&&s.rpe<6){result.lightSets++;return;}
  for(const muscle of d.primary)result.muscles[muscle]++;
  for(const muscle of d.secondary)if(!d.primary.includes(muscle))result.muscles[muscle]+=.5;
}
export function countCompleted(exercises:CompletedExercise[]):VolumeCount {
  const result=empty();for(const ex of exercises)for(const s of ex.sets)countSet(result,ex,{reps:s.completedReps,rpe:s.rpe,kind:s.kind});return result;
}
export function countPlan(plan:PlannedTraining,completed:CompletedMap={}):VolumeCount {
  const result=empty();for(const ex of plan.exercises??[])for(const s of ex.sets){
    const done=completed[ex.id??'']?.find(c=>c.setNum===s.setNum);
    countSet(result,ex,done?{reps:done.completedReps,rpe:done.rpe,kind:done.kind}:{reps:s.targetReps,rpe:s.targetRpe,kind:s.kind});
  }return result;
}
function add(to:VolumeCount,from:VolumeCount){
  for(const l of Object.keys(to.lifts) as Powerlift[])to.lifts[l]+=from.lifts[l];
  for(const m of Object.keys(to.muscles) as Muscle[])to.muscles[m]+=from.muscles[m];
  for(const k of ['workSets','powerReps','unknownRpe','lightSets','unknownExercises'] as const)to[k]+=from[k];
}
export function estimatedMinutes(plan:PlannedTraining):number {
  let seconds=8*60;
  for(const ex of plan.exercises??[]) {
    seconds+=60+(definition(ex)?.powerlift?180:0);
    ex.sets.forEach((s,i)=>{seconds+=Math.max(0,s.targetReps)*(definition(ex)?.power?6:4)+(i<ex.sets.length-1?Math.max(0,s.restSec):0);});
  }return Math.ceil(seconds/60);
}
export function weeklyProjection(plan:PlannedTraining,week:WeekDay[],sessions:WorkoutSession[],completed:CompletedMap={},sessionId?:string) {
  const dates=week.map(d=>d.date), actual=empty(),projected=empty();
  const records=sessions.filter(s=>dates.includes(s.date)&&s.id!==sessionId);
  for(const s of records)add(actual,countCompleted(s.exercises??[]));
  add(projected,actual);
  for(const day of week)if(day.date!==plan.date&&!day.isPast&&day.planned&&!records.some(s=>s.date===day.date))add(projected,countPlan(day.planned));
  const current=countPlan(plan,completed);add(projected,current);
  return {actual,projected,current};
}
export function volumeAdvice(plan:PlannedTraining,week:WeekDay[],sessions:WorkoutSession[],profile:AthleteProfile,targets=DEFAULT_TARGETS,completed:CompletedMap={},sessionId?:string,muscleAlert=16) {
  const counts=weeklyProjection(plan,week,sessions,completed,sessionId),messages:string[]=[];
  const minutes=estimatedMinutes(plan);
  if(minutes>plan.durationMinutes)messages.push(`Mogelijk te veel voor je tijd: circa ${minutes} min tegenover ${plan.durationMinutes} min beschikbaar. Verkort eerst accessoires; behoud rust voor zware sets.`);
  if(counts.current.powerReps>24)messages.push('Veel explosieve reps in deze sessie (>24). Verminder eerst reps/sets als snelheid of techniek afneemt. Dit is een praktische signaalgrens, geen veiligheidslimiet.');
  if(counts.current.powerReps===0)messages.push('Geen explosief blok gepland. Voor je atletische doel kun je een kort techniek- of sprongblok overwegen; vervang zo nodig accessoires in plaats van steeds volume toe te voegen.');
  if((plan.exercises??[]).some(e=>definition(e)?.power&&e.sets.some(s=>s.targetReps>5||(s.targetRpe??0)>7)))messages.push('Explosieve oefening met lange of zware sets: kies korte sets en stop ruim vóór falen.');
  if((plan.exercises??[]).some(e=>definition(e)?.catch)&&!profile.olympicExperience)messages.push('Deze training bevat een opvangbeweging. Kies bij onvoldoende techniekervaring een pull zonder opvang of een eenvoudige sprong, en vraag technische begeleiding.');
  const missing=(plan.exercises??[]).filter(e=>definition(e)?.load!=='bodyweight'&&e.sets.some(s=>s.weight===0)).length;
  if(missing)messages.push(`${missing} oefening(en) zonder gekozen werkgewicht. Stel dit zelf in; een gewicht uit een andere oefening wordt niet overgenomen.`);
  const highRpe=Object.values(completed).flat().filter(s=>s.kind!=='warmup'&&(s.rpe??0)>=9).length;
  if(highRpe)messages.push(`${highRpe} uitgevoerde set(s) op RPE 9–10. Wees terughoudend met extra zware sets en controleer techniek en herstel.`);
  if(counts.projected.unknownRpe)messages.push(`RPE ontbreekt bij ${counts.projected.unknownRpe} set(s). Die tellen voorlopig mee; hun inspanningsgraad is onbekend.`);
  if(counts.projected.unknownExercises)messages.push('Oude of onbekende oefeningen tellen mee als werkset, maar konden niet aan een specifieke lift of spiergroep worden toegewezen.');
  for(const [muscle,sets] of Object.entries(counts.projected.muscles))if(sets>muscleAlert)messages.push(`Veel werk voor ${MUSCLE_LABELS[muscle as Muscle]}: ${sets} fractionele sets, boven je signaalgrens ${muscleAlert}. Controleer of extra sets nog zinvol zijn; dit is geen gemeten herstelgrens.`);
  if(week.filter(d=>d.planned?.type==='kracht').length<2)messages.push('Minder dan twee krachtsessies gepland: dit kan vooruitgang geven, maar beperkt de oefenfrequentie voor drie powerlifts plus powertraining.');
  if(week.some(d=>d.planned?.type==='duur')||sessions.some(s=>s.type==='duur'&&week.some(d=>d.date===s.date)))messages.push('Duurtraining belast ook je herstel. Deze volumetelling berekent geen individuele interferentie of herstelcapaciteit.');
  if(!sessions.some(s=>week.some(d=>d.date===s.date)))messages.push('Nog geen gelogde sessies deze week. De weektotaalsom is vooral planning; trainingen buiten deze app ontbreken.');
  const liftStatus=(Object.keys(targets) as Powerlift[]).map(lift=>({lift,sets:counts.projected.lifts[lift],...targets[lift],
    status:counts.projected.lifts[lift]<targets[lift].min?'laag':counts.projected.lifts[lift]>targets[lift].max?'hoog':'binnen'}));
  return {...counts,minutes,messages,liftStatus};
}
