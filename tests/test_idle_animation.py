"""Idle additions preserve movement, social state, timing, and walking assets."""
import hashlib
import json
import shutil
from pathlib import Path
import pygame
import pytest
from PIL import Image
from civsandbox.animation import SpriteAnimator, CharacterView, DIRECTIONS
from civsandbox.sprites import ASSET_ROOT, CharacterAssets, FRAME_SIZE
from civsandbox.characters import CHARACTERS
from civsandbox.prepare_idle_assets import extract_idle, clean_idle_cell
from civsandbox.rendering import Renderer, advance_frame, handle_event
from civsandbox.simulation import Simulation, FixedTicker
from test_conversations import pair


def animated():
    return SpriteAnimator({d:[f'{d}-walk-{i}' for i in range(5)] for d in DIRECTIONS},
                          idle_frames={d:[f'{d}-idle-{i}' for i in range(4)] for d in DIRECTIONS})

@pytest.mark.parametrize('direction',DIRECTIONS)
def test_directional_idle_progresses_loops_and_keeps_facing(direction):
    a=animated();a.update(0,False,direction)
    for i in range(8):
        assert a.frame==f'{direction}-idle-{i%4}'
        a.update(.25,False)
    assert a.direction==direction and a.state=='idle'


def test_transitions_reset_only_when_state_or_direction_changes():
    a=animated();a.update(.5,False,'left');assert a.index==2
    a.update(0,False,'left');assert a.index==2
    a.update(0,True);assert a.index==1 and a.state=='walk'
    a.update(.125,True);assert a.index==2
    a.update(0,False);assert a.index==0 and a.direction=='left'
    a.update(.25,False);assert a.index==1
    a.update(0,False,'right');assert a.index==0


def test_idle_dt_independence_of_render_rate_and_tick_capture():
    views=[CharacterView((2,2),animated()) for _ in range(2)]
    for view,hz in zip(views,(30,120)):
        for i in range(hz):
            view.capture((2,2),.25)  # even repeated logical observations cannot restart idle
            view.advance(1/hz)
        assert view.animator.index==0
        assert view.position==(2,2)
        view.advance(.375)
        assert view.animator.index==1
    assert views[0].animator.frame==views[1].animator.frame


def test_visual_arrival_precedes_idle_and_social_facing():
    view=CharacterView((1,1),animated());view.capture((2,1),.25)
    view.idle_direction='up'
    view.advance(.125)
    assert view.position==(1.5,1) and view.animator.moving and view.animator.direction=='right'
    view.advance(.125)
    assert view.position==(2,1) and view.animator.state=='idle' and view.animator.direction=='up'
    view.advance(.25)
    assert view.position==(2,1) and view.animator.index==1


def test_real_assets_counts_identity_scale_anchor_and_original_integrity():
    report=json.loads((ASSET_ROOT/'inspection/idle-frames.json').read_text())
    for _,key in CHARACTERS.values():
        info=report[key]
        assert info['character']==key and info['counts']=={d:4 for d in DIRECTIONS}
        assert hashlib.sha256((ASSET_ROOT/'characters'/f'{key}_idle.png').read_bytes()).hexdigest()==info['sha256']
        for d in DIRECTIONS:
            sizes=[]
            for i in range(4):
                im=Image.open(ASSET_ROOT/'processed'/key/'idle'/d/f'{i}.png')
                assert im.size==(160,200) and im.mode=='RGBA'
                bounds=im.getbbox()
                assert bounds[3]==190
                assert im.getpixel((0,0))[3]==0
                sizes.append(bounds[3]-bounds[1])
            assert max(sizes)-min(sizes)<=10
    # Walking original and processed checks remain covered by test_animation.py.


def test_optional_loader_fallback_and_cached_mapping(tmp_path,caplog):
    shutil.copytree(ASSET_ROOT/'processed',tmp_path/'processed')
    shutil.rmtree(tmp_path/'processed'/'ren'/'idle')
    # Partial/corrupt optional set also falls back as one unit.
    (tmp_path/'processed'/'nyra'/'idle'/'left'/'2.png').unlink()
    pygame.display.init();pygame.display.set_mode((1,1))
    try:
        with caplog.at_level('DEBUG',logger='civsandbox.sprites'):
            assets=CharacterAssets(tmp_path)
        assert len([r for r in caplog.records if 'Optional idle' in r.message])==2
        for key in ('ren','nyra'):
            for d in DIRECTIONS:
                assert assets.idle_frames[key][d]==[assets.frames[key][d][0]]
        sim=Simulation()
        try:
            for a in sim.agents:
                key=CHARACTERS[a.id][1]
                idle=assets.idle_for_agent(a)
                assert idle is assets.idle_for_agent(a) and idle is assets.idle_frames[key]
                assert len(idle['down'])==(1 if key in ('ren','nyra') else 4)
                assert all(f.get_size()==FRAME_SIZE for frames in idle.values() for f in frames)
        finally: sim.close()
    finally: pygame.quit()


def test_static_fallback_and_validation():
    a=SpriteAnimator({d:list(range(5)) for d in DIRECTIONS})
    a.update(300,False,'up');assert a.frame==0 and a.index==0
    for fps in (0,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError): SpriteAnimator(a.frames,idle_fps=fps)
    with pytest.raises(ValueError): SpriteAnimator(a.frames,idle_frames={})
    with pytest.raises(ValueError): extract_idle(Image.new('RGBA',(100,100)),0)


def test_ren_cleanup_retains_enclosed_white_and_alpha():
    im=Image.new('RGBA',(20,20),(250,250,250,210))
    for x in range(5,15):
        for y in range(5,15):im.putpixel((x,y),(20,10,5,250))
    im.putpixel((9,9),(255,255,255,249))
    out=clean_idle_cell(im,True)
    assert out.getpixel((0,0))[3]==0
    assert out.getpixel((9,9))==(255,255,255,249)


def test_idle_timing_not_simulation_speed_or_pause():
    for speed in (1,2,4):
        view=CharacterView((0,0),animated())
        view.advance(.375*speed,speed=speed)
        assert view.animator.index==1
        before=view.animator.elapsed
        view.advance(10,paused=True,speed=speed)
        assert view.animator.elapsed==before


def test_conversation_faces_idle_without_changing_dialogue_or_positions():
    sim,a,b=pair();repeat,_,_=pair();renderer=Renderer()
    try:
        renderer.sync_characters(sim)
        for _ in range(20):
            sim.step();repeat.step();renderer.capture_tick(sim,.25)
            if any(e['action']=='DIALOGUE' for e in sim.events):
                break
        session=sim.social.session_for(a)
        assert session and sim.social.session_for(b) is session
        before=sim.snapshot();positions=(a.position,b.position)
        seen={a.id:set(),b.id:set()}
        for _ in range(60):
            renderer.advance_animation(1/60)
            for agent,d in ((a,'right'),(b,'left')):
                animator=renderer.characters[agent.id].animator
                assert animator.state=='idle' and animator.direction==d
                seen[agent.id].add(animator.index)
            renderer.draw(sim,FixedTicker())
        assert all(values=={0,1,2,3} for values in seen.values())
        assert sim.snapshot()==before and sim.social.session_for(a) is session
        assert (a.position,b.position)==positions
        assert renderer.feedback.speech_notice() is not None
        for _ in range(80):
            sim.step();repeat.step();renderer.capture_tick(sim,.25);renderer.advance_animation(.25)
        assert sim.snapshot()==repeat.snapshot()
        assert any(e['action']=='DIALOGUE' for e in sim.events)
    finally:sim.close();repeat.close();pygame.quit()


def test_preview_uses_existing_renderer_and_does_not_write_simulation():
    sim=Simulation();r=Renderer();ticker=FixedTicker()
    try:
        r.sync_characters(sim);before=sim.snapshot()
        for key in (pygame.K_F8,pygame.K_3,pygame.K_b):
            assert handle_event(pygame.event.Event(pygame.KEYDOWN,key=key),sim,ticker,r)
        assert r.animation_preview and r.preview_character==2
        r.advance_animation(.25);r.draw(sim,ticker)
        assert sim.snapshot()==before
        for key in ('mira','nyra','kairo','ren'):
            for direction in DIRECTIONS:
                a=r.preview_animators[key][direction]
                assert a.direction==direction
    finally:sim.close();pygame.quit()


@pytest.mark.parametrize('hz',[4,30,120])
def test_idle_render_time_not_lost_at_fixed_tick_boundaries(hz):
    from civsandbox.actions import Action, ActionType
    class Waiting:
        def decide(self,*args): return Action(ActionType.WAIT)
    sim=Simulation(decision_provider=Waiting());r=Renderer();ticker=FixedTicker()
    try:
        r.sync_characters(sim)
        view=r.characters['npc-1']
        for _ in range(hz): advance_frame(r,ticker,sim,1/hz)
        assert view.animator.elapsed==pytest.approx(1)
        assert view.animator.index==0
        assert not view.animator.moving and view.position==(2,2)
    finally:sim.close();pygame.quit()
