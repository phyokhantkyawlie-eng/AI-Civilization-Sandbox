"""Local feedback placement and goal-time hunting variation; no network or new art."""
import random
from collections import Counter

import pygame
import pytest

from civsandbox.actions import ActionType
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.feedback import Notice
from civsandbox.rendering import Renderer
from civsandbox.simulation import Simulation, FixedTicker


@pytest.fixture
def display():
    sim = Simulation(42)
    renderer = Renderer()
    sim.agents[0].position = (5, 5)
    renderer.draw(sim, FixedTicker())
    yield sim, renderer
    sim.close()
    pygame.quit()


def activity(renderer, actor):
    renderer.feedback.notices[actor.id] = Notice(actor.id, 'Gathering', '', '', 'gather', 3)


def test_activity_anchor_uses_this_frames_interpolated_position(display, monkeypatch):
    sim, renderer = display
    actor = sim.agents[0]
    activity(renderer, actor)
    renderer.draw(sim, FixedTicker())
    first = renderer.feedback_cards[actor.id].copy()
    # Fractional render coordinates differ from the authoritative integer tile.
    renderer.characters[actor.id].position = (5.5, 5.25)
    lines = []
    monkeypatch.setattr(pygame.draw, 'line', lambda *args, **kwargs: lines.append(args))
    renderer.character_rects[actor.id].move_ip(18, 9)
    renderer.draw_feedback()
    second = renderer.feedback_cards[actor.id]
    assert (second.x-first.x, second.y-first.y) == (18, 9)
    assert actor.position == (5, 5)
    assert not lines  # No connectors, short or long.
    # A full frame derives the same position from CharacterView rather than a cached card.
    renderer.draw(sim, FixedTicker())
    assert renderer.feedback_cards[actor.id] == second


def test_activity_hidden_during_movement_and_outside_viewport(display):
    sim, renderer = display
    actor = sim.agents[0]
    activity(renderer, actor)
    renderer.characters[actor.id].animator.update(0, True, 'right')
    renderer.draw_feedback()
    assert actor.id not in renderer.feedback_cards
    renderer.characters[actor.id].animator.update(0, False)
    renderer.character_rects[actor.id].move_ip(-2000, 0)
    renderer.draw_feedback()
    assert actor.id not in renderer.feedback_cards


def test_expired_activity_and_canceled_activity_do_not_linger(display):
    sim, renderer = display
    actor = sim.agents[0]
    activity(renderer, actor)
    renderer.feedback.clock = 3
    renderer.draw_feedback()
    assert not renderer.feedback_cards
    renderer.feedback.clock = 0
    activity(renderer, actor)
    renderer.feedback.consume([dict(event_id=1, actor_id=actor.id, action='WAIT', executed=True)])
    assert actor.id not in renderer.feedback.notices


def test_crowding_hides_secondary_label_without_distant_relocation(display):
    sim, renderer = display
    a, b = sim.agents[:2]
    b.position = a.position
    activity(renderer, a)
    activity(renderer, b)
    renderer.draw(sim, FixedTicker())
    assert len(renderer.feedback_cards) == 1
    for key, card in renderer.feedback_cards.items():
        anchor = renderer.character_rects[key]
        assert abs(card.centerx-anchor.centerx) <= 1
        assert anchor.top-card.bottom == 18
        assert renderer.map_rect.contains(card)


def test_speech_requires_current_nearby_engaged_session():
    from test_conversations import pair
    sim, a, b = pair()
    renderer = Renderer()
    try:
        sim.step()
        renderer.draw(sim, FixedTicker())
        assert renderer.feedback.speech_notice() is not None
        activity(renderer, a)
        renderer.draw_feedback()
        assert len(renderer.feedback_cards) == 1  # Accepted speech wins.
        old = b.position
        b.position = (20, 15)
        assert renderer.feedback.speech_notice() is None
        b.position = old
        sim.social.cancel_session(sim.social.session_for(a).id, 'test cancel')
        assert renderer.feedback.speech_notice() is None
    finally:
        sim.close()
        pygame.quit()


def food_choice(hunger=65):
    from test_wildlife import hunt_fixture
    sim, actor, chicken, _ = hunt_fixture()
    actor.hunger = hunger
    return sim, actor, chicken


def test_hunting_is_possible_with_available_berries_and_scored_by_hunger():
    sim, actor, _ = food_choice(60)
    try:
        rule = RuleBasedDecisionProvider()
        assert any(sim.resources.stocks().values())
        low = next(c for c in rule.candidates(actor, sim.world, sim.resources) if c.goal == 'HUNT_FOOD')
        actor.hunger = 85
        high = next(c for c in rule.candidates(actor, sim.world, sim.resources) if c.goal == 'HUNT_FOOD')
        assert high.utility > low.utility
        actor.hunger = 20
        assert not any(c.goal == 'HUNT_FOOD' for c in rule.candidates(actor, sim.world, sim.resources))
    finally:
        sim.close()


@pytest.mark.parametrize('constraint', ['exhausted', 'cooked_meal', 'no_station', 'unreachable_station'])
def test_hunting_requires_energy_empty_meals_and_practical_cooking(constraint):
    sim, actor, _ = food_choice()
    try:
        if constraint == 'exhausted':
            actor.energy = 10
        elif constraint == 'cooked_meal':
            actor.inventory.add('cooked_chicken')
        elif constraint == 'no_station':
            sim.resources.cooking_station = None
        else:
            sim.resources.cooking_station.position = (-20, -20)
        rule = RuleBasedDecisionProvider()
        assert not any(c.goal == 'HUNT_FOOD' for c in rule.candidates(actor, sim.world, sim.resources))
        if constraint == 'cooked_meal':
            assert rule.decide(actor, sim.world, sim.resources, random.Random(2)).kind == ActionType.EAT
    finally:
        sim.close()


def test_seeded_preference_is_bounded_and_sampled_once_per_new_goal():
    sim, actor, _ = food_choice()
    try:
        chosen = Counter()
        for seed in range(24):
            rule = RuleBasedDecisionProvider()
            action = rule.decide(actor, sim.world, sim.resources, random.Random(seed))
            plan = rule.plans[actor.id]
            chosen[plan.goal] += 1
            rng = random.Random(100)
            state = rng.getstate()
            rule.tick = 1
            assert rule.decide(actor, sim.world, sim.resources, rng).kind == action.kind
            assert rule.plans[actor.id] is plan
            assert rng.getstate() == state  # No tick-by-tick resampling/oscillation.
            for candidate in rule.debug[actor.id]['utilities']:
                if candidate['goal'] == 'HUNT_FOOD':
                    assert -12 <= candidate['components']['seeded_preference'] <= 26
        assert chosen['HUNT_FOOD'] > 0 and chosen['GATHER_FOOD'] > 0
    finally:
        sim.close()


def test_balanced_policy_conserves_every_food_item_in_seeded_shortage():
    sim = Simulation(42, scenario='food_shortage', event_limit=60000)
    initial = {item: sum(a.inventory.quantity(item) for a in sim.agents)
               for item in ('berries', 'raw_chicken', 'cooked_chicken')}
    try:
        for _ in range(2400):
            sim.step()
        counts = Counter(e['action'] for e in sim.events if e.get('executed'))
        meals = Counter((e.get('item') or 'berries') for e in sim.events
                        if e['action'] == 'EAT' and e.get('executed'))
        final = {item: sum(a.inventory.quantity(item) for a in sim.agents) for item in initial}
        assert initial['berries']+counts['GATHER']-meals['berries'] == final['berries']
        assert initial['raw_chicken']+counts['HUNT']-counts['COOK'] == final['raw_chicken']
        assert initial['cooked_chicken']+counts['COOK']-meals['cooked_chicken'] == final['cooked_chicken']
    finally:
        sim.close()
