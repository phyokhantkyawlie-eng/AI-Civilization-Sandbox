import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from civsandbox.feedback import Feedback
from civsandbox.simulation import Simulation
from civsandbox.actions import Action, ActionType


def event(number=1, **kwargs):
    return dict(event_id=number, actor_id="npc-1", action="TALK", executed=True,
                changed=True, decision_source="rule-based", **kwargs)


def test_only_committed_actions_show_and_expire_without_replay():
    f = Feedback()
    f.consume([dict(event_id=1, actor_id="npc-1", action="TALK")])
    assert not f.notices
    f.consume([event(2)])
    assert "Rule-based template" in f.notices["npc-1"].speech
    f.advance(3)
    f.consume([event(2)])
    assert not f.notices


def test_actual_gemini_reason_is_attributed_and_reactions_are_event_based():
    f = Feedback()
    e = event(public_reason="There is spare food.")
    e["decision_source"] = "gemini"
    f.consume([e, dict(event_id=2, actor_id="npc-1", target_id="npc-2",
                       action="REQUEST_FOOD", social=True, result="pending")])
    assert f.notices["npc-1"].speech == "Gemini explanation: There is spare food."
    assert f.notices[("npc-2", "reaction")].reaction == "Surprised"
    assert f.sprite_state(f.state_for("npc-1", False)) == "idle"
    assert f.sprite_state(f.state_for("npc-1", True)) == "walk"


def test_all_missing_animation_sets_use_idle():
    f = Feedback()
    for state in ("gather", "eat", "rest", "talk", "share", "idle"):
        assert f.sprite_state(state) == "idle"


def test_trimmed_history_ids_are_stable_and_rejected_social_has_no_speech():
    class Invalid:
        def decide(self, *args):
            return Action(ActionType.TALK, "not-real")
    s = Simulation(decision_provider=Invalid(), event_limit=8)
    f = Feedback()
    for _ in range(20):
        s.step()
        f.consume(s.events)
    assert not f.notices
    ids = [e["event_id"] for e in s.events]
    assert ids == sorted(set(ids))


def test_bubble_layout_stays_inside_map_and_avoids_overlap():
    import pygame
    from civsandbox.rendering import Renderer
    s = Simulation()
    try:
        r = Renderer()
        s.agents[0].position = s.agents[1].position = (0, 0)
        r.draw(s, __import__("civsandbox.simulation", fromlist=["FixedTicker"]).FixedTicker())
        events = [event()]
        e = event(2)
        e["actor_id"] = "npc-2"
        events.append(e)
        r.feedback.consume(events)
        r.draw_feedback()
        bounds = pygame.Rect(20, 78, 864, 648)
        assert len(r.feedback_rects) == 2
        assert all(bounds.contains(rect) for rect in r.feedback_rects)
        assert not r.feedback_rects[0].colliderect(r.feedback_rects[1])
    finally:
        s.close()
        pygame.quit()
