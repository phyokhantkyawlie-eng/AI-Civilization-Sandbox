"""Discrete combat, saved health and deterministic presentation regressions."""
from dataclasses import replace
import copy
import pygame
import pytest
from civsandbox.actions import Action, ActionType, execute
from civsandbox.chicken_animation import ChickenView
from civsandbox.config import Settings
from civsandbox.pacing import ActionTiming
from civsandbox.player import nearby_options
from civsandbox.rendering import Renderer, handle_event
from civsandbox.savegame import checkpoint, restore
from civsandbox.simulation import Simulation, FixedTicker
from test_wildlife import hunt_fixture


def controlled():
    sim, actor, chicken, _ = hunt_fixture()
    sim.set_participant(actor.id)
    return sim, actor, chicken


def test_four_hits_exact_health_single_reward_and_respawn():
    sim, actor, chicken = controlled()
    for hp in (75,50,25,0):
        assert sim.player_attack(chicken.id)
        assert chicken.hp == hp
        assert actor.inventory.quantity('raw_chicken') == int(hp == 0)
    assert not sim.player_attack(chicken.id)
    assert not execute(Action(ActionType.ATTACK,chicken.id),actor,sim.world,sim.resources,sim.tick,sim.social)
    assert len(sim.wildlife.respawns)==1 and not chicken.alive
    assert len([e for e in sim.events if e['action']=='HUNT' and e.get('executed')])==1
    assert len([e for e in sim.events if e['action']=='CHICKEN_HIT'])==4
    assert any('collected raw chicken' in row['text'] for row in sim.history.world)


@pytest.mark.parametrize('offset,accepted', [((0,0),True),((1,0),True),((-1,0),True),((0,1),True),((0,-1),True),((1,1),False),((2,0),False)])
def test_actual_tile_distance_is_manhattan_not_visual(offset,accepted):
    sim,actor,chicken=controlled();actor.position=(8,8);chicken.position=(8+offset[0],8+offset[1])
    before=actor.position
    assert sim.player_attack(chicken.id) is accepted
    assert actor.position==before and chicken.hp==(75 if accepted else 100)
    if not accepted:assert sim.player.message=='Too far away'


def test_pause_busy_capacity_claim_invalid_and_dead_targets_no_effect():
    sim,a,c=controlled()
    sim.paused=True;assert not sim.player_attack(c.id);sim.paused=False
    assert not sim.player_attack('missing')
    a.inventory.add('berries',a.inventory.capacity);assert not sim.player_attack(c.id)
    a.inventory.remove('berries',a.inventory.capacity)
    c.claimed_by='npc-2';assert not sim.player_attack(c.id);c.claimed_by=None
    assert sim.player.submit(Action(ActionType.REST),sim);sim.step()
    assert not sim.player_attack(c.id)
    assert c.hp==100
    assert not any(action.kind==ActionType.HUNT for _,action,_ in nearby_options(sim))


@pytest.mark.parametrize('scale',[.85,1,1.25])
def test_real_mouse_routing_scaled_world_ui_menus_and_discrete_clicks(scale):
    sim,a,c=controlled();renderer=Renderer(window_scale=scale);ticker=FixedTicker()
    try:
        renderer.draw(sim,ticker)
        point=renderer.chicken_rects[c.id].center
        def click(pos,kind=pygame.MOUSEBUTTONDOWN):
            display=renderer.display.get_size()
            real=(round(pos[0]*display[0]/1100),round(pos[1]*display[1]/750))
            handle_event(pygame.event.Event(kind,button=1,pos=real),sim,ticker,renderer)
        click(point);assert c.hp==75
        click(point,pygame.MOUSEBUTTONUP);assert c.hp==75
        handle_event(pygame.event.Event(pygame.MOUSEMOTION,pos=point,rel=(0,0),buttons=(1,0,0)),sim,ticker,renderer)
        assert c.hp==75
        click((905,400));click((400,680));assert c.hp==75
        renderer.participant_ui.open('inventory',sim);click(point);assert c.hp==75
        renderer.participant_ui.menu=None
        renderer.history_open=True;click(point);assert c.hp==75;renderer.history_open=False
        # Control routing wins even if a stale hitbox overlaps a control.
        renderer.chicken_rects[c.id]=renderer.control_buttons['pause'].copy()
        click(renderer.control_buttons['pause'].center);assert sim.paused and c.hp==75
    finally:pygame.quit()


def test_click_far_target_shows_feedback_without_auto_move():
    sim,a,c=controlled();a.position=(8,8);renderer=Renderer()
    try:
        renderer.draw(sim,FixedTicker());before=a.position
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=renderer.chicken_rects[c.id].center),sim,FixedTicker(),renderer)
        assert c.hp==100 and a.position==before and sim.player.direction is None
        assert renderer.notification=='Too far away'
    finally:pygame.quit()


def test_health_save_roundtrip_and_legacy_compatibility():
    sim,a,c=controlled();assert sim.player_attack(c.id)
    saved=checkpoint(sim);loaded=restore(copy.deepcopy(saved))
    assert loaded.wildlife.chickens[c.id].hp==75
    old=copy.deepcopy(saved)
    for record in old['chickens']:
        record.pop('hp');record.pop('max_hp')
    old['configuration']['timing'].pop('hunger_interval_multiplier')
    assert restore(old).wildlife.chickens[c.id].hp==100
    for bad in (-1,101,True,70,0):
        invalid=copy.deepcopy(saved);invalid['chickens'][0]['hp']=bad
        with pytest.raises(ValueError):restore(invalid)


def test_animation_joints_interpolation_pause_death_and_no_sim_effects():
    sim,a,c=controlled();view=ChickenView(c);rng_before=sim.rng.getstate()
    poses=[]
    for _ in range(70):
        view.advance(.05);poses.append(view.joints(c))
    assert max(p['peck'] for p in poses)>.9
    assert min(p['breath'] for p in poses)<-.9 and max(p['breath'] for p in poses)>.9
    c.activity='walking';c.position=(5,2);view.capture(c.position,.25);view.advance(.125)
    assert view.position==(4.5,2) and view.joints(c)['walking']
    clock=view.clock;position=view.position;view.advance(5,True)
    assert view.clock==clock and view.position==position
    surface=pygame.Surface((80,90));before_draw=sim.snapshot()
    view.draw(surface,c,(40,70));assert sim.snapshot()==before_draw
    c.hp=75;view.observe(c);assert view.joints(c)['flinch']==1
    c.hp=0;c.alive=False;view.observe(c);assert view.visible
    view.advance(.81);assert not view.visible
    # Drawing has no access to simulation mutation or its RNG.
    assert sim.rng.getstate()==rng_before and a.inventory.used==0


class WaitProvider:
    name='rule-based'
    def decide(self,*args):return Action(ActionType.WAIT)


def test_hunger_three_times_slower_energy_unchanged_and_time_based():
    slow=Simulation(42,WaitProvider());old=Simulation(42,WaitProvider(),timing=replace(ActionTiming(),hunger_interval_multiplier=1))
    for sim in (slow,old):
        for a in sim.agents:a.hunger=0;a.energy=100
    for _ in range(120):slow.step();old.step()
    assert all(a.hunger==10 and a.energy==70 for a in slow.agents)
    assert all(a.hunger==30 and a.energy==70 for a in old.agents)
    fast=Simulation(42,WaitProvider());normal=Simulation(42,WaitProvider())
    f=FixedTicker();n=FixedTicker();f.speed=4
    for _ in range(40):f.advance(fast,.25);n.advance(normal,1)
    assert fast.snapshot()==normal.snapshot()
    slow.paused=True;before=slow.snapshot()
    for _ in range(20):slow.step()
    assert slow.snapshot()==before
    assert Settings.load().action_timing.hunger_interval_multiplier==3


def test_damage_survives_save_and_death_never_rewards_again():
    sim,a,c=controlled()
    for _ in range(2):assert sim.player_attack(c.id)
    loaded=restore(checkpoint(sim));loaded.paused=False
    for _ in range(2):assert loaded.player_attack(c.id)
    a=loaded.social.agents[a.id]
    assert a.inventory.quantity('raw_chicken')==1
    dead=restore(checkpoint(loaded));dead.paused=False
    assert not dead.player_attack(c.id)
    assert dead.social.agents[a.id].inventory.quantity('raw_chicken')==1
    assert len(dead.wildlife.respawns)==1


def test_click_on_hp_bar_or_transparent_corner_does_not_hit():
    sim,a,c=controlled();renderer=Renderer()
    try:
        renderer.draw(sim,FixedTicker());rect=renderer.chicken_rects[c.id]
        for point in (rect.topleft,(rect.centerx,rect.top-6)):
            handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point),sim,FixedTicker(),renderer)
        assert c.hp==100
    finally:pygame.quit()


def test_renderer_tick_interpolation_death_lifetime_and_load_reset():
    sim,a,c=controlled();renderer=Renderer();ticker=FixedTicker()
    try:
        renderer.draw(sim,ticker);c.position=(5,2)
        renderer.capture_tick(sim,.25);renderer.advance_animation(.125)
        assert renderer.chicken_views[c.id].position==(4.5,2)
        renderer.draw(sim,ticker)
        assert renderer.chicken_rects[c.id].centerx < 20+5*36+18
        # Teleport only this test fixture back into range to exercise discrete input.
        a.position=(4,2)
        for _ in range(4):assert sim.player_attack(c.id)
        renderer.sync_chickens(sim);renderer.draw(sim,ticker)
        view=renderer.chicken_views[c.id]
        assert view.visible and c.id not in renderer.chicken_rects
        renderer.advance_animation(3,paused=True);assert view.visible
        renderer.advance_animation(.81);assert not view.visible
        renderer.reset_after_load(sim);assert not renderer.chicken_views
    finally:pygame.quit()


@pytest.mark.parametrize('value',['0','-1','1.5','garbage'])
def test_invalid_hunger_multiplier_is_rejected(tmp_path,monkeypatch,value):
    monkeypatch.setenv('HUNGER_INTERVAL_MULTIPLIER',value)
    with pytest.raises(ValueError):Settings.load(tmp_path/'absent.env')


def test_speech_and_participant_hud_are_not_click_through():
    sim,a,c=controlled();renderer=Renderer();ticker=FixedTicker()
    try:
        renderer.draw(sim,ticker)
        point=renderer.chicken_rects[c.id].center
        renderer.feedback_rects=[pygame.Rect(point[0]-10,point[1]-10,20,20)]
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point),sim,ticker,renderer)
        assert c.hp==100
        renderer.feedback_rects=[]
        # Bottom-row wildlife is beneath the Participant HUD; clicks belong to UI.
        c.position=(4,17);a.position=(3,17);renderer.draw(sim,ticker)
        point=renderer.chicken_rects[c.id].center
        assert 680 <= point[1] <= 727
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point),sim,ticker,renderer)
        assert c.hp==100
    finally:pygame.quit()


def test_foreground_npc_opaque_pixels_block_chicken_clicks():
    sim,a,c=controlled();peer=sim.agents[1];peer.position=(4,3)
    renderer=Renderer();ticker=FixedTicker()
    try:
        renderer.draw(sim,ticker)
        rect=renderer.character_rects[peer.id];frame=renderer.characters[peer.id].animator.frame
        overlap=rect.clip(renderer.chicken_rects[c.id])
        points=[(x,y) for x in range(overlap.left,overlap.right) for y in range(overlap.top,overlap.bottom)
                if renderer.chicken_views[c.id].hit_test((x,y)) and frame.get_at((x-rect.x,y-rect.y)).a>0]
        assert points, 'Fixture must exercise an actual opaque sprite overlap'
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=points[0]),sim,ticker,renderer)
        assert c.hp==100
    finally:pygame.quit()


def test_observer_click_cannot_damage_chicken():
    sim,a,c=controlled();sim.set_participant();renderer=Renderer();ticker=FixedTicker()
    try:
        renderer.draw(sim,ticker)
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=renderer.chicken_rects[c.id].center),sim,ticker,renderer)
        assert c.hp==100 and a.inventory.used==0
    finally:pygame.quit()


def test_chicken_keeps_arrival_direction_when_it_stops():
    sim,a,c=controlled();view=ChickenView(c)
    c.position=(4,1);view.capture(c.position,.25)
    view.advance(.25);view.advance(.01)
    assert not view.animator.moving and view.animator.direction=='up'
    surface=pygame.Surface((80,90));view.draw(surface,c,(40,70))
    assert view.animator.direction=='up'
    # Rear-facing idle must not suddenly redraw a side-facing eye.
    assert not any(surface.get_at((x,y))[:3]==(50,45,40)
                   for x in range(80) for y in range(90))
