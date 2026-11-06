"""Human-readable HUD, bounded truthful histories and in-game checkpoint controls."""
import pygame
import pytest

from civsandbox.actions import Action,ActionType
from civsandbox.history import History,WORLD_LIMIT,CONVERSATION_LIMIT
from civsandbox.simulation import Simulation,FixedTicker
from civsandbox.ui_state import hunger_status,energy_status,inventory_lines,goal_label,relationship_summary,unavailable_reason
from civsandbox.rendering import Renderer,handle_event


@pytest.mark.parametrize('value,expected',[(0,'Well fed'),(54,'Well fed'),(55,'Hungry'),(85,'Starving')])
def test_hud_hunger_words_follow_authoritative_definition(value,expected):
    assert hunger_status(value)[0]==expected


@pytest.mark.parametrize('value,expected',[(0,'Exhausted'),(20,'Tired'),(31,'Rested'),(100,'Rested')])
def test_hud_energy_words(value,expected):
    assert energy_status(value)[0]==expected


def test_inventory_goal_and_relationship_summary_are_live_and_guarded():
    sim=Simulation();actor,peer=sim.agents[:2]
    assert inventory_lines(actor)==['Empty']
    actor.inventory.add('raw_chicken')
    assert inventory_lines(actor)==['Raw chicken x 1']
    actor.inventory.convert('raw_chicken','cooked_chicken')
    assert inventory_lines(actor)==['Cooked chicken x 1']
    actor.trust[peer.id]=10
    assert peer.name in relationship_summary(actor,sim.social)
    sim.social.memory_enabled=False
    assert relationship_summary(actor,sim.social)=='History unavailable'
    sim.set_participant(actor.id)
    assert goal_label(actor,sim)=='Choose an action'


def test_history_only_reports_committed_work_and_keeps_count_timestamp():
    sim=Simulation();history=History()
    history.consume([dict(event_id=1,tick=1,actor_id='npc-1',action='ACTIVITY',accepted_start=True)],sim.clock,sim.social)
    assert not history.world
    events=[dict(event_id=i,tick=i,actor_id='npc-1',action='GATHER',executed=True) for i in (2,3)]
    history.consume(events,sim.clock,sim.social)
    assert len(history.world)==1 and history.world[0]['count']==2
    assert history.world[0]['timestamp'].startswith('Day 1 ')
    history.consume(events,sim.clock,sim.social)
    assert history.world[0]['count']==2
    history.consume([dict(event_id=4,tick=4,actor_id='npc-1',action='DIALOGUE',turn=0,session_id='fake',text='Not accepted')],sim.clock,sim.social)
    assert not history.conversations


def test_history_retention_is_bounded_and_social_turns_have_separate_channel():
    from test_conversations import pair,until_finished
    sim,a,b=pair();until_finished(sim)
    assert len(sim.history.conversations)==2
    assert not any('Good to see' in row['text'] for row in sim.history.world)
    for i in range(500):
        sim.history.world.append({'tick':i})
        sim.history.conversations.append({'tick':i})
    assert len(sim.history.world)==WORLD_LIMIT and len(sim.history.conversations)==CONVERSATION_LIMIT


def test_unavailable_actions_explain_actual_blocker():
    sim=Simulation();a=sim.agents[0]
    assert 'raw chicken' in unavailable_reason(Action(ActionType.COOK,sim.cooking_station.id),a,sim)
    bush=next(iter(sim.resources.bushes.values()));bush.quantity=0
    assert 'depleted' in unavailable_reason(Action(ActionType.GATHER,bush.position),a,sim)
    a.food=5
    assert 'full' in unavailable_reason(Action(ActionType.GATHER,bush.position),a,sim)
    assert 'Raw chicken' in unavailable_reason(Action(ActionType.EAT,item='raw_chicken'),a,sim)


def test_save_load_help_news_and_conversation_controls(tmp_path):
    sim=Simulation(42);sim.set_participant('npc-1');r=Renderer();ticker=FixedTicker()
    sim.save_path=tmp_path/'world.json'
    key=lambda value:pygame.event.Event(pygame.KEYDOWN,key=value)
    try:
        r.draw(sim,ticker)
        assert {'pause','slower','faster','save','load','help'}<=set(r.control_buttons)
        handle_event(key(pygame.K_F1),sim,ticker,r);r.draw(sim,ticker)
        assert r.participant_ui.menu=='help'
        handle_event(key(pygame.K_ESCAPE),sim,ticker,r)
        sim.agents[0].food=2
        handle_event(key(pygame.K_F5),sim,ticker,r)
        assert sim.save_path.exists() and 'saved' in r.notification
        sim.agents[0].food=0
        handle_event(key(pygame.K_F9),sim,ticker,r);r.draw(sim,ticker)
        assert r.participant_ui.menu=='load'
        handle_event(key(pygame.K_1),sim,ticker,r)
        assert sim.player.agent_id=='npc-1' and sim.agents[0].food==2 and sim.paused
        assert r.feedback.current_dialogue is None
        r.draw(sim,ticker)
        handle_event(key(pygame.K_n),sim,ticker,r);r.draw(sim,ticker)
        assert r.world_history_open and not r.history_open
        handle_event(key(pygame.K_c),sim,ticker,r);r.draw(sim,ticker)
        assert r.history_open and not r.world_history_open
    finally:
        sim.close();pygame.quit()


def test_failed_ui_load_preserves_running_game(tmp_path):
    sim=Simulation(42);r=Renderer();t=FixedTicker();sim.save_path=tmp_path/'bad.json'
    sim.save_path.write_text('{bad')
    try:
        before=sim.snapshot()
        r.participant_ui.choose('load',sim,r)
        assert sim.snapshot()==before and 'preserved' in r.notification
    finally:sim.close();pygame.quit()


def test_bush_berry_dots_match_real_stock_without_geometry_changes(monkeypatch):
    sim=Simulation();r=Renderer();bush=next(iter(sim.resources.bushes.values()))
    world=sim.world.tiles;dots=[];original=pygame.draw.circle
    def capture(surface,color,*args,**kwargs):
        if color==(161,57,91):dots.append(args)
        return original(surface,color,*args,**kwargs)
    try:
        monkeypatch.setattr(pygame.draw,'circle',capture)
        from civsandbox.world import Tile
        for stock in (0,1,3,5):
            dots.clear();bush.quantity=stock
            r.draw_feature(Tile.BUSH,pygame.Rect(200,200,36,36),sim,bush.position)
            assert len(dots)==stock
        assert sim.world.tiles is world
    finally:sim.close();pygame.quit()


def test_loaded_facing_and_existing_idle_art_are_used(tmp_path):
    from civsandbox.savegame import save_game,load_game
    sim=Simulation();sim.agents[0].facing='left'
    path=tmp_path/'world.json';save_game(sim,path);loaded=load_game(path)
    r=Renderer()
    try:
        r.draw(loaded,FixedTicker())
        view=r.characters['npc-1']
        assert view.animator.direction=='left' and not view.animator.moving
        assert r.assets.idle_for_agent(loaded.agents[0])['left'][0] is view.animator.frame
    finally:loaded.close();pygame.quit()


def test_paused_context_does_not_recalculate_paths_every_frame(monkeypatch):
    from test_participant import controlled
    sim,a,_=controlled();r=Renderer();t=FixedTicker()
    from civsandbox.world import World
    try:
        chicken=sim.wildlife.living()[0]
        a.position=sim.world.neighbors(chicken.position)[0]
        r.participant_ui.open('context',sim)
        calls=[]
        original=World.path
        def capture(self,*args):
            calls.append(args)
            return original(self,*args)
        monkeypatch.setattr(World,'path',capture)
        for _ in range(3):r.draw(sim,t)
        assert not calls
    finally:sim.close();pygame.quit()


@pytest.mark.parametrize('scale',[.85,1.25])
def test_window_scaling_preserves_logical_layout_and_mouse_targets(scale):
    sim=Simulation();r=Renderer(window_scale=scale);t=FixedTicker()
    try:
        r.draw(sim,t)
        assert r.screen.get_size()==(1100,750)
        assert r.display.get_size()==(round(1100*scale),round(750*scale))
        rect=r.control_buttons['help']
        x,y=rect.center;w,h=r.display.get_size()
        event=pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(round(x*w/1100),round(y*h/750)))
        handle_event(event,sim,t,r)
        assert r.participant_ui.menu=='help'
        r.draw(sim,t)
        assert len(r.participant_ui.buttons)==1
    finally:sim.close();pygame.quit()
