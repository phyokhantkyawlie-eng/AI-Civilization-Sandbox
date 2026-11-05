import pytest

from civsandbox.perception import observe
from civsandbox.simulation import Simulation
from civsandbox.world import Tile


@pytest.mark.parametrize("seed", [7, 42, 99])
def test_shortage_natural_requests_and_accounting(seed):
    sim = Simulation(seed, scenario="food_shortage")
    initial = sum(a.food for a in sim.agents)
    reachable = set(sim.world.reachable(sim.agents[0].position))
    assert all(a.position in reachable for a in sim.agents)
    assert len(sim.resources.stocks()) == 2
    assert all(reachable.intersection(sim.world.neighbors(b)) for b in sim.resources.stocks())
    for _ in range(120):
        sim.step()
    social = [e for e in sim.events if e.get("social")]
    requests = {e["request_id"]: e for e in social if e["result"] == "pending"}
    answers = [e for e in social if e["result"] in ("refused", "shared one food")]
    assert requests and answers
    assert len({e["request_id"] for e in answers}) == len(answers)
    for answer in answers:
        req = requests[answer["request_id"]]
        assert answer["actor_id"] == req["target_id"] and answer["target_id"] == req["actor_id"]
        assert 0 <= answer["tick"]-req["tick"] < sim.social.request_lifetime
        assert set(answer["memory_created_for"]) == set(answer["trust_changes"])
    gathered = sum(c.reason == "gather" for c in sim.resources.changes)
    eaten = sum(e["action"] == "EAT" and e.get("executed") and e.get("item", "berries") == "berries" for e in sim.events)
    assert initial + gathered - eaten == sum(a.food for a in sim.agents)


def test_social_cues_are_local_and_survive_disabled_recall():
    sim = Simulation(scenario="food_shortage", memory_enabled=False)
    a = sim.agents[1]
    context, *_ = observe(a, sim.world, sim.resources, sim.agents, social=sim.social)
    peers = {p["id"]: p for p in context["nearby_npcs"]}
    assert peers["npc-1"]["looks_hungry"] and not peers["npc-1"]["carrying_food"]
    assert "carrying_food" not in peers["npc-4"]
    assert "relationships" not in context["social"]
    assert context["agent"]["food"] == 5
