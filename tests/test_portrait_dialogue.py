"""Portrait presentation is tied to accepted sessions and common social execution."""
import hashlib
import json
from pathlib import Path
import pygame
import pytest
from civsandbox.actions import Action,ActionType
from civsandbox.characters import CHARACTERS
from civsandbox.dialogue import SessionState
from civsandbox.dialogue_controller import DialogueController,Line
from civsandbox.dialogue_view import DialogueView,wrap
from civsandbox.portraits import PortraitManager
from civsandbox.rendering import Renderer,handle_event,advance_frame
from civsandbox.simulation import Simulation,FixedTicker
from civsandbox.savegame import checkpoint,restore
from test_conversations import pair,until_finished
from test_participant import invited


class AnswerProvider:
    name='rule-based'
    def __init__(self,answer):self.answer=answer;self.calls=[]
    def bind_social(self,social):self.social=social
    def decide(self,actor,*args):
        self.calls.append(actor.id)
        request=next((r for r in self.social.active_requests(actor) if r.recipient_id==actor.id),None)
        return Action(self.answer,request.requester_id,request_id=request.id) if request else Action(ActionType.WAIT)


def scene(answer=ActionType.SHARE_FOOD):
    sim=Simulation(7,AnswerProvider(answer),scenario='food_shortage');sim.set_participant('npc-1')
    a,b=sim.agents[:2];a.hunger=b.hunger=30;a.food=0;b.food=3
    c=DialogueController();assert c.open(sim,b.id)[0]
    return sim,a,b,c


def settle(c,sim):
    for _ in range(40):
        if c.owner:c.advance(60,sim)
        if not c.active or c.phase=='choosing':return
        c.continue_line(sim)
    raise AssertionError('Dialogue did not become ready')


@pytest.mark.parametrize('agent_id',CHARACTERS)
def test_real_portrait_mapping_alpha_dimensions_hash_and_aspect(agent_id):
    pygame.display.init();pygame.display.set_mode((1,1))
    try:
        manager=PortraitManager();record=json.loads((manager.root/'manifest.json').read_text())[agent_id]
        assert record['name']==CHARACTERS[agent_id][0]
        assert hashlib.sha256((manager.root/record['file']).read_bytes()).hexdigest()==record['sha256']
        original=manager.original(agent_id)
        assert original.get_size()==tuple(record['size']) and original.get_flags()&pygame.SRCALPHA
        image=manager.fit(agent_id,(350,430));assert image.get_width()<=350 and image.get_height()<=430
        assert abs(image.get_width()/image.get_height()-original.get_width()/original.get_height())<.005
        assert manager.fit(agent_id,(350,430)) is image and manager.loads==1
        assert manager.original(agent_id,'happy') is original and manager.loads==1
        assert manager.original('../../secrets') is None
    finally:pygame.quit()


def test_missing_and_corrupt_assets_render_sprite_name_fallback(tmp_path):
    sim,a,b,c=scene();settle(c,sim);r=Renderer()
    try:
        (tmp_path/'ren.png').write_bytes(b'not a png')
        view=DialogueView(PortraitManager(tmp_path));surface=pygame.Surface((900,650))
        view.draw(surface,c,sim,r.assets)
        assert view.portrait_rect is None and view.portraits.original(b.id) is None
        assert view.layout['portrait'].colliderect(surface.get_rect())
        first=dict(view.portraits.originals);view.draw(surface,c,sim,r.assets)
        assert view.portraits.originals==first
    finally:c.close(sim);pygame.quit()


@pytest.mark.parametrize('size',[(640,480),(800,600),(1100,750),(1440,900)])
def test_responsive_layout_full_portrait_visible_and_text_pages(size):
    sim,a,b,c=scene();settle(c,sim);r=Renderer()
    try:
        view=DialogueView();surface=pygame.Surface(size)
        c.current=Line(b.id,'A long readable sentence about the village and its people. '*40);c.serial+=1
        view.draw(surface,c,sim,r.assets)
        assert len(view.pages)>1
        bounds=surface.get_rect()
        assert bounds.contains(view.portrait_rect) and view.portrait_rect.bottom<view.layout['panel'].top
        assert all(bounds.contains(rect) for rect,index in view.rows)
        font=view.font(max(22,round(size[1]*.037)))
        assert all(font.size(line)[0]<=view.layout['panel'].width-48 for page in view.pages for line in page)
        index=view.page;view.proceed(c,sim);assert view.complete and view.page==index
        view.proceed(c,sim);assert view.page==index+1
    finally:c.close(sim);pygame.quit()


def test_long_unbroken_words_wrap_without_overflow():
    pygame.font.init()
    try:
        font=pygame.font.Font(None,25)
        assert all(font.size(line)[0]<=80 for line in wrap('x'*500,font,80))
    finally:pygame.quit()


def test_modal_stops_faces_and_freezes_all_ordinary_world_state():
    sim,a,b,c=scene();before=(sim.tick,a.position,b.position,a.hunger,a.energy,sim.wildlife.rng.getstate(),sim.resources.stocks())
    assert sim.social.session_for(a) is sim.social.session_for(b)
    assert (a.facing,b.facing)==('right','left') and sim.input_blocked
    for _ in range(100):sim.step()
    c.advance(.1,sim)
    assert before==(sim.tick,a.position,b.position,a.hunger,a.energy,sim.wildlife.rng.getstate(),sim.resources.stocks())
    assert not a.memories  # accepted start does not pre-award even greeting trust
    settle(c,sim);assert len([m for m in a.memories if m.result=='greeted'])==1
    c.close(sim);assert not sim.input_blocked and not sim.social.active_sessions
    sim.step();assert sim.tick==before[0]+1


@pytest.mark.parametrize('answer,food,result',[(ActionType.SHARE_FOOD,(1,2),'shared one food'),(ActionType.REFUSE_REQUEST,(0,3),'refused')])
def test_requests_use_provider_validate_transfer_trust_memory_once(answer,food,result):
    sim,a,b,c=scene(answer);settle(c,sim);before=(a.food,b.food);base_trust=a.trust[b.id]
    assert c.choose('request',sim)
    assert (a.food,b.food)==before
    assert not any(turn.purpose=='shared' for turn in c.session(sim).turns)
    settle(c,sim)
    assert (a.food,b.food)==food and a.food+b.food==sum(before)
    events=[e for e in sim.events if e.get('social') and e.get('result')==result]
    assert len(events)==1 and sim.decision_provider.calls==[b.id]
    assert len([m for m in a.memories if m.result==result])==1
    assert len([m for m in b.memories if m.result==result])==1
    assert a.trust[b.id]==base_trust+events[0]['trust_changes'][a.id]
    for _ in range(20):c.advance(60,sim);c.continue_line(sim)
    assert (a.food,b.food)==food and len([m for m in a.memories if m.result==result])==1
    assert not next(x for x in c.choices(sim) if x.key=='request').enabled
    c.close(sim)


def test_offer_capacity_and_completed_outcome_only():
    sim,a,b,c=scene();settle(c,sim)
    assert not next(x for x in c.choices(sim) if x.key=='offer').enabled
    a.food=2;b.food=b.inventory.capacity
    assert not next(x for x in c.choices(sim) if x.key=='offer').enabled
    b.food=1;assert c.choose('offer',sim)
    assert (a.food,b.food)==(2,1)
    settle(c,sim);assert (a.food,b.food)==(1,2)
    assert len([e for e in sim.events if e.get('result')=='offered one food'])==1
    c.close(sim)


@pytest.mark.parametrize('mutation',['distance','incapacitated','busy','missing'])
def test_open_rejects_unavailable_targets_with_message(mutation):
    sim=Simulation(7,scenario='food_shortage');sim.set_participant('npc-1');a,b=sim.agents[:2]
    if mutation=='distance':b.position=(20,2)
    if mutation=='incapacitated':b.incapacitated_until=50
    if mutation=='busy':
        b.energy=50;assert sim.progress.execute(Action(ActionType.REST),b,sim.world,sim.resources,0,'test')
    if mutation=='missing':del sim.social.agents[b.id]
    c=DialogueController();ok,reason=c.open(sim,b.id)
    assert not ok and reason and not c.active and sim.social.modal_pair is None


def test_cancellation_before_completion_retains_food_and_locks_release():
    sim,a,b,c=scene();settle(c,sim);a.food=2
    assert c.choose('offer',sim);c.advance(.25,sim);c.close(sim,canceled=True)
    assert (a.food,b.food)==(2,3) and not sim.progress.jobs and not sim.progress.locks
    assert not sim.social.pending and sim.social.modal_pair is None
    for _ in range(30):sim.step()
    assert not any(e.get('result')=='offered one food' for e in sim.events)


@pytest.mark.parametrize('change',['move','remove','mode','collapse'])
def test_invalidated_or_disappeared_partner_safely_closes(change):
    sim,a,b,c=scene();settle(c,sim);assert c.choose('request',sim)
    if change=='move':b.position=(20,2)
    if change=='remove':del sim.social.agents[b.id]
    if change=='mode':sim.set_participant('npc-3')
    if change=='collapse':b.incapacitated_until=20
    c.advance(.1,sim)
    assert not c.active and sim.social.modal_pair is None and not sim.progress.jobs
    assert (a.food,b.food)==(0,3)


@pytest.mark.parametrize('kind',[ActionType.TALK,ActionType.OFFER_FOOD,ActionType.REQUEST_FOOD])
def test_incoming_invitation_keeps_player_consent_and_no_timeout(kind):
    sim,a,b=invited(kind);c=DialogueController();tick=sim.tick
    assert c.open_incoming(sim)
    c.advance(10000,sim)
    assert sim.tick==tick and c.active and sim.player.pending is None
    before=(a.food,b.food);c.continue_line(sim)
    assert [x.key for x in c.choices(sim)]==['accept','decline']
    assert c.choose('accept',sim);settle(c,sim)
    if kind==ActionType.OFFER_FOOD:assert (a.food,b.food)==(before[0]+1,before[1]-1)
    elif kind==ActionType.REQUEST_FOOD:
        assert c.incoming and c.incoming.request_id
        assert (a.food,b.food)==before
        assert c.choose('share',sim);settle(c,sim)
        assert (a.food,b.food)==(before[0]-1,before[1]+1)
    else:assert (a.food,b.food)==before
    c.close(sim);assert not sim.input_blocked


def test_incoming_request_can_be_refused_without_food_or_double_memory():
    sim,a,b=invited(ActionType.REQUEST_FOOD);c=DialogueController();assert c.open_incoming(sim)
    c.continue_line(sim);assert c.choose('accept',sim);settle(c,sim);before=(a.food,b.food)
    assert c.choose('refuse',sim);settle(c,sim)
    assert (a.food,b.food)==before
    assert len([m for m in a.memories if m.result=='refused'])==1
    c.close(sim)


def test_nonresponse_provider_is_not_replaced_with_a_fake_share_or_refusal():
    from test_participant import WaitingAI
    sim=Simulation(7,WaitingAI(),scenario='food_shortage');sim.set_participant('npc-1')
    c=DialogueController();assert c.open(sim,'npc-2')[0];settle(c,sim)
    before=(sim.agents[0].food,sim.agents[1].food)
    assert c.choose('request',sim);settle(c,sim)
    assert not c.active and (sim.agents[0].food,sim.agents[1].food)==before
    assert not any(e.get('result') in ('shared one food','refused') for e in sim.events)


def test_memory_disabled_never_uses_historical_trust_or_thank_choices():
    from civsandbox.social import Memory
    sim,a,b,c=scene();settle(c,sim)
    a.memories.append(Memory(0,b.id,a.id,'SHARE_FOOD','shared one food',6))
    assert any(x.key=='thank_help' for x in c.choices(sim))
    sim.social.memory_enabled=False;a.trust[b.id]=100
    assert not any(x.key=='thank_help' for x in c.choices(sim))
    assert sim.social.trust_for(a,b.id)==0
    c.close(sim)


def test_npc_to_npc_sessions_keep_existing_world_flow_no_portrait_modal():
    sim,a,b=pair();r=Renderer()
    try:
        sim.step();r.draw(sim,FixedTicker())
        assert not r.dialogue.active and sim.social.modal_pair is None
        until_finished(sim)
        assert any(e['action']=='DIALOGUE' for e in sim.events)
        assert any(m.result=='greeted' for m in a.memories)
    finally:sim.close();pygame.quit()


def test_modal_ui_keyboard_mouse_priority_and_manual_reveal():
    sim,a,b,c=scene();r=Renderer();r.dialogue=c;t=FixedTicker()
    try:
        r.draw(sim,t);before=a.position
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_w),sim,t,r)
        assert a.position==before and sim.player.direction is None
        assert not r.dialogue_view.complete
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN),sim,t,r)
        assert r.dialogue_view.complete
        advance_frame(r,t,sim,30)
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN),sim,t,r)
        r.draw(sim,t);assert c.phase=='choosing' and r.dialogue_view.rows
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_DOWN),sim,t,r)
        assert r.dialogue_view.selected==1
        assert c.owner is None
        rect,index=r.dialogue_view.rows[0]
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=rect.center),sim,t,r)
        assert c.owner==a.id
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE),sim,t,r)
        assert not c.active and not sim.input_blocked
    finally:sim.close();pygame.quit()


def test_save_load_does_not_resume_unfinished_dialogue_or_duplicate_food():
    sim,a,b,c=scene();settle(c,sim);assert c.choose('request',sim)
    saved=restore(checkpoint(sim))
    assert saved.social.modal_pair is None and not saved.social.active_sessions and not saved.progress.jobs
    assert (saved.agents[0].food,saved.agents[1].food)==(0,3)
    c.close(sim,canceled=True)


def test_two_ui_sessions_cannot_overlap_and_topics_do_not_farm_greeting_trust():
    sim,a,b,c=scene();settle(c,sim);session=c.session_id;trust=a.trust[b.id]
    assert not c.open(sim,'npc-3')[0] and c.session_id==session
    for topic in ('smalltalk','how','smalltalk'):
        assert c.choose(topic,sim);settle(c,sim)
    assert a.trust[b.id]==trust
    assert len([m for m in a.memories if m.result=='greeted'])==1
    c.close(sim);assert c.open(sim,b.id)[0];settle(c,sim)
    assert a.trust[b.id]==trust
    c.close(sim)


def test_background_social_jobs_and_clock_do_not_advance_during_modal():
    sim=Simulation(7,scenario='food_shortage');sim.set_participant('npc-1')
    third,fourth=sim.agents[2:]
    assert sim.progress.execute(Action(ActionType.TALK,fourth.id),third,sim.world,sim.resources,0,'rule-based')
    background=sim.social.session_for(third);job=sim.progress.jobs[third.id]
    before=(third.position,fourth.position,third.hunger,fourth.energy,len(background.turns),background.current_turn,job.finish_tick,sim.social.tick)
    c=DialogueController();assert c.open(sim,'npc-2')[0];c.advance(100,sim)
    assert (third.position,fourth.position,third.hunger,fourth.energy,len(background.turns),background.current_turn,job.finish_tick,sim.social.tick)==before
    assert sim.progress.jobs[third.id] is job
    c.close(sim)
    for _ in range(100):sim.step()
    assert background.state==SessionState.COMPLETED


@pytest.mark.parametrize('scale',[.85,1,1.25])
def test_scaled_dialogue_mouse_choice_routes_once_without_world_input(scale):
    sim,a,b,c=scene();settle(c,sim);r=Renderer(window_scale=scale);r.dialogue=c;t=FixedTicker()
    try:
        r.draw(sim,t);r.dialogue_view.shown=float('inf')
        row,index=next((rect,i) for rect,i in r.dialogue_view.rows if i==3)
        width,height=r.display.get_size();pos=(round(row.centerx*width/1100),round(row.centery*height/750))
        before=a.position
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=pos),sim,t,r)
        assert c.owner==a.id and sim.tick==0 and a.position==before and sim.player.direction is None
        assert len(sim.progress.jobs)==1
    finally:c.close(sim,canceled=True);pygame.quit()


def test_final_revalidation_rejects_capacity_change_without_success_line():
    sim,a,b,c=scene();settle(c,sim);a.food=2;b.food=1
    assert c.choose('offer',sim);b.food=b.inventory.capacity;c.advance(100,sim)
    assert not c.active and (a.food,b.food)==(2,5)
    assert any(e['action']=='REJECTED' and 'full' in e['reason'] for e in sim.events)
    assert not any(e.get('result')=='offered one food' for e in sim.events)


def test_request_provider_exception_safely_cancels_without_invented_refusal():
    sim,a,b,c=scene();settle(c,sim)
    def fail(*args):raise OSError('offline failure')
    sim.decision_provider.decide=fail
    assert c.choose('request',sim);settle(c,sim)
    assert not c.active and (a.food,b.food)==(0,3)
    assert not any(e.get('result') in ('refused','shared one food') for e in sim.events)


def test_missing_partner_during_pending_request_releases_all_claims():
    sim,a,b,c=scene();settle(c,sim);assert c.choose('request',sim)
    c.advance(100,sim);assert sim.social.pending and c.owner==b.id
    del sim.social.agents[b.id];c.advance(.1,sim)
    assert not c.active and not sim.social.pending and not sim.progress.jobs and not sim.progress.locks
    assert a.food==0


def test_idle_frames_continue_for_both_participants_without_logical_motion():
    sim,a,b,c=scene();r=Renderer();r.dialogue=c;t=FixedTicker()
    try:
        r.sync_characters(sim);r.draw(sim,t)
        before=(a.position,b.position,sim.tick);indices={a.id:set(),b.id:set()}
        for _ in range(60):
            advance_frame(r,t,sim,1/60);r.draw(sim,t)
            for actor in (a,b):
                animator=r.characters[actor.id].animator
                assert animator.state=='idle' and animator.direction==actor.facing
                indices[actor.id].add(animator.index)
        assert all(len(values)==4 for values in indices.values())
        assert before==(a.position,b.position,sim.tick)
    finally:c.close(sim,canceled=True);pygame.quit()


def test_memory_off_greeting_ignores_accumulated_trust():
    texts=[]
    for trust in (-100,100):
        sim=Simulation(7,memory_enabled=False,scenario='food_shortage');sim.set_participant('npc-1')
        sim.agents[1].trust['npc-1']=trust
        c=DialogueController();assert c.open(sim,'npc-2')[0]
        texts.append(c.current.text);c.close(sim,canceled=True)
    assert texts[0]==texts[1]


def test_repeated_render_does_not_consume_rng_or_reload_portraits():
    sim,a,b,c=scene();r=Renderer();r.dialogue=c
    try:
        r.draw(sim,FixedTicker());rng=sim.social.dialogue_rng.getstate();loads=r.dialogue_view.portraits.loads
        for _ in range(20):r.draw(sim,FixedTicker())
        assert sim.social.dialogue_rng.getstate()==rng and r.dialogue_view.portraits.loads==loads==1
    finally:c.close(sim,canceled=True);pygame.quit()


def test_portrait_turns_stay_in_history_without_replaying_as_world_bubbles():
    from civsandbox.feedback import Feedback
    sim,a,b,c=scene();settle(c,sim)
    feedback=Feedback();feedback.consume(sim.events,sim.social)
    assert feedback.history and feedback.current_dialogue is None and not feedback.dialogue_queue
    assert len(sim.history.conversations)==len([e for e in sim.events if e['action']=='DIALOGUE'])
    c.close(sim)


def test_long_name_has_safe_nameplate_without_clipping():
    sim,a,b,c=scene();b.name='A very long villager name '*20;r=Renderer()
    try:
        view=DialogueView();view.draw(pygame.Surface((640,480)),c,sim,r.assets)
        assert view.displayed_name.endswith('...')
    finally:c.close(sim,canceled=True);pygame.quit()


def test_expired_incoming_request_cannot_open_or_transfer_food():
    sim,a,b=invited(ActionType.REQUEST_FOOD)
    assert sim.player.answer(sim,True)
    for _ in range(100):
        sim.step()
        if sim.player.pending and sim.player.pending.request_id:break
    assert sim.player.pending.request_id
    request=next(iter(sim.social.pending.values()));sim.social.tick=request.expires_tick
    c=DialogueController();before=(a.food,b.food)
    assert not c.open_incoming(sim) and not c.active
    assert (a.food,b.food)==before and not sim.social.pending


def test_real_rule_provider_can_share_and_refuse_without_character_scripts():
    outcomes=set()
    for seed in range(1,13):
        sim=Simulation(seed,scenario='food_shortage');sim.set_participant('npc-2')
        player=sim.agents[1];donor=sim.agents[0]
        player.food=0;donor.food=3;donor.hunger=25
        c=DialogueController();assert c.open(sim,donor.id)[0];settle(c,sim)
        assert c.choose('request',sim);settle(c,sim)
        results=[e['result'] for e in sim.events if e.get('social') and e['action'] in ('SHARE_FOOD','REFUSE_REQUEST')]
        outcomes.update(results)
        assert player.food+donor.food==3
        c.close(sim);sim.close()
    assert outcomes=={'shared one food','refused'}


def test_invalid_social_targets_still_fail_safely_at_common_scheduler():
    sim=Simulation(7)
    for action in (None,Action(ActionType.TALK,{}),Action(ActionType.REQUEST_FOOD,[])):
        assert not sim.progress.execute(action,sim.agents[0],sim.world,sim.resources,0,'test')


def test_other_accepted_job_cannot_be_completed_by_stale_dialogue_driver():
    sim,a,b,c=scene();settle(c,sim);assert c.choose('offer',sim) is False
    a.food=2;assert c.choose('offer',sim)
    sim.progress.cancel_for(a.id)
    # Replace an interrupted UI job externally; the driver must never finish it.
    a.energy=50
    assert sim.progress.execute(Action(ActionType.REST),a,sim.world,sim.resources,0,'test')
    job=sim.progress.jobs[a.id]
    c.advance(100,sim)
    assert not c.active and (a.food,b.food)==(2,3) and a.energy==50
    assert sim.progress.jobs[a.id] is job


def test_long_modal_visit_is_bounded_without_discarding_unread_turns():
    sim,a,b,c=scene();settle(c,sim)
    for _ in range(80):
        if [x.key for x in c.choices(sim)]==['goodbye']:break
        assert c.choose('smalltalk',sim);settle(c,sim)
    assert [x.key for x in c.choices(sim)]==['goodbye']
    assert len(c.session(sim).turns)<=64
    assert all(t.delivered for t in c.session(sim).turns) and not c.queue
    assert c.active and a.trust[b.id]==1
    c.close(sim)


def test_small_window_keyboard_scroll_keeps_highlighted_choice_visible():
    from civsandbox.social import Memory
    sim,a,b,c=scene();settle(c,sim);b.hunger=60
    a.memories.append(Memory(0,b.id,a.id,'SHARE_FOOD','shared one food',6))
    r=Renderer();view=DialogueView();screen=pygame.Surface((640,480))
    try:
        view.draw(screen,c,sim,r.assets);view.shown=float('inf')
        for _ in range(6):
            view.handle(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_DOWN),c,sim)
            view.draw(screen,c,sim,r.assets)
        assert view.selected==6 and view.scroll>0
        assert any(index==view.selected for rect,index in view.rows)
    finally:c.close(sim);pygame.quit()


def test_second_controller_cannot_take_over_an_existing_modal_lease():
    sim,a,b,c=scene();settle(c,sim);session=c.session_id
    other=DialogueController();ok,reason=other.open(sim,b.id)
    assert not ok and reason and not other.active
    assert c.active and c.session_id==session and sim.social.session_for(a).id==session
    c.close(sim)


def test_visible_leave_button_cancels_before_transfer_even_while_text_types():
    sim,a,b,c=scene();settle(c,sim);a.food=2;b.food=1
    assert c.choose('offer',sim)
    r=Renderer();r.dialogue=c;t=FixedTicker()
    try:
        r.draw(sim,t);assert not r.dialogue_view.complete
        rect=r.dialogue_view.layout['close']
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=rect.center),sim,t,r)
        assert not c.active and (a.food,b.food)==(2,1) and not sim.progress.jobs
    finally:sim.close();pygame.quit()


def test_actual_world_click_opens_nearby_npc_and_explains_out_of_range():
    sim=Simulation(7,scenario='food_shortage');sim.set_participant('npc-1');r=Renderer();t=FixedTicker()
    try:
        before=[a.position for a in sim.agents];r.draw(sim,t)
        point=r.character_rects['npc-2'].center
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point),sim,t,r)
        assert r.dialogue.active and r.dialogue.peer_id=='npc-2' and r.dialogue.current.speaker_id=='npc-2'
        assert [a.position for a in sim.agents]==before
        r.dialogue.close(sim);r.draw(sim,t)
        point=r.character_rects['npc-3'].center
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point),sim,t,r)
        assert not r.dialogue.active and 'closer' in r.notification
        assert [a.position for a in sim.agents]==before
    finally:sim.close();pygame.quit()


def test_incoming_offer_acceptance_is_disabled_if_inventory_becomes_full():
    sim,a,b=invited(ActionType.OFFER_FOOD);c=DialogueController();assert c.open_incoming(sim)
    a.food=a.inventory.capacity;c.continue_line(sim)
    accept=next(x for x in c.choices(sim) if x.key=='accept')
    assert not accept.enabled and 'room' in accept.reason
    assert not c.choose('accept',sim)
    before=(a.food,b.food);assert c.choose('decline',sim)
    assert not c.active and (a.food,b.food)==before
