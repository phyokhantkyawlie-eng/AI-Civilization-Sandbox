"""Main-project character assets and animations driven by observed simulation moves."""
import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
import pytest
from PIL import Image

from civsandbox.animation import CharacterView, DIRECTIONS, SpriteAnimator
from civsandbox.characters import CHARACTERS
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.simulation import FixedTicker, Simulation
from civsandbox.sprites import ASSET_ROOT, CharacterAssets, FOOT_ANCHOR, FRAME_SIZE
from civsandbox.world import Tile, World


def animator(fps=8):
    return SpriteAnimator({d: [f"{d}-{i}" for i in range(5)] for d in DIRECTIONS}, fps)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_idle_and_four_walk_frames_per_direction(direction):
    a = animator()
    a.update(0, True, direction)
    assert a.frame == f"{direction}-1"
    for expected in (2, 3, 4, 1):
        a.update(.125, True)
        assert a.frame == f"{direction}-{expected}"
    a.update(.1, False)
    assert a.index == 0 and a.frame == f"{direction}-0"
    assert a.direction == direction


def test_direction_change_and_dt_independence():
    a, b = animator(), animator()
    for _ in range(120):
        a.update(1/120, True, "left")
    for _ in range(30):
        b.update(1/30, True, "left")
    assert a.index == b.index == 1
    a.update(0, True, "up")
    assert a.frame == "up-1"
    a.update(0, False)
    assert a.frame == "up-0"
    a.update(0, True)
    assert a.frame == "up-1"


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_animation_times(value):
    with pytest.raises(ValueError):
        animator(value)
    with pytest.raises(ValueError):
        animator().update(value, True)
    with pytest.raises(ValueError):
        CharacterView((0, 0), animator()).advance(value)


def test_frame_structure_and_fps_validation():
    with pytest.raises(ValueError):
        SpriteAnimator({}, 8)
    with pytest.raises(ValueError):
        animator(0)
    with pytest.raises(ValueError):
        animator().update(0, True, "northwest")
    slow, fast = animator(4), animator(8)
    slow.update(.125, True)
    fast.update(.125, True)
    assert slow.index == 1 and fast.index == 2


def test_original_metadata_normalization_and_contact_sheets():
    report = json.loads((ASSET_ROOT/"inspection"/"frames.json").read_text())
    for _, key in CHARACTERS.values():
        original = ASSET_ROOT/"characters"/f"{key}.png"
        assert hashlib.sha256(original.read_bytes()).hexdigest() == report[key]["sha256"]
        with Image.open(original) as source:
            assert source.size == (887, 1774)
            assert source.mode == ("RGBA" if key == "nyra" else "RGB")
        assert len(report[key]["frames"]) == 20
        for direction in DIRECTIONS:
            for index in range(5):
                with Image.open(ASSET_ROOT/"processed"/key/f"{direction}_{index}.png") as frame:
                    assert frame.mode == "RGBA" and frame.size == (160, 200)
                    assert frame.getbbox()[3] == 190  # common, stable foot baseline
                    assert frame.getchannel("A").getextrema() == (0, 255)
    for background in ("dark", "light"):
        with Image.open(ASSET_ROOT/"inspection"/f"contact-{background}.png") as contact:
            assert contact.size == (820, 3520)


def test_main_loader_maps_all_four_actual_characters():
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    try:
        assets = CharacterAssets()
        sim = Simulation()
        assert {a.name for a in sim.agents} == {"Mira", "Nyra", "Kairo", "Ren"}
        hashes = set()
        for agent in sim.agents:
            name, key = CHARACTERS[agent.id]
            assert agent.name == name
            assert assets.for_agent(agent) is assets.frames[key]
            for direction in DIRECTIONS:
                assert len(assets.for_agent(agent)[direction]) == 5
                assert all(frame.get_size() == FRAME_SIZE for frame in assets.for_agent(agent)[direction])
            hashes.add(hashlib.sha256(pygame.image.tobytes(assets.for_agent(agent)["down"][0], "RGBA")).digest())
        assert len(hashes) == 4
        assert FOOT_ANCHOR == (20, 48)
    finally:
        pygame.quit()


def test_observed_steps_retain_obstacle_corner_and_stop_at_idle():
    view = CharacterView((0, 0), animator())
    view.capture((0, 1), .25)
    view.capture((1, 1), .25)
    view.advance(.125)
    assert view.position == (0, .5) and view.animator.direction == "down"
    view.advance(.125)
    assert view.position == (0, 1) and view.animator.direction == "right"
    view.advance(.125)
    assert view.position == (.5, 1)
    view.advance(.125)
    assert view.position == (1, 1) and view.animator.index == 0
    assert view.animator.direction == "right"
    assert not view.segments


def test_pause_and_unobserved_state_change_do_not_invent_movement():
    view = CharacterView((0, 0), animator())
    view.capture((1, 0), .25)
    view.advance(.1)
    before = view.position
    view.advance(10, paused=True)
    assert view.position == before and view.animator.index == 0
    view.advance(.15)
    assert view.position == (1, 0)
    view.capture((3, 3), .25)
    assert view.position == (3, 3) and not view.segments and view.animator.index == 0


def test_dirt_and_grass_paths_avoid_water():
    g, d, w = Tile.GRASS, Tile.DIRT, Tile.WATER
    world = World(((g, w, d), (d, d, d)))
    route = world.path((0, 0), (2, 0))
    assert route == [(0, 1), (1, 1), (2, 1), (2, 0)]
    assert not world.walkable((-1, 0)) and not world.walkable((1, 0))


def test_tick_capture_does_not_modify_npc_state_and_autonomy_stays_safe():
    sim, repeat = Simulation(42), Simulation(42)
    ticker = FixedTicker()
    views = {a.id: CharacterView(a.position, animator()) for a in sim.agents}
    positions = {a.id: {a.position} for a in sim.agents}
    observed = []
    def capture(state):
        observed.append(state.tick)
        for agent in state.agents:
            view = views[agent.id]
            before = view.logical_position
            assert agent.position == before or agent.position in state.world.neighbors(before)
            assert state.world.walkable(agent.position)
            positions[agent.id].add(agent.position)
            view.capture(agent.position, ticker.interval/ticker.speed)
    for _ in range(300):
        for view in views.values():
            view.advance(.25)
        ticker.advance(sim, .25, on_step=capture)
        repeat.step()
    assert observed == list(range(1, 301))
    assert sim.snapshot() == repeat.snapshot()
    assert all(len(visited) > 5 for visited in positions.values())


def test_multi_tick_capture_preserves_each_path_step():
    sim, ticker = Simulation(), FixedTicker()
    observed = []
    ticker.advance(sim, 2, on_step=lambda state: observed.append([a.position for a in state.agents]))
    assert len(observed) == 8
    for first, second in zip(observed, observed[1:]):
        for a, b in zip(first, second):
            assert a == b or b in sim.world.neighbors(a)


def test_click_hits_interpolated_artwork_and_inspector_uses_real_state():
    from civsandbox.rendering import Renderer, handle_event
    from civsandbox.agents import Goal
    from civsandbox.actions import Action, ActionType, execute
    sim = Simulation()
    try:
        renderer = Renderer()
        renderer.sync_characters(sim)
        agent = sim.agents[0]
        agent.goal = Goal("explore", (3, 2))
        assert execute(Action(ActionType.MOVE_TO, (3, 2)), agent, sim.world, sim.resources, 1)
        renderer.capture_tick(sim, .25)
        renderer.advance_animation(.125)
        renderer.draw(sim, FixedTicker())
        assert renderer.characters[agent.id].position == (2.5, 2)
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                   pos=renderer.character_rects[agent.id].center)
        handle_event(event, sim, FixedTicker(), renderer)
        assert renderer.selected_id == agent.id and agent.position == (3, 2)
        assert renderer.characters[agent.id].animator.direction == "right"
        renderer.draw(sim, FixedTicker())
    finally:
        sim.close()
        pygame.quit()


def test_multi_tick_idle_gap_is_retained_between_real_moves():
    view = CharacterView((0, 0), animator())
    view.capture((1, 0), .25)
    view.capture((1, 0), .25)  # actual stationary tick
    view.capture((1, 1), .25)
    view.advance(.375)
    assert view.position == (1, 0) and view.animator.index == 0
    view.advance(.25)
    assert view.position == (1, .5) and view.animator.direction == "down"
    view.advance(.125)
    assert view.position == (1, 1) and view.animator.index == 0


def test_main_loop_straight_walk_uses_all_frames_across_ticks_and_speed_changes():
    from civsandbox.rendering import Renderer, advance_frame
    from civsandbox.actions import Action, ActionType
    class WalkLane:
        def decide(self, agent, world, resources, rng):
            return Action(ActionType.MOVE_TO, (23, 2))
    sim = Simulation(42, WalkLane())
    renderer = Renderer()
    renderer.sync_characters(sim)
    ticker = FixedTicker()
    view = renderer.characters["npc-1"]
    seen = set()
    try:
        for frame in range(90):
            if frame == 52:
                ticker.speed = 2
            advance_frame(renderer, ticker, sim, 1/60)
            if view.animator.moving:
                seen.add(view.animator.index)
                assert view.animator.direction == "right"
                assert 0 <= sim.agents[0].position[0]-view.position[0] <= 1.000001
        assert seen == {1, 2, 3, 4}
    finally:
        sim.close()
        pygame.quit()
