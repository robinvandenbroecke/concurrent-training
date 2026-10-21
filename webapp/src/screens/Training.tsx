import React, { useState, useEffect } from 'react';
import type {
  PlannedTraining, PlannedExercise, CompletedSet, CompletedExercise, LiftType, EnduranceSport, IntensityType
} from '../types';
import { api } from '../api/adapter';
import { LIFT_NAMES, SPORT_NAMES, INTENSITY_NAMES } from '../data/demoData';
import { useTimer } from '../hooks/useTimer';
import { IconCheck, IconClock } from '../components/Icons';
import { KEYS, localDate, parseVelocities, readDraft, readProfile, writeJson, saveEditedPlan } from '../api/local';
import { definition, normalizePlan } from '../data/exercises';
import type { CompletedMap } from '../domain/volume';
import PlanEditor from '../components/PlanEditor';
import VolumePanel from '../components/VolumePanel';

interface Props {
  plan: PlannedTraining | null;
  onSaved: () => void;
  isDemo: boolean;
  hasVbt: boolean;
  editRequest?: number;
  onPlanEdited: () => void;
}

// ── Rest timer popup ──────────────────────────────────────────────────────────
function RestTimer({ seconds, onDone }: { seconds: number; onDone: () => void }) {
  const timer = useTimer(seconds);
  useEffect(() => { timer.start(); }, []);
  useEffect(() => { if (timer.seconds === 0 && timer.running) { timer.pause(); onDone(); } }, [timer.seconds]);

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex',
      flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }}>
      <div className="card" style={{ width: 240, textAlign: 'center' }}>
        <div className="card-title">Rusttijd</div>
        <div className="timer-display">{timer.formatted}</div>
        <button className="btn btn-secondary btn-full" style={{ marginTop: 16 }} onClick={onDone}>
          Overslaan
        </button>
      </div>
    </div>
  );
}

// ── Set logging row ───────────────────────────────────────────────────────────
function SetRow({
  setNum, planned, completed, hasVbt, onComplete, allowZero, loadLabel
}: {
  setNum: number;
  planned: { weight: number; targetReps: number; restSec: number; targetRpe?: number; kind?: 'work'|'warmup' };
  allowZero: boolean;
  loadLabel: string;
  completed: CompletedSet | null;
  hasVbt: boolean;
  onComplete: (s: CompletedSet) => void;
}) {
  const [weight, setWeight] = useState(String(planned.weight));
  const [reps, setReps] = useState(String(planned.targetReps));
  const [rpe, setRpe] = useState('');
  const [vel, setVel] = useState('');
  const [note, setNote] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [warmup,setWarmup]=useState(planned.kind==='warmup');
  const done = !!completed;

  const submit = () => {
    const w = parseFloat(weight);
    const r = Number(reps);
    if (!Number.isFinite(w) || w < 0 || (!allowZero && w === 0) || w > 500 || !Number.isInteger(r) || r < 1 || r > 100) { setValidationError('Vul een geldig gewicht en 1–100 uitgevoerde reps in.'); return; }
    if (rpe && (!Number.isFinite(Number(rpe)) || Number(rpe) < 1 || Number(rpe) > 10)) { setValidationError('RPE moet tussen 1 en 10 liggen.'); return; }
    let velocities: (number | null)[];
    try { velocities = parseVelocities(hasVbt ? vel : '', r); } catch (e) { setValidationError((e as Error).message); return; }
    setValidationError('');
    onComplete({
      setNum, kind:warmup?'warmup':'work',
      weight: w,
      targetReps: planned.targetReps,
      completedReps: r,
      velocities,
      rpe: rpe ? parseFloat(rpe) : undefined,
      note: note || undefined,
    });
  };

  if (done) {
    return (
      <div className="set-row" style={{ background: 'rgba(94,203,138,0.06)', borderRadius: 6, padding: '8px 6px' }}>
        <div className="set-num" style={{ color: 'var(--c-success)' }}>✓</div>
        <div className="text-small">
          <strong>{completed!.weight} kg</strong> × {completed!.completedReps}
        </div>
        {completed!.rpe && <div className="text-small text-muted">RPE {completed!.rpe}</div>}
        <div />
      </div>
    );
  }

  return (
    <div style={{ borderBottom: '1px solid var(--c-border)', paddingBottom: 10, marginBottom: 10 }}>
      <div className="row between" style={{ marginBottom: 8 }}>
        <span className="set-num" style={{ fontSize: 14, color: 'var(--c-text2)' }}>Set {setNum}</span>
        <span className="text-small text-muted">Plan: {planned.weight} kg × {planned.targetReps}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
        <div>
          <label className="form-label">{loadLabel} (kg)</label>
          <input
            className="form-input large"
            type="number" min="0" max="500" step="2.5"
            value={weight}
            onChange={e => setWeight(e.target.value)}
          />
        </div>
        <div>
          <label className="form-label">Reps</label>
          <input
            className="form-input large"
            type="number" min="0" max="100" step="1"
            value={reps}
            onChange={e => setReps(e.target.value)}
          />
        </div>
      </div>

      <button
        className="collapse-toggle text-muted"
        onClick={() => setExpanded(v => !v)}
        style={{ marginBottom: expanded ? 8 : 0 }}
      >
        {expanded ? '▲ Minder' : '▼ RPE / snelheid / opmerking'}
      </button>

      {expanded && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
          <div>
            <label className="form-label">RPE (1–10)</label>
            <input
              className="form-input"
              type="number" min="1" max="10" step="0.5"
              value={rpe}
              onChange={e => setRpe(e.target.value)}
              placeholder="—"
            />
          </div>
          {hasVbt && (
            <div>
            <label className="form-label">Snelheid per rep (m/s)</label>
              <input
                className="form-input"
                type="text"
                value={vel}
                onChange={e => setVel(e.target.value)}
                placeholder="0.50; -; 0.42"
              />
            </div>
          )}
          <div style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Opmerking</label>
            <input
              className="form-input"
              type="text" maxLength={120}
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Pijn, techniek, etc."
            />
          </div>
        </div>
      )}

      <label className="warmup-toggle"><input type="checkbox" checked={warmup} onChange={e=>setWarmup(e.target.checked)}/> Opwarmset (telt niet als werkset)</label>
      {planned.targetRpe && <p className="text-xs text-muted">Doel-RPE {planned.targetRpe}. Vul je werkelijk ervaren RPE zelf in.</p>}
      <button className="btn btn-primary btn-full btn-sm" onClick={submit}>
        <IconCheck /> Bevestig set {setNum}
      </button>
      {validationError && <p role="alert" className="text-small" style={{ color: 'var(--c-warn)' }}>{validationError}</p>}
    </div>
  );
}

// Confirmed sets belong to stable exercise-instance IDs, never to display positions.
function StrengthFlow({exercises,hasVbt,completed,onChange,onSave}:{exercises:PlannedExercise[];hasVbt:boolean;completed:CompletedMap;onChange:(m:CompletedMap)=>void;onSave:(e:CompletedExercise[])=>void}){
  const [selected,setSelected]=useState(exercises[0]?.id),[rest,setRest]=useState<number|null>(null);
  const ex=exercises.find(e=>e.id===selected)??exercises[0];
  const finish=()=>onSave(exercises.map(e=>({id:e.id,exerciseId:e.exerciseId,lift:e.lift,displayName:e.displayName,sets:completed[e.id!]??[]})).filter(e=>e.sets.length>0));
  if(!ex)return <p className="text-small text-muted">Voeg oefeningen toe via Training aanpassen.</p>;
  const d=definition(ex),sets=completed[ex.id!]??[];
  return <div>
    {rest!==null&&<RestTimer seconds={rest} onDone={()=>setRest(null)}/>}
    <div className="h-scroll"><div className="row" style={{minWidth:'max-content',paddingBottom:12}}>{exercises.map(e=><button key={e.id} className={`pill ${ex.id===e.id?'selected':''}`} onClick={()=>setSelected(e.id)}>{(completed[e.id!]?.length??0)>=e.sets.length?'✓ ':''}{e.displayName}</button>)}</div></div>
    <div className="card"><div className="row between"><h3>{ex.displayName}</h3><span className="text-small text-muted">{sets.length}/{ex.sets.length} sets</span></div>
      <p className="text-xs text-muted">{d?.cue}{d?.load==='bodyweight'?' Vul alleen extra gewicht in; 0 kg is toegestaan.':''}</p>
      {ex.sets.map(ps=><SetRow key={`${ex.id}:${ps.setNum}:${ps.weight}:${ps.targetReps}`} setNum={ps.setNum} planned={ps} completed={sets.find(s=>s.setNum===ps.setNum)??null} hasVbt={hasVbt}
        allowZero={d?.load==='bodyweight'||d?.load==='assistance'} loadLabel={d?.load==='assistance'?'Ondersteuning':d?.load==='bodyweight'?'Extra gewicht':'Gewicht'} onComplete={set=>{
          onChange({...completed,[ex.id!]:[...sets.filter(s=>s.setNum!==set.setNum),set].sort((a,b)=>a.setNum-b.setNum)});
          if(set.setNum<ex.sets.length)setRest(ps.restSec);
        }}/>)}</div>
    <button className="btn btn-primary btn-full" disabled={!Object.values(completed).some(s=>s.length)} onClick={finish}><IconCheck/> Training afronden</button>
  </div>;
}

// ── Endurance logging ─────────────────────────────────────────────────────────
function EnduranceFlow({
  defaultSport, defaultDuration, defaultIntensity, onSave
}: {
  defaultSport: EnduranceSport;
  defaultDuration: number;
  defaultIntensity: IntensityType;
  onSave: (result: { sport: EnduranceSport; durationMinutes: number; intensityType: IntensityType; rpe?: number; avgPower?: number }) => void;
}) {
  const [sport, setSport] = useState<EnduranceSport>(defaultSport);
  const [duration, setDuration] = useState(String(defaultDuration));
  const [intensity, setIntensity] = useState<IntensityType>(defaultIntensity);
  const [rpe, setRpe] = useState('');
  const [power, setPower] = useState('');
  const [validationError, setValidationError] = useState('');

  const submit = () => {
    const d = Number(duration);
    if (!Number.isFinite(d) || d <= 0 || d > 600) { setValidationError('Vul een duur tussen 0 en 600 minuten in.'); return; }
    if (rpe && (!Number.isFinite(Number(rpe)) || Number(rpe) < 1 || Number(rpe) > 10)) { setValidationError('RPE moet tussen 1 en 10 liggen.'); return; }
    if (power && (!Number.isFinite(Number(power)) || Number(power) < 0 || Number(power) > 2000)) { setValidationError('Vul een gemiddeld vermogen van 0 tot 2000 W in.'); return; }
    setValidationError('');
    onSave({
      sport,
      durationMinutes: d,
      intensityType: intensity,
      rpe: rpe ? parseFloat(rpe) : undefined,
      avgPower: power ? parseFloat(power) : undefined,
    });
  };

  return (
    <div className="card">
      <div className="form-group">
        <label className="form-label">Sport</label>
        <select className="form-select" value={sport} onChange={e => setSport(e.target.value as EnduranceSport)}>
          {(Object.entries(SPORT_NAMES) as [EnduranceSport, string][]).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label className="form-label">Duur (minuten)</label>
        <input className="form-input large" type="number" min="1" max="600" value={duration}
          onChange={e => setDuration(e.target.value)} />
      </div>
      <div className="form-group">
        <label className="form-label">Intensiteit</label>
        <select className="form-select" value={intensity} onChange={e => setIntensity(e.target.value as IntensityType)}>
          {(Object.entries(INTENSITY_NAMES) as [IntensityType, string][]).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">RPE (1–10)</label>
          <input className="form-input" type="number" min="1" max="10" step="0.5"
            value={rpe} onChange={e => setRpe(e.target.value)} placeholder="—" />
        </div>
        <div>
          <label className="form-label">Gm. vermogen (W)</label>
          <input className="form-input" type="number" min="0" max="2000"
            value={power} onChange={e => setPower(e.target.value)} placeholder="—" />
          <p className="text-xs text-muted" style={{ marginTop: 3 }}>Optioneel</p>
        </div>
      </div>
      <button className="btn btn-primary btn-full" style={{ marginTop: 14 }} onClick={submit}>
        <IconCheck /> Sessie opslaan
      </button>
      {validationError && <p role="alert" className="text-small" style={{ color: 'var(--c-warn)' }}>{validationError}</p>}
    </div>
  );
}

export default function Training({plan:incoming,onSaved,isDemo,hasVbt,editRequest=0,onPlanEdited}:Props){
  const initial=React.useRef(readDraft());
  const [plan,setPlan]=useState<PlannedTraining|null>(()=>initial.current?.plan??(incoming?normalizePlan(incoming):null));
  const [phase,setPhase]=useState<'start'|'active'|'done'>(initial.current?.phase??'start');
  const [completed,setCompleted]=useState<CompletedMap>(initial.current?.completed??{});
  const [editor,setEditor]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[draftError,setDraftError]=useState('');
  const startTime=React.useRef(initial.current?.startTime??new Date().toISOString());
  const sessionId=React.useRef(initial.current?.sessionId??crypto.randomUUID());
  const previousIncoming=React.useRef(incoming);
  const elapsed=useTimer(0,'up');
  useEffect(()=>{if(initial.current?.phase==='active'){elapsed.reset(Math.max(0,Math.floor((Date.now()-Date.parse(startTime.current))/1000)));elapsed.start();}},[]);
  useEffect(()=>{
    if(previousIncoming.current===incoming)return;
    previousIncoming.current=incoming;
    const draft=readDraft();
    if(draft&&draft.plan.date===incoming?.date&&draft.plan.title===incoming?.title){
      setPlan(draft.plan);setCompleted(draft.completed);setPhase(draft.phase);startTime.current=draft.startTime;sessionId.current=draft.sessionId??crypto.randomUUID();
      if(draft.phase==='active'){elapsed.reset(Math.max(0,Math.floor((Date.now()-Date.parse(draft.startTime))/1000)));elapsed.start();}
    }else{
      setPlan(incoming?normalizePlan(incoming):null);setCompleted({});setPhase('start');sessionId.current=crypto.randomUUID();elapsed.reset();setError('');setDraftError('');
    }
    setEditor(false);
  },[incoming]);
  useEffect(()=>{if(editRequest>0)setEditor(true);},[editRequest]);
  const draft=(p:PlannedTraining,stage:'start'|'active',sets:CompletedMap)=>({plan:p,phase:stage,startTime:startTime.current,completed:sets,exerciseIndex:0,sessionId:sessionId.current});
  const record=(next:CompletedMap)=>{
    setCompleted(next);
    if(plan)try{writeJson(KEYS.draft,draft(plan,'active',next));setDraftError('');}catch(e){setDraftError((e as Error).message);}
  };
  const saveEdit=async(next:PlannedTraining)=>{
    saveEditedPlan(next,draft(next,phase==='active'?'active':'start',completed));
    setPlan(next);setEditor(false);setDraftError('');onPlanEdited();
  };
  const start=()=>{
    startTime.current=new Date().toISOString();setCompleted({});setPhase('active');elapsed.reset();elapsed.start();
    if(plan)try{writeJson(KEYS.draft,draft(plan,'active',{}));}catch(e){setDraftError((e as Error).message);}
  };
  const saveStrength=async(exercises:CompletedExercise[])=>{
    setSaving(true);setError('');elapsed.pause();const endTime=new Date().toISOString();
    try{
      await api.saveStrengthWorkout({sessionId:sessionId.current,title:plan?.title,athleteId:1,startTime:startTime.current,endTime,
        durationMinutes:Math.max(0,Math.round((Date.parse(endTime)-Date.parse(startTime.current))/60000)),completedExercises:exercises,
        exercises:exercises.map(ex=>({lift:ex.lift,sets:ex.sets.map(s=>({weight:s.weight,target_reps:s.targetReps,reps:s.velocities.map((v,i)=>({weight:s.weight,velocity:v??undefined,rep_num:i+1,rest_before:0})),set_end_rpe:s.rpe}))}))});
      localStorage.removeItem(KEYS.draft);setPhase('done');onSaved();
    }catch(e){setError((e as Error).message);elapsed.start();}finally{setSaving(false);}
  };
  const saveEndurance=async(r:{sport:EnduranceSport;durationMinutes:number;intensityType:IntensityType;rpe?:number;avgPower?:number})=>{
    setSaving(true);setError('');
    try{await api.saveEnduranceSession({sessionId:sessionId.current,athleteId:1,sport:r.sport,startTime:plan?startTime.current:new Date(Date.now()-r.durationMinutes*60000).toISOString(),durationMinutes:r.durationMinutes,intensityType:r.intensityType,rpe:r.rpe,averagePowerW:r.avgPower});
      localStorage.removeItem(KEYS.draft);elapsed.pause();setPhase('done');onSaved();
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  if(phase==='done')return <div className="screen"><div className="empty-state"><h2>Training afgerond!</h2><p>{isDemo?'Lokaal op dit toestel opgeslagen.':'Opgeslagen op de server.'}</p><button className="btn btn-secondary" onClick={()=>{setPhase('start');elapsed.reset();setCompleted({});sessionId.current=crypto.randomUUID();}}>Nieuwe training</button></div></div>;
  return <div className="screen">
    {error&&<p role="alert" className="editor-error">{error}</p>}{draftError&&<p role="alert" className="editor-error">{draftError}</p>}
    {!plan&&<div className="card"><h3>Vrije training</h3><button className="btn btn-primary btn-full" onClick={()=>{setPlan({date:localDate(),type:'kracht',title:'Vrije krachttraining',durationMinutes:readProfile()?.sessionDurationMinutes??60,exercises:[]});setEditor(true);}}>Krachttraining samenstellen</button><h3 style={{marginTop:20}}>Vrije duurtraining</h3><EnduranceFlow defaultSport="running" defaultDuration={45} defaultIntensity="easy" onSave={saveEndurance}/></div>}
    {plan&&<>
      <div style={{display:editor?'none':'block'}}>
        <div className="card"><h2>{plan.title}</h2><p className="text-small text-muted">{phase==='active'?`${elapsed.formatted} verstreken`:`Beschikbaar: ${plan.durationMinutes} min`}</p>
          {phase==='start'&&<><p className="text-small text-muted">{plan.reason}</p>{plan.exercises?.map(ex=><div key={ex.id} className="plan-summary"><strong>{ex.displayName}</strong><span className="text-small text-muted">{ex.sets.length} sets × {ex.sets[0]?.targetReps} · doel-RPE {ex.sets[0]?.targetRpe??'zelf kiezen'} · rust {ex.sets[0]?.restSec} sec</span></div>)}
            {plan.date>localDate()&&<p className="text-small text-muted">Gepland voor {plan.date}. Je kunt de training nu voorbereiden en op die dag starten.</p>}
            <button className="btn btn-primary btn-full" disabled={plan.date>localDate()||(plan.type==='kracht'&&!plan.exercises?.length)} onClick={start}>▶ Start training</button></>}
          {plan.type==='kracht'&&<button className="btn btn-secondary btn-full" style={{marginTop:10}} onClick={()=>setEditor(true)}>Training aanpassen</button>}
        </div>
        {phase==='active'&&plan.type==='kracht'&&<StrengthFlow exercises={plan.exercises??[]} hasVbt={hasVbt} completed={completed} onChange={record} onSave={saveStrength}/>}
        {phase==='active'&&plan.endurance&&<EnduranceFlow defaultSport={plan.endurance.sport} defaultDuration={plan.endurance.durationMinutes} defaultIntensity={plan.endurance.intensityType} onSave={saveEndurance}/>}
        {plan.type==='kracht'&&<VolumePanel plan={plan} completed={completed} sessionId={sessionId.current}/>}
      </div>
      {editor&&<PlanEditor plan={plan} completed={completed} sessionId={sessionId.current} onSave={saveEdit} onCancel={()=>setEditor(false)}/>}
    </>}
    {saving&&<div className="save-overlay"><div className="card">Opslaan…</div></div>}
  </div>;
}
