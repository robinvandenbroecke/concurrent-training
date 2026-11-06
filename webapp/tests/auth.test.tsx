import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {JSDOM} from 'jsdom';
import type {SupabaseClient,Session} from '@supabase/supabase-js';
import type {CloudTransport,AccountRecord} from '../src/api/cloud';

test('login, registration validation, recovery and account switching keep private data behind authentication',async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test/concurrent-training/',pretendToBeVisual:true}),w=dom.window;
  Object.assign(globalThis,{window:w,document:w.document,localStorage:w.localStorage,HTMLElement:w.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
  Object.defineProperty(globalThis,'navigator',{value:w.navigator,configurable:true});w.confirm=()=>true;
  const {createRoot}=await import('react-dom/client'),{default:Auth}=await import('../src/screens/Auth'),{default:AccountGate}=await import('../src/screens/AccountGate'),{TrainingApp}=await import('../src/App');
  const {KEYS,readProfile}=await import('../src/api/local');
  const host=document.getElementById('root')!;let root=createRoot(host),listener:((event:string,session:Session|null)=>void)|undefined,calls=0;
  const session=(id:string)=>({user:{id,email:`${id}@example.invalid`}} as Session);
  let current:Session|null=null;
  const fake={auth:{
    getSession:async()=>({data:{session:current},error:null}),
    onAuthStateChange:(cb:typeof listener)=>{listener=cb;return{data:{subscription:{unsubscribe:()=>{listener=undefined;}}}};},
    signInWithPassword:async({email}:{email:string})=>{calls++;if(email==='wrong@example.invalid')return{error:{code:'invalid_credentials'}};current=session(email.split('@')[0]);listener?.('SIGNED_IN',current);return{error:null};},
    signUp:async()=>{calls++;return{data:{session:null},error:null};},
    resetPasswordForEmail:async()=>{calls++;return{error:null};},
    updateUser:async()=>{calls++;return{error:null};},
    signOut:async()=>{current=null;listener?.('SIGNED_OUT',null);return{error:null};},
  }} as unknown as SupabaseClient;
  const flush=async()=>{await act(async()=>{await new Promise(r=>setTimeout(r,0));});};
  const click=async(el:Element|undefined|null)=>{assert.ok(el);await act(async()=>{el.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));});await flush();};
  const button=(text:RegExp)=>[...host.querySelectorAll('button')].find(b=>text.test(b.textContent!.trim()));
  const fill=async(selector:string,value:string)=>{const e=host.querySelector(selector)!;assert.ok(e);await act(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value')!.set!.call(e,value);e.dispatchEvent(new w.Event('input',{bubbles:true}));});};
  const submit=async()=>{await act(async()=>{host.querySelector('form')!.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));});await flush();};
  const mount=async(element:React.ReactNode)=>{await act(async()=>root.unmount());root=createRoot(host);await act(async()=>root.render(element));await flush();};
  try{
    await act(async()=>root.render(<Auth client={fake} onRecovered={()=>{}}/>));await flush();
    await fill('#auth-email','wrong@example.invalid');await fill('#auth-password','wrong-password');await submit();assert.match(host.textContent!,/onjuist/);
    await click(button(/^Account aanmaken$/));await fill('#auth-password','12345678');await fill('#auth-repeat','different');const before=calls;await submit();assert.equal(calls,before);assert.match(host.textContent!,/tweemaal hetzelfde/);
    await fill('#auth-repeat','12345678');await submit();assert.match(host.textContent!,/bevestig je e-mailadres/);
    await click(button(/^Wachtwoord vergeten$/));await submit();assert.match(host.textContent!,/Als dit adres een account heeft/);
    let recovered=false;await mount(<Auth client={fake} recovery onRecovered={()=>{recovered=true;}}/>);await fill('#auth-password','abcdefgh');await fill('#auth-repeat','abcdefgh');await submit();assert.equal(recovered,true);
    const profile={name:'Alice privé',priority:'kracht',experienceYears:2,availableDays:[1,3],sessionDurationMinutes:60,hasVbt:false,hasStravaSync:false,capacities:{},onboardingComplete:true};
    const records=new Map<string,AccountRecord>([['alice',{state:{[KEYS.profile]:profile},revision:1}]]);
    const transportFactory=(_:SupabaseClient,id:string):CloudTransport=>({loadState:async()=>records.get(id)??null,saveState:async(state,revision)=>{const saved={state,revision:revision+1};records.set(id,saved);return saved;},loadSessions:async()=>[],insertSession:async s=>({...s,savedToServer:true})});
    await mount(<AccountGate client={fake} transportFactory={transportFactory}><TrainingApp cloudMode/></AccountGate>);
    assert.match(host.textContent!,/Inloggen/);assert.doesNotMatch(host.textContent!,/Alice privé/);
    await fill('#auth-email','alice@example.invalid');await fill('#auth-password','password');await submit();await flush();assert.match(host.textContent!,/Alice privé/);assert.equal(readProfile()?.name,'Alice privé');
    await click(button(/^Uitloggen$/));assert.match(host.textContent!,/Inloggen/);assert.doesNotMatch(host.textContent!,/Alice privé/);
    await fill('#auth-email','bob@example.invalid');await fill('#auth-password','password');await submit();await flush();assert.doesNotMatch(host.textContent!,/Alice privé/);assert.equal(readProfile(),null);assert.ok(host.querySelector('input[placeholder="Naam"]'));
  }finally{await act(async()=>root.unmount());w.close();}
});
