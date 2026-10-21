import React, { useEffect, useState } from 'react';
import type { ReadinessData, PlannedTraining, AthleteProfile } from '../types';
import { api } from '../api/adapter';
import { LIFT_NAMES, SPORT_NAMES, INTENSITY_NAMES } from '../data/demoData';
import { IconPlay, IconClock, IconInfo } from '../components/Icons';

interface Props {
  profile: AthleteProfile;
  onStartTraining: (plan: PlannedTraining) => void;
  onEditTraining: (plan: PlannedTraining) => void;
  isDemo: boolean;
}

function ReadinessBar({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  const pct = Math.round(value * 100);
  const color = value >= 0.75 ? 'var(--c-success)' : value >= 0.55 ? 'var(--c-accent)' : 'var(--c-warn)';
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="row between text-small" style={{ marginBottom: 4 }}>
        <span>{label}</span>
        <span style={{ color, fontWeight: 700 }}>{pct}%</span>
      </div>
      <div className="readiness-bar-wrap">
        <div className="readiness-bar" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function Vandaag({ profile, onStartTraining, onEditTraining, isDemo }: Props) {
  const [readiness, setReadiness] = useState<ReadinessData | null>(null);
  const [plan, setPlan] = useState<PlannedTraining | null>(null);
  const [loading, setLoading] = useState(true);
  const [showExpl, setShowExpl] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.getReadiness(), api.getTodayPlan()])
      .then(([r, p]) => { setReadiness(r); setPlan(p); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="screen">
      <div className="empty-state"><p className="text-muted">Laden…</p></div>
    </div>
  );

  const overall = readiness?.overall ?? null;
  const overallPct = overall !== null ? Math.round(overall * 100) : null;
  const overallColor = overall !== null
    ? overall >= 0.75 ? 'var(--c-success)' : overall >= 0.55 ? 'var(--c-accent)' : 'var(--c-warn)'
    : 'var(--c-text2)';

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

      {/* Readiness overview */}
      <div className="card">
        <div className="row between" style={{ marginBottom: 12 }}>
          <div className="card-title" style={{ margin: 0 }}>Belastbaarheid vandaag</div>
          <button
            className="collapse-toggle"
            onClick={() => setShowExpl(v => !v)}
            aria-expanded={showExpl}
            aria-label="Toelichting belastbaarheid"
          >
            <IconInfo />
          </button>
        </div>

        {readiness === null ? (
          <p className="text-muted text-small">Onvoldoende gegevens om belastbaarheid te schatten.</p>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%',
                background: `conic-gradient(${overallColor} ${(overall ?? 0) * 360}deg, var(--c-surface2) 0)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{
                  width: 50, height: 50, borderRadius: '50%', background: 'var(--c-surface)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, fontWeight: 700, color: overallColor,
                }}>
                  {overallPct !== null ? `${overallPct}%` : '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: overallColor }}>
                  {overallPct !== null
                    ? overallPct >= 75 ? 'Goed'
                      : overallPct >= 55 ? 'Matig'
                      : 'Laag'
                    : 'Onbekend'}
                </div>
                <div className="text-muted text-small">
                  {readiness.assessment_status === 'demo_schatting'
                    ? 'Demoschatting'
                    : 'Modelschatting — experimenteel'}
                </div>
              </div>
            </div>

            {Object.entries(readiness.per_lift).map(([lift, val]) => (
              <ReadinessBar key={lift} label={LIFT_NAMES[lift] ?? lift} value={val} />
            ))}
            {readiness.endurance !== null && (
              <ReadinessBar label="Duurvermogen" value={readiness.endurance} />
            )}

            {showExpl && readiness.explanations.length > 0 && (
              <div style={{ marginTop: 10, borderTop: '1px solid var(--c-border)', paddingTop: 10 }}>
                {readiness.explanations.map((e, i) => (
                  <p key={i} className="text-muted text-small" style={{ marginBottom: 4 }}>• {e}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>

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
      </div>
    </div>
  );
}
