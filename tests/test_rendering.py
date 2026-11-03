"""Exercise display, actual input events, and clean shutdown using SDL dummy."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from civsandbox.rendering import Renderer, handle_event, run
from civsandbox.simulation import FixedTicker, Simulation


def test_render_and_controls():
    sim, ticker = Simulation(), FixedTicker()
    try:
        renderer = Renderer()
        renderer.draw(sim, ticker)
        assert renderer.screen.get_size() == (1100, 750)
        for expected in (True, False):
            handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE), sim, ticker)
            assert sim.paused is expected
        handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP), sim, ticker)
        assert ticker.speed == 2
        for _ in range(10):
            handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN), sim, ticker)
        assert ticker.speed == 0.5
        assert not handle_event(pygame.event.Event(pygame.QUIT), sim, ticker)
        assert not handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), sim, ticker)
    finally:
        pygame.quit()


def test_application_loop_quits_cleanly(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)])
    run(Simulation())
    assert not pygame.display.get_init()


def test_click_inspector_tracks_selected_npc_and_overlap():
    sim, ticker = Simulation(), FixedTicker()
    try:
        renderer = Renderer()
        position = (20+2*36+18, 78+2*36+18)
        click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
        handle_event(click, sim, ticker, renderer)
        assert renderer.selected_id == sim.agents[0].id
        for _ in range(50):
            sim.step()
        renderer.draw(sim, ticker)
        assert renderer.selected_id == sim.agents[0].id
        sim.agents[1].position = sim.agents[0].position = (2, 2)
        handle_event(click, sim, ticker, renderer)
        assert renderer.selected_id == sim.agents[1].id
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20+23*36+18, 78+17*36+18)),
                     sim, ticker, renderer)
        assert renderer.selected_id is None
    finally:
        pygame.quit()


def test_social_inspector_tabs_and_memory_paging():
    sim, ticker = Simulation(), FixedTicker()
    try:
        renderer = Renderer()
        renderer.debug = True
        renderer.selected_id = sim.agents[0].id
        for tick in range(1, 10):
            sim.social.advance(tick)
            sim.social.record("npc-1", "npc-2", "TALK", "greeted", {"npc-1": 1})
        for index, tab in enumerate(("State", "Traits", "Trust", "Memory")):
            handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=(902+index*48, 190)), sim, ticker, renderer)
            assert renderer.inspector_tab == tab
            renderer.draw(sim, ticker)
        handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1), sim, ticker, renderer)
        renderer.draw(sim, ticker)
        assert renderer.memory_page == 1
        handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB), sim, ticker, renderer)
        assert renderer.inspector_tab == "State"
        sim.social.memory_enabled = False
        renderer.inspector_tab = "Memory"
        renderer.draw(sim, ticker)
    finally:
        sim.close()
        pygame.quit()


def test_selected_rule_based_agent_has_accurate_decision_caption():
    sim = Simulation()
    try:
        renderer = Renderer()
        renderer.debug = True
        renderer.selected_id = sim.agents[0].id
        original = renderer.small
        labels = []
        class RecordingFont:
            size = original.size
            def render(self, label, *args):
                labels.append(label)
                return original.render(label, *args)
        renderer.small = RecordingFont()
        renderer.draw(sim, FixedTicker())
        assert "No model decision recorded" in " ".join(labels)
        assert "Select a villager" not in labels
    finally:
        sim.close()
        pygame.quit()


def test_polished_controls_and_cached_ground_are_reused():
    sim, ticker = Simulation(), FixedTicker()
    try:
        renderer = Renderer()
        renderer.draw(sim, ticker)
        cached = dict(renderer.ground_cache)
        for button in ("pause", "faster", "slower", "pause"):
            handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=renderer.control_buttons[button].center),
                         sim, ticker, renderer)
        assert not sim.paused and ticker.speed == 1
        renderer.draw(sim, ticker)
        assert cached == renderer.ground_cache
    finally:
        sim.close()
        pygame.quit()
