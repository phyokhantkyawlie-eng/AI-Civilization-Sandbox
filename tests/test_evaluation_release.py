"""Streaming metrics and controlled offline evaluation without scripted outcomes."""
import json
import pytest

from civsandbox.config import Settings
from civsandbox.experiments import run_trial,run_batch,prepare_scenario,HUNTING_PROFILES
from civsandbox.measurements import Measurements
from civsandbox.simulation import Simulation


def test_streaming_counters_survive_log_trimming_and_activity_denominators():
    from test_participant import WaitingAI
    sim=Simulation(7,decision_provider=WaitingAI(),event_limit=8)
    record=Measurements()
    for _ in range(120):
        sim.step();record.capture(sim)
    assert len(sim.events)<=8
    assert record.events['opportunities']==480
    assert record.samples==480 and sum(record.activity_ticks.values())==480
    assert record.energy_sum>0 and record.incapacitated_ticks==0
    before=record.events.copy()
    record.ingest([])
    assert record.events==before


@pytest.mark.parametrize('scenario',['normal_survival','food_shortage','social_memory'])
def test_initial_state_and_seed_are_reproducible_across_memory_modes(scenario):
    off=run_trial(Settings(),7,80,False,scenario)
    on=run_trial(Settings(),7,80,True,scenario)
    again=run_trial(Settings(),7,80,False,scenario)
    assert off['initial_state_sha256']==on['initial_state_sha256']==again['initial_state_sha256']
    assert off['initial_agents']==on['initial_agents']
    for key in ('average_hunger','average_energy','goal_choices','final_food_items','final_trust','state_series'):
        assert off[key]==again[key]
    assert off['npc_tick_samples']==320 and off['survival_rate'] is None
    assert 0<=off['operational_availability']<=1
    assert off['food_conservation'] and off['gemini_calls']==0


def test_profiles_define_initial_conditions_only_with_real_mobile_chickens():
    for name,(hunger,energy,item,quantity,scarce) in HUNTING_PROFILES.items():
        sim=Simulation(7,scenario='food_shortage')
        prepare_scenario(sim,'hunting_decisions',name)
        assert len(sim.wildlife.living())==2
        assert all(a.hunger==hunger and a.energy==energy for a in sim.agents)
        assert all(a.inventory.used==quantity for a in sim.agents)
        assert all(b.quantity==(0 if scarce else 5) for b in sim.resources.bushes.values())
        assert not sim.wildlife.pursuits and not sim.decision_provider.plans
        assert all(c.next_move_tick<100 for c in sim.wildlife.living())
        assert all(sim.world.walkable(c.position) for c in sim.wildlife.living())
        assert not any(e.get('action')=='HUNT' for e in sim.events)


def test_hunting_profiles_are_paired_by_profile_as_well_as_seed(tmp_path):
    rows=run_batch(Settings(),1,2,7,tmp_path/'profiles','hunting_decisions')
    data=json.loads((tmp_path/'profiles'/'summary.json').read_text())
    assert len(rows)==14 and len(data['summary']['paired_differences'])==7
    assert len(data['summary']['strata'])==7
    for profile in HUNTING_PROFILES:
        pair=[r for r in rows if r['profile']==profile]
        assert pair[0]['initial_state_sha256']==pair[1]['initial_state_sha256']
    assert data['summary']['paired_summary']['average_hunger']['approximate_95_ci_mean'] is None


@pytest.mark.parametrize('mode,expected',[('paired',4),('on',2),('off',2)])
def test_selectable_memory_mode_and_valid_exports(tmp_path,mode,expected):
    folder=tmp_path/mode
    rows=run_batch(Settings(),2,4,7,folder,'normal_survival',memory_mode=mode)
    assert len(rows)==expected and all(r['status']=='completed' for r in rows)
    config=json.loads((folder/'configuration.json').read_text())
    assert config['network_enabled'] is False and config['game_mode']=='observer'
    assert not any(k in config for k in ('api_key','gemini_tick_wall_seconds'))


def test_external_provider_cannot_be_mislabeled_as_offline_or_make_calls(tmp_path):
    with pytest.raises(ValueError):run_trial(Settings(provider='gemini'),7,1,True)
    with pytest.raises(ValueError):run_batch(Settings(provider='gemini'),1,1,7,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_memory_off_policy_has_no_hidden_trust_or_memory_inputs():
    from civsandbox.social import Memory
    sim=Simulation(7,memory_enabled=False,scenario='food_shortage')
    rule=sim.decision_provider;a,b=sim.agents[:2]
    before=rule.candidates(a,sim.world,sim.resources)
    a.trust[b.id]=-100;b.trust[a.id]=100
    a.memories.append(Memory(0,b.id,a.id,'REFUSE_REQUEST','refused',-4))
    assert rule.candidates(a,sim.world,sim.resources)==before


def test_extended_run_trajectories_and_logs_are_bounded_without_lost_totals():
    row=run_trial(Settings(),7,4400,False,'normal_survival')
    assert row['completed_ticks']==4400 and row['action_opportunities']==17600
    assert row['retained_engine_events']<=4096 and len(row['state_series'])<=1001
    assert sum(row['activity_npc_ticks'].values())==17600
    assert row['food_conservation'] and not row['duplicate_chicken_ids'] and not row['duplicate_meat_rewards']
    assert row['gathering_decisions']>0 and row['gathering_actions']>0


def test_spawn_latency_distinguishes_initial_spawn_and_repopulation():
    record=Measurements()
    record.ingest([{'action':'CHICKEN_SPAWN','target':'chicken-1','tick':0},
                   {'action':'ACTIVITY','activity_action':'HUNT','target':'chicken-1','accepted_start':True,'tick':1},
                   {'action':'CHICKEN_SPAWN','target':'chicken-2','tick':100},
                   {'action':'ACTIVITY','activity_action':'HUNT','target':'chicken-2','accepted_start':True,'tick':120}])
    assert record.events['near_spawn_hunts']==1 and record.events['near_repopulation_hunts']==0
    assert record.events['repopulations']==1 and record.minimum_spawn_delay==1


def test_hunting_profile_cannot_be_silently_ignored(tmp_path):
    with pytest.raises(ValueError):
        run_batch(Settings(),1,1,7,tmp_path/'invalid','normal_survival',profile='hungry')
    assert not (tmp_path/'invalid').exists()
