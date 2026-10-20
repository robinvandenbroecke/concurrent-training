import React, { useState } from 'react';
import type { AthleteProfile, Priority, LiftType } from '../types';
import { LIFT_NAMES } from '../data/demoData';

interface Props {
  onComplete: (profile: AthleteProfile) => void;
}

const DAYS = ['Zo', 'Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za'];
const DAY_INDICES = [0, 1, 2, 3, 4, 5, 6];

const TOTAL_STEPS = 5;

export default function Onboarding({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [priority, setPriority] = useState<Priority>('balans');
  const [experience, setExperience] = useState(2);
  const [days, setDays] = useState<number[]>([1, 3, 5]);
  const [duration, setDuration] = useState(60);
  const [hasVbt, setHasVbt] = useState(false);
  const [capacities, setCapacities] = useState<Partial<Record<LiftType, number>>>({});
  const [saveError, setSaveError] = useState('');

  const toggleDay = (d: number) => {
    setDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d].sort());
  };

  const updateCapacity = (lift: LiftType, val: string) => {
    const n = parseFloat(val);
    if (val === '') setCapacities(p => { const next = { ...p }; delete next[lift]; return next; });
    else if (Number.isFinite(n) && n > 0 && n <= 500) setCapacities(p => ({ ...p, [lift]: n }));
  };

  const canNext = () => {
    if (step === 0) return name.trim().length > 0;
    if (step === 2) return days.length > 0;
    return true;
  };

  const next = () => {
    if (step < TOTAL_STEPS - 1) setStep(s => s + 1);
    else finish();
  };

  const finish = async () => {
    try { await onComplete({
      name: name.trim() || 'Atleet',
      priority,
      experienceYears: experience,
      availableDays: days,
      sessionDurationMinutes: duration,
      hasVbt,
      hasStravaSync: false,
      capacities,
      onboardingComplete: true,
    }); } catch (e) { setSaveError((e as Error).message); }
  };

  return (
    <div className="onboarding-screen">
      {/* Progress */}
      <div style={{ padding: '20px 16px 0', background: 'var(--c-bg)' }}>
        <div className="progress-dots">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div key={i} className={`progress-dot ${i <= step ? 'done' : ''}`} />
          ))}
        </div>
        <div className="text-muted text-small" style={{ textAlign: 'center', marginBottom: 8 }}>
          Stap {step + 1} van {TOTAL_STEPS}
        </div>
      </div>

      <div className="onboarding-content">
        {step === 0 && (
          <div>
            <h1 style={{ marginBottom: 8 }}>Welkom 👋</h1>
            <p className="text-muted" style={{ marginBottom: 24 }}>
              Concurrent Training helpt je kracht en duur slim te combineren.
              We starten met een paar korte vragen.
            </p>
            <div className="form-group">
              <label className="form-label">Jouw naam</label>
              <input
                className="form-input"
                type="text"
                placeholder="Naam"
                value={name}
                onChange={e => setName(e.target.value)}
                autoFocus
                maxLength={80}
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div>
            <h2 style={{ marginBottom: 8 }}>Wat is jouw doel?</h2>
            <p className="text-muted text-small" style={{ marginBottom: 20 }}>
              Dit bepaalt de nadruk van je trainingsplanning.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {([
                ['kracht', 'Kracht', 'Prioriteit op spiermassa en sterker worden'],
                ['duur', 'Duur', 'Prioriteit op conditie, VO₂max en uithoudingsvermogen'],
                ['balans', 'Balans', 'Gelijkwaardige nadruk op kracht én duur'],
              ] as [Priority, string, string][]).map(([val, label, desc]) => (
                <button
                  key={val}
                  className={`card ${priority === val ? 'card--selected' : ''}`}
                  onClick={() => setPriority(val)}
                  style={{
                    border: `2px solid ${priority === val ? 'var(--c-accent)' : 'var(--c-border)'}`,
                    cursor: 'pointer', textAlign: 'left', background: 'var(--c-surface)',
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: 3 }}>{label}</div>
                  <div className="text-muted text-small">{desc}</div>
                </button>
              ))}
            </div>

            <div className="form-group" style={{ marginTop: 20 }}>
              <label className="form-label">Ervaring met krachttraining</label>
              <select
                className="form-select"
                value={experience}
                onChange={e => setExperience(Number(e.target.value))}
              >
                <option value={0}>Beginner (&lt; 1 jaar)</option>
                <option value={2}>Gemiddeld (1–3 jaar)</option>
                <option value={5}>Gevorderd (3–7 jaar)</option>
                <option value={10}>Expert (7+ jaar)</option>
              </select>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 style={{ marginBottom: 8 }}>Beschikbare dagen</h2>
            <p className="text-muted text-small" style={{ marginBottom: 20 }}>
              Op welke dagen kun je trainen? Kies minimaal 1 dag.
            </p>
            <div className="pill-group" style={{ marginBottom: 20 }}>
              {DAY_INDICES.map(d => (
                <button
                  key={d}
                  className={`pill ${days.includes(d) ? 'selected' : ''}`}
                  onClick={() => toggleDay(d)}
                >
                  {DAYS[d]}
                </button>
              ))}
            </div>

            <div className="form-group">
              <label className="form-label">Sessieduur (minuten)</label>
              <select
                className="form-select"
                value={duration}
                onChange={e => setDuration(Number(e.target.value))}
              >
                <option value={30}>30 min</option>
                <option value={45}>45 min</option>
                <option value={60}>60 min</option>
                <option value={75}>75 min</option>
                <option value={90}>90 min</option>
              </select>
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            <h2 style={{ marginBottom: 8 }}>Huidig niveau</h2>
            <p className="text-muted text-small" style={{ marginBottom: 4 }}>
              Vul een recent uitgevoerd werkgewicht in voor ongeveer vijf herhalingen. Gebruik voor de power clean een werkgewicht voor twee herhalingen.
            </p>
            <p className="text-muted text-xs" style={{ marginBottom: 20 }}>
              ⚠️ Dit is geen PR-gewicht van vroeger — gebruik je huidige belastbaarheid.
            </p>
            {(Object.keys(LIFT_NAMES) as LiftType[])
              .filter(k => k !== 'other' && k !== 'clean')
              .map(lift => (
                <div className="form-group" key={lift}>
                  <label className="form-label">{LIFT_NAMES[lift]} (kg)</label>
                  <input
                    className="form-input"
                    type="number"
                    min="0.5" max="500" step="0.5"
                    value={capacities[lift] ?? ''}
                    onChange={e => updateCapacity(lift, e.target.value)}
                    placeholder="kg"
                  />
                </div>
              ))}
            <p className="text-muted text-xs">
              Je kunt dit later aanpassen. Onbekende oefeningen kun je leeg laten.
            </p>
          </div>
        )}

        {step === 4 && (
          <div>
            <h2 style={{ marginBottom: 8 }}>Extra opties</h2>
            <p className="text-muted text-small" style={{ marginBottom: 20 }}>
              Optionele integraties en meetapparatuur.
            </p>

            <button
              className="card"
              onClick={() => setHasVbt(v => !v)}
              style={{
                border: `2px solid ${hasVbt ? 'var(--c-accent)' : 'var(--c-border)'}`,
                cursor: 'pointer', textAlign: 'left', background: 'var(--c-surface)',
                width: '100%', marginBottom: 10,
              }}
            >
              <div className="row between">
                <div>
                  <div style={{ fontWeight: 700 }}>VBT-sensor</div>
                  <div className="text-muted text-small">Velocity-Based Training — snelheidsmeting per rep</div>
                </div>
                <div style={{ fontSize: 20 }}>{hasVbt ? '✅' : '◻️'}</div>
              </div>
            </button>

            <div className="card" style={{ background: 'var(--c-surface)' }}>
              <div className="row between">
                <div>
                  <div style={{ fontWeight: 700 }}>Strava</div>
                  <div className="text-muted text-small">Duuractiviteiten importeren</div>
                </div>
                <div className="tag" style={{ background: 'var(--c-surface2)', color: 'var(--c-text2)' }}>
                  Later
                </div>
              </div>
              <p className="text-xs text-muted" style={{ marginTop: 8 }}>
                Strava OAuth vereist een actieve backend. Instelbaar na installatie.
              </p>
            </div>

            <div className="card" style={{ marginTop: 12, borderColor: 'rgba(232,184,109,0.3)', background: 'rgba(232,184,109,0.05)' }}>
              <p className="text-small">
                <span className="text-accent" style={{ fontWeight: 700 }}>Lokaal prototype.</span>{' '}
                De app werkt volledig zonder server.
                Gegevens worden lokaal opgeslagen op dit apparaat.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="onboarding-footer">
        {saveError && <p role="alert" style={{ color: 'var(--c-warn)' }}>{saveError}</p>}
        <div style={{ display: 'flex', gap: 10 }}>
          {step > 0 && (
            <button className="btn btn-ghost" onClick={() => setStep(s => s - 1)} style={{ flex: 1 }}>
              Terug
            </button>
          )}
          <button
            className="btn btn-primary"
            style={{ flex: 2 }}
            onClick={next}
            disabled={!canNext()}
          >
            {step === TOTAL_STEPS - 1 ? 'Start' : 'Volgende'}
          </button>
        </div>
      </div>
    </div>
  );
}
