import React, { useState } from 'react';
import type { PlannedTraining } from '../types';
import { buildWeek, KEYS, localDate, readJson, readProfile, readSessions, writeJson } from '../api/local';
import { DEFAULT_TARGETS, LIFT_LABELS, MUSCLE_LABELS, volumeAdvice, type CompletedMap, type VolumeTargets } from '../domain/volume';
import type { Muscle, Powerlift } from '../data/exercises';

function loadSettings(){
  const s=readJson<{targets:VolumeTargets;muscleAlert:number}|null>(KEYS.volumeTargets,null);
  const valid=s&&(['squat','bench','deadlift'] as const).every(l=>Number.isFinite(s.targets?.[l]?.min)&&Number.isFinite(s.targets?.[l]?.max)&&s.targets[l].min>=0&&s.targets[l].max>=s.targets[l].min&&s.targets[l].max<=40);
  return valid?{targets:s.targets,muscleAlert:Number.isFinite(s.muscleAlert)&&s.muscleAlert>=8?s.muscleAlert:16}:{targets:DEFAULT_TARGETS,muscleAlert:16};
}
export default function VolumePanel({plan,completed={},sessionId}:{plan:PlannedTraining;completed?:CompletedMap;sessionId?:string}){
  const [settings,setSettings]=useState(loadSettings),[message,setMessage]=useState('');
  const profile=readProfile(); if(!profile)return null;
  const sessions=readSessions(),today=localDate(),week=buildWeek(profile,new Date(`${plan.date}T12:00:00`),sessions,readJson(KEYS.overrides,{})).map(d=>({...d,isPast:d.date<today,isToday:d.date===today}));
  const report=volumeAdvice(plan,week,sessions,profile,settings.targets,completed,sessionId,settings.muscleAlert);
  return <section className="card volume-panel" aria-label="Volumefeedback" aria-live="polite">
    <h3>Volume & tijd</h3>
    <p className="text-small text-muted">Deze sessie bij afronding: {report.current.workSets} kracht/accessoiressets · {report.current.powerReps} explosieve reps · circa {report.minutes} min.</p>
    <p className="text-xs text-muted">Kalenderweek {week[0]?.date}–{week[6]?.date}: {report.actual.workSets} sets al gelogd; {report.projected.workSets} inclusief deze sessie en resterende planning. Gemiste dagen worden niet ingehaald.</p>
    <div className="volume-grid">{report.liftStatus.map(s=><div key={s.lift} className={`volume-status ${s.status}`}>
      <strong>{LIFT_LABELS[s.lift]}: {s.sets} sets</strong><span>Weekdoel {s.min}–{s.max}</span>
      <span>{s.status==='laag'?'Onder je weekdoel — mogelijk te weinig':s.status==='hoog'?'Boven je weekdoel — mogelijk te veel':'Binnen je gekozen weekdoel'}</span>
    </div>)}</div>
    <p className="text-xs text-muted">Dit zijn instelbare startreferenties, geen bewezen persoonlijk optimum. Alleen directe powerliftwerksets tellen hierboven mee, ook bij lage RPE. Opwarmsets tellen niet mee. Gewicht en inspanning bepalen mee de waarde van een set.</p>
    {report.messages.length>0&&<ul className="volume-messages">{report.messages.map(m=><li key={m}>{m}</li>)}</ul>}
    <details><summary>Spiergroepen en onderbouwing</summary>
      <p className="text-small">Grove spiergroeptelling: directe sets + ½ indirecte sets. Voor deze benadering tellen sets onder RPE 6 niet mee; onbekende RPE voorlopig wel. Deze RPE-keuze is een praktische conventie. Power- en sprongsets blijven apart; hun vermoeidheid is hiermee niet nul.</p>
      <div className="volume-grid">{Object.entries(report.projected.muscles).map(([m,n])=><span key={m}>{MUSCLE_LABELS[m as Muscle]}: {n}</span>)}</div>
      <p className="text-small text-muted">Bij kracht tellen specificiteit, belasting en herhaalde blootstelling mee. Voor power: korte, snelle sets en voldoende rust. Meer volume geeft gemiddeld afnemende meeropbrengst. Herstel, slaap en andere sport bepalen mee wat passend is.</p>
      <p className="source-links"><a href="https://pubmed.ncbi.nlm.nih.gov/41843416/" target="_blank" rel="noreferrer">ACSM 2026</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/41343037/" target="_blank" rel="noreferrer">Volume 2026</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/36952649/" target="_blank" rel="noreferrer">NSCA olympisch</a></p>
    </details>
    <details><summary>Mijn volumedoelen aanpassen</summary>
      <p className="text-xs text-muted">Pas aan met je trainingsrespons of coach. De app meet geen maximale herstelbare dosis en kent trainingen buiten de app niet.</p>
      {(['squat','bench','deadlift'] as Powerlift[]).map(l=><div key={l} className="target-row"><strong>{LIFT_LABELS[l]}</strong>{(['min','max'] as const).map(k=><label key={k}>{k==='min'?'Min. sets':'Max. sets'}<input aria-label={`${LIFT_LABELS[l]} ${k}`} className="form-input" type="number" min="0" max="40" step="1" value={settings.targets[l][k]} onChange={e=>setSettings(s=>({...s,targets:{...s.targets,[l]:{...s.targets[l],[k]:Number(e.target.value)}}}))}/></label>)}</div>)}
      <label className="form-label">Signaalgrens per spiergroep per week<input className="form-input" type="number" min="8" max="40" value={settings.muscleAlert} onChange={e=>setSettings(s=>({...s,muscleAlert:Number(e.target.value)}))}/></label>
      <button type="button" className="btn btn-ghost btn-sm" onClick={()=>{try{
        if(Object.values(settings.targets).some(t=>!Number.isInteger(t.min)||!Number.isInteger(t.max)||t.min<0||t.max<t.min||t.max>40)||!Number.isInteger(settings.muscleAlert)||settings.muscleAlert<8||settings.muscleAlert>40)throw new Error('Gebruik hele setdoelen van 0–40 met max ≥ min; de spiergroepsignaalgrens is 8–40.');
        writeJson(KEYS.volumeTargets,settings);setMessage('Volumedoelen opgeslagen.');
      }catch(e){setMessage((e as Error).message);}}}>Bewaar volumedoelen</button>
      {message&&<p role="status" className="text-small">{message}</p>}
    </details>
  </section>;
}
