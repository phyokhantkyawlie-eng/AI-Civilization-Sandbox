"""Pygame presentation and input; all world updates live in simulation.py."""
import pygame

from .simulation import FixedTicker, Simulation
from .world import Tile
from .animation import SpriteAnimator, CharacterView
from .feedback import Feedback
from .characters import CHARACTERS
from .inventory import ITEM_NAMES
from .ui_state import activity, hunger_status, energy_status, StatusThresholds
from .sprites import CharacterAssets, FOOT_ANCHOR, FRAME_SIZE

SOCIAL_LABELS = {"REQUEST_FOOD": "ask", "SHARE_FOOD": "share",
                 "REFUSE_REQUEST": "refuse", "TALK": "talk"}

WINDOW = (1100, 750)
TILE_SIZE = 36
ORIGIN = (20, 78)


class Renderer:
    def __init__(self, animation_fps=8.0):
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode(WINDOW)
        pygame.display.set_caption("AI Civilization Sandbox | Animated Characters")
        self.font = pygame.font.Font(None, 23)
        self.title = pygame.font.Font(None, 32)
        self.small = pygame.font.Font(None, 19)
        self.selected_id = None
        self.debug = False
        self.selected_bush = None
        self.inspector_tab = "State"
        self.memory_page = 0
        self.assets = CharacterAssets()
        self.animation_fps = animation_fps
        self.characters = {}
        self.character_rects = {}
        self.chicken_rects = {}
        self.feedback = Feedback()
        self.ground_cache = {}
        self.lighting_cache = {}
        self.name_labels = {}
        self.draw_feet = {}
        self.control_buttons = {}
        self.map_rect = pygame.Rect(ORIGIN, (24*TILE_SIZE, 18*TILE_SIZE))

    def text(self, text, position, color=(225, 233, 235), title=False):
        self.screen.blit((self.title if title else self.font).render(text, True, color), position)

    def draw(self, simulation, ticker):
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
        self.feedback.consume(simulation.events)
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
            else:
                chicken, foot = item
                self.draw_chicken(chicken, foot, simulation.tick)
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
            self.screen.blit(label, (background.x+4, y))
        darkness = simulation.time_of_day.darkness
        if darkness:
            if darkness not in self.lighting_cache:
                tint = pygame.Surface(self.map_rect.size, pygame.SRCALPHA)
                tint.fill((15, 22, 55, darkness))
                self.lighting_cache[darkness] = tint
            self.screen.blit(self.lighting_cache[darkness], self.map_rect)
        self.draw_feedback()
        if self.debug:
            self.text("PAUSED" if simulation.paused else "RUNNING", (900, 82), title=True)
            self.text(f"Tick {simulation.tick} / {ticker.speed:g}x", (900, 116))
            self.text(f"Seed: {simulation.seed}", (900, 141))
            self.screen.blit(self.small.render("Click NPC / Tab: inspect", True, (168, 187, 192)), (900, 163))
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
        self.draw_controls(simulation)
        pygame.display.flip()


    def sync_characters(self, simulation):
        for agent in simulation.agents:
            if agent.id not in self.characters:
                self.characters[agent.id] = CharacterView(
                    agent.position, SpriteAnimator(self.assets.for_agent(agent), self.animation_fps))
            elif self.characters[agent.id].logical_position != agent.position:
                # draw() used without tick callbacks (e.g. a restored snapshot): snap, never cut corners.
                self.characters[agent.id].snap(agent.position)

    def capture_tick(self, simulation, seconds):
        for agent in simulation.agents:
            if agent.id not in self.characters:
                self.characters[agent.id] = CharacterView(
                    agent.position, SpriteAnimator(self.assets.for_agent(agent), self.animation_fps))
            else:
                self.characters[agent.id].capture(agent.position, seconds)
            if simulation.progress.held(agent) or simulation.social.active_requests(agent):
                self.characters[agent.id].snap(agent.position)
                self.characters[agent.id].animator.update(0, False, agent.facing)

    def advance_animation(self, elapsed, paused=False, **timing):
        if not paused:
            self.feedback.advance(elapsed)
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
        state = self.feedback.state_for(agent.id, view.animator.moving)
        sprite_state = self.feedback.sprite_state(state)
        frame = view.animator.frame if sprite_state == "walk" else view.animator.frames[view.animator.direction][0]
        self.screen.blit(frame, rect)
        self.character_rects[agent.id] = rect

    def draw_controls(self, simulation):
        self.control_buttons = {}
        for key, label, x, width in (("pause", "Resume" if simulation.paused else "Pause", 900, 88),
                                     ("slower", "-", 992, 44), ("faster", "+", 1040, 44)):
            rect = pygame.Rect(x, 674, width, 28)
            pygame.draw.rect(self.screen, (70, 91, 89), rect, border_radius=5)
            self.screen.blit(self.small.render(label, True, (245, 230, 191)), (x+10, 682))
            self.control_buttons[key] = rect
        self.screen.blit(self.small.render("Space / arrows / Esc", True, (179, 197, 192)), (900, 716))

    def draw_bar(self, title, value, description, color, y):
        self.text(title, (906, y))
        self.screen.blit(self.small.render(description, True, color), (1000, y+3))
        pygame.draw.rect(self.screen, (22, 34, 39), (906, y+24, 178, 12), border_radius=5)
        width = round(178*max(0, min(100, value))/100)
        if width:
            pygame.draw.rect(self.screen, color, (906, y+24, width, 12), border_radius=5)

    def draw_friendly_panel(self, simulation, ticker):
        pygame.draw.rect(self.screen, (24, 34, 39), (0, 0, 1100, 74))
        self.text("STARFALL VILLAGE", (20, 17), title=True)
        now = simulation.time_of_day
        self.text(f"Day {now.day}  ·  {now.hour:02d}:{now.minute:02d}  ·  {now.period.title()}", (20, 49), (193, 205, 181))
        self.text("F3 · Details", (944, 24), (193, 205, 181))
        pygame.draw.rect(self.screen, (35, 49, 54), (892, 74, 204, 594), border_radius=10)
        self.text("Paused" if simulation.paused else "Village life", (906, 87), title=True)
        self.text(f"Speed {ticker.speed:g}×", (906, 124), (193, 205, 181))
        actor = next((a for a in simulation.agents if a.id == self.selected_id), None)
        if actor:
            self.text(actor.name, (906, 172), actor.color, title=True)
            self.screen.blit(self.small.render(activity(actor, simulation), True, (235, 222, 184)), (906, 207))
            rules = simulation.survival
            thresholds = StatusThresholds(rules.hungry, rules.inefficient_hunger, rules.rest_energy, rules.collapse_energy)
            label, color = hunger_status(actor.hunger, thresholds)
            self.draw_bar("Hunger", actor.hunger, label, color, 244)
            label, color = energy_status(actor.energy, thresholds)
            self.draw_bar("Energy", actor.energy, label, color, 300)
            self.text(f"Inventory ({actor.inventory.used}/{actor.inventory.capacity})", (906, 366))
            for row, (item, quantity) in enumerate(sorted(actor.inventory.items.items())):
                self.text(f"{ITEM_NAMES[item]} × {quantity}", (906, 397+row*20), (226, 179, 161))
            if not actor.inventory.used:
                self.text("Empty", (906, 397), (193, 205, 181))
            goal = actor.goal.purpose.title() if actor.goal else "Reevaluating"
            self.screen.blit(self.small.render(f"Goal: {goal}", True, (193, 205, 181)), (906, 350))
            self.screen.blit(self.small.render(actor.personality_name, True, (193, 205, 181)), (906, 451))
        elif self.selected_bush is not None:
            bush = simulation.resources.bushes[self.selected_bush]
            self.text("Berry bush", (906, 172), title=True)
            self.text(f"Berries {bush.quantity}/{bush.capacity}", (906, 213))
            self.screen.blit(self.small.render(f"{bush.id} · {bush.position}", True, (193, 205, 181)), (906, 242))
            remaining = bush.ticks_until_regeneration
            if remaining is not None:
                self.text("Regrowing", (906, 272), (193, 205, 181))
                self.text(f"Next berry in {remaining*.25:g}s", (906, 302))
                self.draw_bar("Regeneration", 100*bush.regeneration_progress/bush.regeneration_interval, "", (106, 164, 104), 340)
            else:
                self.text("Fully grown", (906, 272))
        else:
            self.text("Meet the villagers", (906, 172))
            self.screen.blit(self.small.render("Click a person or berry bush", True, (193, 205, 181)), (906, 207))
        self.text("Village news", (906, 480))
        interesting = [e for e in reversed(simulation.events) if e.get("social") or (
            e.get("executed") and e["action"] in ("GATHER", "EAT", "HUNT")) or e["action"] == "HUNT_FAILED"][:4]
        names = {a.id: a.name for a in simulation.agents}
        for index, event in enumerate(interesting):
            if event.get("social"):
                target = names.get(event.get("target_id"), "someone")
                verb = {"pending": "asked", "shared one food": "shared with", "refused": "declined",
                        "greeted": "greeted", "expired": "waited for"}.get(event.get("result"), "met")
                text = f"{event['agent']} {verb} {target}"
            elif event["action"] == "HUNT_FAILED":
                name = names.get(event.get("actor_id"), "Villager")
                text = f"{name}'s hunt ended"
            elif event["action"] == "HUNT":
                text = f"{event['agent']} collected raw chicken"
            elif event["action"] == "EAT":
                text = f"{event['agent']} ate berries"
            else:
                text = f"{event['agent']} picked berries"
            words, lines, line = text.split(), [], ""
            for word in words:
                candidate = (line+" "+word).strip()
                if self.small.size(candidate)[0] > 176 and line:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for row, line in enumerate(lines[:2]):
                self.screen.blit(self.small.render(line, True, (211, 218, 207)),
                                 (906, 516+index*36+row*16))

    def draw_feedback(self):
        occupied = []
        # A single action and reaction per NPC bounds layout work to eight cards.
        for notice in self.feedback.notices.values():
            anchor = self.character_rects.get(notice.actor_id)
            if anchor is None:
                continue
            text = notice.speech or notice.label or notice.reaction
            if not text:
                continue
            name = CHARACTERS.get(notice.actor_id, (notice.actor_id, ""))[0]
            words = (name+": "+text).split()
            lines, line = [], ""
            for word in words:
                candidate = (line+" "+word).strip()
                if self.small.size(candidate)[0] > 198 and line:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            lines = lines[:4]
            width = min(216, max(self.small.size(line)[0] for line in lines)+16)
            height = len(lines)*17+12
            bounds = pygame.Rect(20, 78, 864, 648)
            choices = [pygame.Rect(anchor.centerx-width//2, anchor.top-height-18, width, height),
                       pygame.Rect(anchor.centerx-width//2, anchor.bottom+8, width, height)]
            choices += [pygame.Rect(x, y, width, height) for y in range(80, 700-height, height+4)
                        for x in range(22, 884-width, width+4)]
            card = None
            for candidate in choices:
                candidate.clamp_ip(bounds)
                if (not any(candidate.colliderect(other.inflate(4, 4)) for other in occupied)
                        and not any(candidate.colliderect(sprite.inflate(0, 24))
                                    for sprite in self.character_rects.values())):
                    card = candidate
                    break
            if card is None:
                continue
            occupied.append(card)
            pygame.draw.line(self.screen, (230, 213, 163), anchor.midtop, card.center, 1)
            pygame.draw.rect(self.screen, (244, 234, 204), card, border_radius=6)
            pygame.draw.rect(self.screen, (120, 105, 76), card, 1, border_radius=6)
            for i, line in enumerate(lines):
                self.screen.blit(self.small.render(line, True, (45, 54, 48)),
                                 (card.x+8, card.y+6+i*17))
        self.feedback_rects = occupied

    def draw_chicken(self, chicken, foot, tick):
        x, y = foot
        pecking = chicken.activity == "pecking"
        bob = (tick//2) % 2 if chicken.moving else 0
        head_x = x+chicken.facing*8
        head_y = y-8 if pecking else y-17-bob
        pygame.draw.ellipse(self.screen, (54, 72, 49), (x-10, y-3, 20, 6))
        pygame.draw.line(self.screen, (221, 159, 62), (x-3,y-4), (x-4,y+1-bob), 2)
        pygame.draw.line(self.screen, (221, 159, 62), (x+3,y-4), (x+5,y+1+bob), 2)
        pygame.draw.ellipse(self.screen, (230, 223, 194), (x-10,y-18-bob,20,15))
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
            pygame.draw.circle(self.screen, (39, 82, 54), (cx, cy-5), 15)
            pygame.draw.circle(self.screen, (54, 104, 60), (cx-5, cy-9), 10)
            pygame.draw.circle(self.screen, (70, 120, 65), (cx-5, cy-12), 6)
        elif tile == Tile.BUSH:
            if position == self.selected_bush:
                pygame.draw.ellipse(self.screen, (246, 225, 146), rect.inflate(-1, -5), 2)
            stock = simulation.resources.available(position)
            pygame.draw.ellipse(self.screen, (48, 104, 59) if stock else (104, 110, 73), rect.inflate(-4, -12))
            if not stock:
                pygame.draw.line(self.screen, (124, 145, 87), (cx-7, cy+5), (cx+5, cy-4), 2)
            if simulation.resources.available(position):
                for dx, dy in ((-6, 0), (5, 2), (0, -4)):
                    pygame.draw.circle(self.screen, (161, 57, 91), (cx+dx, cy+dy), 3)
                    pygame.draw.circle(self.screen, (233, 140, 150), (cx+dx-1, cy+dy-1), 1)
        elif tile == Tile.WATER:
            pygame.draw.rect(self.screen, (56, 126, 161), rect)
            pygame.draw.line(self.screen, (102, 169, 193), (cx-9, cy), (cx+8, cy), 2)
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
                     f"Food: {selected.food}/5", f"Doing: {selected.current_action}",
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
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and renderer:
        clicked = next((key for key, rect in renderer.control_buttons.items() if rect.collidepoint(event.pos)), None)
        if clicked:
            key = {"pause": pygame.K_SPACE, "slower": pygame.K_DOWN, "faster": pygame.K_UP}[clicked]
            return handle_event(pygame.event.Event(pygame.KEYDOWN, key=key), simulation, ticker, renderer)
        renderer.select_at(event.pos, simulation)
    if event.type == pygame.MOUSEWHEEL and renderer and renderer.inspector_tab == "Memory":
        renderer.memory_page = max(0, renderer.memory_page-event.y)
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key == pygame.K_F3 and renderer:
            renderer.debug = not renderer.debug
        if event.key == pygame.K_TAB and renderer:
            tabs = ("State", "Traits", "Trust", "Memory")
            renderer.inspector_tab = tabs[(tabs.index(renderer.inspector_tab)+1) % len(tabs)]
        if event.key == pygame.K_SPACE:
            simulation.paused = not simulation.paused
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            index = ticker.speeds.index(ticker.speed)
            delta = 1 if event.key == pygame.K_UP else -1
            ticker.speed = ticker.speeds[max(0, min(len(ticker.speeds)-1, index+delta))]
    return True


def advance_frame(renderer, ticker, simulation, elapsed):
    """Split one frame at logical tick boundaries, retaining continuous walk phase."""
    until_tick = ticker.interval - ticker.accumulator

    def completed_tick(state):
        nonlocal until_tick
        renderer.advance_animation(until_tick, speed=ticker.speed, tick_boundary=True)
        renderer.capture_tick(state, ticker.interval)
        until_tick = ticker.interval

    count = ticker.advance(simulation, elapsed, on_step=completed_tick)
    remainder = ticker.accumulator if count else elapsed*ticker.speed
    renderer.advance_animation(remainder, simulation.paused, speed=ticker.speed)


def run(simulation: Simulation, animation_fps=8.0) -> None:
    try:
        renderer = Renderer(animation_fps)
        renderer.sync_characters(simulation)
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
