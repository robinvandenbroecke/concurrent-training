import React, { useEffect, useState } from 'react';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { CloudStore, type SyncStatus, type CloudTransport } from '../api/cloud';
import { accountStorage, exportLocal, getLocalStore, KEYS, observeStorage, readProfile, readSessions, selectStorage } from '../api/local';
import { cloudTransport, getSupabase } from '../api/supabase';
import { api } from '../api/adapter';
import Auth from './Auth';

export function downloadAccountCopy(recovery = false) {
  const content=recovery?getLocalStore().getItem('ct_conflict_backup'):JSON.stringify(exportLocal(),null,2);
  if(!content)return;
  const blob=new Blob([content],{type:'application/json'}),url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=recovery?'ct_herstelkopie.json':'ct_account_export.json';a.click();URL.revokeObjectURL(url);
}
export default function AccountGate({ children, client: suppliedClient, transportFactory = cloudTransport }: { children: React.ReactNode; client?: SupabaseClient; transportFactory?: (client: SupabaseClient, userId: string) => CloudTransport }) {
  const [client]=useState(()=>suppliedClient??getSupabase());
  const [session,setSession]=useState<Session|null>(null),[authReady,setAuthReady]=useState(false);
  const [recovery,setRecovery]=useState(()=>new URLSearchParams(window.location.hash.slice(1)).get('type')==='recovery');
  const [active,setActive]=useState<{store:CloudStore;id:string}|null>(null);
  const [error,setError]=useState(''),[attempt,setAttempt]=useState(0),[appVersion,setAppVersion]=useState(0);
  const [status,setStatus]=useState<SyncStatus>({phase:'pending',message:'Database laden…'});
  const [legacy,setLegacy]=useState(false),[busy,setBusy]=useState(false);
  useEffect(()=>{
    let live=true,events=0;
    // Callbacks remain synchronous: awaiting an auth operation here can deadlock refresh.
    const {data:{subscription}}=client.auth.onAuthStateChange((event,next)=>{
      if(!live)return;events++;setSession(next);setAuthReady(true);
      if(event==='PASSWORD_RECOVERY')setRecovery(true);
      if(event==='SIGNED_OUT')setRecovery(false);
    });
    client.auth.getSession().then(({data,error})=>{if(live){if(error)setError('Aanmelding kon niet worden hersteld. Log opnieuw in.');if(events===0)setSession(data.session);setAuthReady(true);}});
    return()=>{live=false;subscription.unsubscribe();};
  },[client]);
  const userId=session?.user.id;
  useEffect(()=>{
    setActive(null);setError('');setLegacy(false);
    if(!userId)return;
    let live=true;
    const store=new CloudStore(userId,accountStorage(userId),transportFactory(client,userId),s=>{if(live)setStatus(s);});
    const online=()=>{void store.flush().catch(()=>{});};
    store.initialize().then(()=>{
      if(!live)return;
      selectStorage(store.storage);observeStorage((key,storage)=>store.changed(key,storage));api.useCloud(store);
      setActive({store,id:userId});
      const owner=localStorage.getItem('ct_legacy_owner');
      setLegacy((!owner||owner===userId)&&localStorage.getItem(`ct_legacy_dismissed_${userId}`)!=='yes'&&!!(readProfile(localStorage)||readSessions(localStorage).length));
      if(store.status.phase==='pending')online();
      window.addEventListener('online',online);
    }).catch(e=>{if(live)setError(e.message);});
    return()=>{live=false;store.stop();window.removeEventListener('online',online);if(getLocalStore()===store.storage){observeStorage();selectStorage();api.disconnectCloud();}};
  },[userId,client,attempt,transportFactory]);
  const run=async(action:()=>Promise<void>)=>{setBusy(true);setError('');try{await action();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
  const logout=()=>run(async()=>{
    if(active&&status.phase!=='saved'&&!window.confirm('Er zijn mogelijk wijzigingen die nog niet in de database staan. Ze blijven op dit toestel bij dit account. Toch uitloggen?'))return;
    const {error}=await client.auth.signOut({scope:'local'});if(error)throw new Error('Uitloggen is niet bevestigd. Controleer je verbinding en probeer opnieuw.');
  });
  if(!authReady)return <main className="auth-screen"><p role="status">Aanmelding controleren…</p></main>;
  if(!session||recovery)return <Auth client={client} recovery={recovery&&!!session} onRecovered={()=>setRecovery(false)}/>;
  const ownsActive=active?.id===userId;
  return <div className="account-shell">
    <aside className="account-bar">
      <details><summary>Account · {session.user.email}</summary><div className="account-actions">
        <button className="btn btn-secondary btn-sm" disabled={busy||!ownsActive} onClick={()=>run(async()=>{await active!.store.flush();setAttempt(n=>n+1);})}>Opslaan en vernieuwen</button>
        <button className="btn btn-ghost btn-sm" disabled={!ownsActive} onClick={()=>downloadAccountCopy()}>Lokale kopie exporteren</button>
        {ownsActive&&active!.store.storage.getItem('ct_conflict_backup')&&<button className="btn btn-ghost btn-sm" onClick={()=>downloadAccountCopy(true)}>Herstelkopie downloaden</button>}
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={()=>setRecovery(true)}>Wachtwoord wijzigen</button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={logout}>Uitloggen</button>
      </div></details>
      {ownsActive&&<p className={`sync-status ${status.phase}`} role="status">{status.message}</p>}
      {error&&<p role="alert" className="editor-error">{error}</p>}
      {ownsActive&&status.phase==='conflict'&&<div className="account-notice"><p>Exporteer eventueel eerst je lokale versie. Bij herladen blijft ook een lokale herstelkopie bewaard.</p><button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>run(async()=>{
        if(!window.confirm('Profiel, planning en open training vervangen door de databaseversie? Je lokale versie blijft als herstelkopie op dit toestel.'))return;
        await active!.store.useDatabaseVersion();setAppVersion(n=>n+1);
      })}>Databaseversie gebruiken</button></div>}
      {ownsActive&&['pending','error'].includes(status.phase)&&<button className="btn btn-ghost btn-sm" disabled={busy} onClick={()=>run(()=>active!.store.flush())}>Opnieuw opslaan</button>}
      {ownsActive&&legacy&&<div className="account-notice"><p>Op dit toestel staan eerdere lokale gegevens{readProfile(localStorage)?.name?` van ${readProfile(localStorage)!.name}`:''} ({readSessions(localStorage).length} trainingen). Alleen overnemen als dit jouw gegevens zijn.</p>
        <button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>run(async()=>{
          localStorage.setItem('ct_legacy_owner',userId!);await active!.store.importLegacy(localStorage);localStorage.setItem(`ct_legacy_dismissed_${userId}`,'yes');setLegacy(false);setAppVersion(n=>n+1);
        })}>Overnemen in dit account</button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={()=>{localStorage.setItem(`ct_legacy_dismissed_${userId}`,'yes');setLegacy(false);}}>Niet overnemen</button>
      </div>}
    </aside>
    {ownsActive?<div className="account-content" key={`${userId}:${appVersion}`}>{children}</div>:<main className="auth-screen"><div className="card"><p role="status">{error?'Accountgegevens zijn nog niet geladen.':'Accountgegevens laden…'}</p>{error&&<button className="btn btn-primary" onClick={()=>setAttempt(n=>n+1)}>Opnieuw proberen</button>}</div></main>}
  </div>;
}
