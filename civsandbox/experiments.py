"""Paired, isolated social-memory trials around the existing simulation."""
import argparse
import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

from .config import Settings, create_provider
from .simulation import Simulation
from .inventory import ITEM_DEFINITIONS
from .measurements import Measurements
from .resources import ResourceChange

METRICS = ("requests", "shares", "refusals", "cooperation_rate", "survival_rate",
           "average_hunger", "invalid_action_rate", "gemini_calls", "fallback_count",
           "wall_seconds", "average_energy", "gathering_actions", "hunting_attempts",
           "hunting_successes", "cooking_completions", "incapacitations",
           "operational_availability", "social_interactions_per_minute", "mean_trust_change")


def rate(numerator, denominator):
    return numerator / denominator if denominator else None


def initial_fingerprint(sim):
    """Hash physical/RNG state, excluding the experimental treatment flag."""
    state = {"world": [[t.value for t in row] for row in sim.world.tiles],
             "agents": sim.snapshot()["agents"], "chickens": sim.snapshot()["chickens"], "cooking_station": sim.snapshot()["cooking_station"],
             "wildlife_rng": repr(sim.wildlife.rng.getstate()), "resources": sim.resources.stocks().__repr__(),
             "rng": repr(sim.rng.getstate()), "dialogue_rng":repr(sim.social.dialogue_rng.getstate()),
             "bushes":[asdict(b) for b in sim.resources.bushes.values()],
             "configuration":{'clock':asdict(sim.clock),'survival':asdict(sim.survival),
                              'timing':asdict(sim.progress.timing),'social':asdict(sim.social.settings),
                              'wildlife':asdict(sim.wildlife.settings)}}
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


SCENARIOS = {'default':'default','normal_survival':'default','food_shortage':'food_shortage',
             'social_memory':'food_shortage','hunting_decisions':'food_shortage'}
HUNTING_PROFILES = {
    'well_fed':(25,90,None,0,False), 'moderate':(65,90,None,0,False),
    'hungry':(90,90,None,0,False), 'exhausted':(90,15,None,0,False),
    'carried_berries':(90,90,'berries',2,False),
    'carried_meal':(90,90,'cooked_chicken',1,False),
    'scarce_berries':(90,90,None,0,True),
}


def prepare_scenario(sim, scenario, profile):
    if scenario!='hunting_decisions':
        if profile!='baseline':
            raise ValueError('Profiles apply only to hunting_decisions')
        return
    hunger,energy,item,quantity,scarce = HUNTING_PROFILES[profile]
    for actor in sim.agents:
        actor.inventory.items.clear()
        if item:
            actor.inventory.add(item,quantity)
        actor.hunger,actor.energy = hunger,energy
    for bush in sim.resources.bushes.values():
        bush.capacity = 5
        bush.quantity = 0 if scarce else 5
        bush.regeneration_interval = 240 if scarce else 20
        bush.regeneration_progress = 0
    sim.resources.changes = [ResourceChange(0,b.position,0,b.quantity,'initial',None)
                             for b in sim.resources.bushes.values()]
    # Standardize a reachable encounter opportunity, not a decision or reward.
    # Chickens retain their normal movement/fear FSM from the first tick onward.
    occupied = {a.position for a in sim.agents}|{sim.cooking_station.position}
    choices = sorted(p for p in sim.world.reachable(sim.agents[0].position)
                     if p not in occupied and 3<=min(sum(abs(x-y) for x,y in zip(p,a.position)) for a in sim.agents)<=4)
    for chicken,point in zip(sim.wildlife.living(),choices):
        chicken.position = point
    for event in sim.wildlife.events:
        if event['action']=='CHICKEN_SPAWN':
            event['position'] = sim.wildlife.chickens[event['target']].position


def metrics(sim, hunger_sum, samples, fallback_count, elapsed, recorder=None):
    record = recorder or Measurements()
    if recorder is None:
        record.ingest(sim.events)
    e,c = record.events,record.completed
    requests,shares,refusals = (e['social:'+name] for name in ('pending','shared one food','refused'))
    invalid = e['REJECTED']+e['model_rejected']
    rule = getattr(sim.decision_provider,'rule',sim.decision_provider)
    stats = getattr(rule,'stats',{})
    ticks = record.ticks if recorder else sim.tick
    seconds = ticks*.25
    result = {
        'completed_sessions':e['session:COMPLETED'],'canceled_sessions':e['session:CANCELED'],
        'dialogue_turns':e['DIALOGUE'],'thanks_turns':e['thanks'],
        'campfire_conversations':e['campfire_completed'],'voluntary_food_transfers':e['social:offered one food'],
        'gathering_actions':c['GATHER'],'hunting_attempts':e['hunt_attempts'],
        'hunting_successes':c['HUNT'],'failed_hunts':e['HUNT_FAILED'],'pending_hunts':len(sim.wildlife.pursuits),
        'hunting_decisions':record.goals['HUNT_FOOD'], 'gathering_decisions':record.goals['GATHER_FOOD'],
        'eligible_hunt_choices':stats.get('eligible_hunt_choices'),
        'goal_choices':dict(record.goals),'cooking_completions':c['COOK'],
        'meals_consumed':dict(record.meals),'incapacitations':e['incapacitations'],
        'incapacitated_npc_ticks':record.incapacitated_ticks if recorder else None,
        'operational_availability':1-record.incapacitated_ticks/record.samples if record.samples else None,
        'activity_npc_ticks':dict(record.activity_ticks),
        'activity_npc_seconds':{key:value*.25 for key,value in record.activity_ticks.items()},
        'longest_activity_run_seconds':{key:value*.25 for key,value in record.longest_runs.items()},
        'failed_plans':stats.get('failed'),'interrupted_plans':stats.get('interrupted'),
        'failed_plan_reasons':dict(record.failed_reasons),'invalid_actions_by_type':dict(record.invalid_by_action),
        'final_food_items':{item:sum(a.inventory.quantity(item) for a in sim.agents) for item in ITEM_DEFINITIONS},
        'requests':requests,'shares':shares,'refusals':refusals,
        'cooperation_rate':rate(shares,shares+refusals),'survival_rate':None,
        'average_hunger':rate(hunger_sum,samples),
        'average_energy':rate(record.energy_sum,record.samples),
        'social_interactions_per_minute':rate(e['session:COMPLETED']*60,seconds),
        'invalid_actions':invalid,'action_opportunities':e['opportunities'],
        'invalid_action_rate':rate(invalid,e['opportunities']),
        'gemini_calls':sim.ai_summary()['api_calls'],'fallback_count':fallback_count,
        'expired_requests':e['social:expired'],'unanswered_requests':len(sim.social.pending),
        'final_trust':{a.id:a.trust.copy() for a in sim.agents},
        'wall_seconds':elapsed,'simulation_seconds':seconds,
        'chicken_spawns':e['CHICKEN_SPAWN'],'chicken_repopulations':e['repopulations'],
        'hunts_within_one_tick_of_spawn':e['near_spawn_hunts'],
        'hunts_within_one_tick_of_repopulation':e['near_repopulation_hunts'],
        'minimum_hunt_spawn_delay_ticks':record.minimum_spawn_delay,
        'mean_hunt_spawn_delay_ticks':rate(record.spawn_delay_sum,record.spawn_delay_count),
        'first_120_hunting_attempts':record.first_120_attempts,
        'duplicate_chicken_ids':record.duplicate_spawn_ids,'duplicate_meat_rewards':record.duplicate_rewards,
        'final_chickens_alive':len(sim.wildlife.living()),
    }
    return result


def run_trial(settings, seed, ticks, memory, scenario='food_shortage', tick_seconds=.25, profile='baseline'):
    # tick_seconds is retained for old callers only; offline trials never sleep.
    if settings.provider not in ('rule-based','mock'):
        raise ValueError('Evaluation supports offline providers only')
    if scenario not in SCENARIOS or type(ticks) is not int or ticks<0:
        raise ValueError('Invalid evaluation scenario/duration')
    if scenario=='hunting_decisions' and profile not in HUNTING_PROFILES:
        raise ValueError('Select a hunting profile')
    provider = create_provider(replace(settings,memory_enabled=memory))
    sim = Simulation(seed,provider,memory_enabled=memory,memory_path=None,scenario=SCENARIOS[scenario],
                     event_limit=4096,decision_trace_limit=100,timing=settings.action_timing,
                     day_clock=settings.day_clock,survival=settings.survival,
                     wildlife_settings=settings.wildlife,social_settings=settings.social)
    prepare_scenario(sim,scenario,profile)
    row = {'seed':seed,'scenario':scenario,'profile':profile,
           'condition':'MEMORY_ON' if memory else 'MEMORY_OFF','provider':settings.provider,
           'algorithm':('local utility + bounded task planner' if settings.provider=='rule-based' else 'offline mock adapter + local planner'),
           'model':None,'status':'running',
           'initial_state_sha256':initial_fingerprint(sim),
           'initial_trust':{a.id:a.trust.copy() for a in sim.agents},
           'initial_agents':[asdict(a) for a in sim.agents],
           'initial_chickens_alive':len(sim.wildlife.living()),
           'initial_food_items':{item:sum(a.inventory.quantity(item) for a in sim.agents) for item in ITEM_DEFINITIONS}}
    record = Measurements()
    series = []
    sample_every = max(1,math.ceil(ticks/1000))
    started = time.perf_counter()
    fallbacks = 0
    try:
        for _ in range(ticks):
            sim.step()
            record.capture(sim)
            fallbacks += sum(bool(s.get('fallback')) for s in sim.ai_summary()['agents'].values())
            if sim.tick==1 or sim.tick%sample_every==0 or sim.tick==ticks:
                series.append({'tick':sim.tick,'mean_hunger':sum(a.hunger for a in sim.agents)/4,
                               'mean_energy':sum(a.energy for a in sim.agents)/4,
                               'wild_berries':sum(sim.resources.stocks().values()),
                               'carried_edible_items':sum(sum(a.inventory.quantity(item) for a in sim.agents)
                                                         for item,d in ITEM_DEFINITIONS.items() if d.hunger_reduction>0),
                               'chickens_alive':len(sim.wildlife.living()),
                               'active_agents':sum(not a.incapacitated_until for a in sim.agents)})
        row['status'] = 'completed'
    except Exception as error:
        row.update(status='failed',error=type(error).__name__)
    finally:
        row.update(metrics(sim,record.hunger_sum,record.samples,fallbacks,time.perf_counter()-started,record))
        row.update(completed_ticks=record.ticks,last_engine_tick=sim.tick,npc_tick_samples=record.samples,
                   series_sample_interval_ticks=sample_every,state_series=series,
                   hunger_series=[{'tick':s['tick'],'mean_hunger':s['mean_hunger']} for s in series],
                   recent_decisions=sim.decision_trace,retained_engine_events=len(sim.events))
        row['trust_changes'] = {key:{peer:value-row['initial_trust'][key][peer] for peer,value in trust.items()}
                                for key,trust in row['final_trust'].items()}
        changes = [value for peers in row['trust_changes'].values() for value in peers.values()]
        row['mean_trust_change'] = sum(changes)/len(changes)
        i,f,m = row['initial_food_items'],row['final_food_items'],row['meals_consumed']
        row['food_conservation'] = (i['berries']+row['gathering_actions']-m.get('berries',0)==f['berries']
                                   and i['raw_chicken']+row['hunting_successes']-row['cooking_completions']==f['raw_chicken']
                                   and i['cooked_chicken']+row['cooking_completions']-m.get('cooked_chicken',0)==f['cooked_chicken'])
        if not row['food_conservation'] or record.duplicate_rewards or record.duplicate_spawn_ids:
            row.update(status='failed',error='ConservationOrIdentityError')
        sim.close()
    return row


def describe(values, allow_ci=True):
    values = [v for v in values if v is not None]
    n = len(values)
    mean = statistics.mean(values) if n else None
    sd = statistics.stdev(values) if n >= 2 else None
    # Normal approximation is explicitly withheld for tiny samples.
    ci = None
    if n >= 5 and allow_ci:
        margin = 1.96*sd/math.sqrt(n)
        ci = [mean-margin, mean+margin]
    return {"n": n, "mean": mean, "sample_stddev": sd, "approximate_95_ci_mean": ci}


def summarize_group(rows):
    completed = [r for r in rows if r["status"] == "completed"]
    homogeneous = len({(r.get('scenario'),r.get('profile')) for r in rows})<=1
    modes = {mode: {m: describe([r.get(m) for r in completed if r["condition"] == mode],homogeneous)
                    for m in METRICS} for mode in ("MEMORY_OFF", "MEMORY_ON")}
    by_seed = {}
    for row in completed:
        unit = (row.get('scenario'),row.get('profile'),row['seed'])
        by_seed.setdefault(unit, {})[row["condition"]] = row
    differences = {m: [] for m in METRICS}
    paired = []
    for (scenario,profile,seed), pair in by_seed.items():
        if len(pair) != 2:
            continue
        off, on = pair["MEMORY_OFF"], pair["MEMORY_ON"]
        if off["initial_state_sha256"] != on["initial_state_sha256"]:
            continue
        delta = {m: on[m]-off[m] if on.get(m) is not None and off.get(m) is not None else None for m in METRICS}
        paired.append({'seed':seed,'scenario':scenario,'profile':profile,'on_minus_off':delta})
        for m in METRICS:
            differences[m].append(delta[m])
    return {"conditions": modes, "paired_differences": paired,
            "paired_summary": {m: describe(v,homogeneous) for m, v in differences.items()},
            "failed_trials": sum(r["status"] == "failed" for r in rows),
            "total_gemini_calls": sum(r.get("gemini_calls", 0) for r in rows),
            "total_fallback_npc_ticks": sum(r.get("fallback_count", 0) for r in rows),
            "warnings": ["Survival unavailable: the simulation has no death mechanic.",
                         "Confidence intervals use a normal approximation across seed-level trials.",
                         "Fewer than 5 complete pairs: descriptive pilot only." if len(paired) < 5
                         else "Seed sampling limits generalization.",
                         "Mixed profiles: pooled confidence intervals withheld; inspect strata." if not homogeneous
                         else "Only independent seed-level trials support the approximate intervals."]}


def summarize(rows):
    result = summarize_group(rows)
    keys = sorted({(r.get('scenario','food_shortage'),r.get('profile','baseline')) for r in rows})
    result['strata'] = {scenario+'/'+profile:summarize_group([r for r in rows
                        if r.get('scenario','food_shortage')==scenario and r.get('profile','baseline')==profile])
                        for scenario,profile in keys}
    return result


def export(output, config, rows):
    payload = {"configuration": config, "trials": rows, "summary": summarize(rows)}
    path = output/"summary.json"
    temporary = output/"summary.tmp"
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False))
    temporary.replace(path)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    if fields:
        with (output/"trials.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                                 for k, v in row.items()})


def run_batch(settings, runs, ticks, seed, output, scenario='food_shortage', tick_seconds=.25, memory_mode='paired', profile=None):
    if settings.provider not in ('rule-based','mock') or scenario not in SCENARIOS:
        raise ValueError('Offline evaluation provider/scenario required')
    if type(runs) is not int or runs<1 or type(ticks) is not int or ticks<0:
        raise ValueError('Positive runs and nonnegative ticks required')
    if memory_mode not in ('paired','on','off'):
        raise ValueError('Invalid memory mode')
    if profile and scenario!='hunting_decisions':
        raise ValueError('Hunting profiles require hunting_decisions')
    profiles = ([profile] if profile else list(HUNTING_PROFILES)) if scenario=='hunting_decisions' else ['baseline']
    if any(p not in HUNTING_PROFILES for p in profiles) and scenario=='hunting_decisions':
        raise ValueError('Unknown hunting profile')
    modes = (False,True) if memory_mode=='paired' else (memory_mode=='on',)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    config = {'format_version':2,'algorithm':('local utility + bounded task planner' if settings.provider=='rule-based' else 'offline mock adapter + local planner'),
              'provider':settings.provider,
              'model':None,'network_enabled':False,'game_mode':'observer','runs':runs,'ticks':ticks,
              'seeds':list(range(seed,seed+runs)),'scenario':scenario,'profiles':profiles,
              'conditions':['MEMORY_ON' if m else 'MEMORY_OFF' for m in modes],
              'social':asdict(settings.social),'wildlife':asdict(settings.wildlife),
              'day_clock':asdict(settings.day_clock),'survival':asdict(settings.survival),
              'action_timing':asdict(settings.action_timing),'food_catalog':{k:asdict(v) for k,v in ITEM_DEFINITIONS.items()},
              'hunting_profiles':HUNTING_PROFILES if scenario=='hunting_decisions' else None,
              'engine_event_limit':4096,'maximum_trajectory_samples':1001}
    (output/'configuration.json').write_text(json.dumps(config,indent=2))
    rows = []
    try:
        for name in profiles:
            for index in range(runs):
                for memory in modes:
                    trial_seed = seed+index
                    print(f'{scenario}/{name}: seed {trial_seed}, MEMORY_{"ON" if memory else "OFF"}',file=sys.stderr,flush=True)
                    try:
                        row = run_trial(settings,trial_seed,ticks,memory,scenario,tick_seconds,name)
                    except Exception as error:
                        row = {'seed':trial_seed,'condition':'MEMORY_ON' if memory else 'MEMORY_OFF',
                               'scenario':scenario,'profile':name,'provider':settings.provider,
                               'status':'failed','error':type(error).__name__}
                    rows.append(row)
                    export(output,config,rows)
    finally:
        export(output,config,rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("rule-based", "mock"), default="rule-based")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument('--scenario',choices=tuple(SCENARIOS),default='food_shortage')
    parser.add_argument('--memory-mode',choices=('paired','on','off'),default='paired')
    parser.add_argument('--profile',choices=tuple(HUNTING_PROFILES))
    parser.add_argument("--max-ai-calls", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--output-root", type=Path, default=Path("experiments"))
    args = parser.parse_args()
    if args.runs < 1 or args.ticks < 0 or args.max_ai_calls < 0:
        parser.error("runs must be positive; ticks and call budget must be nonnegative")
    settings = Settings(provider=args.provider,max_calls=0)
    output = args.output_root/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        rows = run_batch(settings,args.runs,args.ticks,args.seed,output,args.scenario,memory_mode=args.memory_mode,profile=args.profile)
    except KeyboardInterrupt:
        print(f"Interrupted; completed trials saved in {output}", file=sys.stderr)
        return 130
    except ValueError:
        print('Invalid experiment configuration',file=sys.stderr)
        return 2
    except OSError:
        print("Could not write experiment output", file=sys.stderr)
        return 1
    print(output)
    return int(any(r["status"] != "completed" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
