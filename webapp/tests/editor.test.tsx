import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {JSDOM} from 'jsdom';

test('future editing and live add/reorder preserve confirmed measurements through reload and save',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test/concurrent-training/',pretendToBeVisual:true}),w=dom.window;
 Object.assign(globalThis,{window:w,document:w.document,localStorage:w.localStorage,HTMLElement:w.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
 Object.defineProperty(globalThis,'navigator',{value:w.navigator,configurable:true});w.confirm=()=>true;
 const {createRoot}=await import('react-dom/client'),{default:App}=await import('../src/App.tsx');
 const {KEYS,localDate,readDraft,readJson,readSessions,writeJson}=await import('../src/api/local.ts');
 const {createExercise}=await import('../src/data/exercises.ts');
 const today=new Date(),future=new Date(today);future.setDate(today.getDate()+1);
 const host=document.getElementById('root')!;let root=createRoot(host);
 const profile={name:'Editor Test',priority:'kracht' as const,experienceYears:3,availableDays:[today.getDay(),future.getDay()],sessionDurationMinutes:30,hasVbt:true,hasStravaSync:false,capacities:{squat:50,bench:40,deadlift:70},onboardingComplete:true};
 writeJson(KEYS.profile,profile);
 writeJson(KEYS.overrides,{[localDate(today)]:{date:localDate(today),type:'kracht',title:'Testtraining',durationMinutes:30,exercises:[createExercise('back_squat',profile,'test-squat',2),createExercise('bench_press',profile,'test-bench',2)]}});
 const flush=async()=>{await act(async()=>{await new Promise(r=>setTimeout(r,0));});};
 const visible=(el:Element)=>{for(let p:Element|null=el;p;p=p.parentElement)if((p as HTMLElement).style?.display==='none')return false;return true;};
 const active=()=>[...host.querySelectorAll('main > div')].find(e=>(e as HTMLElement).style.display==='block')!;
 const button=(name:RegExp)=>[...host.querySelectorAll('button')].find(e=>visible(e)&&name.test(e.textContent?.trim()??''));
 const click=async(el:Element|null|undefined)=>{assert.ok(el,'control exists');await act(async()=>{el.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));});await flush();};
 const fill=async(el:HTMLInputElement|null,value:string)=>{assert.ok(el,'input exists');await act(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value')!.set!.call(el,value);el.dispatchEvent(new w.Event('input',{bubbles:true}));el.dispatchEvent(new w.Event('change',{bubbles:true}));});};
 const labelled=(label:string)=>active().querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
 try{
  await act(async()=>root.render(<App/>));await flush();
  // On Sundays the next day is in the following week, so use another future day in the current week if possible.
  if(today.getDay()!==0){
   await click(button(/^Week$/));const day=[...active().querySelectorAll('.week-cell')].find(e=>e.querySelector('.day-num')?.textContent===String(future.getDate()));await click(day);
   await click(button(/^Training aanpassen$/));assert.match(active().textContent!,/Squat: 2 sets/);await fill(labelled('Zoek oefening'),'front squat');await click(active().querySelector('[aria-label="Toevoegen: Front squat"]'));
   await fill(labelled('Gewicht Front squat (kg)'),'45');await click(button(/^Wijzigingen bewaren$/));
   const overrides=readJson<Record<string,any>>(KEYS.overrides,{});assert.ok(overrides[localDate(future)].exercises.some((e:any)=>e.exerciseId==='front_squat'&&e.sets[0].weight===45));
   await act(async()=>root.unmount());root=createRoot(host);await act(async()=>root.render(<App/>));await flush();await click(button(/^Training$/));assert.equal(readDraft()?.plan.date,localDate(future));assert.match(active().textContent!,/Front squat/);
   await click(button(/^Vandaag$/));
  }
  await click(button(/^Training aanpassen$/));await fill(labelled('Zoek oefening'),'pull-up');await click(active().querySelector('[aria-label="Toevoegen: Pull-up"]'));await click(button(/^Wijzigingen bewaren$/));
  await click(button(/Start training/));let row=button(/^Bevestig set 1$/)!.parentElement!;
  await fill(row.querySelector('input[type="number"]'),'42.5');await fill(row.querySelectorAll<HTMLInputElement>('input[type="number"]')[1],'3');await click([...row.querySelectorAll('button')].find(b=>/RPE \/ snelheid/.test(b.textContent??'')));
  await fill(row.querySelector('input[min="1"]'),'8');await fill(row.querySelector('input[placeholder="0.50; -; 0.42"]'),'0.5; -; 0.4');await click(button(/^Bevestig set 1$/));await click(button(/^Overslaan$/));
  const draft=readDraft()!,squat=draft.plan.exercises!.find(e=>e.exerciseId==='back_squat')!,confirmed=draft.completed[squat.id!][0];
  await click(button(/^Training aanpassen$/));let fs=[...active().querySelectorAll('fieldset')].find(f=>f.querySelector('legend')?.textContent?.includes('Back squat'))!;
  assert.equal(fs.querySelector<HTMLButtonElement>('button:last-child')!.disabled,true);
  await click(active().querySelector('[aria-label="Back squat omlaag"]'));await fill(labelled('Sets Back squat'),'3');await fill(labelled('Gewicht Back squat (kg)'),'70');
  await fill(labelled('Zoek oefening'),'front squat');await click(active().querySelector('[aria-label="Toevoegen: Front squat"]'));await fill(labelled('Gewicht Front squat (kg)'),'45');await click(button(/^Wijzigingen bewaren$/));
  const after=readDraft()!;assert.deepEqual(after.completed[squat.id!][0],confirmed);assert.equal(after.plan.exercises!.find(e=>e.id===squat.id)!.sets[1].weight,70);assert.equal(after.plan.exercises![0].exerciseId,'bench_press');
  await act(async()=>root.unmount());root=createRoot(host);await act(async()=>root.render(<App/>));await flush();await click(button(/^Training$/));assert.deepEqual(readDraft()!.completed[squat.id!][0],confirmed);
  await click(button(/^Pull-up$/));row=button(/^Bevestig set 1$/)!.parentElement!;await fill(row.querySelectorAll<HTMLInputElement>('input[type="number"]')[1],'5');await click(button(/^Bevestig set 1$/));await click(button(/^Overslaan$/));await click(button(/^Training afronden$/));
  const sessions=readSessions();assert.equal(sessions.length,1);assert.equal(sessions[0].exercises!.find(e=>e.exerciseId==='pull_up')!.sets[0].weight,0);assert.deepEqual(sessions[0].exercises!.find(e=>e.exerciseId==='back_squat')!.sets[0].velocities,[.5,null,.4]);
  assert.equal(readDraft(),null);await click(button(/^Historie$/));assert.match(active().textContent!,/Pull-up/);
 }finally{await act(async()=>root.unmount());dom.window.close();}
});
