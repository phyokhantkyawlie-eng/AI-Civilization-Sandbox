"""Behavior contracts tested in small worlds with known geometry and stocks."""
import random

import pytest

from civsandbox.actions import Action, ActionType, execute, validate
from civsandbox.agents import Agent, Goal
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.resources import Resources
from civsandbox.simulation import Simulation
from civsandbox.world import Tile, World


def fixture_world():
    world = World(((Tile.GRASS, Tile.GRASS, Tile.BUSH),
                   (Tile.GRASS, Tile.GRASS, Tile.GRASS)))
    return world, Resources(world), Agent("a", "Ada", (1, 0), (255, 0, 0))


def test_gather_depletion_replenishment_and_complete_ledger():
    world, resources, agent = fixture_world()
    gather = Action(ActionType.GATHER, (2, 0))
    for tick in range(1, 6):
        assert execute(gather, agent, world, resources, tick)
    assert agent.food == 5
    assert resources.available((2, 0)) == 0
    agent.food = 0
    assert not execute(gather, agent, world, resources, 6)
    resources.replenish(19)
    assert resources.available((2, 0)) == 0
    resources.replenish(20)
    assert resources.available((2, 0)) == 1
    assert execute(gather, agent, world, resources, 21)
    for tick in range(40, 161, 20):
        resources.replenish(tick)
    assert resources.available((2, 0)) == 5
    reconstructed = {}
    for change in resources.changes:
        assert reconstructed.get(change.position, 0) == change.before
        assert 0 <= change.after <= resources.capacity
        reconstructed[change.position] = change.after
    assert reconstructed == resources.stocks()
    assert sum(c.reason == "gather" for c in resources.changes) == 6
    assert all(c.agent_id == "a" for c in resources.changes if c.reason == "gather")


def test_eating_resting_and_needs_clamp():
    world, resources, agent = fixture_world()
    agent.food, agent.hunger, agent.energy = 1, 20, 98
    assert execute(Action(ActionType.EAT), agent, world, resources, 1)
    assert (agent.food, agent.hunger) == (0, 0)
    assert not execute(Action(ActionType.EAT), agent, world, resources, 1)
    assert execute(Action(ActionType.REST), agent, world, resources, 1)
    assert agent.energy == 100
    agent.hunger, agent.energy = 100, 0
    agent.advance_needs()
    assert (agent.hunger, agent.energy) == (100, 0)
    agent.hunger, agent.energy = 25, 50
    agent.advance_needs()
    assert (agent.hunger, agent.energy) == (26, 50)
    assert execute(Action(ActionType.MOVE_TO, (0, 1)), agent, world, resources, 2)
    assert agent.position in ((0, 0), (1, 1))  # either shortest-route first step
    assert agent.energy == 50 and agent.energy_spent_micro == 100_000
    tired = Agent("b", "Basil", (1, 0), (0, 0, 0), energy=1)
    assert execute(Action(ActionType.GATHER, (2, 0)), tired, world, resources, 2)
    assert tired.energy == 0 and tired.food == 1


@pytest.mark.parametrize("action", [
    Action(ActionType.GATHER, (0, 0)),
    Action(ActionType.GATHER, (20, 20)),
    Action(ActionType.GATHER, None),
    Action(ActionType.MOVE_TO, (2, 0)),
    Action(ActionType.MOVE_TO, (-1, 0)),
    Action(ActionType.MOVE_TO, (1, 0)),
    Action(ActionType.MOVE_TO, (1.0, 1)),
    Action(ActionType.MOVE_TO, [0, 0]),
    Action(ActionType.MOVE_TO, (True, 0)),
    Action(ActionType.EAT),
    Action(ActionType.REST, (0, 0)),
    Action(ActionType.WAIT, (0, 0)),
    Action("MOVE_TO", (0, 0)),
    None,
])
def test_invalid_actions_are_atomic_noops(action):
    world, resources, agent = fixture_world()
    before = (agent.position, agent.food, agent.hunger, agent.energy, agent.current_action)
    stock, changes = resources.stocks(), resources.changes.copy()
    assert not execute(action, agent, world, resources, 1)
    assert before == (agent.position, agent.food, agent.hunger, agent.energy, agent.current_action)
    assert stock == resources.stocks() and changes == resources.changes


def test_distant_gather_unreachable_move_exhaustion_and_full_inventory():
    world, resources, agent = fixture_world()
    agent.position = (0, 0)
    assert not validate(Action(ActionType.GATHER, (2, 0)), agent, world, resources)
    agent.energy = 0
    assert not validate(Action(ActionType.MOVE_TO, (0, 1)), agent, world, resources)
    agent.position, agent.energy, agent.food = (1, 0), 50, 5
    assert not validate(Action(ActionType.GATHER, (2, 0)), agent, world, resources)
    split = World(((Tile.GRASS, Tile.WATER, Tile.GRASS),))
    agent.position = (0, 0)
    assert not validate(Action(ActionType.MOVE_TO, (2, 0)), agent, split, Resources(split))


def test_priority_and_rest_hysteresis():
    world, resources, agent = fixture_world()
    provider, rng = RuleBasedDecisionProvider(), random.Random(0)
    agent.hunger, agent.food, agent.energy = 90, 1, 0
    assert provider.decide(agent, world, resources, rng).kind == ActionType.EAT
    agent.food = 0
    assert provider.decide(agent, world, resources, rng).kind == ActionType.REST
    agent.current_action, agent.energy = "REST", 60
    assert provider.decide(agent, world, resources, rng).kind == ActionType.REST
    agent.energy = 70
    assert provider.decide(agent, world, resources, rng).kind == ActionType.GATHER


def test_food_goal_continuity_and_depleted_goal_replanning():
    world = World(((Tile.GRASS, Tile.GRASS, Tile.GRASS, Tile.BUSH),
                   (Tile.GRASS, Tile.GRASS, Tile.GRASS, Tile.GRASS)))
    resources = Resources(world)
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0), hunger=80)
    provider, rng = RuleBasedDecisionProvider(), random.Random(42)
    first = provider.decide(agent, world, resources, rng)
    goal = agent.goal
    assert goal == Goal("food", (3, 0))
    assert execute(first, agent, world, resources, 1)
    second = provider.decide(agent, world, resources, rng)
    assert agent.goal == goal and second.target == first.target
    for tick in range(2, 5):
        execute(provider.decide(agent, world, resources, rng), agent, world, resources, tick)
    assert agent.hunger < 80  # reached bush, gathered, ate
    for tick in range(5):
        resources.collect((3, 0), tick, "other")
    agent.food = 0
    assert provider.decide(agent, world, resources, rng).kind == ActionType.WAIT
    assert agent.goal is None


def test_no_reachable_resources_or_movement_waits():
    world = World(((Tile.GRASS, Tile.WATER, Tile.BUSH),))
    resources = Resources(world)
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0))
    provider = RuleBasedDecisionProvider()
    assert provider.decide(agent, world, resources, random.Random(0)) == Action(ActionType.WAIT)
    agent.food = 2
    assert provider.decide(agent, world, resources, random.Random(0)).kind == ActionType.WAIT


def test_last_food_cannot_be_gathered_twice():
    world, resources, first = fixture_world()
    for tick in range(4):
        resources.collect((2, 0), tick, "setup")
    second = Agent("b", "Basil", first.position, (0, 0, 0))
    action = Action(ActionType.GATHER, (2, 0))
    assert execute(action, first, world, resources, 5)
    assert not execute(action, second, world, resources, 5)
    assert (first.food, second.food, resources.available((2, 0))) == (1, 0, 0)


def test_provider_injection_invalid_fallback_and_pause():
    class InvalidProvider:
        def decide(self, agent, world, resources, rng):
            return Action(ActionType.MOVE_TO, (-1, 0))

    sim = Simulation(decision_provider=InvalidProvider())
    positions = [a.position for a in sim.agents]
    sim.step()
    assert [a.position for a in sim.agents] == positions
    assert all(a.current_action == "WAIT" for a in sim.agents)
    assert all(a.hunger == 26 and a.energy == 90 and a.energy_spent_micro == 20_000 for a in sim.agents)
    assert sum(e["action"] == "REJECTED" for e in sim.events) == 4
    sim.paused = True
    before = sim.snapshot()
    for _ in range(30):
        sim.step()
    assert sim.snapshot() == before


def test_long_run_resource_conservation_and_need_bounds():
    sim = Simulation(42)
    for _ in range(1500):
        sim.step()
        assert all(0 <= a.hunger <= 100 and 0 <= a.energy <= 100 and 0 <= a.food <= 5
                   and sim.world.walkable(a.position) for a in sim.agents)
    gathered = sum(c.before-c.after for c in sim.resources.changes if c.reason == "gather")
    eaten = sum(e["action"] == "EAT" and e.get("executed") and e.get("item", "berries") == "berries" for e in sim.events)
    assert gathered == eaten + sum(a.food for a in sim.agents)
    assert {e["action"] for e in sim.events} >= {"MOVE_TO", "GATHER", "EAT", "REST"}
    assert all(0 <= stock <= 5 for stock in sim.resources.stocks().values())
