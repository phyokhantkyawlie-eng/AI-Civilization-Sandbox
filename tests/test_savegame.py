"""Full-world validation, transactionality and committed-only checkpoints."""
import copy
import json

import pytest

from civsandbox.actions import Action,ActionType
from civsandbox.savegame import save_game,load_game,load_into,checkpoint,restore,SaveError
from civsandbox.simulation import Simulation


def totals(sim):
    return {item:sum(a.inventory.quantity(item) for a in sim.agents)
            for item in ('berries','raw_chicken','cooked_chicken')}


@pytest.mark.parametrize('mode',['observer','participant'])
@pytest.mark.parametrize('provider',['rule-based','mock'])
def test_full_roundtrip_preserves_physical_history_and_identity(tmp_path,mode,provider):
    from civsandbox.config import Settings,create_provider
    sim=Simulation(7,create_provider(Settings(provider=provider)),scenario='food_shortage')
    for _ in range(220):sim.step()
    if mode=='participant':sim.set_participant('npc-3')
    sim.agents[0].facing='left'
    path=tmp_path/'world.json'
    before=totals(sim)
    save_game(sim,path,'npc-2')
    loaded=load_game(path)
    assert len(loaded.agents)==4 and [a.id for a in loaded.agents]==[a.id for a in sim.agents]
    assert loaded.world.tiles==sim.world.tiles and loaded.tick==sim.tick
    assert loaded.time_of_day==sim.time_of_day and loaded.resources.stocks()==sim.resources.stocks()
    assert totals(loaded)==before and loaded.selected_id=='npc-2'
    assert (loaded.player.agent_id if loaded.player else None)==('npc-3' if mode=='participant' else None)
    for original,actor in zip(sim.agents,loaded.agents):
        for attr in ('name','position','hunger','energy','inventory','trust','memories','personality','facing'):
            assert getattr(actor,attr)==getattr(original,attr)
    assert list(loaded.history.world)==list(sim.history.world)
    assert list(loaded.history.conversations)==list(sim.history.conversations)
    assert not loaded.progress.jobs and not loaded.social.pending and not loaded.social.sessions
    for _ in range(3):
        save_game(loaded,path)
        loaded=load_game(path)
        assert totals(loaded)==before


def test_checkpoint_does_not_touch_live_jobs_or_reward_unfinished_cooking(tmp_path):
    from test_cooking_plans import station_fixture
    sim,actor,station,action=station_fixture()
    sim.step()
    finish=sim.progress.jobs[actor.id].finish_tick
    path=tmp_path/'world.json'
    save_game(sim,path)
    assert station.occupied_by==actor.id and sim.progress.jobs[actor.id].finish_tick==finish
    loaded=load_game(path)
    assert loaded.cooking_station.occupied_by is None
    assert loaded.agents[0].inventory.quantity('raw_chicken')==1
    assert loaded.agents[0].inventory.quantity('cooked_chicken')==0
    assert not loaded.progress.jobs


def test_active_hunt_and_conversation_load_as_unclaimed_idle_without_rewards(tmp_path):
    from test_wildlife import hunt_fixture
    from test_conversations import pair
    for sim in (hunt_fixture()[0],pair()[0]):
        sim.step()
        path=tmp_path/'world.json'
        before=totals(sim)
        save_game(sim,path)
        loaded=load_game(path)
        assert totals(loaded)==before
        assert not loaded.wildlife.pursuits and not loaded.progress.locks and not loaded.social.active_sessions
        assert all(c.claimed_by is None for c in loaded.wildlife.living())


def test_successful_hunt_dead_identity_respawn_and_meat_survive_load(tmp_path):
    from test_wildlife import hunt_fixture
    sim,actor,chicken,_=hunt_fixture()
    for _ in range(6):sim.step()
    assert not chicken.alive
    path=tmp_path/'world.json';save_game(sim,path)
    loaded=load_game(path)
    assert not loaded.wildlife.chickens[chicken.id].alive
    assert loaded.wildlife.sequence==sim.wildlife.sequence
    assert loaded.wildlife.respawns==sim.wildlife.respawns
    assert loaded.agents[0].inventory.quantity('raw_chicken')==1


@pytest.mark.parametrize('bad',[
    'negative_food','overflow','duplicate_npc','wrong_name','blocked_npc','needs','duplicate_chicken',
    'overgrown_bush','missing_bush','bad_trust','bad_memory','version','provider','rng','mode','nan','world_size',
])
def test_bad_files_do_not_replace_current_world(tmp_path,bad):
    sim=Simulation(42)
    payload=checkpoint(sim)
    if bad=='negative_food':payload['agents'][0]['inventory']['items']={'berries':-1}
    elif bad=='overflow':payload['agents'][0]['inventory']['items']={'berries':100}
    elif bad=='duplicate_npc':payload['agents'][1]=copy.deepcopy(payload['agents'][0])
    elif bad=='wrong_name':payload['agents'][0]['name']='Ren'
    elif bad=='blocked_npc':payload['agents'][0]['position']=payload['station']['position']
    elif bad=='needs':payload['agents'][0]['hunger']=101
    elif bad=='duplicate_chicken':payload['chickens'].append(copy.deepcopy(payload['chickens'][0]))
    elif bad=='overgrown_bush':payload['resources'][0]['quantity']=1001
    elif bad=='missing_bush':payload['resources'].pop()
    elif bad=='bad_trust':payload['agents'][0]['trust']['npc-2']=101
    elif bad=='bad_memory':payload['agents'][0]['memories']=[{'tick':0,'actor_id':'ghost'}]
    elif bad=='version':payload['version']=999
    elif bad=='provider':payload['provider']='gemini'
    elif bad=='rng':payload['rng']=[]
    elif bad=='mode':payload['player_id']='npc-5';payload['mode']='participant'
    elif bad=='nan':payload['agents'][0]['hunger']=float('nan')
    elif bad=='world_size':payload['world'].pop()
    path=tmp_path/'broken.json';path.write_text(json.dumps(payload))
    before=sim.snapshot()
    with pytest.raises(SaveError):load_into(sim,path)
    assert sim.snapshot()==before


def test_atomic_failure_and_foreign_history_preservation(tmp_path,monkeypatch):
    sim=Simulation(42);path=tmp_path/'world.json';save_game(sim,path)
    original=path.read_bytes()
    import civsandbox.savegame as saves
    def fail(*args):raise OSError('simulated interrupted replacement')
    monkeypatch.setattr(saves.os,'replace',fail)
    with pytest.raises(SaveError):save_game(sim,path)
    assert path.read_bytes()==original and not list(tmp_path.glob('.world-*'))
    social=tmp_path/'social.json';social.write_text('{"version":1,"agents":{}}')
    before=social.read_bytes()
    with pytest.raises(SaveError):save_game(sim,social)
    assert social.read_bytes()==before


def test_invalid_json_duplicate_keys_and_missing_file_are_safe(tmp_path):
    path=tmp_path/'world.json'
    for data in ('{','{"version":1,"version":2}','[]'):
        path.write_text(data)
        with pytest.raises(SaveError):load_game(path)
    with pytest.raises(SaveError):load_game(tmp_path/'absent.json')


def test_loading_keeps_legacy_private_history_untouched(tmp_path):
    legacy=tmp_path/'social.json'
    sim=Simulation(7,memory_path=legacy)
    for _ in range(30):sim.step()
    sim.social.save()
    original=legacy.read_bytes()
    path=tmp_path/'world.json';save_game(sim,path)
    loaded=load_game(path)
    assert loaded.social.memory_path is None
    for _ in range(20):loaded.step()
    loaded.close()
    assert legacy.read_bytes()==original


def test_same_checkpoint_resumes_reproducibly(tmp_path):
    sim=Simulation(42)
    for _ in range(60):sim.step()
    path=tmp_path/'world.json';save_game(sim,path)
    a,b=load_game(path),load_game(path)
    for _ in range(150):a.step();b.step()
    assert a.snapshot()==b.snapshot()


def test_regeneration_continues_once_from_saved_tick_without_catchup_food(tmp_path):
    from test_participant import controlled
    sim,_,_=controlled()
    for _ in range(79):sim.step()
    bush=next(iter(sim.resources.bushes.values()))
    bush.quantity=1;bush.regeneration_progress=19
    path=tmp_path/'world.json';save_game(sim,path)
    loaded=load_game(path)
    restored=loaded.resources.bushes[bush.position]
    assert restored.quantity==1 and restored.regeneration_progress==19
    loaded.resources.replenish(80)
    assert restored.quantity==2
    loaded.resources.replenish(80)
    assert restored.quantity==2
