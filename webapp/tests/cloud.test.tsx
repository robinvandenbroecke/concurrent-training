import test from 'node:test';
import assert from 'node:assert/strict';
import { CloudStore, STATE_KEYS, type CloudTransport, type AccountRecord, type AccountState } from '../src/api/cloud';
import { KEYS, accountStorage, appendSession, readDraft, readProfile, readSessions, writeJson, observeStorage, type StorageLike } from '../src/api/local';
import type { WorkoutSession } from '../src/types';
function memory():StorageLike { const m=new Map<string,string>();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>{m.set(k,v);},removeItem:k=>{m.delete(k);}}; }
const profile={name:'Atleet',priority:'kracht',experienceYears:2,availableDays:[1,3],sessionDurationMinutes:60,hasVbt:true,hasStravaSync:false,capacities:{squat:50},onboardingComplete:true};
const workout:WorkoutSession={id:'session-1',date:'2026-11-06',type:'kracht',title:'Kracht',durationMinutes:45,savedToServer:false,exercises:[{lift:'squat',displayName:'Squat',sets:[{setNum:1,weight:80,targetReps:3,completedReps:3,velocities:[.5,null,.42],rpe:8,note:'Gemeten'}]}]};
class Server implements CloudTransport {
  state:AccountRecord|null=null; sessions=new Map<string,WorkoutSession>();offline=false;lostResponse=false;
  async loadState(){if(this.offline)throw Error('offline');return structuredClone(this.state);}
  async saveState(state:AccountState,revision:number){
    if(this.offline)throw Error('offline');if((this.state?.revision??0)!==revision)return null;
    this.state={state:structuredClone(state),revision:revision+1};if(this.lostResponse){this.lostResponse=false;throw Error('lost response');}return structuredClone(this.state);
  }
  async loadSessions(){if(this.offline)throw Error('offline');return structuredClone([...this.sessions.values()]);}
  async insertSession(s:WorkoutSession){if(this.offline)throw Error('offline');if(!this.sessions.has(String(s.id)))this.sessions.set(String(s.id),structuredClone({...s,savedToServer:true}));return structuredClone(this.sessions.get(String(s.id))!);}
}
function connect(store:CloudStore){observeStorage((key,storage)=>store.changed(key,storage));}

test('cache and late callbacks remain isolated when another user signs in',async()=>{
  const disk=memory(),a=accountStorage('alice',disk),b=accountStorage('bob',disk),server=new Server();
  const store=new CloudStore('alice',a,server);await store.initialize();connect(store);
  writeJson(KEYS.profile,profile,a);appendSession(workout,a);await store.flush();store.stop();observeStorage();
  assert.equal(readProfile(b),null);assert.deepEqual(readSessions(b),[]);assert.equal(readSessions(a)[0].savedToServer,true);
  writeJson(KEYS.profile,{...profile,name:'Bob'},b);assert.equal(readProfile(a)?.name,'Atleet');
});
test('a second device restores profile, planning, targets, open sets and full measured sessions',async()=>{
  const server=new Server(),disk=memory(),first=new CloudStore('a',disk,server);await first.initialize();connect(first);
  const draft={plan:{date:'2026-11-06',type:'kracht',title:'Open',durationMinutes:60,exercises:[]},phase:'active',startTime:'2026-11-06T10:00:00Z',completed:{},exerciseIndex:0};
  writeJson(KEYS.profile,profile,disk);writeJson(KEYS.draft,draft,disk);writeJson(KEYS.overrides,{'2026-11-07':null},disk);writeJson(KEYS.volumeTargets,{custom:9},disk);appendSession(workout,disk);await first.flush();
  const otherDisk=memory(),other=new CloudStore('a',otherDisk,server);await other.initialize();
  assert.deepEqual(readProfile(otherDisk),profile);assert.deepEqual(readDraft(otherDisk)?.plan.title,'Open');
  assert.deepEqual(readSessions(otherDisk)[0].exercises,workout.exercises);assert.equal(readSessions(otherDisk)[0].savedToServer,true);
  for(const key of STATE_KEYS)assert.deepEqual(JSON.parse(otherDisk.getItem(key)!),JSON.parse(disk.getItem(key)!));first.stop();other.stop();observeStorage();
});
test('offline failure survives reload and retry inserts one session with missing VBT samples intact',async()=>{
  const disk=memory(),server=new Server(),store=new CloudStore('a',disk,server);await store.initialize();connect(store);server.offline=true;
  appendSession(workout,disk);writeJson(KEYS.profile,profile,disk);await assert.rejects(store.flush());assert.equal(readSessions(disk)[0].savedToServer,false);store.stop();
  const reload=new CloudStore('a',disk,server);await reload.initialize();assert.equal(reload.status.phase,'error');server.offline=false;
  await reload.flush();await reload.flush();assert.equal(server.sessions.size,1);assert.deepEqual(readSessions(disk)[0].exercises![0].sets[0].velocities,[.5,null,.42]);assert.equal(readSessions(disk)[0].savedToServer,true);reload.stop();observeStorage();
});
test('new device cannot overwrite an account with empty state when loading fails',async()=>{
  const server=new Server();server.offline=true;const store=new CloudStore('a',memory(),server);await assert.rejects(store.initialize(),/geen leeg profiel/);assert.equal(server.state,null);store.stop();
});
test('concurrent devices cannot silently overwrite planning or confirmed sets',async()=>{
  const server=new Server(),a=memory(),b=memory(),first=new CloudStore('a',a,server),second=new CloudStore('a',b,server);await first.initialize();await second.initialize();
  connect(first);writeJson(KEYS.profile,profile,a);await first.flush();connect(second);writeJson(KEYS.profile,{...profile,name:'Nieuw'},b);await assert.rejects(second.flush(),/ander toestel/);
  assert.equal(second.status.phase,'conflict');assert.equal(server.state!.state[KEYS.profile]&& (server.state!.state[KEYS.profile] as typeof profile).name,'Atleet');assert.equal(readProfile(b)?.name,'Nieuw');
  await second.useDatabaseVersion();assert.equal(readProfile(b)?.name,'Atleet');assert.ok(b.getItem('ct_conflict_backup')?.includes('Nieuw'));first.stop();second.stop();observeStorage();
});
test('lost HTTP confirmation of a committed profile write is recovered without duplicates',async()=>{
  const server=new Server(),disk=memory(),store=new CloudStore('a',disk,server);await store.initialize();connect(store);writeJson(KEYS.profile,profile,disk);server.lostResponse=true;
  await assert.rejects(store.flush());assert.equal(server.state!.revision,1);await store.flush();assert.equal(store.status.phase,'saved');assert.equal(server.state!.revision,1);store.stop();observeStorage();
});
test('existing completed session cannot be overwritten by a different retry',async()=>{
  const server=new Server(),disk=memory(),store=new CloudStore('a',disk,server);await store.initialize();appendSession(workout,disk);await store.saveSession('session-1');
  appendSession({...workout,title:'Changed'},disk);await assert.rejects(store.saveSession('session-1'));assert.equal(server.sessions.get('session-1')!.title,'Kracht');assert.equal(readSessions(disk)[0].savedToServer,false);store.stop();
});
test('legacy migration is explicit, idempotent and leaves the source backup intact',async()=>{
  const source=memory(),disk=memory(),server=new Server();writeJson(KEYS.profile,profile,source);appendSession(workout,source);
  const store=new CloudStore('a',disk,server);await store.initialize();assert.equal(readProfile(disk),null);assert.equal(server.sessions.size,0);
  await store.importLegacy(source);await store.importLegacy(source);assert.equal(server.sessions.size,1);assert.equal(readSessions(source)[0].savedToServer,false);assert.equal(readProfile(source)?.name,'Atleet');store.stop();
});
