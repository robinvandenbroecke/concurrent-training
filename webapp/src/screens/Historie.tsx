import React, { useEffect, useState } from 'react';
import type { WorkoutSession, TrendPoint, LiftType } from '../types';
import { api } from '../api/adapter';
import { LIFT_NAMES, SPORT_NAMES } from '../data/demoData';
import { exportLocal, importLocal } from '../api/local';

interface Props {
  isDemo: boolean;
}

function TrendMiniChart({ data }: { data: TrendPoint[] }) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map(p => p.value));
  const min = Math.min(...data.map(p => p.value));
  const range = max - min || 1;
  return (
    <div className="mini-chart">
      {data.map((p, i) => (
        <div
          key={i}
          className={`mini-bar ${p.isEstimate ? 'estimate' : ''}`}
          style={{ height: `${Math.max(8, ((p.value - min) / range) * 44 + 4)}px` }}
          title={`${p.date}: ${p.value} kg${p.isEstimate ? ' (schatting)' : ''}`}
        />
      ))}
    </div>
  );
}

function ExportButton({ isDemo }: { isDemo: boolean }) {
  const handleExport = () => {
    try {
      const blob = new Blob([JSON.stringify(exportLocal(), null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'ct_export.json'; a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Export mislukt');
    }
  };

  return (
    <button className="btn btn-ghost btn-sm" onClick={handleExport}>
      ↓ Export data (JSON)
    </button>
  );
}

export default function Historie({ isDemo }: Props) {
  const [sessions, setSessions] = useState<WorkoutSession[]>([]);
  const [trends, setTrends] = useState<Record<string, TrendPoint[]>>({});
  const [activeTab, setActiveTab] = useState<'sessies' | 'trends'>('sessies');
  const [loading, setLoading] = useState(true);
  const [selectedLift, setSelectedLift] = useState<LiftType>('squat');
  const [revision, setRevision] = useState(0);
  const [importMessage, setImportMessage] = useState('');

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getHistory(60),
      api.getLiftTrend(selectedLift, 30),
    ])
      .then(([s, t]) => {
        setSessions(s);
        setTrends(p => ({ ...p, [selectedLift]: t }));
      })
      .finally(() => setLoading(false));
  }, [selectedLift, revision]);

  if (loading) return <div className="screen"><div className="empty-state"><p className="text-muted">Laden…</p></div></div>;

  return (
    <div className="screen">
      {isDemo && (
        <div style={{
          background: 'rgba(232,184,109,0.12)', border: '1px solid rgba(232,184,109,0.3)',
          borderRadius: 'var(--radius-sm)', padding: '8px 12px', marginBottom: 12, fontSize: 12,
        }}>
          <span className="text-accent" style={{ fontWeight: 700 }}>LOKAAL</span>
          {' '}— Alleen gegevens die je op dit toestel hebt geregistreerd. Geen serveropslag.
        </div>
      )}

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['sessies', 'trends'] as const).map(t => (
          <button
            key={t}
            className={`pill ${activeTab === t ? 'selected' : ''}`}
            onClick={() => setActiveTab(t)}
            style={{ flex: 1 }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Sessions tab */}
      {activeTab === 'sessies' && (
        <>
          {sessions.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <p className="text-muted">Nog geen trainingen geregistreerd.</p>
            </div>
          ) : (
            sessions.map((s, i) => (
              <div className="card" key={i} style={{ padding: '12px 14px' }}>
                <div className="row between" style={{ marginBottom: 4 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span className={`tag tag-${s.type}`}>{s.type === 'kracht' ? 'Kracht' : 'Duur'}</span>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>{s.title}</span>
                  </div>
                  <span className="text-xs text-muted">{s.date}</span>
                </div>

                {s.durationMinutes > 0 && (
                  <div className="text-small text-muted">{s.durationMinutes} min</div>
                )}

                {s.exercises?.map(ex => (
                  <div key={ex.lift} style={{ marginTop: 6 }}>
                    <div className="text-small" style={{ fontWeight: 600 }}>{ex.displayName}</div>
                    {ex.sets.map(set => (
                      <div key={set.setNum} className="text-xs text-muted" style={{ marginLeft: 8 }}>
                        Set {set.setNum}: {set.weight} kg × {set.completedReps} reps
                        {set.rpe && ` — RPE ${set.rpe}`}
                        {set.note && ` — "${set.note}"`}
                      </div>
                    ))}
                  </div>
                ))}

                {!s.savedToServer && (
                  <div className="text-xs" style={{ color: 'var(--c-text3)', marginTop: 4 }}>
                    Alleen lokaal opgeslagen
                  </div>
                )}
              </div>
            ))
          )}

          {isDemo && (
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <ExportButton isDemo={isDemo} />
              <label className="btn btn-ghost btn-sm" style={{ marginTop: 8, cursor: 'pointer' }}>
                ↑ Sessies importeren
                <input type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={async e => {
                  const file = e.target.files?.[0]; if (!file) return;
                  try {
                    if (file.size > 10 * 1024 * 1024) throw new Error('Gebruik een JSON-bestand kleiner dan 10 MB.');
                    importLocal(await file.text()); setRevision(n => n + 1); setImportMessage('Sessies toegevoegd. Je huidige profiel blijft behouden.');
                  } catch (error) { setImportMessage((error as Error).message); }
                  e.target.value = '';
                }} />
              </label>
              {importMessage && <p role="status" className="text-small">{importMessage}</p>}
            </div>
          )}
        </>
      )}

      {/* Trends tab */}
      {activeTab === 'trends' && (
        <>
          <div className="card">
            <div className="card-title">Oefening</div>
            <div className="pill-group" style={{ marginBottom: 16 }}>
              {(Object.keys(LIFT_NAMES) as LiftType[])
                .filter(k => k !== 'other' && k !== 'clean')
                .map(lift => (
                  <button
                    key={lift}
                    className={`pill ${selectedLift === lift ? 'selected' : ''}`}
                    onClick={() => setSelectedLift(lift)}
                  >
                    {LIFT_NAMES[lift]}
                  </button>
                ))}
            </div>

            <div style={{ marginBottom: 8 }}>
              <div className="row between text-small" style={{ marginBottom: 6 }}>
                <span style={{ fontWeight: 700 }}>{LIFT_NAMES[selectedLift]} — gelogd werkgewicht</span>
                <span className="text-muted">30 dagen</span>
              </div>
              <TrendMiniChart data={trends[selectedLift] ?? []} />
              {(trends[selectedLift]?.length ?? 0) === 0 && (
                <p className="text-muted text-small">Geen trenddata beschikbaar.</p>
              )}
            </div>

            <div className="row" style={{ gap: 12, marginTop: 8, fontSize: 12 }}>
              <div className="row" style={{ gap: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: 'var(--c-accent)', opacity: 0.7 }} />
                <span className="text-muted">Meting</span>
              </div>
              <div className="row" style={{ gap: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: 'var(--c-accent2)', opacity: 0.35 }} />
                <span className="text-muted">Modelschatting</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">Notitie</div>
            <p className="text-small text-muted">
              De grafiek toont het zwaarste geregistreerde werkgewicht per dag.
              Dit is geen 1RM-schatting of voorspelling van het onderzoeksmodel.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
