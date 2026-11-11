"""Energy is simulation state; optional gather presentation has no world effects."""
from dataclasses import replace
import copy
import hashlib
import pygame
import pytest
from civsandbox.actions import Action,ActionType,execute
from civsandbox.agents import Agent
from civsandbox.energy import EnergyRules
from civsandbox.config import Settings
from civsandbox.interact_animation import InteractionView,phase_at,draw_pose,PHASES
from civsandbox.rendering import Renderer,handle_event,advance_frame
from civsandbox.simulation import Simulation,FixedTicker
from civsandbox.savegame import checkpoint,restore
from test_routines import near_bush

def gather_fixture():
    sim,actor,_ = near_bush()
    bush = next(b for b in sim.resources.bushes.values() if len(sim.world.neighbors(b.position))==4)
    actor.position = sim.world.neighbors(bush.position)[0]
    return sim,actor,bush
from test_wildlife import hunt_fixture
from test_chicken_click_animation import WaitProvider


def test_passive_energy_fifty_times_slower_and_hunger_unchanged():
    sim=Simulation(7,WaitProvider())
    for _ in range(200):sim.step()
    assert all(a.energy==89 and a.energy_spent_micro==0 and a.hunger==42 for a in sim.agents)
    # 50 simulated seconds: old passive -50, new -1. Hunger remains +1 / 3 seconds.


def test_fractional_walk_cost_and_invalid_move_no_double_drain():
    sim=Simulation(7,WaitProvider());a=sim.agents[0];a.energy=50
    start=a.position;neighbor=sim.world.neighbors(start)[0]
    for i in range(10):
        assert execute(Action(ActionType.MOVE_TO,neighbor if i%2==0 else start),a,sim.world,sim.resources,i,sim.social)
    assert a.energy==49 and a.energy_spent_micro==0
    before=(a.energy,a.energy_spent_micro)
    assert not execute(Action(ActionType.MOVE_TO,(-1,0)),a,sim.world,sim.resources,11,sim.social)
    assert (a.energy,a.energy_spent_micro)==before


def test_walking_does_not_also_pay_idle_cost_on_needs_boundary():
    sim=Simulation(7,WaitProvider());a=sim.agents[0];sim.set_participant(a.id)
    assert sim.player.submit(Action(ActionType.MOVE_TO,sim.world.neighbors(a.position)[0]),sim)
    sim.step()
    assert (a.energy,a.energy_spent_micro)==(90,100_000)


def test_completed_gather_costs_once_and_cancel_costs_nothing():
    sim,a,bush=gather_fixture();a.energy=50
    action=Action(ActionType.GATHER,bush.position)
    assert sim.progress.execute(action,a,sim.world,sim.resources,1,'test')
    finish=sim.progress.jobs[a.id].finish_tick
    assert (a.energy,a.food)==(50,0)
    assert sim.progress.execute(action,a,sim.world,sim.resources,finish,'test')
    assert (a.energy,a.food)==(49,1)
    assert sim.progress.execute(action,a,sim.world,sim.resources,finish+1,'test')
    sim.progress.cancel_for(a.id)
    assert (a.energy,a.food)==(49,1)


def test_hunt_step_cost_replaces_walk_cost_and_catch_costs_once():
    sim,a,c,hunt=hunt_fixture();a.energy=50
    sim.wildlife.begin(a,c.id)
    neighbor=next(p for p in sim.world.neighbors(a.position) if p!=c.position)
    assert execute(Action(ActionType.MOVE_TO,neighbor),a,sim.world,sim.resources,0,sim.social)
    assert (a.energy,a.energy_spent_micro)==(50,500_000)
    a.position=(3,2);p=sim.wildlife.pursuits[a.id];p.catch_ready_tick=1;sim.wildlife.tick=1
    assert execute(hunt,a,sim.world,sim.resources,1,sim.social)
    assert (a.energy,a.energy_spent_micro)==(46,500_000)
    assert not execute(hunt,a,sim.world,sim.resources,1,sim.social)


def test_cooking_and_rest_use_central_rates():
    sim=Simulation(7);a=sim.agents[0];a.energy=40;a.inventory.add('raw_chicken')
    a.position=sim.world.neighbors(sim.cooking_station.position)[0]
    action=Action(ActionType.COOK,sim.cooking_station.id)
    assert sim.progress.execute(action,a,sim.world,sim.resources,1,'test')
    finish=sim.progress.jobs[a.id].finish_tick;sim.resources.tick=finish
    assert sim.progress.execute(action,a,sim.world,sim.resources,finish,'test')
    assert (a.energy,a.energy_spent_micro)==(40,500_000)
    assert execute(Action(ActionType.REST),a,sim.world,sim.resources,finish,sim.social)
    assert (a.energy,a.energy_spent_micro)==(48,500_000)
    a.energy=99;assert execute(Action(ActionType.REST),a,sim.world,sim.resources,finish,sim.social)
    assert (a.energy,a.energy_spent_micro)==(100,0)


def test_energy_debt_configuration_and_legacy_saves():
    sim=Simulation(7,energy_rules=replace(EnergyRules(),walk_cost=.2));a=sim.agents[0]
    sim.energy_rules.spend(a,.25)
    payload=checkpoint(sim);loaded=restore(copy.deepcopy(payload))
    assert loaded.energy_rules.walk_cost==.2 and loaded.agents[0].energy_spent_micro==250_000
    assert loaded.resources.energy_rules is loaded.energy_rules
    payload['configuration'].pop('energy')
    for actor in payload['agents']:actor.pop('energy_spent_micro')
    assert restore(payload).agents[0].energy_spent_micro==0
    for bad in (-1,1_000_000,True):
        invalid=checkpoint(sim);invalid['agents'][0]['energy_spent_micro']=bad
        with pytest.raises(ValueError):restore(invalid)


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf'),.0001,True])
def test_energy_configuration_rejects_invalid_rates(value):
    with pytest.raises(ValueError):EnergyRules(walk_cost=value)


def setup_renderer_gather(direction='right',enabled=True):
    sim,a,bush=gather_fixture()
    # Use an open controlled map already supplied by the shared resource fixture.
    offsets={'down':(0,-1),'left':(1,0),'right':(-1,0),'up':(0,1)}
    dx,dy=offsets[direction];a.position=(bush.position[0]+dx,bush.position[1]+dy)
    renderer=Renderer(enable_interact_animation=enabled)
    renderer.sync_characters(sim)
    sim.tick=1
    assert sim.progress.execute(Action(ActionType.GATHER,bush.position),a,sim.world,sim.resources,1,'test')
    renderer.capture_tick(sim,.25)
    return sim,a,bush,renderer


@pytest.mark.parametrize('direction',('down','left','right','up'))
def test_four_phases_facing_anchoring_and_no_tick_restarts(direction):
    sim,a,bush,r=setup_renderer_gather(direction)
    try:
        view=r.interactions[a.id];base=a.position;foot=r.foot_position(r.characters[a.id])
        assert a.facing==direction and view.active and view.state=='interact_gather'
        seen=[];pixels=[]
        for phase in range(4):
            view.elapsed=(phase+.5)/4*view.play_cycle
            seen.append(view.phase)
            surface=pygame.Surface((100,110));surface.fill((0,0,0));view.draw(surface,(50,70))
            pixels.append(hashlib.sha256(pygame.image.tobytes(surface,'RGB')).hexdigest())
        assert tuple(seen)==PHASES and len(set(pixels))==4
        view.elapsed=.1;job=sim.progress.jobs[a.id];key=view.key
        sim.tick=2;r.capture_tick(sim,.25)
        assert view.key==key and view.elapsed==.25
        r.advance_animation(.1);assert view.elapsed==pytest.approx(.35)
        r.advance_animation(2,True);assert view.elapsed==pytest.approx(.35)
        assert a.position==base and r.foot_position(r.characters[a.id])==foot
        assert a.food==0 and bush.quantity>0 and job is sim.progress.jobs[a.id]
    finally:pygame.quit()


def test_feature_off_and_invalid_rejected_or_cancelled_actions():
    sim,a,bush,r=setup_renderer_gather(enabled=False)
    try:
        assert not r.interactions[a.id].active
        r.enable_interact_animation=True;r.sync_interactions(sim);assert r.interactions[a.id].active
        sim.progress.cancel_for(a.id);r.sync_interactions(sim);assert not r.interactions[a.id].active
        assert a.food==0
        assert not sim.progress.execute(Action(ActionType.GATHER,(-1,0)),a,sim.world,sim.resources,2,'test')
        r.sync_interactions(sim);assert not r.interactions[a.id].active
        assert sim.progress.execute(Action(ActionType.GATHER,bush.position),a,sim.world,sim.resources,2,'test')
        r.sync_interactions(sim);a.position=(0,0);r.sync_interactions(sim)
        assert not r.interactions[a.id].active and a.food==0
    finally:pygame.quit()


def test_completed_gather_once_returns_to_idle_and_cannot_flicker_rewards():
    sim,a,bush,r=setup_renderer_gather()
    try:
        action=sim.progress.jobs[a.id].action;finish=sim.progress.jobs[a.id].finish_tick
        for _ in range(20):r.advance_animation(.01);r.sync_interactions(sim)
        assert a.food==0
        sim.tick=finish
        assert sim.progress.execute(action,a,sim.world,sim.resources,finish,'test')
        r.capture_tick(sim,.25);assert not r.interactions[a.id].active and a.food==1
        for _ in range(60):r.draw(sim,FixedTicker());r.advance_animation(1/60)
        assert a.food==1 and r.characters[a.id].animator.state=='idle'
    finally:pygame.quit()


def test_walking_transitions_wait_for_visual_arrival_and_never_use_walk_frames():
    sim,a,bush,r=setup_renderer_gather()
    try:
        view=r.characters[a.id];view.snap((a.position[0]-1,a.position[1]));view.capture(a.position,.25)
        r.sync_interactions(sim);assert not r.interactions[a.id].active and view.animator.moving
        r.advance_animation(.25);r.sync_interactions(sim);assert r.interactions[a.id].active
        assert view.animator.state=='idle'
        before=sim.snapshot();r.draw(sim,FixedTicker());assert sim.snapshot()==before
    finally:pygame.quit()


def test_preview_freezes_world_and_all_characters_are_selectable():
    sim=Simulation(7);r=Renderer();ticker=FixedTicker()
    try:
        r.sync_characters(sim);handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F7),sim,ticker,r)
        before=sim.snapshot()
        for key in (pygame.K_1,pygame.K_2,pygame.K_3,pygame.K_4):
            handle_event(pygame.event.Event(pygame.KEYDOWN,key=key),sim,ticker,r)
            advance_frame(r,ticker,sim,.2);r.draw_interact_preview()
            assert r.preview_character==key-pygame.K_1
        assert sim.snapshot()==before and r.interact_preview_clock==pytest.approx(.8)
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_SPACE),sim,ticker,r)
        advance_frame(r,ticker,sim,2);assert r.interact_preview_clock==pytest.approx(.8)
    finally:pygame.quit()


def test_phase_curves_are_continuous_at_wrap_and_boundaries():
    for boundary in (.25,.5,.75,1):
        assert abs(phase_at(boundary-1e-6)[1]-phase_at(boundary+1e-6)[1])<1e-4
    with pytest.raises(ValueError):InteractionView(.1)


def test_presentation_settings_and_env_disable(tmp_path,monkeypatch):
    monkeypatch.setenv('ENABLE_INTERACT_ANIMATION','false')
    monkeypatch.setenv('INTERACT_ANIMATION_SECONDS','1.2')
    settings=Settings.load(tmp_path/'missing.env')
    assert settings.enable_interact_animation is False and settings.interact_animation_seconds==1.2
    monkeypatch.setenv('ENABLE_INTERACT_ANIMATION','maybe')
    with pytest.raises(ValueError):Settings.load(tmp_path/'missing.env')


def test_animation_on_off_produces_identical_real_survival_and_gather_outcomes():
    on=Simulation(42);off=Simulation(42)
    first=Renderer();second=Renderer(enable_interact_animation=False)
    active=False
    try:
        first.sync_characters(on);second.sync_characters(off)
        for _ in range(1200):
            on.step();off.step()
            first.advance_animation(.25);second.advance_animation(.25)
            first.capture_tick(on,.25);second.capture_tick(off,.25)
            active |= any(v.active for v in first.interactions.values())
            assert not any(v.active for v in second.interactions.values())
        assert active and on.snapshot()==off.snapshot()
        assert on.rng.getstate()==off.rng.getstate()
    finally:pygame.quit()


def test_cycle_fits_whole_gather_duration_and_does_not_restart_per_tick():
    sim,a,bush,r=setup_renderer_gather()
    try:
        interaction=r.interactions[a.id];job=sim.progress.jobs[a.id]
        duration=job.duration_ticks*.25
        assert duration/interaction.play_cycle==round(duration/interaction.play_cycle)
        assert .8<=interaction.play_cycle<=1.2
        for tick in range(2,job.finish_tick):
            sim.tick=tick;r.capture_tick(sim,.25)
            assert interaction.elapsed==(tick-1)*.25
        assert phase_at(duration-1e-6,interaction.play_cycle)[1]<1e-5
    finally:pygame.quit()


def test_five_day_offline_survival_is_not_an_exhaustion_rest_loop():
    from civsandbox.experiments import run_trial
    row=run_trial(Settings(),42,12000,True,'normal_survival')
    assert row['status']=='completed' and row['food_conservation']
    assert row['incapacitations']==0 and row['average_energy']>50
    assert row['gathering_actions']>50 and sum(row['meals_consumed'].values())>50
    assert row['activity_npc_ticks'].get('rest',0)/(12000*4)<.10
    assert row['gemini_calls']==0


def test_energy_and_animation_progress_respect_pause_and_speed():
    slow=Simulation(7,WaitProvider());fast=Simulation(7,WaitProvider())
    first=FixedTicker();second=FixedTicker();second.speed=4
    for _ in range(50):first.advance(slow,1);second.advance(fast,.25)
    assert slow.snapshot()==fast.snapshot()
    slow.paused=True;before=slow.snapshot();first.advance(slow,20);assert slow.snapshot()==before
    sim,a,bush,r=setup_renderer_gather()
    try:
        r.interactions[a.id].elapsed=0;r.advance_animation(.4,speed=4)
        assert r.interactions[a.id].elapsed==pytest.approx(.4)
        r.advance_animation(2,paused=True,speed=4)
        assert r.interactions[a.id].elapsed==pytest.approx(.4)
    finally:pygame.quit()


def test_live_f6_toggle_does_not_change_world_or_jobs():
    sim,a,bush,r=setup_renderer_gather()
    try:
        before=sim.snapshot();job=sim.progress.jobs[a.id]
        for expected in (False,True):
            handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F6),sim,FixedTicker(),r)
            assert r.enable_interact_animation is expected
            assert r.interactions[a.id].active is expected
            assert sim.snapshot()==before and sim.progress.jobs[a.id] is job
    finally:pygame.quit()


def test_pause_during_visual_arrival_cannot_start_interaction_early():
    sim,a,bush,r=setup_renderer_gather()
    try:
        character=r.characters[a.id]
        character.snap((a.position[0]-1,a.position[1]));character.capture(a.position,.25)
        character.advance(.125);character.advance(0,paused=True)
        assert not character.animator.moving and character.segments
        r.sync_interactions(sim);assert not r.interactions[a.id].active
        character.advance(.125);r.sync_interactions(sim);assert r.interactions[a.id].active
    finally:pygame.quit()
