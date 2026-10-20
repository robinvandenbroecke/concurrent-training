import React, { useState, useEffect } from 'react';
import type {
  PlannedTraining, PlannedExercise, CompletedSet, CompletedExercise, LiftType, EnduranceSport, IntensityType
} from '../types';
import { api } from '../api/adapter';
import { LIFT_NAMES, SPORT_NAMES, INTENSITY_NAMES } from '../data/demoData';
import { useTimer } from '../hooks/useTimer';
import { IconCheck, IconClock } from '../components/Icons';
import { KEYS, parseVelocities, readDraft, writeJson } from '../api/local';

interface Props {
  plan: PlannedTraining | null;
  onSaved: () => void;
  isDemo: boolean;
  hasVbt: boolean;
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
  setNum, planned, completed, hasVbt, onComplete
}: {
  setNum: number;
  planned: { weight: number; targetReps: number; restSec: number };
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
  const done = !!completed;

  const submit = () => {
    const w = parseFloat(weight);
    const r = Number(reps);
    if (!Number.isFinite(w) || w <= 0 || w > 500 || !Number.isInteger(r) || r < 1 || r > 100) { setValidationError('Vul een geldig gewicht en 1–100 uitgevoerde reps in.'); return; }
    if (rpe && (!Number.isFinite(Number(rpe)) || Number(rpe) < 1 || Number(rpe) > 10)) { setValidationError('RPE moet tussen 1 en 10 liggen.'); return; }
    let velocities: (number | null)[];
    try { velocities = parseVelocities(hasVbt ? vel : '', r); } catch (e) { setValidationError((e as Error).message); return; }
    setValidationError('');
    onComplete({
      setNum,
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
          <label className="form-label">Gewicht (kg)</label>
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

      <button className="btn btn-primary btn-full btn-sm" onClick={submit}>
        <IconCheck /> Bevestig set {setNum}
      </button>
      {validationError && <p role="alert" className="text-small" style={{ color: 'var(--c-warn)' }}>{validationError}</p>}
    </div>
  );
}

// ── Strength workout flow ─────────────────────────────────────────────────────
function StrengthFlow({
  exercises, hasVbt, onSave, initialCompleted, onDraftChange
}: {
  exercises: PlannedExercise[];
  hasVbt: boolean;
  onSave: (completed: CompletedExercise[]) => void;
  initialCompleted: Record<number, CompletedSet[]>;
  onDraftChange: (completed: Record<number, CompletedSet[]>, index: number) => void;
}) {
  const [exIdx, setExIdx] = useState(0);
  const [completedSets, setCompletedSets] = useState<Record<number, CompletedSet[]>>(initialCompleted);
  const [showRest, setShowRest] = useState(false);
  const [restSec, setRestSec] = useState(120);

  const ex = exercises[exIdx];
  const mySets = completedSets[exIdx] ?? [];
  const nextSetNum = mySets.length + 1;
  const allDone = nextSetNum > ex.sets.length;

  useEffect(() => { onDraftChange(completedSets, exIdx); }, [completedSets, exIdx]);

  const handleComplete = (set: CompletedSet) => {
    const updated = { ...completedSets, [exIdx]: [...mySets.filter(s => s.setNum !== set.setNum), set].sort((a, b) => a.setNum - b.setNum) };
    setCompletedSets(updated);
    const plannedRest = ex.sets[set.setNum - 1]?.restSec ?? 120;
    // Show rest timer if more sets left
    if (set.setNum < ex.sets.length) {
      setRestSec(plannedRest);
      setShowRest(true);
    }
  };

  const canFinish = () => {
    return exercises.some((_, i) => (completedSets[i]?.length ?? 0) > 0);
  };

  const doSave = () => {
    const result = exercises.map((ex, i) => ({
      lift: ex.lift,
      displayName: ex.displayName,
      sets: completedSets[i] ?? [],
    })).filter(ex => ex.sets.length > 0);
    onSave(result);
  };

  return (
    <div>
      {showRest && <RestTimer seconds={restSec} onDone={() => setShowRest(false)} />}

      {/* Exercise tabs */}
      <div className="h-scroll" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, paddingBottom: 4, minWidth: 'max-content' }}>
          {exercises.map((ex, i) => {
            const done = (completedSets[i]?.length ?? 0) >= ex.sets.length;
            return (
              <button
                key={i}
                className={`pill ${exIdx === i ? 'selected' : ''}`}
                onClick={() => setExIdx(i)}
                style={done ? { borderColor: 'var(--c-success)', color: 'var(--c-success)' } : {}}
              >
                {done ? '✓ ' : ''}{ex.displayName}
              </button>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3>{ex.displayName}</h3>
          <span className="text-muted text-small">{mySets.length}/{ex.sets.length} sets</span>
        </div>

        {ex.sets.map((ps, i) => (
          <SetRow
            key={`${ex.lift}-${i}`}
            setNum={i + 1}
            planned={ps}
            completed={mySets.find(s => s.setNum === i + 1) ?? null}
            hasVbt={hasVbt}
            onComplete={handleComplete}
          />
        ))}

        {allDone && exIdx < exercises.length - 1 && (
          <button className="btn btn-secondary btn-full" style={{ marginTop: 8 }} onClick={() => setExIdx(exIdx + 1)}>
            Volgende: {exercises[exIdx + 1].displayName} →
          </button>
        )}
      </div>

      <button
        className="btn btn-primary btn-full"
        onClick={doSave}
        disabled={!canFinish()}
        style={{ marginTop: 8 }}
      >
        <IconCheck /> Training afronden
      </button>
      {!canFinish() && (
        <p className="text-muted text-xs" style={{ textAlign: 'center', marginTop: 8 }}>
          Leg minimaal één uitgevoerde set vast. Je kunt de training ook eerder afronden.
        </p>
      )}
    </div>
  );
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

// ── Main Training screen ──────────────────────────────────────────────────────
export default function Training({ plan, onSaved, isDemo, hasVbt }: Props) {
  const [phase, setPhase] = useState<'start' | 'active' | 'done'>(() => readDraft()?.phase ?? 'start');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const elapsed = useTimer(0, 'up');

  const startTime = React.useRef<string>(readDraft()?.startTime ?? new Date().toISOString());
  const sessionId = React.useRef<string>(crypto.randomUUID());
  const completed = React.useRef<Record<number, CompletedSet[]>>(readDraft()?.completed ?? {});
  const [flowKey, setFlowKey] = useState(0);
  const [draftError, setDraftError] = useState('');
  const previousPlan = React.useRef(plan);

  useEffect(() => {
    if (readDraft()?.phase === 'active') { elapsed.reset(Math.floor((Date.now() - Date.parse(startTime.current)) / 1000)); elapsed.start(); }
  }, []);

  useEffect(() => {
    if (previousPlan.current === plan) return;
    previousPlan.current = plan;
    const draft = readDraft();
    if (draft && draft.plan.date === plan?.date && draft.plan.title === plan?.title) {
      completed.current = draft.completed; startTime.current = draft.startTime; setPhase(draft.phase);
    } else {
      setPhase('start'); completed.current = {}; sessionId.current = crypto.randomUUID(); elapsed.reset();
    }
    setFlowKey(n => n + 1);
  }, [plan]);

  const persistDraft = (sets: Record<number, CompletedSet[]>, index: number) => {
    completed.current = sets;
    if (!plan || phase !== 'active') return;
    try { writeJson(KEYS.draft, { plan, phase, startTime: startTime.current, completed: sets, exerciseIndex: index }); setDraftError(''); }
    catch (e) { setDraftError((e as Error).message); }
  };

  const startSession = () => {
    startTime.current = new Date().toISOString();
    elapsed.reset(0);
    elapsed.start();
    completed.current = {};
    setPhase('active');
    if (plan) { try { writeJson(KEYS.draft, { plan, phase: 'active', startTime: startTime.current, completed: {}, exerciseIndex: 0 }); } catch (e) { setDraftError((e as Error).message); } }
  };

  const handleStrengthSave = async (completed: CompletedExercise[]) => {
    setSaving(true);
    setError(null);
    elapsed.pause();
    const endTime = new Date().toISOString();
    try {
      await api.saveStrengthWorkout({
        title: plan?.title, sessionId: sessionId.current,
        durationMinutes: Math.max(0, Math.round((Date.parse(endTime) - Date.parse(startTime.current)) / 60000)),
        completedExercises: completed,
        athleteId: 1,
        startTime: startTime.current,
        endTime,
        exercises: completed.map(ex => ({
          lift: ex.lift as LiftType,
          sets: ex.sets.map(s => ({
            weight: s.weight,
            target_reps: s.targetReps,
            reps: s.velocities.map((v, i) => ({
              weight: s.weight,
              velocity: v ?? undefined,
              rep_num: i + 1,
              rest_before: 0,
            })),
            set_end_rpe: s.rpe,
          })),
        })),
      });
      localStorage.removeItem(KEYS.draft);
      setPhase('done');
      onSaved();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Opslaan mislukt';
      setError(msg);
      elapsed.start();
    } finally {
      setSaving(false);
    }
  };

  const handleEnduranceSave = async (r: { sport: EnduranceSport; durationMinutes: number; intensityType: IntensityType; rpe?: number; avgPower?: number }) => {
    setSaving(true);
    setError(null);
    try {
      await api.saveEnduranceSession({
        sessionId: sessionId.current,
        athleteId: 1,
        sport: r.sport,
        startTime: startTime.current,
        durationMinutes: r.durationMinutes,
        intensityType: r.intensityType,
        rpe: r.rpe,
        averagePowerW: r.avgPower,
      });
      localStorage.removeItem(KEYS.draft);
      elapsed.pause();
      setPhase('done');
      onSaved();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Opslaan mislukt';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  if (phase === 'done') {
    return (
      <div className="screen" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
        <div style={{ fontSize: 56, marginBottom: 16 }}>✅</div>
        <h2 style={{ marginBottom: 8 }}>Training afgerond!</h2>
        <p className="text-muted text-small" style={{ textAlign: 'center', marginBottom: 24 }}>
          {isDemo ? 'Lokaal op dit toestel opgeslagen.' : 'Opgeslagen op de server.'}
        </p>
        <button className="btn btn-secondary" onClick={() => { setPhase('start'); elapsed.reset(); completed.current = {}; sessionId.current = crypto.randomUUID(); setFlowKey(n => n + 1); }}>
          Nieuwe training
        </button>
      </div>
    );
  }

  if (!plan && phase === 'start') {
    return (
      <div className="screen">
        {error && <p role="alert" style={{ color: 'var(--c-warn)' }}>{error}</p>}
        <div className="empty-state">
          <div className="icon">🏋️</div>
          <h3 style={{ marginBottom: 8 }}>Geen training gepland</h3>
          <p className="text-muted text-small" style={{ marginBottom: 20 }}>
            Ga naar <em>Vandaag</em> om een training te starten, of log een vrije sessie:
          </p>
        </div>
        <div className="card">
          <div className="card-title">Vrije duurtraining</div>
          <EnduranceFlow
            defaultSport="running"
            defaultDuration={45}
            defaultIntensity="z2"
            onSave={handleEnduranceSave}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      {/* Session header */}
      {draftError && <p role="alert" className="text-small" style={{ color: 'var(--c-warn)' }}>{draftError}</p>}
      {phase === 'active' && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row between">
            <div>
              <h3>{plan?.title ?? 'Training'}</h3>
              <span className="text-muted text-small row" style={{ gap: 4, marginTop: 2 }}>
                <IconClock /> {elapsed.formatted} verstreken
              </span>
            </div>
            {isDemo && <span className="demo-badge">LOKAAL</span>}
          </div>
        </div>
      )}

      {error && (
        <div style={{
          background: 'rgba(232,126,94,0.15)', border: '1px solid var(--c-warn)',
          borderRadius: 'var(--radius-sm)', padding: '10px 14px', marginBottom: 12,
          fontSize: 13, color: 'var(--c-warn)',
        }}>
          {error}
        </div>
      )}

      {phase === 'start' && plan && (
        <div>
          <div className="card">
            <h2 style={{ marginBottom: 8 }}>{plan.title}</h2>
            <p className="text-muted text-small" style={{ marginBottom: 16 }}>
              Geschatte duur: {plan.durationMinutes} min
            </p>
            {plan.exercises && plan.exercises.map(ex => (
              <div key={ex.lift} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{ex.displayName}</div>
                <div className="text-small text-muted">
                  {ex.sets.length} sets — {ex.sets.map(s => `${s.weight}kg×${s.targetReps}`).join(', ')}
                </div>
              </div>
            ))}
            {plan.endurance && (
              <div>
                <div style={{ fontWeight: 700 }}>{SPORT_NAMES[plan.endurance.sport]}</div>
                <div className="text-small text-muted">
                  {plan.endurance.durationMinutes} min — {INTENSITY_NAMES[plan.endurance.intensityType]}
                </div>
              </div>
            )}
            <div className="divider" />
            <button className="btn btn-primary btn-full" onClick={startSession}>
              ▶ Start training
            </button>
          </div>
        </div>
      )}

      {phase === 'active' && !!plan?.exercises?.length && (
        <StrengthFlow
          key={flowKey}
          exercises={plan.exercises}
          hasVbt={hasVbt}
          onSave={handleStrengthSave}
          initialCompleted={completed.current}
          onDraftChange={persistDraft}
        />
      )}

      {phase === 'active' && plan?.type === 'kracht' && !plan.exercises?.length && <p className="text-muted">Vul eerst recente werkgewichten in via je profiel om een krachtsessie samen te stellen.</p>}

      {phase === 'active' && plan?.endurance && (
        <EnduranceFlow
          defaultSport={plan.endurance.sport}
          defaultDuration={plan.endurance.durationMinutes}
          defaultIntensity={plan.endurance.intensityType}
          onSave={handleEnduranceSave}
        />
      )}

      {saving && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 300,
        }}>
          <div className="card" style={{ textAlign: 'center' }}>
            <p>Opslaan…</p>
          </div>
        </div>
      )}
    </div>
  );
}
