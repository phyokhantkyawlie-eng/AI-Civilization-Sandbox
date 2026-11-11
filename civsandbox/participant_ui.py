"""Small in-game mode/context menus; no simulation effects outside commands."""
import pygame
from pathlib import Path

from .savegame import save_game, load_into, SaveError

from .actions import Action, ActionType, validate
from .inventory import ITEM_NAMES
from .player import nearby_options

ROLES = {'npc-1': 'Generous gatherer; nature-oriented and cooperative.',
         'npc-2': 'Resource-conscious merchant; ambitious and practical.',
         'npc-3': 'Cautious observer; thoughtful and risk-averse.',
         'npc-4': 'Outgoing adventurer; curious and sociable.'}
MOVES = {pygame.K_w:(0,-1), pygame.K_UP:(0,-1), pygame.K_s:(0,1), pygame.K_DOWN:(0,1),
         pygame.K_a:(-1,0), pygame.K_LEFT:(-1,0), pygame.K_d:(1,0), pygame.K_RIGHT:(1,0)}


class ParticipantUI:
    def __init__(self):
        self.menu = None
        self.page = 0
        self.buttons = []
        self.options = []
        self.allowed = {}
        self.inspect = None
        self.keys = []
        self.previews = {}
        self.layout_token = None
        self.veil = pygame.Surface((1100,750), pygame.SRCALPHA)
        self.veil.fill((0,0,0,125))

    def stop(self, sim):
        self.keys.clear()
        if sim.player:
            sim.player.direction = None

    def open(self, menu, sim):
        self.stop(sim)
        self.menu, self.page = menu, 0
        self.buttons = []
        self.layout_token = None
        self.allowed = {}
        if menu == 'context':
            self.options = []
            seen = set()
            for label, action, target in nearby_options(sim):
                self.options.append((label, action))
                if target not in seen:
                    self.options.append(('Inspect '+target[0], target))
                    seen.add(target)
            self.options += [('Eat berries', Action(ActionType.EAT, item='berries')),
                             ('Eat cooked chicken', Action(ActionType.EAT, item='cooked_chicken')),
                             ('Rest until recovered', Action(ActionType.REST)),
                             ('Cancel activity', 'cancel')]
        if sim.player and menu in ('context','inventory'):
            actor = sim.social.agents[sim.player.agent_id]
            choices = [choice for _,choice in self.options if isinstance(choice,Action)] if menu=='context' else [
                Action(ActionType.EAT,item='berries'),Action(ActionType.EAT,item='cooked_chicken'),Action(ActionType.REST)]
            self.allowed = {choice:validate(choice,actor,sim.world,sim.resources,sim.social) for choice in choices}

    def handle(self, event, sim, renderer):
        """Return True if this event belongs to participant/menu input."""
        if event.type == pygame.WINDOWFOCUSLOST:
            self.stop(sim)
        if event.type == pygame.KEYUP and event.key in MOVES:
            if event.key in self.keys:
                self.keys.remove(event.key)
            if sim.player:
                sim.player.direction = MOVES[self.keys[-1]] if self.keys else None
            return bool(sim.player)
        pending = bool(sim.player and sim.player.pending)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F5:
                path = sim.save_path or Path(__file__).resolve().parent.parent/'data'/'world_save.json'
                try:
                    save_game(sim,path,renderer.selected_id)
                    sim.save_path = path
                    renderer.notify('World saved. F9 loads this checkpoint.')
                except SaveError as error:
                    renderer.notify(str(error))
                return True
            if not pending and event.key in (pygame.K_F1,pygame.K_F9):
                self.open('help' if event.key==pygame.K_F1 else 'load',sim)
                return True
        if pending or self.menu:
            token = ('prompt', id(sim.player.pending)) if pending else ('menu', self.menu)
            if self.layout_token != token:
                self.buttons = []  # Never route a click through a previous menu layout.
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if pending:
                        sim.player.answer(sim, False)
                    else:
                        self.menu = None
                    self.stop(sim)
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    i = event.key-pygame.K_1
                    if i < len(self.buttons):
                        self.choose(self.buttons[i][1], sim, renderer)
                return True
            if event.type == pygame.MOUSEWHEEL:
                self.page = max(0, self.page-event.y)
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, choice in self.buttons:
                    if rect.collidepoint(event.pos):
                        self.choose(choice, sim, renderer)
                        break
                return True
            return event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYUP)
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_m:
            self.open('modes', sim)
            return True
        if not sim.player:
            return False
        if event.key in MOVES and not renderer.debug:
            if event.key not in self.keys:
                self.keys.append(event.key)
            sim.player.direction = MOVES[event.key]
            sim.player.resting = False
            return True
        if event.key == pygame.K_e:
            self.open('context', sim)
            return True
        if event.key == pygame.K_i:
            self.open('inventory', sim)
            return True
        if event.key == pygame.K_BACKSPACE:
            sim.player.cancel(sim)
            self.stop(sim)
            return True
        if event.key == pygame.K_ESCAPE:
            self.open('modes', sim)
            return True
        return False

    def choose(self, choice, sim, renderer):
        if isinstance(choice, tuple) and choice[0] == 'mode':
            sim.set_participant(choice[1])
            renderer.selected_id = choice[1]
            self.menu = None
            self.stop(sim)
        elif isinstance(choice, tuple) and choice[0] == 'answer':
            sim.player.answer(sim, choice[1])
            self.stop(sim)
        elif isinstance(choice, Action):
            if sim.player.submit(choice, sim):
                self.menu = None
        elif isinstance(choice, tuple):
            self.inspect = choice
            self.menu = 'inspect'
        elif choice == 'load':
            path = sim.save_path or Path(__file__).resolve().parent.parent/'data'/'world_save.json'
            try:
                load_into(sim,path)
                renderer.reset_after_load(sim)
            except SaveError as error:
                renderer.notify(str(error))
            self.menu = None
        elif choice == 'cancel':
            sim.player.cancel(sim)
            self.menu = None
        elif choice == 'close':
            self.menu = None

    def button(self, renderer, label, y, choice, enabled=True):
        rect = pygame.Rect(255, y, 590, 38)
        pygame.draw.rect(renderer.screen, (62,86,78) if enabled else (52,58,57), rect, border_radius=5)
        renderer.screen.blit(renderer.font.render(label, True, (237,230,202) if enabled else (161,169,161)), (267,y+10))
        self.buttons.append((rect, choice))

    def draw(self, renderer, sim):
        player = sim.player
        if player:
            actor = sim.social.agents[player.agent_id]
            renderer.screen.blit(renderer.small.render('Participant: '+actor.name+' | M: modes', True, (232,215,164)), (620,24))
            hint = 'E: actions | Click nearby chicken: hit | I: inventory | Backspace: cancel'
            for y, text in ((682, hint), (705, player.message)):
                while renderer.small.size(text)[0] > 840:
                    text = text[:-2]+'…'
                pygame.draw.rect(renderer.screen, (29,43,41), (24,y-2,852,21), border_radius=4)
                renderer.screen.blit(renderer.small.render(text, True, (234,225,199)), (30,y))
        else:
            renderer.screen.blit(renderer.small.render('Observer | M: modes / characters', True, (232,215,164)), (620,24))
        if not self.menu and not (player and player.pending):
            return
        self.buttons = []
        self.layout_token = ('prompt', id(player.pending)) if player and player.pending else ('menu', self.menu)
        renderer.screen.blit(self.veil, (0,0))
        pygame.draw.rect(renderer.screen, (35,49,54), (230,106,640,554), border_radius=12)
        renderer.text('World paused for menu', (255,124), (185,206,189))
        if player and player.pending:
            prompt = player.pending
            peer = sim.social.agents[prompt.actor_id]
            label = 'asks for a berry' if prompt.request_id else {
                ActionType.OFFER_FOOD:'offers you a berry', ActionType.TALK:'would like to talk',
                ActionType.REQUEST_FOOD:'would like to ask for food'}.get(prompt.action.kind, 'would like to interact')
            renderer.text(peer.name+' '+label, (255,170), title=True)
            renderer.text(f'Cancel automatically in {max(0,prompt.remaining_seconds):.0f} seconds. No automatic answer.', (255,214))
            if prompt.request_id:
                actor = sim.social.agents[player.agent_id]
                session = sim.social.session_for(actor)
                questions = [turn.text for turn in session.turns
                             if turn.delivered and turn.purpose == 'question'] if session else []
                if questions:
                    renderer.screen.blit(renderer.small.render('"'+questions[-1]+'"', True,
                                                               (233,221,185)), (255,246))
            accept_label = '1. Share one berry' if prompt.request_id else {
                ActionType.TALK:'1. Greet back (accept)',
                ActionType.OFFER_FOOD:'1. Accept berry and thank',
                ActionType.REQUEST_FOOD:'1. Listen to the request'}.get(prompt.action.kind, '1. Accept')
            self.button(renderer, accept_label, 278, ('answer',True))
            self.button(renderer, '2. Refuse request' if prompt.request_id else '2. Decline invitation', 328, ('answer',False))
            text = player.message
            while renderer.small.size(text)[0] > 580:
                text = text[:-2]+'…'
            renderer.screen.blit(renderer.small.render(text, True, (232,215,164)), (255,398))
            renderer.text('Esc: decline. No food moves until validated completion.', (255,454))
        elif self.menu == 'help':
            renderer.text('Controls and help',(255,170),title=True)
            lines = ['M: choose Observer Mode or control a villager.',
                     'WASD / arrows: move in Participant Mode.',
                     'E: nearby actions. I: inventory / meals / rest.',
                     'Left-click a chicken within one tile: hit (25 HP). Four hits yield raw meat.',
                     'Backspace: cancel unfinished work. Esc: close menus.',
                     'Space: pause. Minus / plus: adjust speed.',
                     'C: conversations. N: village event history.',
                     'F5 / Save: save this world. F9 / Load: review a checkpoint.',
                     'Menus pause everyone. Unanswered invitations cancel safely.',
                     'Food and ingredients change only after an action completes.',
                     'F3: optional detailed inspection. P: plans. S: social sessions.']
            for i,line in enumerate(lines):
                renderer.screen.blit(renderer.small.render(line,True,(221,229,211)),(255,222+i*31))
            self.button(renderer,'1. Back to village',565,'close')
        elif self.menu == 'load':
            renderer.text('Load saved world?',(255,170),title=True)
            renderer.text('Unsaved progress will be replaced.',(255,231))
            renderer.text('Unfinished work resumes safely as idle, without free rewards.',(255,270))
            renderer.text('Legacy social-history files are left untouched.',(255,309))
            self.button(renderer,'1. Load checkpoint',390,'load')
            self.button(renderer,'2. Keep current world',445,'close')
        elif self.menu == 'modes':
            renderer.text('Choose your role', (255,164), title=True)
            for i, actor in enumerate(sim.agents):
                y = 216+i*83
                if actor.id not in self.previews:
                    self.previews[actor.id] = pygame.transform.scale(renderer.assets.for_agent(actor)['down'][0], (48,60))
                renderer.screen.blit(self.previews[actor.id], (250,y-8))
                rect = pygame.Rect(310,y,535,65)
                pygame.draw.rect(renderer.screen, (62,86,78), rect, border_radius=5)
                renderer.text(f'{i+1}. {actor.name} — {actor.personality_name}', (322,y+6))
                renderer.screen.blit(renderer.small.render(ROLES[actor.id], True, (207,221,205)), (322,y+34))
                self.buttons.append((rect, ('mode',actor.id)))
            self.button(renderer, '5. Observer Mode — all four autonomous', 555, ('mode',None))
            renderer.text('Esc: return. Switching preserves this world and inventories.', (255,620))
        elif self.menu == 'context':
            renderer.text('Nearby actions', (255,164), title=True)
            self.page = min(self.page, max(0,len(self.options)-6))
            actor = sim.social.agents[player.agent_id]
            for i, (label, choice) in enumerate(self.options[self.page:self.page+6]):
                enabled = not isinstance(choice,Action) or self.allowed.get(choice,False)
                self.button(renderer, f'{i+1}. '+label+('' if enabled else ' (unavailable)'), 214+i*54, choice, enabled)
            renderer.text('Scroll: more options. 1–6 or click. Esc: close.', (255,564))
            text = player.message
            while renderer.small.size(text)[0]>580:
                text=text[:-2]+'…'
            renderer.screen.blit(renderer.small.render(text,True,(232,215,164)),(255,602))
        elif self.menu == 'inventory':
            actor = sim.social.agents[player.agent_id]
            renderer.text(actor.name+f' — Inventory {actor.inventory.used}/{actor.inventory.capacity}', (255,170), title=True)
            for i, (item, count) in enumerate(actor.inventory.items.items()):
                renderer.text(f'{ITEM_NAMES[item]}: {count}', (255,222+i*30))
            if not actor.inventory.used:
                renderer.text('Empty', (255,222))
            for label, y, action in (
                    ('1. Eat berries',362,Action(ActionType.EAT,item='berries')),
                    ('2. Eat cooked chicken',414,Action(ActionType.EAT,item='cooked_chicken')),
                    ('3. Rest until recovered',466,Action(ActionType.REST))):
                self.button(renderer,label,y,action,self.allowed.get(action,False))
            message = player.message
            while renderer.small.size(message)[0]>580:
                message=message[:-2]+'…'
            renderer.screen.blit(renderer.small.render(message,True,(232,215,164)),(255,524))
            renderer.text('Raw chicken must be cooked. Esc: close.', (255,560))
        elif self.menu == 'inspect':
            kind, key = self.inspect
            renderer.text('Inspect '+kind, (255,170), title=True)
            if kind == 'bush':
                bush = sim.resources.bushes[key]
                lines = ['Berry bush',f'Berries available: {bush.quantity}/{bush.capacity}',
                         f'Next berry in {bush.ticks_until_regeneration*.25:g} seconds' if bush.ticks_until_regeneration is not None else 'Fully grown']
            elif kind == 'chicken':
                chicken = sim.wildlife.chickens.get(key)
                lines = ['Chicken',chicken.activity.capitalize(),'Alive' if chicken.alive else 'No longer alive'] if chicken else ['Chicken no longer present']
            elif kind == 'station':
                station = sim.cooking_station
                lines = ['Campfire','Cooking: '+sim.social.agents[station.occupied_by].name if station.occupied_by else 'Available', 'One raw chicken becomes one cooked chicken.']
            else:
                actor = sim.social.agents[player.agent_id]
                peer = sim.social.agents[key]
                trust = sim.social.trust_for(actor,key)
                label = 'Growing trust' if trust>0 else 'Low trust' if trust<0 else 'Getting acquainted'
                lines = [peer.name+' — '+peer.personality_name,label if sim.social.memory_enabled else 'Historical memory disabled']
                friendly = {'shared one food':'shared a berry','offered one food':'offered a berry',
                            'refused':'declined a request','greeted':'exchanged greetings','pending':'asked for food'}
                lines += [sim.social.agents[m['actor_id']].name+' '+friendly.get(m['result'],'ended an interaction')
                          for m in sim.social.relevant_memories(actor,{key},4)]
            for i, line in enumerate(lines):
                renderer.text(line, (255,230+i*34))
            self.button(renderer, '1. Close', 554, 'close')
