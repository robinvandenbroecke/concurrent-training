import type { AthleteProfile, PlannedTraining, WorkoutSession } from '../types';
import { createExercise, definition } from '../data/exercises';

export function strengthSlots(profile:AthleteProfile): number {
  const n=new Set(profile.availableDays).size;
  return profile.priority==='kracht' ? (n<=2?n:Math.ceil(n*2/3)) : profile.priority==='duur' ? Math.floor(n/3) : Math.ceil(n/2);
}
export function strengthOrdinal(profile:AthleteProfile,index:number): number {
  const n=new Set(profile.availableDays).size, s=strengthSlots(profile);
  return Math.floor((index+1)*s/n)-1;
}
export function strengthProgram(profile:AthleteProfile,date:string,index:number,sessions:WorkoutSession[]=[]): PlannedTraining {
  const ordinal=strengthOrdinal(profile,index), b=ordinal%2===1, minutes=profile.sessionDurationMinutes;
  const mainSets=minutes<45?2:3;
  const make=(id:string,sets:number,reps?:number,rpe?:number)=>{
    const ex=createExercise(id,profile,`${date}:${id}`,sets);
    const recent=[...sessions].filter(s=>s.date<=date).sort((a,b)=>b.date.localeCompare(a.date)).flatMap(s=>s.exercises??[]).find(e=>definition(e)?.id===id&&e.sets.some(s=>s.kind!=='warmup'&&s.completedReps>0));
    const recentSet=recent?.sets.filter(s=>s.kind!=='warmup'&&s.completedReps>0).at(-1);
    if(recentSet)ex.sets=ex.sets.map(s=>({...s,weight:recentSet.weight}));
    ex.sets=ex.sets.map(s=>({...s,targetReps:reps??s.targetReps,targetRpe:rpe??s.targetRpe}));return ex;
  };
  const power=profile.olympicExperience?'power_clean':'clean_pull';
  const exercises=[make(b?'deadlift':'back_squat',mainSets,b?3:4,7),make('bench_press',mainSets,b?5:4,7)];
  // Very short sessions prioritize the powerlifts. Extra work is visible, never silently added beyond the time budget.
  if(minutes>=45) exercises.unshift(make(power,3,2,6));
  if(minutes>=60) {
    if(b) exercises.push(make('back_squat',2,4,6));
    else if(strengthSlots(profile)===1)exercises.push(make('deadlift',2,3,7));
    exercises.push(make('barbell_row',2,8,7));
  }
  return {date,type:'kracht',title:`Krachttraining ${b?'B':'A'} — powerlifting & atletisch`,durationMinutes:minutes,
    reason:'Startschema: korte explosieve sets, daarna specifieke powerlifts en trekwerk. RPE-doel 6–8; controleer het laatst gelogde of zelf opgegeven werkgewicht. Na twee geslaagde blootstellingen kun je de kleinste gewichtsprong overwegen; behoud techniek en doel-RPE. Bij tijdgebrek eerst accessoires verminderen.',exercises};
}
