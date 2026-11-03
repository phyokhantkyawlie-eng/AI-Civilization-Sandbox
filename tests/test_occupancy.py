from types import SimpleNamespace
from civsandbox.occupancy import Occupancy
from civsandbox.world import Tile, World
from civsandbox.simulation import Simulation


def test_detour_avoids_occupied_tile():
    world = World(((Tile.GRASS,)*3, (Tile.GRASS,)*3))
    actor = SimpleNamespace(id="a", position=(0, 0))
    blocker = SimpleNamespace(id="b", position=(1, 0))
    assert Occupancy().next_step(actor, (2, 0), world, [actor, blocker]) == (0, 1)


def test_narrow_passage_has_bounded_wait_and_valid_recovery():
    world = World(((Tile.GRASS,)*3,))
    actor = SimpleNamespace(id="a", position=(0, 0))
    blocker = SimpleNamespace(id="b", position=(1, 0))
    occupancy = Occupancy()
    for _ in range(3):
        assert occupancy.next_step(actor, (2, 0), world, [actor, blocker]) is None
    assert occupancy.next_step(actor, (2, 0), world, [actor, blocker]) == (1, 0)
    actor.position = (1, 0)
    assert occupancy.next_step(actor, (2, 0), world, [actor, blocker]) == (2, 0)


def test_reservation_replay_bounds_and_bounded_event_history():
    a, b = Simulation(42, event_limit=50), Simulation(42, event_limit=50)
    for _ in range(200):
        a.step()
        b.step()
        assert a.snapshot() == b.snapshot()
        assert len(a.events) <= 50
        assert all(a.world.walkable(agent.position) for agent in a.agents)
