import React, { useEffect, useState } from 'react';
import { evaluateEngine, type EngineOutcome } from '../engine/client';
import { concurrentLines, effortLine, enduranceLines, exerciseName, loadLines, modelLines, outcomeNotice, strengthLines } from '../engine/text';
import { localDate, readProfile, readSessions } from '../api/local';

/** Shows only what the engine could state from the user's own data, with the reason when it could not. */
export default function EngineCard({ compact = false }: { compact?: boolean }) {
  const [outcome, setOutcome] = useState<EngineOutcome | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setOutcome(null);
    evaluateEngine(readSessions(), readProfile(), localDate(), { force: attempt > 0 }).then(o => { if (live) setOutcome(o); });
    return () => { live = false; };
  }, [attempt]);
  if (!outcome) return <section className="card" aria-busy="true"><div className="card-title">Inzicht uit je eigen gegevens</div><p className="text-small text-muted" role="status">Berekenen… Een slapende server kan tot een minuut nodig hebben.</p></section>;
  const notice = outcomeNotice(outcome);
  const response = outcome.state === 'ok' ? outcome.response : outcome.cached?.response;
  const staleDate = outcome.state === 'unavailable' ? outcome.cached?.fetchedAt.slice(0, 10) : undefined;
  const strength = response?.strength.filter(b => b.e1rm_estimate.status === 'ok' || b.velocity.length > 0) ?? [];
  return <section className="card" aria-label="Inzicht uit je eigen gegevens">
    <div className="card-title">Inzicht uit je eigen gegevens</div>
    {notice && <p className="text-small" role="status">{notice} <button className="btn btn-ghost btn-sm" onClick={() => setAttempt(n => n + 1)}>Opnieuw proberen</button></p>}
    {staleDate && <p className="text-xs text-muted">Hieronder staat de laatst bekende berekening van {staleDate}; je gegevens zijn sindsdien gewijzigd.</p>}
    {response && <>
      <p className="text-small text-muted">Er is geen gevalideerde belastbaarheidsscore. Je ziet metingen, schattingen met hun onzekerheid en de reden wanneer een uitspraak niet mogelijk is.</p>
      <h3 className="engine-heading">Belasting</h3>
      <ul className="engine-list">{loadLines(response).map(l => <li key={l}>{l}</li>)}</ul>
      {modelLines(response).length > 0 && <><h3 className="engine-heading">Verwachte restvermoeidheid (experimenteel model)</h3>
        <ul className="engine-list">{modelLines(response).map(l => <li key={l}>{l}</li>)}</ul></>}
      {concurrentLines(response).length > 0 && <><h3 className="engine-heading">Kracht en duur op dezelfde dag</h3>
        <ul className="engine-list">{concurrentLines(response).slice(compact ? -2 : -6).map(l => <li key={l}>{l}</li>)}</ul></>}
      {(!compact || response.endurance.cp_model.efforts_used > 0 || response.endurance.cp_model.status !== 'insufficient_data') && <><h3 className="engine-heading">Duurvermogen</h3>
        <ul className="engine-list">{[...enduranceLines(response), effortLine(response)].filter(Boolean).map(l => <li key={l!}>{l}</li>)}</ul></>}
      {strength.length === 0
        ? <p className="text-small text-muted">Nog geen krachtuitspraken: daarvoor is een werkset met RPE 7 of hoger nodig, of snelheidsmetingen op minstens drie gewichten.</p>
        : strength.slice(0, compact ? 3 : 40).map(block => <details key={block.exercise} open={!compact}>
          <summary>{exerciseName(block.exercise)} · {block.sessions} trainingen</summary>
          <ul className="engine-list">{strengthLines(block).map(l => <li key={l}>{l}</li>)}</ul></details>)}
      <p className="text-xs text-muted">Voor deze berekening gaan je trainingen zonder naam, titels of notities naar de rekenserver. Die bewaart ze niet.</p>
      <p className="text-xs text-muted">Rekenmotor {response.engine_version}, contract {response.contract_version}, op basis van {response.sessions_used} trainingen. Controlecode invoer: {response.input_digest.slice(0, 12)}.</p>
    </>}
  </section>;
}
