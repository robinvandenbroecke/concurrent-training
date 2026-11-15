import type { EngineOutcome, EngineResponse, EngineStrength, EngineVelocityGroup, FatigueEffect } from './client';
import { EXERCISES } from '../data/exercises';

const nl = (n: number, digits = 1) => n.toLocaleString('nl-BE', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
const METRIC: Record<string, string> = { mean_concentric: 'gemiddelde concentrische snelheid', mean_propulsive: 'gemiddelde propulsieve snelheid', peak: 'pieksnelheid', unspecified: 'snelheidsmaat niet opgegeven' };
const REASON: Record<string, string> = {
  too_few_points: 'te weinig snelheidsmetingen', too_few_distinct_loads: 'minder dan drie verschillende gewichten gemeten',
  load_range_too_narrow: 'de gemeten gewichten liggen te dicht bij elkaar (minder dan 25 % spreiding)',
  velocity_does_not_decrease_with_load: 'de snelheid daalt niet met het gewicht; controleer de invoer of het meetprotocol',
  poor_linear_fit: 'de metingen volgen geen rechte lijn (R² onder 0,90)',
  no_earlier_valid_profile: 'er is nog geen bruikbaar profiel uit eerdere trainingen',
  latest_loads_outside_calibrated_range: 'de laatste gewichten vallen buiten het gemeten bereik; er wordt niet geëxtrapoleerd',
  rpe_missing: 'RPE ontbreekt', set_too_far_from_failure: 'de set lag te ver van falen (RPE onder 7)',
  too_many_repetitions: 'te veel herhalingen voor een bruikbare schatting',
  no_recent_set_with_rpe_7_or_higher: 'geen werkset met RPE 7 of hoger in de laatste zes weken',
};
export const UNAVAILABLE: Record<string, string> = {
  signed_out: 'Log in om berekeningen op te vragen.',
  offline: 'De rekenmotor is nu niet bereikbaar (geen verbinding of de server start nog op). Je trainingen blijven gewoon bewaard; er wordt niets lokaal nagebootst.',
  not_configured: 'De rekenmotor is op deze server nog niet gekoppeld aan accounts.',
  session_expired: 'Je aanmelding is verlopen. Log opnieuw in.',
  busy: 'Te veel aanvragen kort na elkaar. Probeer het over een minuut opnieuw.',
  version_mismatch: 'App en rekenmotor gebruiken een verschillende versie. Vernieuw de app.',
  error: 'De rekenmotor gaf een fout. Er wordt geen resultaat getoond.',
  invalid_request: 'De rekenmotor kon deze aanvraag niet verwerken. Er wordt geen resultaat getoond.',
};
export function exerciseName(id: string): string { return EXERCISES.find(e => e.id === id)?.name ?? id; }

export function velocityLines(group: EngineVelocityGroup): string[] {
  const lines: string[] = [];
  const p = group.profile;
  if (p.status === 'ok') lines.push(`Eigen load–velocity-profiel (${METRIC[group.metric] ?? group.metric}): ${p.points} metingen op ${p.distinct_loads} gewichten, ${nl(p.load_range_kg![0])}–${nl(p.load_range_kg![1])} kg, R² ${nl(p.r2!, 2)}. Alleen geldig binnen dit bereik.`);
  else lines.push(`Geen load–velocity-profiel: ${p.reasons.map(r => REASON[r] ?? r).join('; ')}.`);
  const d = group.latest_deviation;
  if (d.status === 'ok') {
    const size = `${d.deviation_pct! > 0 ? '+' : ''}${nl(d.deviation_pct!)} %`;
    lines.push(d.interpretation === 'within_noise'
      ? `Laatste training (${d.date}): ${size} tegenover je profiel uit eerdere trainingen — binnen de meetspreiding.`
      : `Laatste training (${d.date}): ${size} tegenover je profiel uit eerdere trainingen — ${d.interpretation === 'slower' ? 'trager' : 'sneller'} dan de meetspreiding verklaart. Dit is een gemeten prestatieverschil, geen meting van vermoeidheid.`);
  } else if (p.status === 'ok') lines.push(`Geen vergelijking voor de laatste training: ${REASON[d.reason ?? ''] ?? d.reason}.`);
  const f = group.forecast_check;
  if (f.status === 'ok') lines.push(f.dynamic_model_beats_simple_baselines
    ? `Voorspeltoets op ${f.test_sessions} eigen trainingen: het dynamische model (${f.best}) voorspelde beter dan de eenvoudige vergelijkingen. Dit blijft een experimentele toets met vaste, niet-gekalibreerde parameters.`
    : `Voorspeltoets op ${f.test_sessions} eigen trainingen: geen model voorspelde beter dan een eenvoudige vergelijking (beste: ${f.best}). Er wordt daarom geen modelvoorspelling getoond.`);
  if (group.warnings.includes('velocity_metric_unknown')) lines.push('De snelheidsmaat van deze metingen is niet opgegeven. Stel je meter en snelheidsmaat in bij Profiel op het scherm Vandaag.');
  return lines;
}

export function strengthLines(block: EngineStrength): string[] {
  const lines: string[] = [];
  const e = block.e1rm_estimate;
  if (e.status === 'ok') lines.push(`Geschatte 1RM uit ${nl(e.basis!.weight_kg)} kg × ${e.basis!.reps} bij RPE ${nl(e.basis!.rpe)} (${e.basis!.date}): ongeveer ${nl(e.value_kg!, 0)} kg, plausibel bereik ${nl(e.low_kg!, 0)}–${nl(e.high_kg!, 0)} kg. Een schatting, geen gemeten 1RM.`);
  else if (e.status === 'insufficient_data') lines.push(`Geen 1RM-schatting: ${REASON[e.reason ?? ''] ?? e.reason}.`);
  for (const group of block.velocity) lines.push(...velocityLines(group));
  const losses = block.last_session_velocity_loss.filter(l => l.velocity_loss !== null);
  if (losses.length) lines.push(`Snelheidsverlies laatste training: ${losses.map(l => `set ${l.set} ${nl(l.velocity_loss! * 100, 0)} %`).join(', ')} (snelste tegenover laatste gemeten rep).`);
  return lines;
}

export function loadLines(r: EngineResponse): string[] {
  const now = r.load.last_7_days, before = r.load.previous_28_days;
  const lines = [`Laatste 7 dagen: ${now.strength_work_sets} krachtwerksets, ${nl(now.endurance_minutes, 0)} min duurtraining.`];
  if (r.load.previous_28_days_covered) lines.push(`De vier weken daarvoor, per week: ${nl(before.strength_work_sets / 4)} werksets, ${nl(before.endurance_minutes / 4, 0)} min duurtraining.`);
  else lines.push('Er is nog geen vijf weken historie; een vergelijking met eerdere weken wordt niet gemaakt.');
  if (now.endurance_load !== null) lines.push(`Externe duurbelasting (vermogen² × tijd tegenover je referentievermogen): ${nl(now.endurance_load, 0)} minuut-equivalenten.`);
  else if (now.endurance_load_method === 'mixed_methods') lines.push('Duurbelasting is deze week op verschillende manieren gemeten (vermogen, RPE of alleen duur) en wordt daarom niet opgeteld.');
  lines.push('Dit zijn beschrijvende totalen. Er wordt geen blessurerisico, herstelstatus of acute:chronische ratio uit afgeleid.');
  return lines;
}

export function concurrentLines(r: EngineResponse): string[] {
  return r.concurrent.map(f => {
    if (f.code === 'explosive_work_within_3h_of_endurance') return `${f.date}: explosief krachtwerk en duurtraining lagen ${nl(f.gap_hours!)} uur uit elkaar. In groepsonderzoek is de winst in explosieve kracht kleiner wanneer beide in dezelfde sessie vallen dan bij minstens 3 uur tussentijd (Schumann e.a. 2022). Dat is een gemiddelde, geen voorspelling voor jou.`;
    if (f.code === 'strength_within_3h_of_endurance') return `${f.date}: kracht- en duurtraining lagen ${nl(f.gap_hours!)} uur uit elkaar. Voor maximale kracht en spiergroei toont groepsonderzoek gemiddeld geen nadeel van combineren.`;
    if (f.code === 'same_day_separated_by_3h_or_more') return `${f.date}: kracht en duur op dezelfde dag, ${nl(f.gap_hours!)} uur uit elkaar.`;
    return `${f.date}: kracht en duur op dezelfde dag; volgorde en tussentijd zijn niet geregistreerd.`;
  });
}

export function enduranceLines(r: EngineResponse): string[] {
  const m = r.endurance.cp_model, ref = r.endurance.reference;
  if (m.status === 'ok') return [`Critical power uit ${m.efforts_used} maximale inspanningen: ${nl(m.cp_w!, 0)} W (standaardfout ${nl(m.se_cp_w!, 0)} W), W′ ${nl(m.w_prime_j! / 1000)} kJ. Geldig voor inspanningen van ongeveer 2 tot 20 minuten.`];
  if (ref.source === 'user_entered_cp') return [`Je zelf ingevoerde critical power (${nl(ref.power_w!, 0)} W) wordt gebruikt.`];
  if (ref.source === 'user_entered_threshold_not_cp') return [`Je zelf ingevoerde drempelvermogen (${nl(ref.power_w!, 0)} W) wordt als referentie gebruikt. Dat is geen critical power; W′ is onbekend.`];
  return ['Geen referentievermogen bekend. Vermogensdata worden niet omgezet in een belasting, en er worden geen persoonlijke vermogensdoelen berekend.'];
}

export function outcomeNotice(outcome: EngineOutcome): string | null {
  return outcome.state === 'unavailable' ? UNAVAILABLE[outcome.reason] : null;
}

const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${nl(Math.abs(n))} %`;
function effect(label: string, e: FatigueEffect): string | null {
  if (Math.abs(e.total_pct) < 0.25) return null;
  const cross = Math.abs(e.cross_fatigue_pct) >= 0.25 ? `, waarvan ${signed(e.cross_fatigue_pct)} door de andere trainingsvorm` : '';
  return `${label}: ${signed(e.total_pct)} (onzekerheid ${signed(e.low_pct)} tot ${signed(e.high_pct)})${cross}.`;
}

/** The concurrent model. Every line says whether it rests on the athlete's own data or on group-level assumptions. */
export function modelLines(r: EngineResponse): string[] {
  const m = r.concurrent_model;
  if (!m) return [];
  const lines: string[] = [];
  const now = m.expected_fatigue_effect[0];
  const effects = [effect('Benenkracht', now.strength_lower), effect('Bovenlichaamkracht', now.strength_upper), effect('Duurvermogen', now.endurance)].filter(Boolean) as string[];
  lines.push(effects.length ? `Verwacht effect van je recente trainingen aan het eind van vandaag — ${effects.join(' ')}`
    : 'Het model verwacht aan het eind van vandaag geen merkbare restvermoeidheid van je recente trainingen.');
  const later = m.expected_fatigue_effect[2];
  if (effects.length && later && Math.abs(later.strength_lower.total_pct) < 0.25 && Math.abs(later.endurance.total_pct) < 0.25) lines.push('Over twee dagen is dat verwachte effect weggeëbd, als je tussendoor niet traint.');
  const s = m.strength;
  if (s.status === 'prior_only') lines.push(`Deze verwachting berust op voorlopige modelaannames, geïnspireerd op groepsonderzoek en niet op jouw metingen: daarvoor zijn minstens zes vergelijkbare krachtmetingen nodig (nu ${s.observations}).`);
  else if (s.verdict === 'interaction_shown_in_own_data') lines.push(`In je eigen gegevens (${s.observations} krachtmetingen) past een model met wisselwerking beter bij deze verkennende toets. Dit bewijst geen oorzakelijke interferentie.`);
  else if (s.verdict === 'own_dynamics_shown_in_own_data') lines.push(`Je eigen gegevens (${s.observations} krachtmetingen) passen beter bij een model met recente krachtbelasting, maar ondersteunen de wisselwerking nog niet. Dit is een verkennende samenhang; de overige parameters blijven voorlopige aannames.`);
  else lines.push(`Op ${s.observations} eigen krachtmetingen voorspelt het model nog niet aantoonbaar beter dan een eenvoudige vergelijking. De getallen leunen dus vooral op voorlopige modelaannames, geïnspireerd op groepsonderzoek.`);
  if (m.data.sessions_without_start_time > 0) lines.push(`${m.data.sessions_without_start_time} ${m.data.sessions_without_start_time === 1 ? 'training heeft' : 'trainingen hebben'} geen starttijd. Daar rekent het model met het midden van de dag en kan het niet zien of kracht en duur binnen drie uur van elkaar lagen.`);
  lines.push('Dit is een modelverwachting van een prestatieverschil, geen meting en geen uitspraak over blessurerisico. Het model is niet op echte atleten gevalideerd.');
  return lines;
}

export function effortLine(r: EngineResponse): string | null {
  const m = r.endurance.cp_model;
  if (m.status === 'ok' || !m.reasons.length) return m.warnings.length ? cpWarnings(m.warnings) : null;
  const why: Record<string, string> = { need_three_maximal_efforts_2_to_20_min: 'er zijn minstens drie maximale inspanningen van verschillende duur tussen 2 en 20 minuten nodig',
    power_not_decreasing_with_duration: 'het vermogen daalt niet met de duur, dus minstens één inspanning was niet maximaal',
    cp_standard_error_above_5_percent: 'de inspanningen liggen te ver van één curve om critical power betrouwbaar te bepalen',
    w_prime_standard_error_above_10_percent: 'de inspanningen bepalen W′ te onnauwkeurig', non_physical_parameters: 'de inspanningen geven geen zinvolle curve' };
  return `Nog geen critical power: ${m.reasons.map(x => why[x] ?? x).join('; ')}.`;
}
function cpWarnings(warnings: string[]): string | null {
  const text: Record<string, string> = { no_effort_of_10_min_or_longer_cp_may_be_overestimated: 'zonder inspanning van tien minuten of langer wordt critical power waarschijnlijk overschat',
    efforts_span_more_than_6_weeks: 'de inspanningen liggen meer dan zes weken uit elkaar', repeated_durations_best_effort_used: 'bij gelijke duur telt alleen de beste inspanning',
    durations_too_similar: 'de duren liggen dicht bij elkaar', efforts_outside_2_to_20_min_ignored: 'inspanningen korter dan 2 of langer dan 20 minuten tellen niet mee',
    only_three_efforts_one_degree_of_freedom: 'met drie inspanningen is de foutmarge zelf onzeker' };
  const known = warnings.map(w => text[w]).filter(Boolean);
  return known.length ? `Let op bij deze critical power: ${known.join('; ')}.` : null;
}
