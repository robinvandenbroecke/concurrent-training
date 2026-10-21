import test from 'node:test';
import assert from 'node:assert/strict';
import { EXERCISES, createExercise, definition, normalizePlan } from '../src/data/exercises.ts';
import { editPrescription, moveExercise, removeExercise, replaceExercise, validatePlan } from '../src/domain/editing.ts';
import { countCompleted, countPlan, DEFAULT_TARGETS, volumeAdvice, weeklyProjection } from '../src/domain/volume.ts';
import { buildWeek, exportLocal, importLocal, KEYS, readDraft, readJson, readSessions, saveEditedPlan, writeJson } from '../src/api/local.ts';
import type { AthleteProfile, CompletedSet, PlannedTraining, WorkoutSession } from '../src/types.ts';

const p:AthleteProfile={name:'Test',priority:'kracht',experienceYears:3,availableDays:[1,4],sessionDurationMinutes:60,hasVbt:true,hasStravaSync:false,capacities:{squat:60,bench:50,deadlift:90},onboardingComplete:true};
const set:CompletedSet={setNum:1,weight:60,targetReps:4,completedReps:4,velocities:[.6,null,.5,.45],rpe:7};
const plan:PlannedTraining=normalizePlan({date:'2026-10-22',type:'kracht',title:'Test',durationMinutes:60,exercises:[createExercise('back_squat',p,'squat-1'),createExercise('bench_press',p,'bench-1')]});
function storage(){const data=new Map<string,string>();return{getItem:(k:string)=>data.get(k)??null,setItem:(k:string,v:string)=>{data.set(k,v);},removeItem:(k:string)=>{data.delete(k);}};}

test('catalogue identities are unique and cover all exercise categories',()=>{
 assert.equal(EXERCISES.length,42);assert.equal(new Set(EXERCISES.map(d=>d.id)).size,42);
 assert.deepEqual(new Set(EXERCISES.map(d=>d.category)),new Set(['Powerlifting','Olympisch','Accessoires','Sprongen']));
 for(const d of EXERCISES){const e=createExercise(d.id,p);assert.equal(definition(e)?.id,d.id);validatePlan({...plan,exercises:[e]});}
});
test('two strength days cover all powerlifts and short quality power blocks',()=>{
 const week=buildWeek(p,new Date(2026,9,21)),plans=week.flatMap(d=>d.planned?.exercises??[]);
 assert.ok(plans.some(e=>definition(e)?.powerlift==='deadlift'));
 assert.equal(plans.filter(e=>definition(e)?.powerlift==='bench').length,2);
 assert.ok(plans.some(e=>e.exerciseId==='clean_pull'));assert.ok(plans.every(e=>!definition(e)?.catch));
 const expert=buildWeek({...p,olympicExperience:true},new Date(2026,9,21));
 assert.ok(expert.some(d=>d.planned?.exercises?.some(e=>e.exerciseId==='power_clean')));
});
test('one long strength session includes squat, bench and deadlift',()=>{
 const ex=buildWeek({...p,availableDays:[4]},new Date(2026,9,21)).flatMap(d=>d.planned?.exercises??[]);
 assert.deepEqual(new Set(ex.map(e=>definition(e)?.powerlift).filter(Boolean)),new Set(['squat','bench','deadlift']));
});
test('every priority, day count and time budget stays inside selected training days',()=>{
 for(const priority of ['kracht','balans','duur'] as const)for(let n=1;n<=7;n++)for(const minutes of [15,30,45,60,90]){
   const profile={...p,priority,availableDays:Array.from({length:n},(_,i)=>i),sessionDurationMinutes:minutes};
   const w=buildWeek(profile,new Date(2026,9,21));assert.equal(w.filter(d=>d.planned).length,n);
   for(const d of w)if(d.planned){assert.equal(d.planned.durationMinutes,minutes);if(d.planned.type==='kracht')validatePlan(d.planned);}
 }
});
test('unknown variants never inherit a different lift working weight',()=>{
 assert.equal(createExercise('front_squat',p).sets[0].weight,0);assert.equal(createExercise('back_squat',p).sets[0].weight,60);
});
test('a generated plan can reuse a measured weight only for the same exercise',()=>{
 const sessions:WorkoutSession[]=[{id:'old',date:'2026-10-19',title:'Old',type:'kracht',durationMinutes:45,savedToServer:false,exercises:[{lift:'other',exerciseId:'front_squat',displayName:'Front squat',sets:[{...set,weight:45}]},{lift:'squat',exerciseId:'back_squat',displayName:'Squat',sets:[{...set,weight:65}]}]}];
 const w=buildWeek(p,new Date(2026,9,21),sessions);assert.equal(w[0].planned?.exercises?.find(e=>e.exerciseId==='back_squat')?.sets[0].weight,65);
});
test('confirmed measurements survive reordering and editing future sets',()=>{
 const done={'squat-1':[set]},moved=moveExercise(plan,'squat-1',1);
 assert.equal(moved.exercises![1].id,'squat-1');
 const changed=editPrescription(moved.exercises![1],{count:4,weight:70,reps:3},done);
 assert.equal(changed.sets[0].weight,60);assert.equal(changed.sets[1].weight,70);assert.equal(changed.sets[1].targetReps,3);
 assert.deepEqual(done['squat-1'][0].velocities,[.6,null,.5,.45]);
 assert.throws(()=>removeExercise(plan,'squat-1',done));assert.throws(()=>replaceExercise(plan,'squat-1',createExercise('front_squat'),done));
 assert.throws(()=>editPrescription(plan.exercises![0],{count:1},{'squat-1':[{...set,setNum:2}]}));
});
test('duplicate exercise instances remain separate',()=>{
 const a=createExercise('back_squat',p),b=createExercise('back_squat',p);assert.notEqual(a.id,b.id);
 const edited=removeExercise({...plan,exercises:[a,b]},b.id!,{[a.id!]:[set]});assert.equal(edited.exercises?.length,1);assert.equal(edited.exercises?.[0].id,a.id);
});
test('warmups are excluded, low-RPE powerlift practice counts, power reps stay separate',()=>{
 const exercises=[{lift:'squat' as const,exerciseId:'back_squat',displayName:'Squat',sets:[set,{...set,kind:'warmup' as const},{...set,rpe:5}]},{lift:'power_clean' as const,exerciseId:'power_clean',displayName:'Clean',sets:[{...set,completedReps:2,velocities:[.8,.8]}]}];
 const c=countCompleted(exercises);assert.equal(c.lifts.squat,2);assert.equal(c.workSets,2);assert.equal(c.lightSets,1);assert.equal(c.powerReps,2);assert.equal(c.muscles.quadriceps,1);assert.equal(c.muscles.posterior,.5);
});
test('unknown RPE is counted explicitly and does not become a false readiness score',()=>{
 const c=countCompleted([{lift:'squat',displayName:'Old squat',sets:[{...set,rpe:undefined}]}]);assert.equal(c.unknownRpe,1);assert.equal(c.lifts.squat,1);
});
test('actual reps replace planned reps instead of being added twice',()=>{
 const power={...plan,exercises:[createExercise('power_clean',p,'clean',2)]};
 assert.equal(countPlan(power,{'clean':[{...set,completedReps:1,velocities:[.8]}]}).powerReps,3);
});
test('week projection adds completed sessions, candidate and future days once',()=>{
 const w=buildWeek(p,new Date(2026,9,21));
 const old:WorkoutSession={id:'done',date:'2026-10-19',type:'kracht',title:'Done',durationMinutes:40,savedToServer:false,exercises:[{lift:'squat',displayName:'Squat',sets:[set]}]};
 const c=weeklyProjection(plan,w,[old],{'squat-1':[set]});assert.equal(c.projected.lifts.squat,4);assert.equal(c.actual.lifts.squat,1);
 const retry=weeklyProjection(plan,w,[{...old,id:'active',date:plan.date}],{},'active');assert.equal(retry.actual.workSets,0);
});
test('large changes warn on time, muscle workload and power quality',()=>{
 const large={...plan,durationMinutes:30,exercises:[editPrescription(createExercise('leg_press',p),{count:12}),editPrescription(createExercise('leg_press',p),{count:12}),editPrescription(createExercise('power_clean',p),{count:6,reps:6,rpe:9})]};
 const r=volumeAdvice(large,buildWeek(p,new Date(2026,9,21)),[],p);
 assert.ok(r.messages.some(m=>m.includes('te veel voor je tijd')));assert.ok(r.messages.some(m=>m.includes('Veel werk voor Quadriceps')));assert.ok(r.messages.some(m=>m.includes('Veel explosieve reps')));assert.ok(r.messages.some(m=>m.includes('opvangbeweging')));
});
test('volume status follows editable goals, not a universal optimum',()=>{
 const r=volumeAdvice(plan,buildWeek(p,new Date(2026,9,21)),[],p,{...DEFAULT_TARGETS,squat:{min:4,max:8},bench:{min:0,max:2}});
 assert.equal(r.liftStatus.find(s=>s.lift==='squat')?.status,'laag');assert.equal(r.liftStatus.find(s=>s.lift==='bench')?.status,'hoog');
});
test('legacy index-based drafts migrate without losing measured samples',()=>{
 const s=storage(),legacy={...plan,exercises:[{lift:'squat',displayName:'Old squat',sets:plan.exercises![0].sets}]};
 writeJson(KEYS.draft,{plan:legacy,phase:'active',startTime:'2026-10-21T12:00:00Z',completed:{0:[set]},exerciseIndex:0},s);
 const d=readDraft(s)!;assert.ok(d.plan.exercises![0].id);assert.deepEqual(Object.values(d.completed)[0][0],set);
});
test('plan editing rolls back the prior complete snapshot on a failed second write',()=>{
 const s=storage();writeJson(KEYS.overrides,{'2026-10-22':plan},s);
 const before=readJson(KEYS.overrides,{},s);let writes=0;
 const failing={...s,setItem:(k:string,v:string)=>{if(++writes===2)throw new Error('quota');s.setItem(k,v);}};
 assert.throws(()=>saveEditedPlan({...plan,title:'Changed'},{plan,phase:'active',startTime:'2026-10-21T12:00:00Z',completed:{'squat-1':[set]},exerciseIndex:0},failing));
 assert.deepEqual(readJson(KEYS.overrides,{},s),before);assert.equal(readDraft(s),null);
});
test('zero added weight and warmup metadata survive local export/import',()=>{
 const a=storage(),b=storage();writeJson(KEYS.sessions,[{id:'bw',date:'2026-10-21',type:'kracht',title:'BW',durationMinutes:10,savedToServer:false,exercises:[{id:'jump-1',exerciseId:'countermovement_jump',lift:'other',displayName:'Jump',sets:[{...set,weight:0,kind:'warmup'}]}]}],a);
 importLocal(JSON.stringify(exportLocal(a)),b);assert.deepEqual(readSessions(b),readSessions(a));
});
