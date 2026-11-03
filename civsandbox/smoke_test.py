"""Explicit opt-in: one Gemini request and one validated action in an isolated world."""
from dataclasses import replace
import json

from .actions import execute
from .ai import GeminiDecisionProvider, safe_text
from .config import Settings
from .perception import observe, action_dict
from .simulation import Simulation


def run_smoke(settings=None):
    settings = settings or Settings.load()
    settings = replace(settings, provider="gemini", max_calls=min(1, settings.max_calls))
    provider = GeminiDecisionProvider(settings)
    simulation = Simulation(memory_enabled=settings.memory_enabled, scenario="food_shortage")
    provider.bind_social(simulation.social)
    agent = simulation.agents[0]
    report = {"model": safe_text(settings.model, settings.api_key) or None, "valid_response": None,
              "executed": False, "fallback_count": 0, "error": None}
    try:
        context, choices, world, resources = observe(
            agent, simulation.world, simulation.resources, simulation.agents, social=simulation.social)
        _, reason = provider.request(context, choices, agent, world, resources)
        if agent.id in provider.pending:
            provider.pending[agent.id].done.wait(settings.timeout_seconds + 0.1)
            action, reason = provider.poll(agent, world, resources)
            if action:
                report["valid_response"] = {**action_dict(action), "reasoning": action.reasoning}
                report["executed"] = execute(action, agent, simulation.world, simulation.resources,
                                             simulation.tick, simulation.social)
                reason = "" if report["executed"] else "execution rejected"
        report.update(error=reason or None, api_calls=provider.api_calls)
        print(json.dumps(report))
        return 0 if report["executed"] else (1 if provider.api_calls else 2)
    finally:
        simulation.close()
        provider.close()


if __name__ == "__main__":
    raise SystemExit(run_smoke())
