import React, { useRef, useState } from 'react';
import type { PlannedExercise, PlannedTraining } from '../types';
import { EXERCISES, createExercise, definition, normalizePlan } from '../data/exercises';
import { readProfile } from '../api/local';
import { editPrescription, moveExercise, removeExercise, replaceExercise, validatePlan } from '../domain/editing';
import type { CompletedMap } from '../domain/volume';
import VolumePanel from './VolumePanel';

function NumberField({label,value,onValue,min,max,step=1}:{label:string;value:number;onValue:(v:number)=>void;min:number;max:number;step?:number}){
  const [text,setText]=useState(String(value));
  React.useEffect(()=>setText(String(value)),[value]);
  return <label className="editor-field">{label}<input aria-label={label} className="form-input" type="number" required min={min} max={max} step={step} value={text} onChange={e=>{const t=e.target.value;setText(t);const n=Number(t);if(t!==''&&Number.isFinite(n)&&n>=min&&n<=max&&(step!==1||Number.isInteger(n)))onValue(n);}}/></label>;
}
export default function PlanEditor({plan,completed={},sessionId,onSave,onCancel}:{plan:PlannedTraining;completed?:CompletedMap;sessionId?:string;onSave:(p:PlannedTraining)=>Promise<void>;onCancel:()=>void}){
  const [working,setWorking]=useState(()=>normalizePlan(plan)),[search,setSearch]=useState(''),[category,setCategory]=useState(''),[equipment,setEquipment]=useState('');
  const [replacement,setReplacement]=useState<string|null>(null),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  const form=useRef<HTMLFormElement>(null),profile=readProfile()??undefined;
  const edit=(action:()=>PlannedTraining)=>{try{setWorking(action());setError('');}catch(e){setError((e as Error).message);}};
  const update=(ex:PlannedExercise,patch:Parameters<typeof editPrescription>[1])=>edit(()=>({...working,exercises:working.exercises?.map(e=>e.id===ex.id?editPrescription(e,patch,completed):e)}));
  const filtered=EXERCISES.filter(d=>(!category||d.category===category)&&(!equipment||d.equipment===equipment)&&`${d.name} ${d.id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase().trim()));
  const add=(id:string)=>edit(()=>{
    if(!replacement&&(working.exercises?.length??0)>=30)throw new Error('Maximaal 30 oefeningen per sessie.');
    const ex=createExercise(id,profile);
    const result=replacement?replaceExercise(working,replacement,ex,completed):{...working,exercises:[...(working.exercises??[]),ex]};
    setReplacement(null);return result;
  });
  return <div className="plan-editor">
    <div className="card"><h2>Training aanpassen</h2><p className="text-small text-muted">Wijzig de volgorde, oefeningen en resterende sets. Groepsvelden gelden voor alle resterende sets. Bevestigde sets en hun meetgegevens blijven behouden.</p>
    </div>
    <form ref={form} onSubmit={async e=>{e.preventDefault();try{validatePlan(working);setSaving(true);await onSave(working);}catch(e){setError((e as Error).message);}finally{setSaving(false);}}}>
      <div className="card"><NumberField label="Beschikbare tijd (min)" value={working.durationMinutes} min={15} max={180} onValue={n=>setWorking(p=>({...p,durationMinutes:n}))}/></div>
      {(working.exercises??[]).map((ex,index)=>{
        const done=completed[ex.id!]??[],d=definition(ex),first=ex.sets.find(s=>!done.some(c=>c.setNum===s.setNum))??ex.sets[0];
        const locked=done.length>0;
        return <fieldset className="card editor-exercise" key={ex.id}><legend>{index+1}. {ex.displayName}</legend>
          <p className="text-xs text-muted">{d?.cue} {done.length>0&&`${done.length} set(s) bevestigd en vergrendeld.`}</p>
          <div className="editor-fields">
            <NumberField label={`Sets ${ex.displayName}`} value={ex.sets.length} min={Math.max(1,...done.map(s=>s.setNum))} max={12} onValue={n=>update(ex,{count:n})}/>
            <NumberField label={`${d?.load==='assistance'?'Ondersteuning':d?.load==='bodyweight'?'Extra gewicht':'Gewicht'} ${ex.displayName} (kg)`} value={first.weight} min={0} max={500} step={.5} onValue={n=>update(ex,{weight:n})}/>
            <NumberField label={`Reps ${ex.displayName}`} value={first.targetReps} min={1} max={30} onValue={n=>update(ex,{reps:n})}/>
            <NumberField label={`Doel-RPE ${ex.displayName}`} value={first.targetRpe??7} min={4} max={10} step={.5} onValue={n=>update(ex,{rpe:n})}/>
            <NumberField label={`Rust ${ex.displayName} (sec)`} value={first.restSec} min={15} max={600} step={15} onValue={n=>update(ex,{rest:n})}/>
            <label className="editor-field">Settype<select aria-label={`Settype ${ex.displayName}`} className="form-select" value={first.kind??'work'} onChange={e=>update(ex,{kind:e.target.value as 'work'|'warmup'})}><option value="work">Werksets</option><option value="warmup">Opwarmsets</option></select></label>
          </div>
          <div className="row wrap editor-actions">
            <button type="button" className="btn btn-ghost btn-sm" aria-label={`${ex.displayName} omhoog`} disabled={index===0} onClick={()=>edit(()=>moveExercise(working,ex.id!,-1))}>↑</button>
            <button type="button" className="btn btn-ghost btn-sm" aria-label={`${ex.displayName} omlaag`} disabled={index===(working.exercises?.length??0)-1} onClick={()=>edit(()=>moveExercise(working,ex.id!,1))}>↓</button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={locked} onClick={()=>setReplacement(ex.id!)}>Vervangen</button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={locked} onClick={()=>edit(()=>removeExercise(working,ex.id!,completed))}>Verwijderen</button>
          </div>
        </fieldset>;
      })}
      <div className="card catalogue"><h3>Oefeningencatalogus</h3>
        <p className="text-small text-muted">{EXERCISES.length} oefeningen. Gewichten van andere oefeningen worden niet automatisch overgenomen.</p>
        {replacement&&<p role="status">Vervang {working.exercises?.find(e=>e.id===replacement)?.displayName}: kies hieronder.<button type="button" className="btn btn-ghost btn-sm" onClick={()=>setReplacement(null)}>Annuleer vervanging</button></p>}
        <input className="form-input" type="search" aria-label="Zoek oefening" placeholder="Zoek oefening…" value={search} onChange={e=>setSearch(e.target.value)}/>
        <div className="editor-fields catalogue-filters"><label>Categorie<select aria-label="Oefeningcategorie" className="form-select" value={category} onChange={e=>setCategory(e.target.value)}><option value="">Alle categorieën</option>{['Powerlifting','Olympisch','Accessoires','Sprongen'].map(c=><option key={c}>{c}</option>)}</select></label>
        <label>Materiaal<select aria-label="Oefeningmateriaal" className="form-select" value={equipment} onChange={e=>setEquipment(e.target.value)}><option value="">Alle materialen</option>{['Halter','Dumbbells','Machine/kabel','Lichaamsgewicht'].map(c=><option key={c}>{c}</option>)}</select></label></div>
        <div className="catalogue-list">{filtered.map(d=><div key={d.id} className="catalogue-item"><div><strong>{d.name}</strong><span className="text-xs text-muted">{d.category} · {d.equipment}{d.catch?' · techniek met opvang':''}</span></div><button type="button" aria-label={`${replacement?'Vervang door':'Toevoegen'}: ${d.name}`} className="btn btn-secondary btn-sm" onClick={()=>add(d.id)}>{replacement?'Kies':'+ Voeg toe'}</button></div>)}{filtered.length===0&&<p>Geen oefeningen gevonden.</p>}</div>
      </div>
      <VolumePanel plan={working} completed={completed} sessionId={sessionId}/>
      {error&&<p role="alert" className="editor-error">{error}</p>}
      <div className="editor-footer"><button type="button" disabled={saving} className="btn btn-secondary" onClick={onCancel}>Annuleren</button><button type="submit" disabled={saving} className="btn btn-primary">{saving?'Opslaan…':'Wijzigingen bewaren'}</button></div>
    </form>
  </div>;
}
