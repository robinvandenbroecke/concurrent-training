"""Scientific invariants; runnable with stdlib unittest as well as pytest."""
import copy
from datetime import date, datetime, timedelta, timezone
import math
import unittest
from app.domain.rep_engine import RepState, RepEngineParams, LiftVelocityProfile, SessionInput, SetInput, simulate_strength_session
from app.domain.day_engine import DayState, PerLiftState, DayEngineParams, decay_day_state_to_date, simulate_day_transition, compute_readiness, update_capacity_with_saturation
from app.domain.program_engine import ProgramConfig, ProgramMode, Priority, BlockType, create_microcycle_template
from app.domain.endurance_engine import compute_endurance_load
from app.schemas import PowerPoint
from research.evaluate import evaluate
from research.reference_model import ForecastModel, Parameters


class AuditInvariants(unittest.TestCase):
    def rep_state(self):
        return RepState({'squat': .5}, .6, 1.2, RepEngineParams())

    def session(self, velocities, **kwargs):
        return SessionInput(sets=[SetInput('squat', 60, velocities, **kwargs)],
                            profiles={'squat':LiftVelocityProfile('squat',1,.005)},
                            init_A_local={'squat':1},init_A_sys=1,init_M=0,R_mito=0,e1rm={'squat':100})

    def test_rest_is_independent_of_partition(self):
        whole,split=self.rep_state(),self.rep_state()
        whole.apply_rest(180,.5)
        for _ in range(180): split.apply_rest(1,.5)
        for field in ['x_sys','x_M']:
            self.assertAlmostEqual(getattr(whole,field),getattr(split,field),places=12)
        self.assertAlmostEqual(whole.A_local('squat'),split.A_local('squat'),places=12)

    def test_small_rest_cannot_add_fatigue(self):
        state=self.rep_state(); previous=state.A_local('squat')
        state.apply_rest(.0001)
        self.assertGreaterEqual(state.A_local('squat'),previous)

    def test_long_rest_approaches_recovery(self):
        state=self.rep_state(); state.apply_rest(86400)
        self.assertAlmostEqual(state.A_local('squat'),1)

    def test_missing_velocity_still_counts_performed_reps(self):
        out=simulate_strength_session(self.session([None]*5))
        self.assertEqual(len(out.sets[0].reps),5)
        self.assertLess(out.final_A_sys,1)
        self.assertTrue(all(not r.observation_available for r in out.sets[0].reps))

    def test_count_only_input(self):
        out=simulate_strength_session(self.session([],performed_reps=5))
        self.assertEqual(len(out.sets[0].reps),5)

    def test_partial_velocity_preserves_indices(self):
        out=simulate_strength_session(self.session([None,.5,None,.4]))
        self.assertEqual([r.observation_available for r in out.sets[0].reps],[False,True,False,True])

    def test_logged_metabolic_state_is_post_rep(self):
        out=simulate_strength_session(self.session([.5]))
        self.assertAlmostEqual(out.sets[0].reps[-1].A_M,out.final_A_M)

    def test_future_reps_do_not_change_earlier_predictions(self):
        short=self.session([.5,.48],rest_before_sec=60)
        long=self.session([.5,.48,.44,.40,.35],rest_before_sec=60)
        a,b=simulate_strength_session(short),simulate_strength_session(long)
        self.assertEqual(a.sets[0].reps,b.sets[0].reps[:2])

    def test_final_rpe_not_used_to_predict_earlier_reps(self):
        a=simulate_strength_session(self.session([.5,.45],set_end_rpe=5))
        b=simulate_strength_session(self.session([.5,.45],set_end_rpe=10))
        self.assertEqual(a.sets[0].reps,b.sets[0].reps)

    def test_profile_rejects_nonfinite(self):
        for value in [math.nan,math.inf]:
            with self.assertRaises(ValueError): LiftVelocityProfile('squat',value,.01)

    def test_missing_power_is_not_coasting(self):
        with self.assertRaises((TypeError,ValueError)):
            compute_endurance_load(sport='cycling',duration_minutes=1,declared_intensity='z2',power_data=[{'power':None}])

    def test_zero_watts_are_accepted_by_api(self):
        self.assertEqual(PowerPoint(power=0,timestamp=0).power,0)

    def test_coasting_and_irregular_timestamps_have_correct_integral(self):
        out=compute_endurance_load(sport='cycling',duration_minutes=1,declared_intensity='mixed',
            power_data=[{'timestamp':0,'power':200},{'timestamp':10,'power':0},{'timestamp':50,'power':200}],threshold_power_w=200)
        self.assertAlmostEqual(out.average_power_w,200/3)
        self.assertAlmostEqual(out.total,1/3)
        self.assertAlmostEqual(out.u_z2+out.u_hiit,out.total)
        self.assertIsNone(out.normalized_power_w)

    def test_zero_power_does_not_fall_back_to_positive_load(self):
        out=compute_endurance_load(sport='cycling',duration_minutes=60,declared_intensity='hiit',average_power_w=0,threshold_power_w=200)
        self.assertEqual(out.total,0)

    def test_power_load_is_not_silently_clipped(self):
        a=compute_endurance_load(sport='cycling',duration_minutes=1,declared_intensity='hiit',average_power_w=400,threshold_power_w=200)
        self.assertAlmostEqual(a.total,4)

    def test_timestamp_order_is_checked(self):
        with self.assertRaises(ValueError):
            compute_endurance_load(sport='cycling',duration_minutes=1,declared_intensity='z2',power_data=[{'power':100,'timestamp':1},{'power':100,'timestamp':0}])

    def test_day_decay_is_independent_of_partition(self):
        state=DayState(date(2026,1,1),{'squat':PerLiftState(.6,.5,100)},D_sys=.5,R_mito=.7,E_fat=.3,T_legs=.2)
        p=DayEngineParams(); a=decay_day_state_to_date(state,date(2026,1,8),p)
        b=state
        for _ in range(7): b=decay_day_state_to_date(b,b.date+timedelta(days=1),p)
        self.assertAlmostEqual(a.per_lift['squat'].D_l,b.per_lift['squat'].D_l)
        self.assertAlmostEqual(a.D_sys,b.D_sys)
        self.assertAlmostEqual(a.R_mito,b.R_mito)

    def test_empty_training_day_matches_rest_day(self):
        state=DayState(date(2026,1,1),{'squat':PerLiftState(.5,1,100)},R_mito=.8)
        out,_,_=simulate_day_transition(state,[],[])
        rest=decay_day_state_to_date(state,state.date+timedelta(days=1),DayEngineParams())
        self.assertEqual(out.per_lift,rest.per_lift)
        self.assertEqual(out.R_mito,rest.R_mito)
        self.assertEqual(out.per_lift['squat'].C_l,100)

    def test_easy_endurance_has_load_cost(self):
        out,_,_=simulate_day_transition(DayState(date(2026,1,1)),[],[('cycling',180,'z2')])
        self.assertGreater(out.E_fat,0)

    def test_fractional_saturation_above_ceiling_is_real(self):
        result=update_capacity_with_saturation(250,1,.1,DayEngineParams(capacity_saturation_alpha=.5))
        self.assertTrue(math.isfinite(result))

    def test_power_clean_uses_same_load_proxy_gate(self):
        state=DayState(date(2026,1,1),{'power_clean':PerLiftState()},T_legs=.5)
        self.assertEqual(compute_readiness(state,DayEngineParams()).per_lift['power_clean'],0)

    def test_priority_respects_configured_frequency(self):
        for priority in Priority:
            config=ProgramConfig(ProgramMode.CONCURRENT,priority,days_per_week_strength=2,days_per_week_endurance=1)
            plan=create_microcycle_template(config,BlockType.BASE,0,date(2026,1,5))
            self.assertEqual(sum(bool(d.primary_lifts) for d in plan.days),2)
            self.assertEqual(sum(bool(d.endurance_zone) for d in plan.days),1)

    def test_nested_models_reduce_exactly_to_M0(self):
        p=Parameters(k_strength=0,k_endurance=0)
        models=[ForecastModel(m,p) for m in ['M0','M1','M2']]
        for model in models:
            model.advance(datetime(2026,1,1,tzinfo=timezone.utc));model.add_dose(10,30);model.observe(.6,.7)
        self.assertEqual(len({m.predict(.7) for m in models}),1)

    def manifest(self):
        return {'data_source':'synthetic','test_start':{'a':'2026-01-02T00:00:00Z'},'profiles':{'a':{'squat':{'a':1,'b':.005,'min_load_kg':20,'max_load_kg':100,'calibrated_before':'2025-12-01T00:00:00Z'}}}}

    def events(self):
        return [{'event_id':str(i),'athlete_id':'a','timestamp':f'2026-01-0{i}T12:00:00Z','kind':'observation','lift':'squat','load_kg':60,'velocity_m_s':.6} for i in range(1,4)]

    def test_future_observations_cannot_change_prefix_predictions(self):
        rows=self.events();before=evaluate(self.manifest(),rows)
        rows[-1]['velocity_m_s']=1.2;after=evaluate(self.manifest(),rows)
        self.assertEqual(before['predictions'][:2],after['predictions'][:2])
        self.assertEqual(before['predictions'][-1]['predictions'],after['predictions'][-1]['predictions'])

    def test_duplicates_rejected(self):
        rows=self.events()
        with self.assertRaises(ValueError): evaluate(self.manifest(),rows+[rows[-1]])

    def test_future_calibration_rejected(self):
        m=self.manifest();m['profiles']['a']['squat']['calibrated_before']='2026-01-02T00:00:00Z'
        with self.assertRaises(ValueError): evaluate(m,self.events())

    def test_missing_provenance_rejected(self):
        m=self.manifest();del m['data_source']
        with self.assertRaises(ValueError): evaluate(m,self.events())

    def test_dose_without_observation_changes_next_forecast(self):
        rows=self.events();baseline=evaluate(self.manifest(),rows)
        dose={'event_id':'dose','athlete_id':'a','timestamp':'2026-01-01T13:00:00Z','kind':'strength','lift':'squat','dose':20}
        result=evaluate(self.manifest(),rows[:1]+[dose]+rows[1:])
        self.assertLess(result['predictions'][1]['predictions']['M1'],baseline['predictions'][1]['predictions']['M1'])

if __name__=='__main__':
    unittest.main()
