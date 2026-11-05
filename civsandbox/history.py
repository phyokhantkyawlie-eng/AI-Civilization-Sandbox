"""Bounded, timestamped presentation histories from committed simulation events."""
from collections import deque

from .inventory import ITEM_NAMES

WORLD_LIMIT = 200
CONVERSATION_LIMIT = 120


def timestamp(clock, tick):
    moment = clock.at(tick)
    return f'Day {moment.day} {moment.hour:02d}:{moment.minute:02d}'


def world_message(event, names):
    actor = names.get(event.get('actor_id'), event.get('agent', 'Villager'))
    target = names.get(event.get('target_id'), 'a neighbor')
    action, result = event['action'], event.get('result')
    if event.get('social'):
        phrases = {'pending':f'{actor} asked {target} for food',
                   'shared one food':f'{actor} shared a berry with {target}',
                   'offered one food':f'{actor} offered {target} a berry',
                   'refused':f'{actor} declined {target}\'s request'}
        text = phrases.get(result)
        if text and any(value > 0 for value in event.get('trust_changes', {}).values()):
            text += '; trust grew'
        elif text and any(value < 0 for value in event.get('trust_changes', {}).values()):
            text += '; trust fell slightly'
        return text
    if action == 'SURVIVAL':
        return actor+(' is recovering' if result=='incapacitated' else ' is ready to act again')
    if action == 'HUNT_FAILED':
        return actor+' could not catch a chicken'
    if not event.get('executed'):
        return None
    return {'GATHER':f'{actor} picked berries', 'HUNT':f'{actor} collected raw chicken',
            'COOK':f'{actor} cooked chicken',
            'EAT':f'{actor} ate {ITEM_NAMES.get(event.get("item"), "Berries").lower()}'}.get(action)


class History:
    def __init__(self):
        self.world = deque(maxlen=WORLD_LIMIT)
        self.conversations = deque(maxlen=CONVERSATION_LIMIT)
        self.last_event = 0

    def consume(self, events, clock, social):
        names = {key:actor.name for key,actor in social.agents.items()}
        fresh = []
        for event in reversed(events):
            if event.get('event_id',0) <= self.last_event:
                break
            fresh.append(event)
        for event in reversed(fresh):
            self.last_event = event['event_id']
            if event['action'] == 'DIALOGUE':
                session = social.sessions.get(event.get('session_id'))
                turn = event.get('turn')
                if (session and type(turn) is int and 0 <= turn < len(session.turns)
                        and session.turns[turn].delivered
                        and session.turns[turn].speaker_id == event.get('actor_id')
                        and session.turns[turn].text == event.get('text')):
                    self.conversations.append({key:event[key] for key in ('tick','actor_id','target_id','text')})
                    self.conversations[-1]['timestamp'] = timestamp(clock,event['tick'])
                continue
            text = world_message(event,names)
            if text:
                # Collapse repeated work by the same actor, retaining the count
                # and latest timestamp rather than spamming a second log row.
                if self.world and self.world[-1]['text']==text and event['tick']-self.world[-1]['tick']<=60:
                    self.world[-1]['count'] += 1
                    self.world[-1]['tick'] = event['tick']
                    self.world[-1]['timestamp'] = timestamp(clock,event['tick'])
                else:
                    self.world.append({'tick':event['tick'],'timestamp':timestamp(clock,event['tick']),
                                       'actor_id':event.get('actor_id'),'text':text,'count':1})
