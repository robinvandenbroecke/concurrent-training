import type { PlannedTraining, PlannedExercise, PlannedSet } from '../types';
import type { CompletedMap } from './volume';
export function editPrescription(ex:PlannedExercise,patch:{count?:number;weight?:number;reps?:number;rpe?:number;rest?:number;kind?:'work'|'warmup'},done:CompletedMap={}):PlannedExercise {
  const locked=done[ex.id??'']??[], count=patch.count??ex.sets.length;
  if(!Number.isInteger(count)||count<1||count>12||locked.some(s=>s.setNum>count))throw new Error('Bevestigde sets blijven behouden. Verminder alleen nog niet uitgevoerde sets.');
  const base=ex.sets[ex.sets.length-1]??{setNum:1,weight:0,targetReps:5,restSec:180,targetRpe:7,kind:'work'};
  const sets=Array.from({length:count},(_,i):PlannedSet=>{
    const old=ex.sets[i]??{...base,setNum:i+1};
    if(locked.some(s=>s.setNum===i+1))return old;
    return{...old,setNum:i+1,weight:patch.weight??old.weight,targetReps:patch.reps??old.targetReps,
      restSec:patch.rest??old.restSec,targetRpe:patch.rpe??old.targetRpe,kind:patch.kind??old.kind};
  });
  return{...ex,sets};
}
export function removeExercise(plan:PlannedTraining,id:string,done:CompletedMap={}):PlannedTraining {
  if(done[id]?.length)throw new Error('Een oefening met bevestigde sets kan niet worden verwijderd of vervangen.');
  return{...plan,exercises:plan.exercises?.filter(e=>e.id!==id)};
}
export function replaceExercise(plan:PlannedTraining,id:string,replacement:PlannedExercise,done:CompletedMap={}):PlannedTraining {
  removeExercise(plan,id,done);
  return{...plan,exercises:plan.exercises?.map(e=>e.id===id?replacement:e)};
}
export function moveExercise(plan:PlannedTraining,id:string,offset:number):PlannedTraining {
  const exercises=[...(plan.exercises??[])],index=exercises.findIndex(e=>e.id===id),target=index+offset;
  if(index<0||target<0||target>=exercises.length)return plan;
  [exercises[index],exercises[target]]=[exercises[target],exercises[index]];
  return{...plan,exercises};
}
export function validatePlan(plan:PlannedTraining){
  if(!Number.isFinite(plan.durationMinutes)||plan.durationMinutes<15||plan.durationMinutes>180)throw new Error('Kies 15–180 minuten beschikbare tijd.');
  const exercises=plan.exercises??[];
  if(exercises.length>30||new Set(exercises.map(e=>e.id)).size!==exercises.length||exercises.some(e=>!e.id))throw new Error('Oefeningen moeten elk een eigen identiteit hebben (maximaal 30).');
  for(const ex of exercises){
    if(ex.sets.length<1||ex.sets.length>12)throw new Error('Gebruik 1–12 sets per oefening.');
    for(const s of ex.sets)if(!Number.isFinite(s.weight)||s.weight<0||s.weight>500||!Number.isInteger(s.targetReps)||s.targetReps<1||s.targetReps>30
      ||!Number.isFinite(s.restSec)||s.restSec<15||s.restSec>600||!Number.isFinite(s.targetRpe??7)||(s.targetRpe??7)<4||(s.targetRpe??7)>10)throw new Error('Controleer gewicht, reps, rust en doel-RPE.');
  }
}
