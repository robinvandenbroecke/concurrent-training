"""Prefix-only exploratory forecasts from explicit events and fixed calibration.

python -m research.evaluate --manifest research/example_manifest.json --events
research/example_events.csv --output artifacts/audit_2026_09/reference_demo.json

Standard library only. No application DB, saved states or mutable profiles.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from .reference_model import ForecastModel, Parameters


def timestamp(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError("Research timestamps require UTC offset")
    return value.astimezone(timezone.utc)


def number(text, name, positive=False):
    value = float(text)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"Invalid {name}")
    return value


def metrics(rows, model):
    errors = [r['predictions'][model] - r['observed_m_s'] for r in rows]
    n = len(errors)
    return {'n': n, 'mae_m_s': sum(abs(e) for e in errors)/n if n else None,
            'rmse_m_s': math.sqrt(sum(e*e for e in errors)/n) if n else None,
            'bias_m_s': sum(errors)/n if n else None}


def evaluate(manifest, events):
    if manifest.get('data_source') not in {'synthetic', 'real'}:
        raise ValueError("Manifest must explicitly label data_source")
    # Cutoffs are supplied in advance, never recalculated from future rows.
    # All calibration is completed before the first event for that athlete.
    cutoffs = {a: timestamp(v) for a, v in manifest['test_start'].items()}
    params = Parameters(**manifest.get('parameters', {}))
    profiles = manifest['profiles']
    models, last_ratio, predictions = {}, {}, []
    last_time, seen_ids = {}, set()
    for event in events:
        event_id = event['event_id']
        if not event_id or event_id in seen_ids:
            raise ValueError("Every event must have a unique nonempty event_id")
        seen_ids.add(event_id)
        athlete = event['athlete_id']
        at = timestamp(event['timestamp'])
        if athlete not in cutoffs or athlete not in profiles:
            raise ValueError("Athlete lacks profile or predefined test cutoff")
        if athlete in last_time and at < last_time[athlete]:
            raise ValueError("Events must be chronological within athlete")
        last_time[athlete] = at
        for lift, profile in profiles[athlete].items():
            if timestamp(profile['calibrated_before']) >= at:
                raise ValueError("Calibration cannot include the current/future event")
            key = (athlete, lift)
            models.setdefault(key, {m: ForecastModel(m, params) for m in ('M0','M1','M2')})
            for model in models[key].values():
                model.advance(at)
        kind = event['kind']
        lift = event.get('lift', '')
        if kind == 'strength':
            if (athlete, lift) not in models:
                raise ValueError("Strength dose lacks a lift profile")
            dose = number(event['dose'], 'strength dose')
            for model in models[(athlete, lift)].values():
                model.add_dose(strength=dose)
        elif kind == 'endurance':
            dose = number(event['dose'], 'endurance dose')
            for name in profiles[athlete]:
                for model in models[(athlete, name)].values():
                    model.add_dose(endurance=dose)
        elif kind == 'observation':
            key = (athlete, lift)
            if key not in models:
                raise ValueError("Observation lacks profile")
            profile = profiles[athlete][lift]
            load = number(event['load_kg'], 'load', positive=True)
            observed = number(event['velocity_m_s'], 'velocity', positive=True)
            if not profile['min_load_kg'] <= load <= profile['max_load_kg']:
                raise ValueError("Probe outside calibrated load range; do not silently clamp")
            a = number(profile['a'], 'intercept', positive=True)
            b = number(profile['b'], 'slope magnitude', positive=True)
            reference = a - b * load
            if reference <= 0:
                raise ValueError("Invalid reference velocity")
            forecast = {m: model.predict(reference) for m, model in models[key].items()}
            forecast['fixed_profile'] = reference
            forecast['last_observation'] = reference * last_ratio.get(key, 1.0)
            predictions.append({'event_id': event_id, 'athlete_id': athlete, 'lift': lift,
                                'timestamp': at.isoformat(), 'split': 'test' if at >= cutoffs[athlete] else 'train',
                                'observed_m_s': observed, 'reference_m_s': reference, 'predictions': forecast})
            # Only after prediction does this event update each model.
            for model in models[key].values():
                model.observe(observed, reference)
            last_ratio[key] = observed / reference
        else:
            raise ValueError("Unknown event kind")
    test = [r for r in predictions if r['split']=='test']
    names = ['fixed_profile','last_observation','M0','M1','M2']
    by_athlete = {a: {m: metrics([r for r in test if r['athlete_id']==a],m) for m in names} for a in cutoffs}
    return {'model_version':'research-reference-v1', 'data_source':manifest['data_source'],
            'evaluation_kind':'fixed_parameter_exploratory_prequential_holdout',
            'prefix_only':True, 'runtime_model_validated':False, 'clinical_or_coaching_efficacy_demonstrated':False,
            'parameters':vars(params), 'n_test':len(test),
            'metrics':{m:metrics(test,m) for m in names}, 'per_athlete':by_athlete,
            'limitations':['Candidate parameters are not fitted or fairly tuned against all literature baselines',
                           'No calibrated predictive intervals, causal inference or athlete-external validation',
                           'Manifest calibration provenance must be independently verified',
                           'Endurance coupling is phenomenological, not a chronic interference mechanism'],
            'predictions':predictions}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    with args.events.open(newline='') as f:
        events=list(csv.DictReader(f))
    report=evaluate(manifest,events)
    report['input_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.manifest,args.events)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['data_source','n_test','metrics']},indent=2))


if __name__=='__main__':
    main()
