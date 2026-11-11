"""Articulated procedural chickens. Presentation only; never changes wildlife/RNG.

Body/wing breath, independent neck/head pecks, planted alternating feet and
staggered blinks are analytic curves. CharacterView retains observed grid steps
and corners; a tiny animator adapter reuses its tested interpolation queue.
"""
import math
import pygame
from .animation import CharacterView


class ChickenMotion:
    def __init__(self):
        self.moving = False
        self.direction = 'right'
        self.elapsed = 0.0

    def update(self, dt, moving, direction=None):
        self.moving = moving
        self.direction = direction or self.direction
        self.elapsed += dt


class ChickenView(CharacterView):
    death_seconds = .8

    def __init__(self, chicken):
        super().__init__(chicken.position, ChickenMotion())
        self.animator.direction = 'right' if chicken.facing > 0 else 'left'
        self.phase = int(chicken.id.rsplit('-', 1)[-1]) * 1.731
        self.clock = 0.0
        self.hit_shapes = []
        self.hp = chicken.hp
        self.alive = chicken.alive
        self.hit_age = 10.0
        self.death_age = 0.0 if chicken.alive else self.death_seconds

    def observe(self, chicken):
        if chicken.hp < self.hp:
            self.hit_age = 0.0
        if self.alive and not chicken.alive:
            self.death_age = 0.0
            self.segments.clear()
        self.hp, self.alive = chicken.hp, chicken.alive

    def advance(self, dt, paused=False, **timing):
        if not paused:
            self.clock += dt
            self.hit_age += dt
            if not self.alive:
                self.death_age += dt
        super().advance(dt, paused, **timing)

    @property
    def visible(self):
        return self.alive or self.death_age < self.death_seconds

    def joints(self, chicken):
        t = self.clock
        walking = self.animator.moving
        stride = math.sin(t*(23 if chicken.activity == 'fleeing' else 16)+self.phase)
        breath = math.sin(t*3.2+self.phase)
        peck = 0.0
        if self.alive and not walking and chicken.activity == 'pecking':
            # Two purposeful neck dips, with a quiet interval between bouts.
            cycle = (t+self.phase) % 3.4
            if cycle < 1.0:
                peck = math.sin(cycle*math.pi*2)**2
        blink_phase = (t+self.phase) % 4.7
        flinch = max(0.0, 1-self.hit_age/.22)
        death = min(1.0, self.death_age/self.death_seconds) if not self.alive else 0.0
        return dict(stride=stride if walking else 0, bob=abs(stride)*1.4 if walking else breath*.45,
                    breath=breath, peck=peck, blink=blink_phase < .12,
                    flinch=flinch, death=death, walking=walking)

    def hit_test(self, point):
        """Only the visible animal silhouette is clickable, never its HP/shadow."""
        px, py = point
        for cx, cy, w, h in self.hit_shapes:
            if ((px-cx)/(w/2))**2+((py-cy)/(h/2))**2 <= 1:
                return True
        return False

    def draw(self, screen, chicken, foot):
        pose = self.joints(chicken)
        direction = self.animator.direction
        facing = -1 if direction == 'left' else 1
        rear = direction == 'up'
        x, y = foot
        sink = pose['death']*13
        x -= facing*pose['flinch']*3
        y += sink-pose['flinch']*3
        bob = pose['bob']
        peck = pose['peck']
        dead = pose['death']
        flash = pose['flinch'] > 0 and int(self.hit_age*30)%2 == 0
        cream = (255,163,145) if flash else (253,242,208)
        shade = (221,115,105) if flash else (220,200,157)
        outline, orange = (103,77,56), (230,157,53)

        self.hit_shapes = []

        def ellipse(color, cx, cy, w, h, border=0):
            if color == outline:
                self.hit_shapes.append((cx,cy,w,h))
            pygame.draw.ellipse(screen,color,pygame.Rect(round(cx-w/2),round(cy-h/2),round(w),round(h)),border)

        def line(color, a, b, width=1):
            pygame.draw.line(screen,color,tuple(round(v) for v in a),tuple(round(v) for v in b),width)

        ellipse((53,71,46), x,foot[1]-1,27*(1-dead*.5),7)
        # Far leg first: alternating lift, short shin, three-toed planted foot.
        for side in (-1,1):
            lift=max(0,pose['stride']*side)*3
            sx=x+side*5+pose['stride']*side*2
            if dead:lift=-dead*2
            line(outline,(x+side*4,y-8-bob),(sx,y-1-lift),3)
            line(orange,(x+side*4,y-7-bob),(sx,y-1-lift),2)
            line(orange,(sx-2,y-lift),(sx+4,y-lift),2)
            line(orange,(sx,y-lift),(sx+2,y+2-lift))
            self.hit_shapes.append((sx,y-3-lift,6,10))
        # Tail feathers are individual lobes, not a whole-sprite rotation.
        tail_x=x-facing*11
        for offset in (-3,0,3):
            ellipse(outline,tail_x-facing*abs(offset)*.5,y-17+offset-bob,8,12)
            ellipse(shade,tail_x-facing*abs(offset)*.5,y-18+offset-bob,5,9)
        body_h=21+pose['breath']*.5-dead*6
        ellipse(outline,x,y-13-bob,29,body_h+2)
        ellipse(cream,x,y-14-bob,27,body_h)
        ellipse(shade,x-facing*3,y-12-bob,15,11)
        ellipse(cream,x-facing*4,y-14-bob,13,9)
        # Separate articulated neck/head reaches toward the ground during pecks.
        hx=x+facing*(9+peck*5)
        hy=y-25-bob+peck*17+dead*5
        ellipse(outline,hx-facing*2,hy+6,10,15)
        ellipse(cream,hx-facing*2,hy+5,8,13)
        ellipse(outline,hx,hy,17,18)
        ellipse(cream,hx,hy-.5,15,16)
        # Three-lobed comb and tiny wattle.
        for dx,dy,r in ((-3,-8,3),(0,-10,3),(3,-8,2)):
            pygame.draw.circle(screen,(198,73,69),(round(hx+dx),round(hy+dy)),r)
        ellipse((198,73,69),hx+facing*5,hy+7,4,6)
        beak=[(round(hx+facing*7),round(hy)),(round(hx+facing*13),round(hy+3)),(round(hx+facing*7),round(hy+5))]
        pygame.draw.polygon(screen,orange,beak)
        self.hit_shapes.append((hx+facing*9,hy+2,8,5))
        if rear:
            ellipse(shade,hx,hy+1,7,6)
        elif dead:
            for sign in (-1,1):
                line(outline,(hx+facing*3-2,hy-1+sign*2),(hx+facing*3+2,hy-1-sign*2),1)
        elif pose['blink']:
            line(outline,(hx+facing*3-2,hy-1),(hx+facing*3+2,hy-1),2)
        else:
            pygame.draw.circle(screen,(50,45,40),(round(hx+facing*4),round(hy-1)),2)
            pygame.draw.circle(screen,(255,255,240),(round(hx+facing*4),round(hy-2)),1)
        if peck > .8 and not dead:
            for dx in (0,4):
                pygame.draw.circle(screen,(218,183,109),(round(hx+facing*(10+dx)),round(foot[1]-2)),1)
        if chicken.activity == 'fleeing' and self.alive:
            for offset in (0,5):
                line((234,215,160),(x-facing*20, y-15-offset),(x-facing*15,y-16-offset))
        rect=pygame.Rect(round(x-22),round(y-39),44,42)
        if chicken.hp < chicken.max_hp and self.alive:
            bar=pygame.Rect(round(x-16),round(y-45),32,5)
            pygame.draw.rect(screen,(62,51,44),bar,border_radius=2)
            pygame.draw.rect(screen,(207,88,72),(bar.x+1,bar.y+1,round(30*chicken.hp/chicken.max_hp),3),border_radius=1)
        return rect
