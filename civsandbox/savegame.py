"""Versioned JSON checkpoints; validate a candidate completely before replacing play."""
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import random
import tempfile

from .characters import CHARACTERS
from .cooking import CookingStation
from .daynight import DayClock
from .dialogue import SocialSettings
from .history import WORLD_LIMIT, CONVERSATION_LIMIT, timestamp
from .inventory import Inventory
from .pacing import ActionTiming
from .resources import Resources, ResourceChange
from .social import Memory
from .survival import SurvivalRules
from .wildlife import Chicken, ChickenState, WildlifeSettings
from .world import World, Tile

VERSION = 1
MAX_BYTES = 5_000_000


class SaveError(ValueError):
    """Readable file failure; never includes private settings or file contents."""


def integer(value, low=0, high=10**12):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Integer outside supported range')
    return value


def position(value, world, walkable=True):
    if not isinstance(value,(list,tuple)) or len(value)!=2:
        raise ValueError('Invalid position')
    result = (integer(value[0],0,world.width-1), integer(value[1],0,world.height-1))
    if walkable and not world.walkable(result):
        raise ValueError('Blocked position')
    return result


def text(value, maximum=240):
    if not isinstance(value,str) or not value or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError('Invalid text')
    return value


def tuples(value, depth=0):
    if depth>4:
        raise ValueError('Invalid RNG state')
    return tuple(tuples(v,depth+1) for v in value) if isinstance(value,list) else value


def checkpoint(sim, selected_id=None):
    provider = getattr(sim.decision_provider,'name','rule-based')
    if provider not in ('rule-based','mock'):
        raise SaveError('Only offline providers can be saved')
    social = sim.social
    return {'format':'civsandbox-world','version':VERSION,
            'seed':sim.seed,'scenario':sim.scenario,'tick':sim.tick,
            'provider':provider,'memory_enabled':social.memory_enabled,
            'configuration':{'timing':asdict(sim.progress.timing),'clock':asdict(sim.clock),
                             'survival':asdict(sim.survival),'wildlife':asdict(sim.wildlife.settings),
                             'social':asdict(social.settings)},
            'world':[[tile.value for tile in row] for row in sim.world.tiles],
            'station':{'id':sim.cooking_station.id,'position':sim.cooking_station.position},
            'agents':[{key:asdict(actor)[key] for key in (
                'id','name','position','hunger','energy','inventory','personality','personality_name',
                'facing','incapacitated_until','recovery_grace_until','trust','memories')} for actor in sim.agents],
            'resources':[asdict(bush) for bush in sim.resources.bushes.values()],
            'resource_changes':[asdict(change) for change in sim.resources.changes[-512:]],
            'chickens':[{**asdict(c),'claimed_by':None} for c in sim.wildlife.chickens.values()],
            'wildlife_sequence':sim.wildlife.sequence,'wildlife_home':sim.wildlife.home,
            'respawns':sim.wildlife.respawns,'hunt_cooldowns':sim.wildlife.cooldowns,
            'rng':sim.rng.getstate(),'wildlife_rng':sim.wildlife.rng.getstate(),
            'dialogue_rng':social.dialogue_rng.getstate(),
            'social_tick':social.tick,'request_sequence':social.sequence,
            'agent_cooldowns':social.agent_cooldowns,
            'pair_cooldowns':[[*pair,end] for pair,end in social.pair_cooldowns.items()],
            'request_cooldowns':[[*pair,end] for pair,end in social.request_cooldowns.items()],
            'mode':'participant' if sim.player else 'observer',
            'player_id':sim.player.agent_id if sim.player else None,
            'selected_id':selected_id or sim.selected_id,
            'history':{'world':list(sim.history.world),'conversations':list(sim.history.conversations)},
            'interrupted_actions':bool(sim.progress.jobs or social.active_sessions or social.pending
                                       or sim.player and (sim.player.pending or sim.player.command or sim.player.direction or sim.player.resting)),
            'retention':{'world_events':WORLD_LIMIT,'conversations':CONVERSATION_LIMIT,
                         'memories_per_agent':social.memory_limit,'resource_changes':512}}


def restore(payload):
    """Construct one fully validated replacement; no persisted actions execute."""
    from .simulation import Simulation
    from .config import Settings, create_provider
    if payload['format']!='civsandbox-world' or type(payload['version']) is not int or payload['version']!=VERSION:
        raise ValueError('Unsupported save format/version')
    seed = integer(payload['seed'],-2**63,2**63-1)
    tick = integer(payload['tick'])
    config = payload['configuration']
    if payload['provider'] not in ('rule-based','mock') or type(payload['memory_enabled']) is not bool:
        raise ValueError('Invalid offline provider')
    settings = dict(timing=ActionTiming(**config['timing']),day_clock=DayClock(**config['clock']),
                    survival=SurvivalRules(**config['survival']),wildlife_settings=WildlifeSettings(**config['wildlife']),
                    social_settings=SocialSettings(**config['social']))
    for section in config.values():
        if not isinstance(section,dict) or any(type(v) not in (int,float) or not math.isfinite(v) for v in section.values()):
            raise ValueError('Invalid configuration')
    sim = Simulation(seed,create_provider(Settings(provider=payload['provider'])),
                     memory_enabled=payload['memory_enabled'],memory_path=None,scenario=payload['scenario'],**settings)
    rows = payload['world']
    if len(rows)!=18 or any(len(row)!=24 for row in rows):
        raise ValueError('Unsupported map dimensions')
    world = World(tuple(tuple(Tile(cell) for cell in row) for row in rows))
    station_data = payload['station']
    fire = position(station_data['position'],world,False)
    if station_data['id']!='campfire-1' or world.tiles[fire[1]][fire[0]]!=Tile.CAMPFIRE or sum(t==Tile.CAMPFIRE for row in world.tiles for t in row)!=1:
        raise ValueError('Invalid campfire')
    sim.world,sim.tick = world,tick
    sim.cooking_station = CookingStation('campfire-1',fire)
    sim.resources = Resources(world)
    records = payload['resources']
    if len(records)!=len(sim.resources.bushes):
        raise ValueError('Bush roster mismatch')
    seen = set()
    for record in records:
        point = position(record['position'],world,False)
        if point in seen or point not in sim.resources.bushes:
            raise ValueError('Duplicate or missing bush')
        seen.add(point)
        bush = sim.resources.bushes[point]
        if record['id']!=bush.id:
            raise ValueError('Bush identity mismatch')
        bush.capacity = integer(record['capacity'],1,1000)
        bush.quantity = integer(record['quantity'],0,bush.capacity)
        bush.regeneration_interval = integer(record['regeneration_interval'],1)
        bush.regeneration_progress = integer(record['regeneration_progress'],0,bush.regeneration_interval-1)
        expected_progress = tick % bush.regeneration_interval if bush.quantity < bush.capacity else 0
        if bush.regeneration_progress != expected_progress:
            raise ValueError('Inconsistent resource regeneration clock')
    sim.resources.tick = tick
    sim.resources.changes = []
    if len(payload['resource_changes'])>512:
        raise ValueError('Resource ledger exceeds retention')
    for entry in payload['resource_changes']:
        point = position(entry['position'],world,False)
        if point not in sim.resources.bushes or entry['reason'] not in ('initial','gather','replenish') or entry['agent_id'] not in (*CHARACTERS,None):
            raise ValueError('Invalid resource ledger')
        capacity = sim.resources.bushes[point].capacity
        sim.resources.changes.append(ResourceChange(integer(entry['tick'],0,tick),point,
            integer(entry['before'],0,capacity),integer(entry['after'],0,capacity),entry['reason'],entry['agent_id']))
    sim.resources.cooking_station = sim.cooking_station
    roster = payload['agents']
    if len(roster)!=4 or {a['id'] for a in roster}!=set(CHARACTERS):
        raise ValueError('Invalid/duplicate NPC roster')
    social_tick = integer(payload['social_tick'],tick)
    for record in roster:
        actor = sim.social.agents[record['id']]
        if record['name']!=CHARACTERS[actor.id][0]:
            raise ValueError('NPC artwork/identity mismatch')
        actor.position = position(record['position'],world)
        actor.hunger = integer(record['hunger'],0,100)
        actor.energy = integer(record['energy'],0,100)
        inv = record['inventory']
        actor.inventory = Inventory(integer(inv['capacity'],0,100),inv['items'])
        actor.incapacitated_until = integer(record['incapacitated_until'])
        actor.recovery_grace_until = integer(record['recovery_grace_until'])
        if record['facing'] not in ('up','down','left','right'):
            raise ValueError('Invalid facing')
        actor.facing = record['facing']
        traits = record['personality']
        if not isinstance(traits,dict) or set(traits)!=set(actor.personality) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=5 for v in traits.values()):
            raise ValueError('Invalid personality')
        actor.personality = traits.copy()
        actor.personality_name = text(record['personality_name'],32)
        trust = record['trust']
        if set(trust)!=set(CHARACTERS)-{actor.id}:
            raise ValueError('Invalid directed trust')
        actor.trust = {key:integer(value,-100,100) for key,value in trust.items()}
        memories = record['memories']
        if len(memories)>sim.social.memory_limit:
            raise ValueError('Memory retention exceeded')
        actor.memories = []
        for memory in memories:
            if (memory['actor_id'] not in CHARACTERS or memory['target_id'] not in CHARACTERS
                    or memory['actor_id']==memory['target_id'] or actor.id not in (memory['actor_id'],memory['target_id'])
                    or memory['action'] not in ('TALK','REQUEST_FOOD','SHARE_FOOD','REFUSE_REQUEST','OFFER_FOOD')):
                raise ValueError('Invalid memory participants/action')
            actor.memories.append(Memory(integer(memory['tick'],0,social_tick),memory['actor_id'],memory['target_id'],
                                         memory['action'],text(memory['result'],100),integer(memory['trust_delta'],-200,200)))
    reachable = set(world.reachable(sim.agents[0].position))
    if any(a.position not in reachable for a in sim.agents) or not any(p in reachable for p in world.neighbors(fire)):
        raise ValueError('Disconnected NPC/cooking location')
    wildlife = sim.wildlife
    wildlife.chickens.clear()
    records = payload['chickens']
    if len(records)>wildlife.settings.maximum_population+16:
        raise ValueError('Chicken retention exceeded')
    wildlife.sequence = integer(payload['wildlife_sequence'])
    live_positions = set()
    for record in records:
        key = record['id']
        if not isinstance(key,str) or not key.startswith('chicken-') or not key[8:].isdigit() or not 1<=int(key[8:])<=wildlife.sequence or key != f'chicken-{int(key[8:])}' or key in wildlife.chickens:
            raise ValueError('Duplicate/invalid chicken identity')
        point = position(record['position'],world)
        if point not in reachable or type(record['alive']) is not bool:
            raise ValueError('Invalid chicken state')
        if record['alive'] and point in live_positions:
            raise ValueError('Duplicate living chicken position')
        if record['alive']:
            live_positions.add(point)
        if record['facing'] not in (-1,1) or type(record['facing']) is not int:
            raise ValueError('Invalid chicken direction')
        state = ChickenState(record['state'])
        if record['activity'] not in ('pecking','resting','walking','fleeing','defeated'):
            raise ValueError('Invalid chicken activity')
        wildlife.chickens[key] = Chicken(key,point,state,record['activity'],record['alive'],
            integer(record['threat_radius'],1,24),integer(record['movement_ticks'],1),
            integer(record['next_move_tick']),integer(record['fear_until']),integer(record['calm_until']),
            False,integer(record['facing'],-1,1),None,
            integer(record.get('hp',100 if record['alive'] else 0),0,100),
            integer(record.get('max_hp',100),100,100))
        chicken = wildlife.chickens[key]
        if chicken.alive != (chicken.hp > 0) or chicken.hp % 25:
            raise ValueError('Invalid chicken health')
    if len(live_positions)>wildlife.settings.maximum_population:
        raise ValueError('Population limit exceeded')
    wildlife.tick = tick
    wildlife.home = position(payload['wildlife_home'],world)
    if wildlife.home not in reachable or len(payload['respawns'])>wildlife.settings.maximum_population:
        raise ValueError('Invalid respawn state')
    wildlife.respawns = [integer(value) for value in payload['respawns']]
    wildlife.reserved_tiles = {fire}
    wildlife.events.clear()
    wildlife.cooldowns = {key:integer(value) for key,value in payload['hunt_cooldowns'].items() if key in CHARACTERS}
    if set(payload['hunt_cooldowns'])-set(CHARACTERS):
        raise ValueError('Invalid hunter cooldown')
    sim.resources.wildlife = wildlife
    sim.progress.wildlife = wildlife
    sim.progress.cooking_station = sim.cooking_station
    social = sim.social
    social.tick,social.offset,social.session_tick = social_tick,social_tick-tick,tick
    social.sequence = integer(payload['request_sequence'])
    social.agent_cooldowns = {key:integer(value) for key,value in payload['agent_cooldowns'].items()}
    if set(social.agent_cooldowns)-set(CHARACTERS):
        raise ValueError('Invalid social cooldown')
    for field in ('pair_cooldowns','request_cooldowns'):
        restored = {}
        if len(payload[field])>12:
            raise ValueError('Invalid social pairs')
        for first,second,end in payload[field]:
            if first not in CHARACTERS or second not in CHARACTERS or first==second or (first,second) in restored:
                raise ValueError('Invalid social pair')
            restored[(first,second)] = integer(end)
        setattr(social,field,restored)
    for rng,field in ((sim.rng,'rng'),(wildlife.rng,'wildlife_rng'),(social.dialogue_rng,'dialogue_rng')):
        state = tuples(payload[field])
        if not isinstance(state,tuple) or len(state)!=3:
            raise ValueError('Invalid RNG state')
        if state[2] is not None and (type(state[2]) not in (int,float) or not math.isfinite(state[2])):
            raise ValueError('Invalid RNG Gaussian cache')
        probe = random.Random()
        probe.setstate(state)
        rng.setstate(probe.getstate())
    for field,limit in (('world',WORLD_LIMIT),('conversations',CONVERSATION_LIMIT)):
        history = payload['history'][field]
        if not isinstance(history,list) or len(history)>limit:
            raise ValueError('Invalid history retention')
        for entry in history:
            event_tick = integer(entry['tick'],0,tick)
            if entry['actor_id'] not in (*CHARACTERS,None):
                raise ValueError('Invalid history actor')
            row = {'tick':event_tick,'timestamp':timestamp(sim.clock,event_tick),
                   'actor_id':entry['actor_id'],'text':text(entry['text'])}
            if field=='world':
                row['count'] = integer(entry['count'],1)
            else:
                if entry['target_id'] not in CHARACTERS or entry['actor_id'] not in CHARACTERS or entry['actor_id']==entry['target_id']:
                    raise ValueError('Invalid historical speaker')
                row['target_id'] = entry['target_id']
            getattr(sim.history,field).append(row)
    if payload['mode'] not in ('observer','participant') or payload['selected_id'] not in (*CHARACTERS,None):
        raise ValueError('Invalid mode/selection')
    if payload['mode']=='participant':
        if payload['player_id'] not in CHARACTERS:
            raise ValueError('Invalid controlled NPC')
        sim.set_participant(payload['player_id'])
    elif payload['player_id'] is not None:
        raise ValueError('Observer cannot own a player')
    sim.selected_id = payload['selected_id']
    sim.social.persistence_status = 'world checkpoint; legacy history untouched'
    return sim


def save_game(sim, path, selected_id=None):
    """Atomic replacement; a failed write leaves the previous save intact."""
    path = Path(path)
    temporary = None
    try:
        if path.exists():
            if path.stat().st_size>MAX_BYTES:
                raise ValueError('Existing file too large')
            old = json.loads(path.read_text())
            if old.get('format') != 'civsandbox-world' or old.get('version') != VERSION:
                raise ValueError('Refusing to overwrite another save format')
        payload = checkpoint(sim,selected_id)
        restore(payload)  # Reject impossible live states before writing anything.
        encoded = json.dumps(payload,allow_nan=False,indent=2)
        if len(encoded.encode())>MAX_BYTES:
            raise ValueError('Save exceeds supported size')
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.world-',delete=False) as stream:
            temporary = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError) as error:
        raise SaveError('Could not save world; previous save preserved.') from error
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('Non-finite JSON value')


def load_game(path):
    path = Path(path)
    try:
        if path.stat().st_size>MAX_BYTES:
            raise ValueError('File too large')
        payload = json.loads(path.read_text(),object_pairs_hook=unique_object,parse_constant=invalid_constant)
        sim = restore(payload)
        sim.save_path = path
        return sim
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError) as error:
        raise SaveError('Could not load world: unsupported, damaged or inconsistent save. Current game preserved.') from error


def load_into(sim, path):
    replacement = load_game(path)
    sim.__dict__.clear()
    sim.__dict__.update(replacement.__dict__)
