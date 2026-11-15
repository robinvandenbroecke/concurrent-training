import React, { useEffect, useState } from 'react';
import type { WeekDay } from '../types';
import { api } from '../api/adapter';
import { localDate, readProfile, readSessions } from '../api/local';
import { planItem, planWeek, type PlanOption, type PlanOutcome } from '../engine/client';
import { UNAVAILABLE } from '../engine/text';

const nl = (n: number) => n.toLocaleString('nl-BE', { maximumFractionDigits: 1 });
const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${nl(Math.abs(n))} %`;
const dayLabel = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString('nl-BE', { weekday: 'short', day: 'numeric', month: 'numeric' });

/** Asks the engine in which order the coming trainings are expected to interfere least. Advice, never applied unasked. */
export default function WeekPlanner({ onChanged }: { onChanged: () => void }) {
  const [days, setDays] = useState<WeekDay[]>([]);
  const [keys, setKeys] = useState<Record<string, boolean>>({});
  const [hour, setHour] = useState(18);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<PlanOutcome | null>(null);
  const [message, setMessage] = useState('');
  useEffect(() => { let live = true; api.getUpcomingDays().then(d => { if (live) setDays(d); }); return () => { live = false; }; }, []);
  const items = days.map(d => planItem(d.planned!, !!keys[d.date])).filter(Boolean) as NonNullable<ReturnType<typeof planItem>>[];
  const title = (date: string) => days.find(d => d.date === date)?.planned?.title ?? date;
  if (days.length < 2 || items.length < 2) return <section className="card" aria-label="Volgorde doorrekenen">
    <div className="card-title">Volgorde doorrekenen</div>
    <p className="text-small text-muted">Daarvoor zijn minstens twee geplande trainingen in de komende zeven dagen nodig.</p></section>;
  const run = async () => {
    setBusy(true); setMessage(''); setOutcome(null);
    try { setOutcome(await planWeek(readSessions(), readProfile(), localDate(), items, items.map(i => i.label), hour)); } finally { setBusy(false); }
  };
  const moves = (option: PlanOption) => option.sessions.map(s => ({ from: s.label, to: s.start.slice(0, 10) }));
  const unchanged = (option: PlanOption) => moves(option).every(m => m.from === m.to);
  const apply = async (option: PlanOption) => {
    setBusy(true); setMessage('');
    try { await api.applyArrangement(moves(option)); setOutcome(null); setMessage('De volgorde is overgenomen in je planning.'); onChanged(); }
    catch (e) { setMessage((e as Error).message); } finally { setBusy(false); }
  };
  const rows = (option: PlanOption) => <ul className="engine-list">{option.sessions.map(s => <li key={s.label}>
    <strong>{dayLabel(s.start.slice(0, 10))}</strong> — {title(s.label)}{s.key ? ' (belangrijkste)' : ''}: {Math.abs(s.expected_fatigue_effect_pct) < 0.25
      ? 'geen merkbare restvermoeidheid verwacht' : `verwacht effect van eerdere trainingen ${signed(s.expected_fatigue_effect_pct)} (onzekerheid ${signed(s.low_pct)} tot ${signed(s.high_pct)})`}
    {s.label !== s.start.slice(0, 10) && <span className="text-muted"> · nu gepland op {dayLabel(s.label)}</span>}</li>)}</ul>;
  const response = outcome?.state === 'ok' ? outcome.response : null;
  const priors = response && (response.basis.strength === 'group_level_priors_only' || response.basis.endurance === 'group_level_priors_only');
  return <section className="card" aria-label="Volgorde doorrekenen">
    <div className="card-title">Volgorde doorrekenen</div>
    <p className="text-small text-muted">Het model schat voor elke volgorde hoe fris je aan elke training begint. De trainingen zelf en de dagen blijven dezelfde; alleen de volgorde wisselt.</p>
    <ul className="engine-list" style={{ listStyle: 'none', paddingLeft: 0 }}>{days.map(d => <li key={d.date}>
      <label><input type="checkbox" checked={!!keys[d.date]} onChange={e => { setKeys(k => ({ ...k, [d.date]: e.target.checked })); setOutcome(null); }} /> {dayLabel(d.date)} — {d.planned!.title} <span className="text-muted">· belangrijkste training</span></label></li>)}</ul>
    <label className="text-xs text-muted">Je traint meestal
      <select className="form-select" value={hour} onChange={e => { setHour(Number(e.target.value)); setOutcome(null); }}>
        <option value={8}>'s ochtends</option><option value={18}>'s avonds</option></select></label>
    <button className="btn btn-secondary btn-full" style={{ marginTop: 10 }} disabled={busy} onClick={run}>{busy ? 'Berekenen…' : 'Volgorde doorrekenen'}</button>
    {message && <p className="text-small" role="status">{message}</p>}
    {outcome?.state === 'unavailable' && <p className="text-small" role="status">{UNAVAILABLE[outcome.reason] ?? UNAVAILABLE.error}</p>}
    {response && <>
      <h3 className="engine-heading">{unchanged(response.options[0]) ? 'Je huidige volgorde komt als beste uit' : 'Voorgestelde volgorde'}</h3>
      {rows(response.options[0])}
      {response.difference_best_to_worst_pct !== null && <p className="text-small text-muted">Tussen de beste en de slechtste van {response.arrangements_evaluated} volgordes zit volgens het model {nl(response.difference_best_to_worst_pct)} % verschil in de samengetelde score.</p>}
      <p className="text-small text-muted">{priors
        ? 'Deze rangschikking berust op voorlopige modelaannames, geïnspireerd op groepsonderzoek, niet op jouw metingen. De onzekerheid is groter dan de verschillen: lees ze als een richting, niet als een voorspelling.'
        : 'Deze rangschikking gebruikt je eigen metingen samen met voorlopige modelaannames, geïnspireerd op groepsonderzoek.'} Het model is niet op echte atleten gevalideerd en zegt niets over blessurerisico.</p>
      {!unchanged(response.options[0]) && <button className="btn btn-primary btn-full" disabled={busy} onClick={() => apply(response.options[0])}>Deze volgorde overnemen</button>}
      {response.options.length > 1 && <details style={{ marginTop: 8 }}><summary className="text-small">Andere volgordes die bijna even goed scoren</summary>
        {response.options.slice(1).map((option, i) => <div key={i}>{rows(option)}{!unchanged(option) && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => apply(option)}>Deze overnemen</button>}</div>)}</details>}
    </>}
  </section>;
}
