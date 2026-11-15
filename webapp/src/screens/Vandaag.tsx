import React, { useEffect, useState } from 'react';
import type { PlannedTraining, AthleteProfile, MaximalEffort, VelocityMetric } from '../types';
import { api } from '../api/adapter';
import { isCalendarDate, localDate, readProfile } from '../api/local';
import EngineCard from '../components/EngineCard';
import ProgramSettingsCard from '../components/ProgramSettingsCard';
import { SPORT_NAMES, INTENSITY_NAMES } from '../data/names';
import { IconPlay, IconClock } from '../components/Icons';

interface Props {
  profile: AthleteProfile;
  onProfileChanged?: (profile: AthleteProfile) => void;
  onStartTraining: (plan: PlannedTraining) => void;
  onEditTraining: (plan: PlannedTraining) => void;
  isDemo: boolean;
}

const METRICS: [VelocityMetric, string][] = [['unspecified', 'Niet opgegeven'], ['mean_concentric', 'Gemiddelde concentrische snelheid'],
  ['mean_propulsive', 'Gemiddelde propulsieve snelheid'], ['peak', 'Pieksnelheid']];

/** Meter and metric are stored with every new velocity; without them velocities cannot be compared over time. */
function VelocitySetup({ profile }: { profile: AthleteProfile }) {
  const [metric, setMetric] = useState<VelocityMetric>(profile.velocitySetup?.metric ?? 'unspecified');
  const [device, setDevice] = useState(profile.velocitySetup?.deviceId ?? '');
  const [saved, setSaved] = useState(false);
  const save = async (nextMetric: VelocityMetric, nextDevice: string) => {
    const current = readProfile() ?? profile;
    await api.saveProfile({ ...current, velocitySetup: { metric: nextMetric, deviceId: nextDevice.trim().slice(0, 64) } });
    setSaved(true);
  };
  return <div>
    <div className="setup-row">
      <label className="text-xs text-muted">Snelheidsmaat
        <select className="form-select" value={metric} onChange={e => { const m = e.target.value as VelocityMetric; setMetric(m); void save(m, device); }}>
          {METRICS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="text-xs text-muted">Snelheidsmeter (merk en type)
        <input className="form-input" value={device} maxLength={64} placeholder="bv. lineaire encoder" onChange={e => { setDevice(e.target.value); setSaved(false); }} onBlur={() => void save(metric, device)} /></label>
    </div>
    <p className="text-xs text-muted" style={{ marginTop: 6 }}>{saved ? 'Bewaard. ' : ''}Geldt voor nieuwe metingen. Snelheden van een andere meter of maat worden nooit in hetzelfde profiel gebruikt.</p>
  </div>;
}

/** All-out efforts are the only basis for a critical-power fit; nothing is derived from ordinary rides. */
function MaximalEfforts({ profile }: { profile: AthleteProfile }) {
  const [efforts, setEfforts] = useState<MaximalEffort[]>(profile.maximalEfforts ?? []);
  const [date, setDate] = useState(localDate()), [minutes, setMinutes] = useState(''), [seconds, setSeconds] = useState(''), [power, setPower] = useState('');
  const [error, setError] = useState('');
  const store = async (next: MaximalEffort[]) => { await api.saveProfile({ ...(readProfile() ?? profile), maximalEfforts: next }); setEfforts(next); };
  const add = async () => {
    const duration = Number(minutes || 0) * 60 + Number(seconds || 0), watts = Number(power);
    if (!isCalendarDate(date) || date > localDate() || !Number.isFinite(duration) || duration < 120 || duration > 1200 || !Number.isFinite(watts) || watts < 50 || watts > 2000) {
      setError('Vul een datum tot en met vandaag, een duur van 2 tot 20 minuten en een vermogen van 50 tot 2000 W in.'); return; }
    if (efforts.length >= 20) { setError('Maximaal 20 inspanningen. Verwijder eerst een oude.'); return; }
    setError(''); await store([...efforts, { date, durationSeconds: duration, powerW: watts }].sort((a, b) => a.date.localeCompare(b.date) || a.durationSeconds - b.durationSeconds));
    setMinutes(''); setSeconds(''); setPower('');
  };
  return <details style={{ marginTop: 12 }}>
    <summary className="text-small">Maximale inspanningen op de fiets ({efforts.length})</summary>
    <p className="text-xs text-muted" style={{ margin: '6px 0' }}>Alleen inspanningen waarbij je voluit ging tot je niet meer kon, tussen 2 en 20 minuten. Drie van verschillende duur binnen enkele weken zijn nodig voor een critical power.</p>
    {efforts.map((e, i) => <div key={`${e.date}:${e.durationSeconds}:${e.powerW}:${i}`} className="row between text-small" style={{ marginBottom: 4 }}>
      <span>{e.date} · {Math.floor(e.durationSeconds / 60)}:{String(Math.round(e.durationSeconds % 60)).padStart(2, '0')} · {e.powerW} W</span>
      <button className="btn btn-ghost btn-sm" aria-label={`Verwijder inspanning van ${e.date}`} onClick={() => void store(efforts.filter((_, j) => j !== i))}>Verwijderen</button></div>)}
    <div className="setup-row">
      <label className="text-xs text-muted">Datum<input className="form-input" type="date" value={date} max={localDate()} onChange={e => setDate(e.target.value)} /></label>
      <label className="text-xs text-muted">Gemiddeld vermogen (W)<input className="form-input" inputMode="numeric" value={power} onChange={e => setPower(e.target.value)} /></label>
      <label className="text-xs text-muted">Minuten<input className="form-input" inputMode="numeric" value={minutes} onChange={e => setMinutes(e.target.value)} /></label>
      <label className="text-xs text-muted">Seconden<input className="form-input" inputMode="numeric" value={seconds} onChange={e => setSeconds(e.target.value)} /></label>
    </div>
    {error && <p role="alert" className="editor-error">{error}</p>}
    <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={() => void add()}>Inspanning toevoegen</button>
  </details>;
}

export default function Vandaag({ profile, onStartTraining, onEditTraining, isDemo, onProfileChanged }: Props) {
  const [plan, setPlan] = useState<PlannedTraining | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getTodayPlan()
      .then(p => { setPlan(p); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="screen">
      <div className="empty-state"><p className="text-muted">Laden…</p></div>
    </div>
  );

  return (
    <div className="screen">
      {isDemo && (
        <div style={{
          background: 'rgba(232,184,109,0.12)', border: '1px solid rgba(232,184,109,0.3)',
          borderRadius: 'var(--radius-sm)', padding: '8px 12px', marginBottom: 12, fontSize: 12,
        }}>
          <span className="text-accent" style={{ fontWeight: 700 }}>LOKAAL</span>
          {' '}— Je gegevens blijven op dit toestel. Het onderzoeksmodel is niet gekoppeld.
        </div>
      )}

      {/* What the engine can state from the user's own records */}
      <EngineCard compact />

      {/* Today's plan */}
      <div className="card">
        <div className="card-title">Voorlopig trainingsplan</div>

        {!plan ? (
          <div className="empty-state" style={{ padding: '16px 0' }}>
            <p className="text-muted">Vandaag is geen training gepland. Bekijk de gekozen dagen onder Week.</p>
          </div>
        ) : (
          <>
            <div className="row between" style={{ marginBottom: 8 }}>
              <div>
                <h3>{plan.title}</h3>
                <div className="row" style={{ gap: 8, marginTop: 4 }}>
                  <span className={`tag tag-${plan.type}`}>{plan.type === 'kracht' ? 'Kracht' : 'Duur'}</span>
                  <span className="text-muted text-small row" style={{ gap: 4 }}>
                    <IconClock /> {plan.durationMinutes} min
                  </span>
                </div>
              </div>
            </div>

            {plan.reason && (
              <div style={{
                background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)',
                padding: '8px 12px', marginBottom: 12,
              }}>
                <p className="text-small text-muted">💡 {plan.reason}</p>
              </div>
            )}

            {plan.exercises && (
              <div style={{ marginBottom: 12 }}>
                {plan.exercises.map(ex => (
                  <div key={ex.id??ex.lift} style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>{ex.displayName}</div>
                    <div className="text-small text-muted">
                      {ex.sets.length}×{ex.sets[0]?.targetReps ?? 0} @ {ex.sets.map(s => `${s.weight}kg`).join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {plan.endurance && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>
                  {SPORT_NAMES[plan.endurance.sport]}
                </div>
                <div className="text-small text-muted">
                  {plan.endurance.durationMinutes} min — {INTENSITY_NAMES[plan.endurance.intensityType]}
                </div>
                <div className="text-small text-muted">{plan.endurance.description}</div>
              </div>
            )}

            <button
              className="btn btn-primary btn-full"
              onClick={() => onStartTraining(plan)}
              style={{ gap: 8 }}
            >
              <IconPlay /> Start training
            </button>
            {plan.type==='kracht'&&<button className="btn btn-secondary btn-full" style={{marginTop:8}} onClick={()=>onEditTraining(plan)}>Training aanpassen</button>}
          </>
        )}
      </div>

      <ProgramSettingsCard profile={profile} onSaved={p => onProfileChanged?.(p)} />

      {/* Quick stats */}
      <div className="card">
        <div className="card-title">Profiel</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div style={{ background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)', padding: 10 }}>
            <div className="text-xs text-muted">Doel</div>
            <div style={{ fontWeight: 700, marginTop: 2, textTransform: 'capitalize' }}>{profile.priority}</div>
          </div>
          <div style={{ background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)', padding: 10 }}>
            <div className="text-xs text-muted">Sessieduur</div>
            <div style={{ fontWeight: 700, marginTop: 2 }}>{profile.sessionDurationMinutes} min</div>
          </div>
          <div style={{ background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)', padding: 10 }}>
            <div className="text-xs text-muted">VBT</div>
            <div style={{ fontWeight: 700, marginTop: 2 }}>{profile.hasVbt ? 'Actief' : 'Niet aangesloten'}</div>
          </div>
          <div style={{ background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)', padding: 10 }}>
            <div className="text-xs text-muted">Trainingsdagen/week</div>
            <div style={{ fontWeight: 700, marginTop: 2 }}>{profile.availableDays.length}</div>
          </div>
        </div>
        {profile.hasVbt && <VelocitySetup profile={profile} />}
        <MaximalEfforts profile={profile} />
      </div>
    </div>
  );
}
