import React, { useEffect, useState, useCallback } from 'react';
import type { AthleteProfile, PlannedTraining } from './types';
import { api } from './api/adapter';
import Onboarding from './screens/Onboarding';
import Vandaag from './screens/Vandaag';
import Training from './screens/Training';
import Week from './screens/Week';
import Historie from './screens/Historie';
import { IconHome, IconDumbbell, IconCalendar, IconChart } from './components/Icons';
import { KEYS, readProfile, readDraft } from './api/local';

type Tab = 'vandaag' | 'training' | 'week' | 'historie';

const PROFILE_KEY = 'ct_profile';

function loadStoredProfile(): AthleteProfile | null {
  return readProfile();
}

export default function App() {
  const [profile, setProfile] = useState<AthleteProfile | null>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>('vandaag');
  const [activePlan, setActivePlan] = useState<PlannedTraining | null>(() => readDraft()?.plan ?? null);
  const [trainingSaved, setTrainingSaved] = useState(0); // increment to trigger refresh
  const [editRequest,setEditRequest]=useState(0);

  // Always demo mode in this build (no backend credentials in frontend)
  const isDemo = true;

  useEffect(() => {
    api.configure({ mode: 'demo', baseUrl: '', apiKey: '', athleteId: 1 });
    const stored = loadStoredProfile();
    if (stored?.onboardingComplete) {
      setProfile(stored);
    }
    setReady(true);
  }, []);

  const handleOnboardingComplete = useCallback(async (p: AthleteProfile) => {
    await api.saveProfile(p);
    setProfile(p);
  }, []);

  const handleStartTraining = useCallback((plan: PlannedTraining) => {
    const draft = readDraft();
    if (draft && (draft.plan.date !== plan.date || draft.plan.title !== plan.title)) {
      if (!window.confirm('Er staat nog een training open. Die vervangen door deze training?')) return false;
      localStorage.removeItem(KEYS.draft);
    }
    setActivePlan(plan);
    setTab('training');
    return true;
  }, []);

  const handleEditTraining=(plan:PlannedTraining)=>{if(handleStartTraining(plan))setEditRequest(n=>n+1);};

  const handleTrainingSaved = useCallback(() => {
    setTrainingSaved(n => n + 1);
    // Stay on training tab to show success
  }, []);

  if (!ready) return null;

  if (!profile || !profile.onboardingComplete) {
    return <Onboarding onComplete={handleOnboardingComplete} />;
  }

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header">
        <span className="logo">CT</span>
        <span className="text-muted text-small" style={{ fontSize: 13 }}>{profile.name}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {isDemo && <span className="demo-badge">LOKAAL</span>}
          <button
            className="btn btn-ghost btn-sm"
            style={{ padding: '5px 10px', fontSize: 11 }}
            aria-label="Profiel opnieuw instellen"
            onClick={() => {
              if (window.confirm('Onboarding opnieuw starten?')) {
                localStorage.removeItem(PROFILE_KEY);
                localStorage.removeItem(KEYS.draft);
                localStorage.removeItem(KEYS.overrides);
                localStorage.removeItem(KEYS.volumeTargets);
                setActivePlan(null);
                setProfile(null);
              }
            }}
          >
            ⚙
          </button>
        </div>
      </header>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, overflow: 'hidden', display: tab === 'vandaag' ? 'block' : 'none' }}>
          <Vandaag
            key={trainingSaved}
            profile={profile}
            onStartTraining={handleStartTraining}
            onEditTraining={handleEditTraining}
            isDemo={isDemo}
          />
        </div>
        <div style={{ flex: 1, overflow: 'hidden', display: tab === 'training' ? 'block' : 'none' }}>
          <Training
            plan={activePlan}
            onSaved={handleTrainingSaved}
            isDemo={isDemo}
            hasVbt={profile.hasVbt}
            editRequest={editRequest}
            onPlanEdited={()=>setTrainingSaved(n=>n+1)}
          />
        </div>
        <div style={{ flex: 1, overflow: 'hidden', display: tab === 'week' ? 'block' : 'none' }}>
          <Week key={trainingSaved} onStartTraining={handleStartTraining} onEditTraining={handleEditTraining} onChanged={() => setTrainingSaved(n => n + 1)} />
        </div>
        <div style={{ flex: 1, overflow: 'hidden', display: tab === 'historie' ? 'block' : 'none' }}>
          <Historie key={trainingSaved} isDemo={isDemo} />
        </div>
      </main>

      {/* Bottom navigation */}
      <nav className="app-nav">
        {([
          ['vandaag', 'Vandaag', <IconHome />],
          ['training', 'Training', <IconDumbbell />],
          ['week', 'Week', <IconCalendar />],
          ['historie', 'Historie', <IconChart />],
        ] as [Tab, string, React.ReactNode][]).map(([id, label, icon]) => (
          <button
            key={id}
            className={`nav-item ${tab === id ? 'active' : ''}`}
            onClick={() => setTab(id)}
            aria-current={tab === id ? 'page' : undefined}
          >
            {icon}
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
