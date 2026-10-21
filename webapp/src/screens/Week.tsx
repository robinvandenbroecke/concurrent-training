import React, { useEffect, useState } from 'react';
import type { WeekDay, PlannedTraining } from '../types';
import { api } from '../api/adapter';
import { LIFT_NAMES, SPORT_NAMES, INTENSITY_NAMES } from '../data/demoData';
import { IconClock } from '../components/Icons';

interface Props {
  onStartTraining: (plan: PlannedTraining) => void;
  onEditTraining: (plan: PlannedTraining) => void;
  onChanged: () => void;
}

export default function Week({ onStartTraining, onEditTraining, onChanged }: Props) {
  const [days, setDays] = useState<WeekDay[]>([]);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getWeekDays()
      .then(d => {
        setDays(d);
        const today = d.find(x => x.isToday);
        setSelectedDay(today?.date ?? d[0]?.date ?? null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="screen"><div className="empty-state"><p className="text-muted">Laden…</p></div></div>;

  const selected = days.find(d => d.date === selectedDay);

  const totalTrainings = days.filter(d => d.planned).length;
  const completedCount = days.filter(d => d.completed).length;

  return (
    <div className="screen">
      {/* Week strip */}
      <div className="card">
        <div className="card-title">Week overzicht</div>
        <div className="week-strip">
          {days.map(d => {
            const hasTraining = !!d.planned;
            const isDone = !!d.completed;
            const dotColor = isDone ? 'var(--c-success)'
              : hasTraining ? (d.planned!.type === 'kracht' ? 'var(--c-accent)' : 'var(--c-accent2)')
              : 'transparent';
            return (
              <button
                key={d.date}
                className={`week-cell ${d.isToday ? 'today' : ''} ${selectedDay === d.date ? 'active' : ''}`}
                onClick={() => setSelectedDay(d.date)}
              >
                <span className="day-label">{d.dayName}</span>
                <span className="day-num" style={{ color: d.isToday ? 'var(--c-accent)' : 'inherit' }}>
                  {parseInt(d.date.slice(8))}
                </span>
                <div className="dot" style={{ background: dotColor }} />
              </button>
            );
          })}
        </div>

        <div className="row" style={{ gap: 16, fontSize: 13 }}>
          <span className="text-muted">{completedCount}/{totalTrainings} trainingen gedaan</span>
          <div className="row" style={{ gap: 6 }}>
            <div className="dot" style={{ width: 8, height: 8, borderRadius: 4, background: 'var(--c-accent)' }} />
            <span className="text-muted">kracht</span>
            <div className="dot" style={{ width: 8, height: 8, borderRadius: 4, background: 'var(--c-accent2)', marginLeft: 4 }} />
            <span className="text-muted">duur</span>
          </div>
        </div>

        <div style={{ marginTop: 10, padding: 10, background: 'var(--c-surface2)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--c-text2)' }}>
          ℹ️ Planning gebruikt eenvoudige regels op basis van jouw beschikbare dagen en prioriteit.
          Optimalisatie door het onderzoeksmodel is nog niet volledig geïntegreerd.
        </div>
      </div>

      {/* Selected day detail */}
      {selected && (
        <div className="card">
          <div className="row between" style={{ marginBottom: 10 }}>
            <h3 style={{ textTransform: 'capitalize' }}>
              {selected.dayLabel}
              {selected.isToday && <span className="text-accent" style={{ marginLeft: 6, fontSize: 13 }}>vandaag</span>}
            </h3>
          </div>

          {selected.completed && (
            <div style={{
              background: 'rgba(94,203,138,0.1)', border: '1px solid rgba(94,203,138,0.3)',
              borderRadius: 'var(--radius-sm)', padding: '8px 12px', marginBottom: 12,
            }}>
              <div className="row" style={{ gap: 8 }}>
                <span style={{ color: 'var(--c-success)' }}>✓</span>
                <div>
                  <div className="text-small" style={{ fontWeight: 700 }}>Gedaan — {selected.completed.title}</div>
                  <div className="text-xs text-muted">{selected.completed.durationMinutes} min</div>
                </div>
              </div>
            </div>
          )}

          {!selected.planned && !selected.completed && (
            <div className="empty-state" style={{ padding: '12px 0' }}>
              <p className="text-muted">Rustdag — geen training gepland</p>
            </div>
          )}

          {selected.planned && !selected.completed && (
            <div>
              <div className="row between" style={{ marginBottom: 8 }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{selected.planned.title}</div>
                  <div className="row text-small text-muted" style={{ gap: 6, marginTop: 3 }}>
                    <span className={`tag tag-${selected.planned.type}`}>
                      {selected.planned.type === 'kracht' ? 'Kracht' : 'Duur'}
                    </span>
                    <IconClock />
                    <span>{selected.planned.durationMinutes} min</span>
                  </div>
                </div>
              </div>

              {selected.planned.exercises && (
                <div style={{ marginBottom: 12 }}>
                  {selected.planned.exercises.map(ex => (
                    <div key={ex.id??ex.lift} className="text-small text-muted" style={{ marginBottom: 3 }}>
                      • {ex.displayName}: {ex.sets.length} sets
                    </div>
                  ))}
                </div>
              )}

              {selected.planned.endurance && (
                <div className="text-small text-muted" style={{ marginBottom: 12 }}>
                  {SPORT_NAMES[selected.planned.endurance.sport]} —{' '}
                  {selected.planned.endurance.durationMinutes} min —{' '}
                  {INTENSITY_NAMES[selected.planned.endurance.intensityType]}
                </div>
              )}

              {selected.isToday && (
                <button
                  className="btn btn-primary btn-full"
                  onClick={() => selected.planned && onStartTraining(selected.planned)}
                >
                  ▶ Start training
                </button>
              )}
              {!selected.isPast&&selected.planned.type==='kracht'&&<button className="btn btn-secondary btn-full" style={{marginTop:8}} onClick={()=>onEditTraining(selected.planned!)}>Training aanpassen</button>}
              {!selected.isToday && !selected.isPast && (
                <button className="btn btn-ghost btn-full btn-sm" onClick={async () => { await api.skipDay(selected.date); onChanged(); }}>
                  Overslaan
                </button>
              )}
              {selected.isToday && <button className="btn btn-ghost btn-full btn-sm" onClick={async () => { await api.skipDay(selected.date); onChanged(); }}>Overslaan</button>}
              {selected.isPast && !selected.completed && (
                <div style={{ color: 'var(--c-text3)', fontSize: 13, textAlign: 'center' }}>
                  Overgeslagen
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Simplified note */}
      <div className="card">
        <div className="card-title">Planning — huidige versie</div>
        <p className="text-small text-muted">
          De weekplanning is gebaseerd op jouw beschikbare dagen en prioriteitskeuze.
          Overslaan wordt lokaal bijgehouden.
          Automatisch inhaalvolume wordt niet toegevoegd.
          Volledige integratie met het trainingsmodel is toekomstig werk.
        </p>
      </div>
    </div>
  );
}
