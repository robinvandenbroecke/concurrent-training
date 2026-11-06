import type { WorkoutSession } from '../types';
import { KEYS, type StorageLike, readJson, readSessions, exportLocal, importLocal } from './local';

export const STATE_KEYS = [KEYS.profile, KEYS.draft, KEYS.overrides, KEYS.volumeTargets];
export type AccountState = Record<string, unknown>;
export interface AccountRecord { state: AccountState; revision: number }
export interface CloudTransport {
  loadState(): Promise<AccountRecord | null>;
  saveState(state: AccountState, expectedRevision: number): Promise<AccountRecord | null>;
  loadSessions(): Promise<WorkoutSession[]>;
  insertSession(session: WorkoutSession): Promise<WorkoutSession>;
}
export interface SyncStatus { phase: 'saved' | 'pending' | 'saving' | 'error' | 'conflict'; message: string }
interface Metadata { initialized: boolean; revision: number; dirty: boolean }
const META = 'ct_sync_v1';
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).filter(([,v])=>v!==undefined).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
export function sameSession(a: WorkoutSession, b: WorkoutSession): boolean {
  return canonical({ ...a, id: String(a.id), savedToServer: true }) === canonical({ ...b, id: String(b.id), savedToServer: true });
}

/** One store per authenticated user. PostgreSQL RLS enforces actual ownership. */
export class CloudStore {
  private metadata: Metadata;
  private stopped = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private serial: Promise<unknown> = Promise.resolve();
  private changes = 0;
  status: SyncStatus = { phase: 'pending', message: 'Database laden…' };
  constructor(readonly userId: string, readonly storage: StorageLike, private transport: CloudTransport, private report: (s: SyncStatus) => void = () => {}) {
    this.metadata = readJson(META, { initialized: false, revision: 0, dirty: false }, storage);
  }
  private emit(phase: SyncStatus['phase'], message: string) {
    if (!this.stopped) { this.status = { phase, message }; this.report(this.status); }
  }
  private remember() { this.storage.setItem(META, JSON.stringify(this.metadata)); }
  private snapshot(): AccountState {
    return Object.fromEntries(STATE_KEYS.map(key=>[key, readJson(key, null, this.storage)]));
  }
  private apply(state: AccountState) {
    for (const key of STATE_KEYS) {
      const value = state[key];
      if (value === undefined || value === null) this.storage.removeItem(key);
      else this.storage.setItem(key, JSON.stringify(value));
    }
  }
  private mergeSessions(remote: WorkoutSession[]) {
    const pending = readSessions(this.storage).filter(s=>!s.savedToServer);
    const result = new Map<string, WorkoutSession>(remote.map(s=>[String(s.id), { ...s, id: String(s.id), savedToServer: true }]));
    for (const session of pending) {
      const server = result.get(String(session.id));
      if (!server || !sameSession(server, session)) result.set(String(session.id), session);
    }
    this.storage.setItem(KEYS.sessions, JSON.stringify([...result.values()]));
  }
  async initialize(): Promise<void> {
    try {
      const [remote, sessions] = await Promise.all([this.transport.loadState(), this.transport.loadSessions()]);
      if (this.stopped) return;
      if (!this.metadata.dirty) {
        this.apply(remote?.state ?? {}); this.metadata.revision = remote?.revision ?? 0;
      } else if (canonical(remote?.state ?? {}) === canonical(this.snapshot())) {
        this.metadata.dirty = false; this.metadata.revision = remote?.revision ?? 0;
      }
      this.mergeSessions(sessions); this.metadata.initialized = true; this.remember();
      const pending = this.metadata.dirty || readSessions(this.storage).some(s=>!s.savedToServer);
      this.emit(pending ? 'pending' : 'saved', pending ? 'Lokale wijzigingen wachten op opslag.' : 'Gegevens uit de database geladen.');
    } catch {
      if (!this.metadata.initialized) throw new Error('De database is niet bereikbaar. Probeer opnieuw; er wordt geen leeg profiel over je gegevens geschreven.');
      this.emit('error', 'Database niet bereikbaar. Je werkt met de bewaarde kopie van dit account.');
    }
  }
  changed(key: string, storage: StorageLike) {
    if (this.stopped || storage !== this.storage || ![...STATE_KEYS, KEYS.sessions].includes(key)) return;
    if (key !== KEYS.sessions) { this.metadata.dirty = true; this.changes++; this.remember(); }
    this.emit('pending', 'Nog niet in de database bewaard.');
    clearTimeout(this.timer); this.timer = setTimeout(()=>{ void this.flush().catch(()=>{}); }, 450);
  }
  private enqueue<T>(action: () => Promise<T>): Promise<T> {
    const operation = this.serial.catch(()=>{}).then(async()=>{
      if (this.stopped) throw new Error('Dit account is uitgelogd.');
      return action();
    });
    this.serial = operation; return operation;
  }
  private async pushSession(id: string) {
    const local = readSessions(this.storage).find(s=>String(s.id)===id);
    if (!local) throw new Error('Deze training is niet op dit toestel gevonden.');
    if (local.savedToServer) return;
    const saved = await this.transport.insertSession({ ...local, id });
    if (this.stopped) throw new Error('Dit account is uitgelogd.');
    if (!sameSession(local, saved)) throw new Error('Een andere versie van deze sessie staat al in de database. Exporteer de lokale kopie voordat je verdergaat.');
    this.storage.setItem(KEYS.sessions, JSON.stringify(readSessions(this.storage).map(s=>String(s.id)===id ? { ...saved, savedToServer: true } : s)));
  }
  async saveSession(id: number | string) {
    return this.enqueue(async()=>{
      this.emit('saving', 'Training opslaan…');
      try { await this.pushSession(String(id)); this.emit(this.metadata.dirty || readSessions(this.storage).some(s=>!s.savedToServer) ? 'pending' : 'saved', this.metadata.dirty || readSessions(this.storage).some(s=>!s.savedToServer) ? 'Training bewaard; overige wijzigingen wachten.' : 'In de database bewaard.'); }
      catch { this.emit('error', 'Training nog niet in de database bewaard. Je invoer blijft op dit toestel.'); throw new Error(this.status.message); }
    });
  }
  async flush(): Promise<void> {
    return this.enqueue(async()=>{
      this.emit('saving', 'Opslaan in de database…');
      try {
        for (const session of readSessions(this.storage).filter(s=>!s.savedToServer)) await this.pushSession(String(session.id));
        while (this.metadata.dirty && !this.stopped) {
          const state = this.snapshot(), version = this.changes;
          let saved = await this.transport.saveState(state, this.metadata.revision);
          if (this.stopped) return;
          if (!saved) {
            const current = await this.transport.loadState();
            // Handles a committed write whose HTTP confirmation was lost.
            if (current && canonical(current.state) === canonical(state)) saved = current;
            else { this.emit('conflict', 'Planning of profiel is op een ander toestel gewijzigd. Je lokale versie is behouden.'); throw new Error(this.status.message); }
          }
          this.metadata.revision = saved.revision;
          this.metadata.dirty = this.changes !== version; this.remember();
        }
        this.emit('saved', 'In de database bewaard.');
      } catch (error) {
        if (this.status.phase !== 'conflict') this.emit('error', 'Opslaan is niet bevestigd. Je invoer blijft op dit toestel. Probeer opnieuw.');
        throw error instanceof Error ? error : new Error(this.status.message);
      }
    });
  }
  async useDatabaseVersion() {
    return this.enqueue(async()=>{
      const state = await this.transport.loadState();
      if (this.stopped) return;
      this.storage.setItem('ct_conflict_backup', JSON.stringify({ savedAt: new Date().toISOString(), ...exportLocal(this.storage) }));
      this.apply(state?.state ?? {}); this.metadata = { initialized: true, revision: state?.revision ?? 0, dirty: false }; this.remember();
      this.emit('saved', 'Databaseversie geladen; lokale herstelkopie behouden.');
    });
  }
  async importLegacy(legacy: StorageLike) {
    const data = exportLocal(legacy);
    importLocal(JSON.stringify(data), this.storage);
    for (const key of STATE_KEYS) if (this.storage.getItem(key) === null && legacy.getItem(key) !== null) this.storage.setItem(key, legacy.getItem(key)!);
    this.metadata.dirty = true; this.changes++; this.remember();
    await this.flush();
  }
  stop() { this.stopped = true; clearTimeout(this.timer); }
}
