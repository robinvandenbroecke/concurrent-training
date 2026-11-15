import React, { useState } from 'react';
import type { AthleteProfile, EquipmentTag, ExperienceLevel, ProgramGoal, ProgramSettings } from '../types';
import { api } from '../api/adapter';
import { localDate, readProfile } from '../api/local';
import { EQUIPMENT_LABELS } from '../data/exercises';
import { EQUIPMENT_PRESETS, EXPERIENCE_LABELS, GOAL_LABELS, defaultProgram, weeklyShortfall } from '../domain/generator';
import { strengthSlots } from '../domain/program';

const GOAL_NOTES: Record<ProgramGoal, string> = {
  algemeen: 'Alle grote bewegingen, matige herhalingen. Een brede basis.',
  powerlifting: 'Squat, bankdrukken en deadlift eerst en zwaar, met weinig herhalingen; ondersteunend werk erna.',
  hypertrofie: 'Meer sets per spiergroep en hogere herhalingen; geen explosief blok. Het weekvolume telt het zwaarst.',
  power: 'Explosieve trekken of sprongen eerst, met lichte tot matige last en maximale snelheid; daarna zware basiskracht.',
  concurrent: 'Naast duursport: de hoofdoefeningen blijven, het extra beenwerk vervalt.',
};
const samePreset = (tags: EquipmentTag[]) => Object.entries(EQUIPMENT_PRESETS).find(([key, p]) => key !== 'eigen' && p.tags.length === tags.length && p.tags.every(t => tags.includes(t)))?.[0] ?? 'eigen';

/** Goal, experience and equipment for the generated strength programme. Nothing changes until the athlete saves. */
export default function ProgramSettingsCard({ profile, onSaved }: { profile: AthleteProfile; onSaved: (profile: AthleteProfile) => void }) {
  const stored = profile.program;
  const [draft, setDraft] = useState<ProgramSettings>(stored ?? defaultProgram(profile, localDate()));
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const set = (patch: Partial<ProgramSettings>) => { setDraft(d => ({ ...d, ...patch })); setMessage(''); };
  const toggle = (tag: EquipmentTag) => set({ equipment: draft.equipment.includes(tag) ? draft.equipment.filter(t => t !== tag) : [...draft.equipment, tag] });
  const preview: AthleteProfile = { ...profile, program: draft };
  const sessions = strengthSlots(preview), low = draft.goal === 'hypertrofie' ? weeklyShortfall(preview) : [];
  const save = async (program: ProgramSettings | undefined) => {
    const next = { ...(readProfile() ?? profile), program };
    if (!program) delete next.program;
    if (saving) return;
    setSaving(true);
    try {
    await api.saveProfile(next);
    setMessage(program ? 'Programma bewaard. Nieuwe trainingen volgen dit schema; trainingen die je zelf hebt aangepast blijven zoals ze zijn.' : 'Je gebruikt weer het oorspronkelijke startschema.');
    onSaved(next);
    } catch {
      setMessage("Bewaren is niet gelukt. Controleer je verbinding en probeer opnieuw. Je keuzes blijven hier staan.");
    } finally { setSaving(false); }
  };
  return <section className="card" aria-label="Krachtprogramma">
    <details>
      <summary className="card-title" style={{ cursor: 'pointer' }}>Krachtprogramma{stored ? `: ${GOAL_LABELS[stored.goal]}` : ' instellen'}</summary>
      <p className="text-small text-muted">Het schema is een startpunt dat je voor en tijdens elke training kunt aanpassen. De aantallen volgen groepsonderzoek en zijn geen persoonlijk gemeten grens.</p>
      <label className="text-xs text-muted">Doel
        <select className="form-select" aria-label="Doel van het krachtprogramma" value={draft.goal} onChange={e => set({ goal: e.target.value as ProgramGoal })}>
          {(Object.keys(GOAL_LABELS) as ProgramGoal[]).map(g => <option key={g} value={g}>{GOAL_LABELS[g]}</option>)}</select></label>
      <p className="text-xs text-muted" style={{ margin: '4px 0 10px' }}>{GOAL_NOTES[draft.goal]}</p>
      <label className="text-xs text-muted">Ervaring met krachttraining
        <select className="form-select" aria-label="Ervaring met krachttraining" value={draft.experience} onChange={e => set({ experience: e.target.value as ExperienceLevel })}>
          {(Object.keys(EXPERIENCE_LABELS) as ExperienceLevel[]).map(x => <option key={x} value={x}>{EXPERIENCE_LABELS[x]}</option>)}</select></label>
      <label className="text-xs text-muted" style={{ display: 'block', marginTop: 10 }}>Materiaal
        <select className="form-select" aria-label="Materiaal" value={samePreset(draft.equipment)} onChange={e => { if (e.target.value !== 'eigen') set({ equipment: [...EQUIPMENT_PRESETS[e.target.value].tags] }); }}>
          {Object.entries(EQUIPMENT_PRESETS).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}</select></label>
      <div className="setup-row" style={{ marginTop: 6 }}>{(Object.keys(EQUIPMENT_LABELS) as EquipmentTag[]).map(tag => <label key={tag} className="text-small">
        <input type="checkbox" checked={draft.equipment.includes(tag)} onChange={() => toggle(tag)} /> {EQUIPMENT_LABELS[tag]}</label>)}</div>
      <label className="text-small" style={{ display: 'block', marginTop: 10 }}><input type="checkbox" checked={draft.returning} onChange={e => set({ returning: e.target.checked, cycleStart: e.target.checked ? localDate() : draft.cycleStart })} /> Ik herbegin na een onderbreking: twee lichtere weken vanaf vandaag</label>
      <label className="text-small" style={{ display: 'block', marginTop: 6 }}><input type="checkbox" checked={draft.lighterWeek} onChange={e => set({ lighterWeek: e.target.checked })} /> Elke vierde week lichter</label>
      <p className="text-xs text-muted" style={{ marginTop: 4 }}>Een vaste lichtere week is een gewoonte om vermoeidheid te beheersen. Onderzoek toont er geen voordeel van voor kracht of spiergroei; kies wat voor jou werkt.</p>
      <p className="text-small" role="status" style={{ marginTop: 8 }}>Met je huidige dagen en prioriteit worden dat {sessions} {sessions === 1 ? 'krachttraining' : 'krachttrainingen'} per week van {profile.sessionDurationMinutes} minuten.
        {sessions === 0 ? ' Kies meer trainingsdagen of een andere prioriteit om kracht in te plannen.' : ''}
        {low.length ? ` Voor ${low.join(', ')} blijf je daarmee onder ongeveer tien sets per week.` : ''}
        {!profile.olympicExperience ? ' Olympische varianten met opvang worden niet ingepland zolang je geen techniekervaring hebt aangegeven; trekken en sprongen wel.' : ''}</p>
      <button className="btn btn-primary btn-full" style={{ marginTop: 8 }} disabled={saving} onClick={() => void save(draft)}>Programma bewaren</button>
      {stored && <button className="btn btn-ghost btn-sm" style={{ marginTop: 6 }} disabled={saving} onClick={() => void save(undefined)}>Terug naar het oorspronkelijke startschema</button>}
      {message && <p className="text-small" role="status">{message}</p>}
    </details>
  </section>;
}
