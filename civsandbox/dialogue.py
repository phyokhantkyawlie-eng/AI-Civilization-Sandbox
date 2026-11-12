"""Authored offline turns and session metadata; no effects on needs or inventory."""
from dataclasses import dataclass, field
from enum import Enum
import math


@dataclass(frozen=True)
class SocialSettings:
    agent_cooldown_ticks: int = 40
    pair_cooldown_ticks: int = 96
    request_retry_ticks: int = 80
    repeat_ticks: int = 160
    approach_timeout_ticks: int = 48
    response_timeout_ticks: int = 64
    avoid_ticks: int = 80
    minimum_line_seconds: float = 3.0
    characters_per_second: float = 18.0

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Social durations and reading speed must be finite and positive')
            if name.endswith('_ticks') and type(value) is not int:
                raise ValueError('Social tick settings must be integers')

    def reading_seconds(self, text):
        return max(self.minimum_line_seconds, 1 + len(text)/self.characters_per_second)


class SessionState(str, Enum):
    PROPOSED = 'PROPOSED'
    APPROACHING = 'APPROACHING'
    WAITING_FOR_PARTNER = 'WAITING_FOR_PARTNER'
    ENGAGED = 'ENGAGED'
    RESOLVING = 'RESOLVING'
    COMPLETED = 'COMPLETED'
    CANCELED = 'CANCELED'


@dataclass
class DialogueTurn:
    speaker_id: str
    text: str
    due_tick: int
    duration_ticks: int
    delivered: bool = False
    purpose: str = ""


class IntentKind(str, Enum):
    REQUEST_FOOD = 'REQUEST_FOOD'
    OFFER_FOOD = 'OFFER_FOOD'
    CASUAL_TALK = 'CASUAL_TALK'
    CHECK_ON_PLAYER = 'CHECK_ON_PLAYER'
    THANK_PLAYER = 'THANK_PLAYER'


@dataclass(frozen=True)
class ConversationIntent:
    kind: IntentKind
    item: str | None = None
    quantity: int = 0
    context: dict = field(default_factory=dict)

    def __post_init__(self):
        food = self.kind in (IntentKind.REQUEST_FOOD, IntentKind.OFFER_FOOD)
        if not isinstance(self.kind,IntentKind) or type(self.quantity) is not int:
            raise ValueError('Invalid conversation intent')
        if (food and (self.item!='berries' or self.quantity!=1)
                or not food and (self.item is not None or self.quantity!=0)):
            raise ValueError('Only existing one-berry social transfers are supported')


@dataclass
class InteractionSession:
    id: str
    initiator_id: str
    recipient_id: str
    purpose: str
    state: SessionState
    started_tick: int
    deadline: int
    current_turn: int = -1
    turns: list[DialogueTurn] = field(default_factory=list)
    outcome: str | None = None
    cooldown_until: int = 0
    request_id: str | None = None
    finish_tick: int | None = None
    target_position: tuple[int,int] | None = None
    greeting_recorded: bool = False
    intent: ConversationIntent | None = None
    intent_presented: bool = False
    intent_resolution: str | None = None

    @property
    def participants(self):
        return (self.initiator_id, self.recipient_id)


BANKS = {
    'greeting': ('Good to see you.', 'How is your day going?', 'Hello! Taking a short break?'),
    'campfire': ('Mind some company by the fire?', 'A quiet moment by the fire sounds nice.', 'Shall we take a short break here?'),
    'cautious': ('It seems quiet here. Hello.', 'Hello. Mind a little company?', 'Good to see a familiar face.'),
    'friendly': ('Hello! How are things going?', 'Nice to run into you.', 'Good to have some company.'),
    'nature': ('Good to see you out here.', 'It is nice to take a quiet break.', 'Hello! Mind some company?'),
    'practical': ('A short break before getting back to work?', 'Hello. How are your supplies?', 'Good to see you. Taking a break?'),
    'helped': ('Thanks again for the berry.', 'I remember your help. Thank you.', 'Good to see you. Thanks for helping earlier.'),
    'warm': ('Nice to have your company.', 'It is good to see you.', 'Glad we have a moment to talk.'),
    'reserved': ('Hello. Let us keep this brief.', 'Hello. A short conversation is fine.', 'I can spare a short moment.'),
    'reply': ('Good to see you too.', 'Hello! A short break sounds good.', 'Hello. Nice to see you.'),
    'question': ('Could you spare one berry?', 'May I have a berry, please?', 'I could use a berry. Can you help?', 'Do you have a berry to share?'),
    'urgent_question': ('I am very hungry. Could you spare a berry?', 'Could you help? I really need a berry.', 'I need something to eat. Can you spare a berry?', 'Could I have a berry? I am very hungry.'),
    'consider': ('Let me see what I can spare.', 'Let me check my berries.', 'One moment, let me check.'),
    'offer': ('Would a berry help?', 'You look hungry. May I offer a berry?', 'I have a berry I could share.'),
    'shared': ('Here, take one berry.', 'This berry is for you.', 'Here is a berry to help.'),
    'empty': ('I have no berries to share.', 'Sorry, I do not have a berry to spare.', 'I have no spare berries right now.'),
    'own_need': ('I need these berries for my next meal.', 'Sorry, I need to keep my berries for now.', 'I need to eat too. I will keep this one.'),
    'refusal': ('I will keep my berries for now.', 'I cannot spare a berry this time.', 'Sorry, I am keeping my supplies.'),
    'thanks': ('Thank you. That helps.', 'Thanks for sharing a berry.', 'I appreciate the help.'),
    'acknowledge': ('All right. I will find another way.', 'Okay. Thanks for answering.', 'I understand. I will keep looking.'),
}


def choose_line(social, speaker, partner, purpose, essential=False):
    """Only called for accepted turns or committed interaction outcomes."""
    key = purpose
    if purpose == 'greeting':
        memories=social.relevant_memories(speaker,{partner.id})
        helped=any(m['actor_id']==partner.id and m['target_id']==speaker.id
                   and m['result'] in ('shared one food','offered one food') and m['tick']<social.tick
                   for m in memories)
        trust=social.trust_for(speaker,partner.id)
        if helped:
            key='helped'
        elif trust>=20:
            key='warm'
        elif trust<=-20:
            key='reserved'
        elif speaker.personality.get('risk_aversion', .5) >= .8:
            key = 'cautious'
        elif speaker.personality.get('sociability', .5) >= .8:
            key = 'friendly'
        elif speaker.personality.get('nature_affinity',.5)>=.8:
            key='nature'
        elif speaker.personality.get('resource_focus',.5)>=.8:
            key='practical'
    elif purpose == 'question' and speaker.hunger >= 85:
        key = 'urgent_question'
    elif purpose == 'refusal':
        key = 'empty' if speaker.food == 0 else 'own_need' if speaker.hunger >= 55 else 'refusal'
    options = BANKS[key]
    history = social.repeated_lines
    available = [line for line in options
                 if social.tick-history.get((speaker.id, partner.id, line), -100000) >= social.settings.repeat_ticks]
    if not available:
        if not essential:
            return None
        # Essential requests remain possible; pair/request cooldowns still apply.
        available = [min(options, key=lambda line: history.get((speaker.id, partner.id, line), -100000))]
    return social.dialogue_rng.choice(available)
