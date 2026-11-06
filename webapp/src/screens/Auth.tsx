import React, { useState } from 'react';
import type { SupabaseClient } from '@supabase/supabase-js';
import { authRedirect } from '../api/supabase';

export function authError(error: { code?: string; message?: string }): string {
  if (error.code === 'invalid_credentials') return 'E-mailadres of wachtwoord is onjuist.';
  if (error.code === 'email_not_confirmed') return 'Bevestig eerst je e-mailadres via de link in je mailbox.';
  if (error.code?.includes('rate_limit') || error.code === 'over_email_send_rate_limit') return 'Te veel pogingen. Wacht even en probeer opnieuw.';
  if (error.code === 'user_already_exists') return 'Dit account bestaat al. Kies Inloggen of Wachtwoord vergeten.';
  if (error.code === 'weak_password') return 'Gebruik een sterker wachtwoord van minimaal 8 tekens.';
  if (error.code === 'same_password') return 'Kies een ander wachtwoord dan je huidige wachtwoord.';
  return 'Aanmelden of e-mail versturen is niet gelukt. Controleer je verbinding en probeer opnieuw.';
}
export default function Auth({ client, recovery = false, onRecovered }: { client: SupabaseClient; recovery?: boolean; onRecovered: () => void }) {
  const [mode, setMode] = useState<'login'|'signup'|'reset'>('login');
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[repeat,setRepeat]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setMessage('');
    if ((recovery || mode === 'signup') && (password.length < 8 || password !== repeat)) { setError('Gebruik minimaal 8 tekens en vul tweemaal hetzelfde wachtwoord in.'); return; }
    setBusy(true);
    try {
      if (recovery) {
        const { error } = await client.auth.updateUser({ password }); if (error) throw error;
        setPassword(''); setRepeat(''); onRecovered();
      } else if (mode === 'login') {
        const { error } = await client.auth.signInWithPassword({ email: email.trim(), password }); if (error) throw error;
      } else if (mode === 'signup') {
        const { data, error } = await client.auth.signUp({ email: email.trim(), password, options: { emailRedirectTo: authRedirect() } });
        if (error) throw error;
        if (!data.session) { setMessage('Controleer je mailbox en bevestig je e-mailadres. Open daarna de app en log in.'); setMode('login'); }
        setPassword(''); setRepeat('');
      } else {
        const { error } = await client.auth.resetPasswordForEmail(email.trim(), { redirectTo: authRedirect() }); if (error) throw error;
        setMessage('Als dit adres een account heeft, ontvang je een link om een nieuw wachtwoord te kiezen.');
      }
    } catch (e) { setError(authError(e as { code?: string })); }
    finally { setBusy(false); }
  };
  return <main className="auth-screen"><section className="card auth-card">
    <div className="auth-logo">CT</div><h1>Concurrent Training</h1>
    <p className="text-muted">Log in om je trainingen, profiel en planning in je account te bewaren.</p>
    <h2>{recovery?'Nieuw wachtwoord':mode==='signup'?'Account aanmaken':mode==='reset'?'Wachtwoord vergeten':'Inloggen'}</h2>
    {mode!=='login'&&!recovery&&<p className="account-notice text-small">Tijdens deze testfase zijn bevestigings- en herstelmails beperkt tot vooraf toegelaten adressen.</p>}
    <form onSubmit={submit}>
      {!recovery&&<label className="form-label" htmlFor="auth-email">E-mailadres<input id="auth-email" className="form-input" type="email" autoComplete="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/></label>}
      {(recovery||mode!=='reset')&&<label className="form-label" htmlFor="auth-password">Wachtwoord<input id="auth-password" className="form-input" type="password" autoComplete={recovery||mode==='signup'?'new-password':'current-password'} required minLength={recovery||mode==='signup'?8:undefined} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></label>}
      {(recovery||mode==='signup')&&<label className="form-label" htmlFor="auth-repeat">Herhaal wachtwoord<input id="auth-repeat" className="form-input" type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={repeat} onChange={e=>setRepeat(e.target.value)} disabled={busy}/></label>}
      {error&&<p role="alert" className="editor-error">{error}</p>}{message&&<p role="status" className="account-notice">{message}</p>}
      <button className="btn btn-primary btn-full" disabled={busy} type="submit">{busy?'Even wachten…':recovery?'Wachtwoord bewaren':mode==='signup'?'Account aanmaken':mode==='reset'?'Herstellink versturen':'Inloggen'}</button>
    </form>
    {!recovery&&<div className="auth-links">{(['login','signup','reset'] as const).filter(m=>m!==mode).map(m=><button key={m} className="btn btn-ghost btn-sm" disabled={busy} onClick={()=>{setMode(m);setError('');setMessage('');setPassword('');setRepeat('');}}>{m==='login'?'Inloggen':m==='signup'?'Account aanmaken':'Wachtwoord vergeten'}</button>)}</div>}
    {recovery&&<button className="btn btn-ghost btn-full" disabled={busy} onClick={onRecovered}>Terug naar de app</button>}
    <p className="text-xs text-muted">Je ziet alleen de gegevens van je eigen account. Bestaande lokale trainingen kun je na het inloggen overnemen of via JSON importeren.</p>
  </section></main>;
}
