import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { CloudTransport, AccountRecord, AccountState } from './cloud';
import type { WorkoutSession } from '../types';

// Public browser configuration; never use a secret/service-role key here.
export const SUPABASE_URL = 'https://dvwbkbohdgfuzjenrete.supabase.co';
export const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_5OjH7aLL1qVJiyh7vQAaqw_Fvd0fV5f';
let client: SupabaseClient | undefined;
export function getSupabase() {
  return client ??= createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storageKey: 'ct_auth_v1' },
  });
}
export function authRedirect() { return `${window.location.origin}/concurrent-training/`; }
export function cloudTransport(supabase: SupabaseClient, userId: string): CloudTransport {
  return {
    async loadState() {
      const { data, error } = await supabase.from('ct_training_accounts').select('state,revision').eq('user_id', userId).maybeSingle();
      if (error) throw error; return data as AccountRecord | null;
    },
    async saveState(state: AccountState, revision: number) {
      const query = revision === 0
        ? supabase.from('ct_training_accounts').insert({ user_id: userId, state })
        : supabase.from('ct_training_accounts').update({ state }).eq('user_id', userId).eq('revision', revision);
      const { data, error } = await query.select('state,revision').maybeSingle();
      if (error?.code === '23505') return null;
      if (error) throw error; return data as AccountRecord | null;
    },
    async loadSessions() {
      const sessions: WorkoutSession[] = [];
      for (let offset = 0; ; offset += 500) {
        const { data, error } = await supabase.from('ct_training_sessions').select('id,payload').eq('user_id', userId).order('id').range(offset, offset + 499);
        if (error) throw error;
        sessions.push(...data.map(r=>({ ...r.payload, id: r.id, savedToServer: true })));
        if (data.length < 500) return sessions;
      }
    },
    async insertSession(session: WorkoutSession) {
      const row = { user_id: userId, id: String(session.id), payload: { ...session, id: String(session.id), savedToServer: true } };
      const { data, error } = await supabase.from('ct_training_sessions').upsert(row, { onConflict: 'user_id,id', ignoreDuplicates: true }).select('id,payload').maybeSingle();
      if (error) throw error;
      if (data) return { ...data.payload, id: data.id, savedToServer: true };
      const { data: existing, error: readError } = await supabase.from('ct_training_sessions').select('id,payload').eq('user_id',userId).eq('id',row.id).single();
      if (readError) throw readError; return { ...existing.payload, id: existing.id, savedToServer: true };
    },
  };
}
