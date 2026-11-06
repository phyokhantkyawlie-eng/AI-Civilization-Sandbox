"""Pygame presentation and input; all world updates live in simulation.py."""
import pygame

from .simulation import FixedTicker, Simulation
from .world import Tile
from .animation import SpriteAnimator, CharacterView
from .feedback import Feedback
from .participant_ui import ParticipantUI
from .characters import CHARACTERS
from .history import timestamp
from .ui_state import (activity, hunger_status, energy_status, StatusThresholds,
                       CHARACTER_ROLES, inventory_lines, goal_label, relationship_summary, action_progress)
from .sprites import CharacterAssets, FOOT_ANCHOR, FRAME_SIZE

SOCIAL_LABELS = {"REQUEST_FOOD": "ask", "SHARE_FOOD": "share", "OFFER_FOOD": "offer",
                 "REFUSE_REQUEST": "refuse", "TALK": "talk"}

WINDOW = (1100, 750)
TILE_SIZE = 36
ORIGIN = (20, 78)


class Renderer:
    def __init__(self, animation_fps=8.0, window_scale=1.0, idle_fps=4.0):
        pygame.display.init()
        pygame.font.init()
        if window_scale not in (.85,1.0,1.25):
            raise ValueError('Window scale must be 0.85, 1 or 1.25')
        self.display = pygame.display.set_mode(tuple(round(size*window_scale) for size in WINDOW))
        self.screen = self.display if window_scale==1 else pygame.Surface(WINDOW).convert()
        pygame.display.set_caption("AI Civilization Sandbox | Animated Characters")
        self.font = pygame.font.Font(None, 23)
        self.title = pygame.font.Font(None, 32)
        self.small = pygame.font.Font(None, 19)
        self.station_labels={busy:self.small.render(label,True,(250,226,166)) for busy,label in
                             ((False,"Campfire · Ready"),(True,"Campfire · Busy"))}
        self.selected_id = None
        self.debug = False
        self.plan_debug = False
        self.social_debug = False
        self.history_open = False
        self.history_page = 0
        self.world_history_open = False
        self.news_page = 0
        self.notification = ""
        self.notification_seconds = 0
        self.selected_bush = None
        self.inspector_tab = "State"
        self.memory_page = 0
        self.assets = CharacterAssets()
        self.animation_fps = animation_fps
        self.idle_fps = idle_fps
        self.animation_preview = False
        self.preview_character = 0
        self.preview_clock = 0.0
        self.preview_animators = {}
        for key in ("mira", "nyra", "kairo", "ren"):
            self.preview_animators[key] = {
                d: SpriteAnimator(self.assets.frames[key], self.animation_fps,
                                  idle_frames=self.assets.idle_frames[key], idle_fps=self.idle_fps)
                for d in ("down", "left", "right", "up")}
        self.preview_background = 0
        self.characters = {}
        self.character_rects = {}
        self.chicken_rects = {}
        self.feedback = Feedback()
        self.participant_ui = ParticipantUI()
        self.ground_cache = {}
        self.lighting_cache = {}
        self.name_labels = {}
        self.draw_feet = {}
        self.control_buttons = {}
        self.map_rect = pygame.Rect(ORIGIN, (24*TILE_SIZE, 18*TILE_SIZE))

    def text(self, text, position, color=(225, 233, 235), title=False):
        self.screen.blit((self.title if title else self.font).render(text, True, color), position)

    def draw(self, simulation, ticker):
        if simulation.player and not self.debug:
            self.selected_id = simulation.player.agent_id
        self.screen.fill((24, 34, 39))
        pygame.draw.rect(self.screen, (35, 49, 54), (892, 74, 204, 666), border_radius=10)
        pygame.draw.rect(self.screen, (123, 110, 77), self.map_rect.inflate(6, 6), 3, border_radius=4)
        self.text("AI CIVILIZATION SANDBOX", (20, 18), title=True)
        ai = simulation.ai_summary()
        self.text(f"{simulation.scenario.replace('_', ' ').title()} / Provider: {ai['provider']} / API calls: {ai['api_calls']}/{ai['max_calls']}",
                  (20, 49), (151, 175, 183))
        recall = "on" if simulation.social.memory_enabled else "off"
        self.screen.blit(self.small.render(
            f"Recall: {recall} / History: {simulation.social.persistence_status}",
            True, (151, 175, 183)), (650, 53))
        self.sync_characters(simulation)
        self.feedback.consume(simulation.events, simulation.social)
        if simulation.paused:
            self.advance_animation(0, True)
        layers = []
        for y, row in enumerate(simulation.world.tiles):
            for x, tile in enumerate(row):
                rect = pygame.Rect(ORIGIN[0]+x*TILE_SIZE, ORIGIN[1]+y*TILE_SIZE, TILE_SIZE, TILE_SIZE)
                key = (tile, (x*7+y*11) % 4)
                if key not in self.ground_cache:
                    surface = pygame.Surface((TILE_SIZE, TILE_SIZE))
                    dirt = tile == Tile.DIRT
                    surface.fill((169, 140, 95) if dirt else (91+key[1]*2, 133+key[1]*2, 76))
                    for i in range(5):
                        px, py = (i*13+key[1]*7)%32+2, (i*11+key[1]*5)%32+2
                        if dirt:
                            pygame.draw.line(surface, (151, 123, 84), (px, py), (px+2, py))
                        else:
                            pygame.draw.line(surface, (112, 151, 86), (px, py), (px-1, py-3))
                    if not dirt and key[1] == 2:
                        pygame.draw.circle(surface, (219, 196, 121), (10, 14), 1)
                    self.ground_cache[key] = surface
                self.screen.blit(self.ground_cache[key], rect)
                if tile == Tile.WATER:
                    self.draw_feature(tile, rect, simulation, (x, y))
                elif tile in (Tile.TREE, Tile.BUSH, Tile.HOUSE):
                    layers.append((rect.bottom-4, 0, (tile, rect, (x, y))))
        self.draw_feet = {}
        for agent in simulation.agents:
            view = self.characters[agent.id]
            foot = self.foot_position(view)
            companions = [a for a in simulation.agents if a.position == agent.position]
            if len(companions) > 1:
                index = companions.index(agent)
                foot = (foot[0]+round((index-(len(companions)-1)/2)*12), foot[1])
            self.draw_feet[agent.id] = foot
            layers.append((foot[1], 1, (agent, foot)))
        station=simulation.cooking_station
        layers.append((ORIGIN[1]+station.position[1]*TILE_SIZE+30,3,station))
        self.chicken_rects.clear()
        for chicken in simulation.wildlife.living():
            foot = (ORIGIN[0]+chicken.position[0]*TILE_SIZE+18,
                    ORIGIN[1]+chicken.position[1]*TILE_SIZE+31)
            layers.append((foot[1], 2, (chicken, foot)))
        # Ground first, then terrain/characters sorted by feet so foreground objects occlude correctly.
        self.character_rects.clear()
        for _, kind, item in sorted(layers, key=lambda layer: (layer[0], layer[1])):
            if kind == 0:
                tile, rect, position = item
                self.draw_feature(tile, rect, simulation, position)
            elif kind == 1:
                agent, foot = item
                self.draw_character(agent, foot)
            elif kind == 2:
                chicken, foot = item
                if simulation.player and simulation.social.nearby(simulation.social.agents[simulation.player.agent_id],chicken):
                    pygame.draw.ellipse(self.screen,(237,213,143),(foot[0]-16,foot[1]-5,32,9),2)
                self.draw_chicken(chicken, foot, simulation.tick)
            else:
                if simulation.player and simulation.social.agents[simulation.player.agent_id].position in simulation.world.neighbors(item.position):
                    x,y=ORIGIN[0]+item.position[0]*TILE_SIZE,ORIGIN[1]+item.position[1]*TILE_SIZE
                    pygame.draw.ellipse(self.screen,(237,213,143),(x+2,y+17,32,15),2)
                self.draw_campfire(item)
        # Labels are drawn above foreground terrain so every villager stays identifiable.
        for agent in simulation.agents:
            rect = self.character_rects[agent.id]
            if agent.name not in self.name_labels:
                self.name_labels[agent.name] = self.small.render(agent.name, True, (252, 240, 207))
            label = self.name_labels[agent.name]
            y = rect.top-15 if rect.top >= ORIGIN[1]+7 else rect.bottom
            companions = [a for a in simulation.agents if a.position == agent.position]
            y -= companions.index(agent)*16
            background = pygame.Rect(rect.centerx-label.get_width()//2-4, y-1, label.get_width()+8, 16)
            pygame.draw.rect(self.screen, (29, 43, 41), background, border_radius=4)
            if agent.id == self.selected_id:
                pygame.draw.rect(self.screen,(237,213,143),background,1,border_radius=4)
            self.screen.blit(label, (background.x+4, y))
        darkness = simulation.time_of_day.darkness
        if darkness:
            if darkness not in self.lighting_cache:
                tint = pygame.Surface(self.map_rect.size, pygame.SRCALPHA)
                tint.fill((15, 22, 55, darkness))
                self.lighting_cache[darkness] = tint
            self.screen.blit(self.lighting_cache[darkness], self.map_rect)
        for agent in simulation.agents:
            if simulation.social.engaged(agent):
                rect=self.character_rects[agent.id]
                badge=pygame.Rect(rect.right-2,rect.top+12,13,8)
                pygame.draw.ellipse(self.screen,(237,223,177),badge)
                for dx in (3,6,9):
                    pygame.draw.circle(self.screen,(57,78,66),(badge.x+dx,badge.y+4),1)
        self.draw_feedback()
        if self.debug and self.social_debug:
            self.draw_session_debug(simulation)
        elif self.debug and self.plan_debug:
            self.draw_plan_debug(simulation)
        elif self.debug:
            self.text("PAUSED" if simulation.paused else "RUNNING", (900, 82), title=True)
            self.text(f"Tick {simulation.tick} / {ticker.speed:g}x", (900, 116))
            self.text(f"Seed: {simulation.seed}", (900, 141))
            self.screen.blit(self.small.render("Tab: inspect / P: plans / S: social", True, (168, 187, 192)), (900, 163))
            for i, tab in enumerate(("State", "Traits", "Trust", "Memory")):
                rect = pygame.Rect(900+i*48, 183, 46, 23)
                pygame.draw.rect(self.screen, (57, 81, 89) if tab == self.inspector_tab else (36, 48, 56), rect)
                self.screen.blit(self.small.render(tab, True, (225, 233, 235)), (rect.x+2, rect.y+4))
            selected = next((a for a in simulation.agents if a.id == self.selected_id), None)
            if selected:
                self.draw_inspector(selected, simulation)
            status = ai["agents"].get(self.selected_id, {})
            provider_label = ai.get("mode") if ai.get("mode") == "offline rules" else ai["provider"]
            self.text(f"Provider: {provider_label}", (900, 390))
            self.text(selected.current_action if selected else "No selection", (900, 414))
            self.text(f"Fallback: {'yes' if status.get('fallback') else 'no'}", (900, 438))
            explanation = status.get("reason") if status.get("fallback") else status.get("explanation")
            empty_message = "Select a villager" if selected is None else "No model decision recorded"
            words = (explanation or empty_message).split()
            lines, line = [], ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if self.small.size(candidate)[0] > 186 and line:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for i, line in enumerate(lines[:3]):
                self.screen.blit(self.small.render(line, True, (187, 207, 212)), (900, 465+i*18))
            if selected and ai["provider"] in ("mock", "gemini"):
                self.text("RECENT AI EVENTS", (900, 528))
                visible = [e for e in simulation.events if e["action"] == "AI_DECISION"
                           and e["agent"] == selected.name][-5:]
            else:
                self.text("LIVE EVENTS", (900, 528))
                visible = [e for e in simulation.events if e.get("changed") or e.get("social")
                           or e["action"] in ("GATHER", "EAT", "REJECTED", "AI_DECISION")][-5:]
            social_events = [event for event in reversed(simulation.events) if event.get("social")][:3]
            if social_events:
                pygame.draw.rect(self.screen, (35, 49, 54), (900, 526, 194, 20))
                self.text("SOCIAL EVENTS", (900, 528))
                names = {a.id: a.name for a in simulation.agents}
                for i, event in enumerate(reversed(social_events)):
                    actor = names.get(event.get("actor_id"), event.get("agent", "?"))
                    target = names.get(event.get("target_id"), "?")
                    changes = event.get("trust_changes", {})
                    delta = "/".join(f"{names.get(key, key)}{value:+d}" for key, value in changes.items())
                    lines = [f"t{event['tick']} {actor} > {target}",
                             f"{SOCIAL_LABELS.get(event['action'], event['action'])}: {event.get('result', '')}",
                             f"Trust {delta}" if changes else "No trust change"]
                    for row, text in enumerate(lines):
                        while self.small.size(text)[0] > 190:
                            text = text[:-2]+"…"
                        self.screen.blit(self.small.render(text, True, (235, 212, 157) if row == 0 else (187, 207, 212)),
                                         (900, 548+i*42+row*14))
            else:
                for i, event in enumerate(visible):
                    activity = event.get("reason") if event.get("fallback") else event.get("decision", event["action"])
                    line = f"{event['tick']} {event['agent']}: {activity}"
                    while self.small.size(line)[0] > 190:
                        line = line[:-2]+"…"
                    self.screen.blit(self.small.render(line, True, (187, 207, 212)), (900, 554+i*20))
        else:
            self.draw_friendly_panel(simulation, ticker)
            self.draw_conversation_panel(simulation)
            self.draw_world_history(simulation)
        simulation.selected_id = self.selected_id
        self.draw_controls(simulation)
        self.participant_ui.draw(self, simulation)
        if self.animation_preview:
            self.draw_animation_preview(simulation)
        if self.screen is not self.display:
            pygame.transform.smoothscale(self.screen,self.display.get_size(),self.display)
        pygame.display.flip()


    def sync_characters(self, simulation):
        for agent in simulation.agents:
            if agent.id not in self.characters:
                self.characters[agent.id] = CharacterView(
                    agent.position, SpriteAnimator(self.assets.for_agent(agent), self.animation_fps,
                                    idle_frames=self.assets.idle_for_agent(agent), idle_fps=self.idle_fps))
                self.characters[agent.id].animator.update(0,False,agent.facing)
            elif self.characters[agent.id].logical_position != agent.position:
                # draw() used without tick callbacks (e.g. a restored snapshot): snap, never cut corners.
                self.characters[agent.id].snap(agent.position)

    def capture_tick(self, simulation, seconds):
        for agent in simulation.agents:
            if agent.id not in self.characters:
                self.characters[agent.id] = CharacterView(
                    agent.position, SpriteAnimator(self.assets.for_agent(agent), self.animation_fps,
                                    idle_frames=self.assets.idle_for_agent(agent), idle_fps=self.idle_fps))
                self.characters[agent.id].animator.update(0,False,agent.facing)
            else:
                self.characters[agent.id].capture(agent.position, seconds)
            view = self.characters[agent.id]
            view.idle_direction = agent.facing if (simulation.progress.held(agent) or simulation.social.active_requests(agent)) else None
            if not view.segments:
                view.animator.update(0, False, view.idle_direction)

    def advance_animation(self, elapsed, paused=False, **timing):
        if not paused:
            real_dt = elapsed/timing.get("speed", 1)
            self.preview_clock += real_dt
            moving = self.preview_clock % 3 < 1
            if self.animation_preview:
                for rows in self.preview_animators.values():
                    for direction, animator in rows.items():
                        animator.update(real_dt, moving, direction)
            self.feedback.advance(elapsed)
            self.feedback.advance_reading(elapsed/timing.get("speed",1))
        for view in self.characters.values():
            view.advance(elapsed, paused, **timing)

    @staticmethod
    def foot_position(view):
        return (round(ORIGIN[0]+view.position[0]*TILE_SIZE+TILE_SIZE/2),
                round(ORIGIN[1]+view.position[1]*TILE_SIZE+TILE_SIZE-2))

    def draw_character(self, agent, foot):
        view = self.characters[agent.id]
        pygame.draw.ellipse(self.screen, (44, 64, 44), (foot[0]-9, foot[1]-4, 18, 7))
        if agent.id == self.selected_id:
            pygame.draw.ellipse(self.screen, (255, 239, 147), (foot[0]-14, foot[1]-6, 28, 11), 2)
        rect = pygame.Rect(foot[0]-FOOT_ANCHOR[0], foot[1]-FOOT_ANCHOR[1], *FRAME_SIZE)
        # Activity feedback maps to generic idle until dedicated action art is provided.
        frame = view.animator.frame
        self.screen.blit(frame, rect)
        self.character_rects[agent.id] = rect

    def draw_animation_preview(self, simulation):
        """Overlay in the existing game: cached art, no simulation writes."""
        keys = ("mira", "nyra", "kairo", "ren")
        key = keys[self.preview_character]
        panel = pygame.Rect(35,100,835,625)
        color = ((35,45,55),(228,233,235),(90,135,75))[self.preview_background]
        pygame.draw.rect(self.screen,color,panel)
        ink = (25,35,45) if self.preview_background == 1 else (240,225,195)
        self.screen.blit(self.font.render(f"Animation preview: {key.title()} | 1-4 character | B background | F8 close",True,ink),(50,110))
        self.screen.blit(self.small.render("Each row: walking idle reference | new idle frames | live WALK -> IDLE (1s / 2s)",True,ink),(50,139))
        for row,direction in enumerate(("down","left","right","up")):
            y=171+row*112
            self.screen.blit(self.small.render(direction.upper(),True,ink),(50,y+35))
            frames=[self.assets.frames[key][direction][0]]+self.assets.idle_frames[key][direction]
            for col,frame in enumerate(frames):
                x=130+col*95
                self.screen.blit(pygame.transform.smoothscale(frame,(80,100)),(x,y))
                pygame.draw.line(self.screen,(210,90,70),(x,y+96),(x+80,y+96))
            animator=self.preview_animators[key][direction]
            self.screen.blit(pygame.transform.smoothscale(animator.frame,(80,100)),(690,y))
            self.screen.blit(self.small.render(f"{animator.state} {animator.index}",True,ink),(775,y+35))
        engaged = [a for a in simulation.agents if simulation.social.engaged(a)]
        label = "Live conversation: " + (", ".join(f"{a.name} {self.characters[a.id].animator.direction}/{self.characters[a.id].animator.state}" for a in engaged) or "none active; close preview to observe villagers")
        self.screen.blit(self.small.render(label,True,ink),(50,640))
        self.screen.blit(self.small.render("Preview changes no positions, dialogue timers, or social state. Red lines mark foot anchors.",True,ink),(50,682))

    def draw_controls(self, simulation):
        self.control_buttons = {}
        for key, label, x, width in (("pause", "Resume" if simulation.paused else "Pause", 900, 88),
                                     ("slower", "-", 992, 44), ("faster", "+", 1040, 44)):
            rect = pygame.Rect(x, 674, width, 28)
            pygame.draw.rect(self.screen, (70, 91, 89), rect, border_radius=5)
            self.screen.blit(self.small.render(label, True, (245, 230, 191)), (x+10, 682))
            self.control_buttons[key] = rect
        for key,label,x in (('save','Save',900),('load','Load',965),('help','Help',1030)):
            rect = pygame.Rect(x,712,59,26)
            pygame.draw.rect(self.screen,(55,74,73),rect,border_radius=4)
            self.screen.blit(self.small.render(label,True,(225,225,205)),(x+10,719))
            self.control_buttons[key] = rect

    def draw_bar(self, title, value, description, color, y):
        self.text(title, (906, y))
        self.screen.blit(self.small.render(description, True, color), (1000, y+3))
        pygame.draw.rect(self.screen, (22, 34, 39), (906, y+24, 178, 12), border_radius=5)
        width = round(178*max(0, min(100, value))/100)
        if width:
            pygame.draw.rect(self.screen, color, (906, y+24, width, 12), border_radius=5)

    def wrapped(self, text, x, y, width=178, max_lines=3, color=(218,228,217)):
        lines, line = [], ''
        for word in text.split():
            candidate = (line+' '+word).strip()
            if self.small.size(candidate)[0]>width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        for i, line in enumerate(lines[:max_lines]):
            self.screen.blit(self.small.render(line,True,color),(x,y+i*17))
        return y+min(len(lines),max_lines)*17

    def notify(self, text):
        self.notification, self.notification_seconds = text, 6.0

    def reset_after_load(self, simulation):
        self.characters.clear()
        self.character_rects.clear()
        self.chicken_rects.clear()
        self.feedback = Feedback()
        self.selected_id = simulation.selected_id
        self.selected_bush = None
        self.history_open = self.world_history_open = False
        self.history_page = self.news_page = 0
        self.participant_ui.stop(simulation)
        simulation.paused = True
        self.notify('World loaded. Unfinished activities released safely. Press Play to continue.')

    def draw_friendly_panel(self, simulation, ticker):
        pygame.draw.rect(self.screen,(24,34,39),(0,0,1100,74))
        self.text('AI CIVILIZATION SANDBOX',(20,17),title=True)
        now = simulation.time_of_day
        self.text(f'Day {now.day}  ·  {now.hour:02d}:{now.minute:02d}  ·  {now.period.title()}',
                  (20,49),(193,205,181))
        self.screen.blit(self.small.render('Campfire: '+('Busy' if simulation.cooking_station.occupied_by else 'Ready'),
                                         True,(222,202,153)),(460,49))
        latest = self.notification if self.notification_seconds>0 else (
            simulation.history.world[-1]['text'] if simulation.history.world else 'F1: controls and help')
        while self.small.size(latest)[0]>430:
            latest = latest[:-2]+'…'
        self.screen.blit(self.small.render(latest,True,(216,209,177)),(640,49))
        self.text('F3 · Details',(944,24),(193,205,181))
        pygame.draw.rect(self.screen,(35,49,54),(892,74,204,594),border_radius=10)
        self.text('Paused' if simulation.paused else 'Village life',(906,87))
        self.screen.blit(self.small.render(f'{ticker.speed:g}x speed',True,(184,202,191)),(1018,94))
        actor = next((a for a in simulation.agents if a.id==self.selected_id),None)
        if actor:
            portrait = self.assets.for_agent(actor)['down'][0]
            self.screen.blit(portrait,(906,128))
            self.text(actor.name,(959,132),title=True)
            self.screen.blit(self.small.render(CHARACTER_ROLES[actor.id],True,(222,201,154)),(959,160))
            self.wrapped(activity(actor,simulation),906,192,max_lines=2,color=(235,222,184))
            progress = action_progress(actor,simulation)
            if progress is not None:
                pygame.draw.rect(self.screen,(22,34,39),(906,231,178,4),border_radius=2)
                pygame.draw.rect(self.screen,(221,187,111),(906,231,round(178*progress),4),border_radius=2)
            rules = simulation.survival
            thresholds = StatusThresholds(rules.hungry,rules.inefficient_hunger,rules.rest_energy,rules.collapse_energy)
            label,color = hunger_status(actor.hunger,thresholds)
            self.draw_bar('Hunger',actor.hunger,label,color,244)
            label,color = energy_status(actor.energy,thresholds)
            self.draw_bar('Energy',actor.energy,label,color,294)
            self.text('Inventory',(906,350))
            self.screen.blit(self.small.render(f'{actor.inventory.used}/{actor.inventory.capacity} slots',True,(184,202,191)),(1026,353))
            for row,line in enumerate(inventory_lines(actor)):
                self.screen.blit(self.small.render(line,True,(226,199,166)),(906,379+row*19))
            self.wrapped('Goal: '+goal_label(actor,simulation),906,441,max_lines=2)
            self.wrapped(relationship_summary(actor,simulation.social),906,488,max_lines=2,color=(183,209,187))
        elif self.selected_bush is not None:
            bush = simulation.resources.bushes[self.selected_bush]
            self.text('Berry bush',(906,153),title=True)
            self.text(f'Berries {bush.quantity}/{bush.capacity}',(906,204))
            self.wrapped('Ready to gather' if bush.quantity else 'Depleted; growing new berries',906,250)
            remaining = bush.ticks_until_regeneration
            if remaining is not None:
                self.text(f'Next berry in {remaining*.25:g}s',(906,310))
                self.draw_bar('Regrowth',100*bush.regeneration_progress/bush.regeneration_interval,'',(106,164,104),350)
            else:
                self.text('Fully grown',(906,310))
            self.wrapped('Participant: approach and press E to gather or inspect.',906,424,max_lines=4)
        else:
            self.text('Meet the villagers',(906,153))
            self.wrapped('Click a character to inspect their life. Press M to participate.',906,196,max_lines=5)
        self.text('Village news · N',(906,536))
        records = list(simulation.history.world)[-2:]
        y = 556
        for record in reversed(records):
            self.screen.blit(self.small.render(record['timestamp'],True,(157,185,172)),(906,y))
            suffix = f" (x{record['count']})" if record['count']>1 else ''
            y = self.wrapped(record['text']+suffix,906,y+17,max_lines=2)+7
        if not records:
            self.wrapped('Meaningful events will appear here.',906,568,color=(157,185,172))

    def draw_world_history(self, simulation):
        if not self.world_history_open:
            return
        pygame.draw.rect(self.screen,(35,49,54),(898,120,195,540),border_radius=6)
        self.text('Village history',(904,134))
        self.screen.blit(self.small.render('N: close / scroll: earlier',True,(184,204,192)),(904,164))
        records = list(reversed(simulation.history.world))
        self.news_page = min(self.news_page,max(0,len(records)-1))
        y = 199
        for record in records[self.news_page:self.news_page+5]:
            self.screen.blit(self.small.render(record['timestamp'],True,(229,209,161)),(904,y))
            suffix = f" (x{record['count']})" if record['count']>1 else ''
            y = self.wrapped(record['text']+suffix,904,y+19,max_lines=3)+16
            if y>570:
                break

    def draw_feedback(self):
        """Place local cards from this frame's interpolated sprite rectangles."""
        occupied = []
        self.feedback_cards = {}
        speech = self.feedback.speech_notice()
        notices = ([speech] if speech else []) + list(self.feedback.notices.values())
        for notice in notices:
            anchor = self.character_rects.get(notice.actor_id)
            if (anchor is None or notice.expires <= self.feedback.clock
                    or not self.map_rect.collidepoint(anchor.centerx, anchor.bottom-1)):
                continue
            view = self.characters.get(notice.actor_id)
            # Activity is local status, never a distant floating travel annotation.
            if not notice.speech and view and view.animator.moving:
                continue
            text = notice.speech or notice.label or notice.reaction
            if not text:
                continue
            if notice.speech:
                name = CHARACTERS.get(notice.actor_id, (notice.actor_id, ""))[0]
                text = name+": "+text
            words = text.split()
            lines, line = [], ""
            for word in words:
                candidate = (line+" "+word).strip()
                if self.small.size(candidate)[0] > 198 and line:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            lines = lines[:4] if notice.speech else lines[:1]
            width = min(216, max(self.small.size(line)[0] for line in lines)+16)
            height = len(lines)*17+12
            card = pygame.Rect(anchor.centerx-width//2, anchor.top-height-18, width, height)
            card.clamp_ip(self.map_rect)
            # Dialogue takes priority. Hide crowded secondary cards instead of
            # searching unrelated map locations or drawing connector lines.
            if any(card.colliderect(other.inflate(4, 4)) for other in occupied):
                continue
            if not notice.speech and any(card.colliderect(rect) for key, rect in
                                         self.character_rects.items() if key != notice.actor_id):
                continue
            occupied.append(card)
            self.feedback_cards[notice.actor_id] = card
            pygame.draw.rect(self.screen, (244, 234, 204), card, border_radius=6)
            pygame.draw.rect(self.screen, (120, 105, 76), card, 1, border_radius=6)
            for i, line in enumerate(lines):
                self.screen.blit(self.small.render(line, True, (45, 54, 48)),
                                 (card.x+8, card.y+6+i*17))
        self.feedback_rects = occupied

    def draw_campfire(self, station):
        x=ORIGIN[0]+station.position[0]*TILE_SIZE+18
        y=ORIGIN[1]+station.position[1]*TILE_SIZE+26
        pygame.draw.ellipse(self.screen,(96,86,72),(x-14,y-8,28,15))
        pygame.draw.line(self.screen,(105,64,36),(x-9,y+1),(x+9,y-5),4)
        pygame.draw.line(self.screen,(105,64,36),(x+9,y+1),(x-9,y-5),4)
        pygame.draw.polygon(self.screen,(225,119,49),[(x-7,y-3),(x,y-21),(x+7,y-3)])
        pygame.draw.polygon(self.screen,(249,204,89),[(x-3,y-4),(x+1,y-13),(x+4,y-4)])
        pygame.draw.ellipse(self.screen,(47,55,58),(x-8,y-21,16,10))
        label=self.station_labels[station.occupied_by is not None]
        self.screen.blit(label,(x-label.get_width()//2,y-37))

    def draw_conversation_panel(self, simulation):
        entry = self.feedback.current_dialogue
        names = {a.id:a.name for a in simulation.agents}
        if not self.history_open:
            if entry:
                # A distinct reading panel remains readable after logical completion.
                card = pygame.Rect(24,598,500,80)
                pygame.draw.rect(self.screen,(35,49,54),card,border_radius=7)
                self.screen.blit(self.small.render('Conversation · '+timestamp(simulation.clock,entry['tick'])+' · C: history',True,(222,202,153)),(34,607))
                speaker,partner = names.get(entry['actor_id'],'?'),names.get(entry['target_id'],'?')
                self.wrapped(f'{speaker} > {partner}: '+entry['text'],34,629,width=480,max_lines=2)
            return
        history = list(reversed(simulation.history.conversations))
        pygame.draw.rect(self.screen,(35,49,54),(898,120,195,540),border_radius=6)
        self.text('Conversations',(904,134))
        self.screen.blit(self.small.render('C: close / scroll: earlier',True,(184,204,192)),(904,164))
        self.history_page = min(self.history_page,max(0,len(history)-1))
        y = 198
        for record in history[self.history_page:self.history_page+4]:
            self.screen.blit(self.small.render(record['timestamp'],True,(176,197,181)),(904,y))
            y = self.wrapped(names[record['actor_id']]+' > '+names[record['target_id']],904,y+18,max_lines=1,color=(245,218,158))
            y = self.wrapped(record['text'],904,y,max_lines=3)+13
            if y>555:
                break
        self.screen.blit(self.small.render('Authored offline dialogue',True,(167,190,181)),(904,640))

    def draw_session_debug(self, simulation):
        self.text('SOCIAL SESSIONS',(900,88))
        self.screen.blit(self.small.render('S: inspector / P: plans',True,(168,187,192)),(900,124))
        actor=next((a for a in simulation.agents if a.id==self.selected_id),None)
        if not actor:
            self.text('Select a villager',(900,170))
            return
        social=simulation.social
        session=social.session_for(actor)
        if not session:
            session=next((s for s in reversed(list(social.sessions.values())) if actor.id in s.participants),None)
        lines=[actor.name]
        if session:
            partner=next(key for key in session.participants if key!=actor.id)
            lines += [session.id,session.state.value,'Purpose: '+session.purpose,
                      'Partner: '+social.agents[partner].name,f'Turn: {session.current_turn+1}',
                      f'Start: {session.started_tick}',f'Cooldown: {max(0,session.cooldown_until-social.tick)*.25:g}s',
                      f'Trust: {actor.trust.get(partner,0):+d}','Outcome: '+str(session.outcome or 'pending'),'Transitions:']
            provider=getattr(simulation.decision_provider,'rule',simulation.decision_provider)
            utilities=getattr(provider,'debug',{}).get(actor.id,{}).get('utilities',[])
            changes = [e.get('trust_changes', {}).get(actor.id, 0) for e in simulation.events
                       if e.get('social') and e.get('session_id') == session.id]
            lines += [f'Trust change: {sum(changes):+d}']
            lines += [f"{c['goal']}: {c['score']:.1f}" for c in utilities[:2]]
            lines += [e['previous']+' > '+e['state'] for e in simulation.events
                      if e['action']=='SESSION' and e.get('session_id')==session.id][-5:]
        else:lines.append('No session recorded')
        y=166
        for label in lines:
            while self.small.size(label)[0]>186:label=label[:-2]+'…'
            self.screen.blit(self.small.render(label,True,(221,226,212)),(900,y));y+=22

    def draw_plan_debug(self, simulation):
        self.text('GOAL PLANNER',(900,88),title=True)
        self.screen.blit(self.small.render('P: inspector / F3: game',True,(168,187,192)),(900,124))
        actor=next((a for a in simulation.agents if a.id==self.selected_id),None)
        if not actor:
            self.text('Select a villager',(900,170))
            return
        provider=getattr(simulation.decision_provider,'rule',simulation.decision_provider)
        state=getattr(provider,'debug',{}).get(actor.id,{})
        plan=getattr(provider,'plans',{}).get(actor.id)
        lines=[actor.name,'Goal: '+(plan.goal if plan else state.get('goal','none')),'Top utilities:']
        lines += [f"{c['goal']}: {c['score']:.1f}" for c in state.get('utilities',[])[:5]]
        lines += ['Reason:',state.get('reason','No decision yet'),'Remaining tasks:']
        lines += [step.kind.value+((' '+step.item) if step.item else '') for step in plan.steps] if plan else ['Reevaluating']
        lines += ['Last replan:',state.get('replan','Initial selection')]
        y=161
        for text in lines:
            words=text.split();line=''
            for word in words:
                if self.small.size((line+' '+word).strip())[0]>186 and line:
                    self.screen.blit(self.small.render(line,True,(221,226,212)),(900,y));y+=17;line=''
                line=(line+' '+word).strip()
            self.screen.blit(self.small.render(line,True,(221,226,212)),(900,y));y+=18
            if y>648:break

    def draw_chicken(self, chicken, foot, tick):
        x, y = foot
        pecking = chicken.activity == "pecking"
        bob = (tick//2) % 2 if chicken.moving else 0
        head_x = x+chicken.facing*8
        head_y = y-8 if pecking else y-17-bob
        pygame.draw.ellipse(self.screen, (54, 72, 49), (x-10, y-3, 20, 6))
        pygame.draw.line(self.screen, (221, 159, 62), (x-3,y-4), (x-4,y+1-bob), 2)
        pygame.draw.line(self.screen, (221, 159, 62), (x+3,y-4), (x+5,y+1+bob), 2)
        pygame.draw.ellipse(self.screen,(103,86,57),(x-11,y-19-bob,22,17))
        pygame.draw.ellipse(self.screen, (240, 230, 198), (x-10,y-18-bob,20,15))
        pygame.draw.ellipse(self.screen, (205, 193, 159), (x-6,y-14-bob,10,8), 1)
        pygame.draw.circle(self.screen, (246, 238, 205), (head_x,head_y), 6)
        pygame.draw.circle(self.screen, (185, 64, 53), (head_x-2,head_y-6), 3)
        pygame.draw.circle(self.screen, (38, 43, 41), (head_x+chicken.facing*2,head_y-1), 1)
        pygame.draw.polygon(self.screen, (226, 166, 53), [(head_x+chicken.facing*5,head_y),
                            (head_x+chicken.facing*10,head_y+2), (head_x+chicken.facing*5,head_y+3)])
        if chicken.state == "FLEE":
            self.screen.blit(self.small.render("!", True, (251, 206, 115)), (x-3,y-35))
            pygame.draw.line(self.screen, (208, 199, 161), (x-chicken.facing*16,y-10), (x-chicken.facing*12,y-10))
        elif pecking:
            pygame.draw.circle(self.screen, (199, 167, 99), (head_x+chicken.facing*8,y), 1)
        self.chicken_rects[chicken.id] = pygame.Rect(x-15,y-28,30,32)

    def draw_feature(self, tile, rect, simulation, position):
        cx, cy = rect.center
        if tile == Tile.TREE:
            pygame.draw.rect(self.screen, (112, 77, 48), (cx-3, cy, 6, 13))
            pygame.draw.ellipse(self.screen, (61, 92, 55), (cx-14, cy+8, 28, 8))
            pygame.draw.circle(self.screen, (30, 67, 48), (cx+1, cy-4), 16)
            pygame.draw.circle(self.screen, (39, 82, 54), (cx, cy-5), 15)
            pygame.draw.circle(self.screen, (54, 104, 60), (cx-5, cy-9), 10)
            pygame.draw.circle(self.screen, (70, 120, 65), (cx-5, cy-12), 6)
        elif tile == Tile.BUSH:
            nearby = bool(simulation.player and simulation.social.agents[simulation.player.agent_id].position in simulation.world.neighbors(position))
            if position == self.selected_bush or nearby:
                pygame.draw.ellipse(self.screen, (246, 225, 146), rect.inflate(-1, -5), 2)
            stock = simulation.resources.available(position)
            pygame.draw.ellipse(self.screen,(54,79,49),(cx-15,cy+6,30,9))
            pygame.draw.ellipse(self.screen, (48, 104, 59) if stock else (104, 110, 73), rect.inflate(-4, -12))
            pygame.draw.arc(self.screen,(91,137,74) if stock else (135,139,91),rect.inflate(-7,-15),.3,2.8,2)
            if not stock:
                pygame.draw.line(self.screen, (124, 145, 87), (cx-7, cy+5), (cx+5, cy-4), 2)
            if simulation.resources.available(position):
                for dx, dy in ((-6,0),(5,2),(0,-4),(-3,5),(7,-4))[:min(stock,5)]:
                    pygame.draw.circle(self.screen, (161, 57, 91), (cx+dx, cy+dy), 3)
                    pygame.draw.circle(self.screen, (233, 140, 150), (cx+dx-1, cy+dy-1), 1)
        elif tile == Tile.WATER:
            pygame.draw.rect(self.screen, (56, 126, 161), rect)
            # Small shore edges reflect adjacent terrain; no tile is changed.
            for dx,dy,start,end in ((0,-1,rect.topleft,rect.topright),(0,1,rect.bottomleft,rect.bottomright),
                                    (-1,0,rect.topleft,rect.bottomleft),(1,0,rect.topright,rect.bottomright)):
                x,y=position[0]+dx,position[1]+dy
                if not (0<=x<simulation.world.width and 0<=y<simulation.world.height) or simulation.world.tiles[y][x]!=Tile.WATER:
                    pygame.draw.line(self.screen,(99,156,147),start,end,3)
            offset=(position[0]*11+position[1]*7)%13-6
            pygame.draw.line(self.screen,(102,169,193),(cx-8,cy+offset),(cx+5,cy+offset),1)
        elif tile == Tile.HOUSE:
            pygame.draw.rect(self.screen, (213, 189, 145), (cx-12, cy-2, 24, 16))
            pygame.draw.polygon(self.screen, (155, 77, 61),
                                [(cx-16, cy-2), (cx, cy-16), (cx+16, cy-2)])
            pygame.draw.rect(self.screen, (82, 62, 46), (cx-3, cy+4, 7, 10))
            pygame.draw.rect(self.screen, (243, 209, 128), (cx-9, cy+2, 4, 5))
            pygame.draw.line(self.screen, (112, 58, 48), (cx-11, cy-2), (cx+11, cy-2), 2)
            pygame.draw.rect(self.screen, (116, 101, 84), (cx+7, cy-14, 4, 8))

    def draw_inspector(self, selected, simulation):
        self.text(f"{selected.name} / {selected.personality_name}", (900, 214), selected.color)
        names = {a.id: a.name for a in simulation.agents}
        if self.inspector_tab == "State":
            last_move = next((event for event in reversed(simulation.events)
                              if event.get("agent") == selected.name and event["action"] == "MOVE_TO"), None)
            destination = last_move.get("destination", last_move["target"]) if selected.current_action == "MOVE_TO" and last_move else None
            lines = [f"Hunger: {selected.hunger}/100", f"Energy: {selected.energy}/100",
                     f"Berries: {selected.food}/{selected.inventory.capacity}", f"Doing: {selected.current_action}",
                     f"Position: {selected.position}",
                     f"Destination: {destination or '-'}",
                     f"Facing: {self.characters[selected.id].animator.direction}",
                     f"Goal: {selected.goal.purpose if selected.goal else 'none'}"]
        elif self.inspector_tab == "Traits":
            lines = [f"{key.replace('_', ' ').title()}: {value:.2f}"
                     for key, value in selected.personality.items()]
        elif self.inspector_tab == "Trust":
            lines = [f"To {names[other]}: {value:+d}" for other, value in selected.trust.items()]
            lines += ["Recent interactions:"]
            lines += [f"{m.tick}: {m.action}" for m in selected.memories[-2:]]
        else:
            recall = "on" if simulation.social.memory_enabled else "off (audit only)"
            lines = [f"AI recall: {recall}"]
            newest = list(reversed(selected.memories))
            self.memory_page = min(self.memory_page, max(0, (len(newest)-1)//2))
            for memory in newest[self.memory_page*2:self.memory_page*2+2]:
                lines += [f"t{memory.tick} {names[memory.actor_id]} > {names[memory.target_id]}",
                          f"{SOCIAL_LABELS.get(memory.action, memory.action)}: {memory.result}", f"Own trust effect: {memory.trust_delta:+d}"]
            if not newest:
                lines += ["No interactions yet"]
            lines += [f"Wheel: older / newer ({self.memory_page+1})"]
        for i, line in enumerate(lines):
            # Inspector has a fixed bounded area; clip long audit descriptions.
            while self.small.size(line)[0] > 190:
                line = line[:-2]+"…"
            self.screen.blit(self.small.render(line, True, (225, 233, 235)), (900, 242+i*18))

    def select_at(self, position, simulation):
        x, y = position
        if self.debug and 900 <= x < 1092 and 183 <= y < 206:
            self.inspector_tab = ("State", "Traits", "Trust", "Memory")[(x-900)//48]
            return
        self.memory_page = 0
        # Hit the displayed artwork, including interpolated positions, and cycle overlaps.
        matches = [key for key, rect in reversed(list(self.character_rects.items())) if rect.collidepoint(position)]
        if not matches and not self.map_rect.collidepoint(position):
            return
        tile = ((x-ORIGIN[0])//TILE_SIZE, (y-ORIGIN[1])//TILE_SIZE)
        if not matches:
            matches = [a.id for a in simulation.agents if a.position == tile]
        self.selected_bush = tile if not matches and (0 <= tile[0] < simulation.world.width and 0 <= tile[1] < simulation.world.height and simulation.world.tiles[tile[1]][tile[0]] == Tile.BUSH) else None
        # Repeated clicks cycle through villagers sharing the same tile.
        if self.selected_id in matches:
            self.selected_id = matches[(matches.index(self.selected_id)+1) % len(matches)]
        else:
            self.selected_id = matches[0] if matches else None


def handle_event(event, simulation, ticker, renderer=None) -> bool:
    """Return False when the user requests exit."""
    if renderer and hasattr(event,'pos') and event.type in (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP,pygame.MOUSEMOTION):
        width,height=renderer.display.get_size()
        event=pygame.event.Event(event.type,{**event.dict,'pos':(round(event.pos[0]*WINDOW[0]/width),
                                                               round(event.pos[1]*WINDOW[1]/height))})
    if renderer and event.type == pygame.KEYDOWN:
        if event.key == pygame.K_F8:
            renderer.animation_preview = not renderer.animation_preview
            return True
        if renderer.animation_preview and event.key in (pygame.K_1,pygame.K_2,pygame.K_3,pygame.K_4,pygame.K_b):
            if event.key == pygame.K_b:
                renderer.preview_background = (renderer.preview_background+1)%3
            else:
                renderer.preview_character = event.key-pygame.K_1
            return True
    if renderer and renderer.participant_ui.handle(event, simulation, renderer):
        return True
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and renderer:
        clicked = next((key for key, rect in renderer.control_buttons.items() if rect.collidepoint(event.pos)), None)
        if clicked:
            key = {'pause':pygame.K_SPACE,'slower':pygame.K_MINUS,'faster':pygame.K_EQUALS,
                   'save':pygame.K_F5,'load':pygame.K_F9,'help':pygame.K_F1}[clicked]
            return handle_event(pygame.event.Event(pygame.KEYDOWN, key=key), simulation, ticker, renderer)
        renderer.select_at(event.pos, simulation)
    if event.type == pygame.MOUSEWHEEL and renderer and renderer.world_history_open:
        renderer.news_page = max(0,renderer.news_page-event.y)
    elif event.type == pygame.MOUSEWHEEL and renderer and renderer.history_open:
        renderer.history_page = max(0,renderer.history_page-event.y)
    elif event.type == pygame.MOUSEWHEEL and renderer and renderer.inspector_tab == "Memory":
        renderer.memory_page = max(0, renderer.memory_page-event.y)
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key == pygame.K_F3 and renderer:
            renderer.debug = not renderer.debug
        if event.key == pygame.K_c and renderer:
            renderer.history_open = not renderer.history_open
            renderer.world_history_open = False
        if event.key == pygame.K_n and renderer:
            renderer.world_history_open = not renderer.world_history_open
            renderer.history_open = False
        if event.key == pygame.K_s and renderer and renderer.debug:
            renderer.social_debug = not renderer.social_debug
            renderer.plan_debug = False
        if event.key == pygame.K_p and renderer and renderer.debug:
            renderer.plan_debug = not renderer.plan_debug
            renderer.social_debug = False
        if event.key == pygame.K_TAB and renderer:
            tabs = ("State", "Traits", "Trust", "Memory")
            renderer.inspector_tab = tabs[(tabs.index(renderer.inspector_tab)+1) % len(tabs)]
        if event.key == pygame.K_SPACE:
            simulation.paused = not simulation.paused
        elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_MINUS, pygame.K_EQUALS):
            index = ticker.speeds.index(ticker.speed)
            delta = 1 if event.key in (pygame.K_UP, pygame.K_EQUALS) else -1
            ticker.speed = ticker.speeds[max(0, min(len(ticker.speeds)-1, index+delta))]
    return True


def advance_frame(renderer, ticker, simulation, elapsed):
    """Split one frame at logical tick boundaries, retaining continuous walk phase."""
    renderer.notification_seconds = max(0,renderer.notification_seconds-elapsed)
    if renderer.participant_ui.menu or simulation.input_blocked:
        renderer.participant_ui.stop(simulation)
        if simulation.input_blocked:
            if not simulation.paused:
                simulation.player.advance_prompt(elapsed, simulation)
            renderer.feedback.advance_reading(elapsed, paused=simulation.paused)
        renderer.advance_animation(0, True)
        ticker.accumulator = 0
        return
    until_tick = ticker.interval - ticker.accumulator

    def completed_tick(state):
        nonlocal until_tick
        renderer.advance_animation(until_tick, speed=ticker.speed, tick_boundary=True)
        renderer.capture_tick(state, ticker.interval)
        until_tick = ticker.interval

    count = ticker.advance(simulation, elapsed, on_step=completed_tick)
    remainder = ticker.accumulator if count else elapsed*ticker.speed
    renderer.advance_animation(remainder, simulation.paused, speed=ticker.speed)


def run(simulation: Simulation, animation_fps=8.0, window_scale=1.0, idle_fps=4.0) -> None:
    try:
        renderer = Renderer(animation_fps,window_scale,idle_fps)
        renderer.sync_characters(simulation)
        renderer.selected_id = simulation.player.agent_id if simulation.player else simulation.selected_id
        ticker = FixedTicker()
        clock = pygame.time.Clock()
        running = True
        while running:
            elapsed = clock.tick(60) / 1000
            # Charge elapsed time to the state that was active during that time.
            advance_frame(renderer, ticker, simulation, elapsed)
            for event in pygame.event.get():
                if not handle_event(event, simulation, ticker, renderer):
                    running = False
            if running:
                renderer.draw(simulation, ticker)
    finally:
        simulation.close()
        pygame.quit()
