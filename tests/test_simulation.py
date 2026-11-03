import json
import subprocess
import sys

import pytest

from civsandbox.simulation import FixedTicker, Simulation
from civsandbox.world import Tile, World


def test_bfs_shortest_detour_and_invalid_goals():
    g, w = Tile.GRASS, Tile.WATER
    world = World(((g, w, g), (g, w, g), (g, g, g)))
    route = world.path((0, 0), (2, 0))
    assert len(route) == 6
    previous = (0, 0)
    for position in route:
        assert position in world.neighbors(previous)
        previous = position
    assert previous == (2, 0)
    assert world.path((0, 0), (0, 0)) == []
    assert world.path((0, 0), (1, 0)) == []
    assert world.path((-1, 0), (2, 0)) == []
    assert not world.walkable((3, 0))
    assert not world.walkable((0, -1))
    assert World(((g, w, g),)).path((0, 0), (2, 0)) == []


@pytest.mark.parametrize("seed", [0, 1, 42, 999])
def test_agents_move_safely_and_reproducibly(seed):
    sim, repeat = Simulation(seed), Simulation(seed)
    assert (sim.world.width, sim.world.height) == (24, 18)
    assert set(t for row in sim.world.tiles for t in row) == set(Tile)
    assert len({a.id for a in sim.agents}) == len({a.name for a in sim.agents}) == 4
    moved = set()
    for _ in range(300):
        before = [a.position for a in sim.agents]
        sim.step()
        repeat.step()
        assert sim.snapshot() == repeat.snapshot()
        for i, agent in enumerate(sim.agents):
            assert sim.world.walkable(agent.position)
            assert agent.position == before[i] or agent.position in sim.world.neighbors(before[i])
            if agent.position != before[i]:
                moved.add(agent.id)
    assert len(moved) == 4
    assert sim.world == repeat.world
    assert Simulation(seed+1).world != sim.world


def test_fixed_tick_pause_resume_and_speed():
    sim, ticker = Simulation(), FixedTicker()
    assert ticker.advance(sim, 0.125) == 0
    sim.paused = True
    snapshot = sim.snapshot()
    sim.step()
    ticker.advance(sim, 100)
    assert sim.snapshot() == snapshot
    sim.paused = False
    assert ticker.advance(sim, 0.125) == 1
    ticker.speed = 2
    assert ticker.advance(sim, 0.5) == 4
    assert sim.tick == 5
    with pytest.raises(ValueError):
        ticker.advance(sim, -1)


def test_frame_rate_independence():
    a, b = Simulation(), Simulation()
    ta, tb = FixedTicker(), FixedTicker()
    for _ in range(600):
        ta.advance(a, 1/60)
    for _ in range(200):
        tb.advance(b, 1/20)
    assert a.tick == b.tick == 40
    assert a.snapshot() == b.snapshot()


def test_headless_cli_and_no_pygame_import(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_PATH", str(tmp_path / "history.json"))
    result = subprocess.run([sys.executable, "-m", "civsandbox", "--headless",
                             "--ticks", "25", "--seed", "7"],
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["tick"] == 25
    subprocess.run([sys.executable, "-c", "import runpy, sys; "
                    "sys.argv=['civsandbox','--headless','--ticks','0']; "
                    "runpy.run_module('civsandbox',run_name='__main__'); "
                    "assert 'pygame' not in sys.modules"], check=True, capture_output=True)
    invalid = subprocess.run([sys.executable, "-m", "civsandbox", "--headless",
                              "--ticks", "-1"], capture_output=True)
    assert invalid.returncode == 2
