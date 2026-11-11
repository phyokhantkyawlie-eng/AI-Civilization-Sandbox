"""Removable gather-only prototype: original idle art plus procedural pickup accents.

No arm articulation is claimed: the source PNGs are flattened. Four directions
x four phases are visual states, not sixteen newly illustrated sprite frames.
This module never executes actions, changes resources, or consumes RNG.
"""
import math
import pygame
from .actions import ActionType, validate

PHASES = ('REACH','CONTACT','COLLECT','RETURN')
DIRECTIONS = ('down','left','right','up')
HAND_POINTS = {'down':(6,-17),'left':(-10,-20),'right':(10,-20),'up':(-6,-27)}
CONTACT_POINTS = {'down':(3,8),'left':(-24,-18),'right':(24,-18),'up':(-3,-48)}


def phase_at(elapsed, cycle=1.0):
    if not math.isfinite(cycle) or not .4 <= cycle <= 4:
        raise ValueError('Interaction cycle must be 0.4–4 seconds')
    fraction = (max(0,elapsed) % cycle)/cycle*4
    index = min(3,int(fraction))
    blend = fraction-index
    blend = blend*blend*(3-2*blend)  # ease each phase without discontinuous jumps
    stops = (0,.65,1,.35,0)
    reach = stops[index]+(stops[index+1]-stops[index])*blend
    return index,reach


class InteractionView:
    def __init__(self, cycle=1.0):
        phase_at(0,cycle)
        self.cycle = cycle
        self.play_cycle = cycle
        self.key = None
        self.elapsed = 0.0
        self.direction = 'down'

    @property
    def active(self):
        return self.key is not None

    @property
    def state(self):
        return 'interact_gather' if self.active else 'idle'

    @property
    def phase(self):
        return PHASES[phase_at(self.elapsed,self.play_cycle)[0]]

    def sync(self, sim, actor, character, enabled=True, tick_boundary=False):
        job = sim.progress.jobs.get(actor.id)
        valid = (enabled and job is not None and job.action.kind == ActionType.GATHER
                 and job.duration_ticks*.25 >= .4
                 and not character.animator.moving and not character.segments
                 and validate(job.action,actor,sim.world,sim.resources,sim.social))
        if not valid:
            self.key = None
            return
        key = (job.finish_tick,job.duration_ticks,job.action.target)
        if key != self.key or tick_boundary:
            start = job.finish_tick-job.duration_ticks
            self.elapsed = max(0,(sim.tick-start)*.25)
        duration = job.duration_ticks*.25
        repeats = max(1,round(duration/self.cycle),math.ceil(duration/4))
        self.play_cycle = duration/repeats  # end the final RETURN at actual completion
        self.key = key
        self.direction = actor.facing

    def advance(self, seconds, paused=False):
        if self.active and not paused:
            self.elapsed += seconds

    def draw(self, screen, foot, *, scale=1):
        if self.active:
            draw_pose(screen,foot,self.direction,self.elapsed,self.play_cycle,scale=scale)


def draw_pose(screen, foot, direction, elapsed, cycle=1.0, *, scale=1):
    """Small resource/leaf motion, never a fake arm or a walking-frame cycle."""
    index,reach = phase_at(elapsed,cycle)
    sx,sy = HAND_POINTS[direction];ex,ey = CONTACT_POINTS[direction]
    x = foot[0]+(sx+(ex-sx)*reach)*scale
    y = foot[1]+(sy+(ey-sy)*reach-math.sin(reach*math.pi)*3)*scale
    # Fade the accent into the sprite at both neutral ends of a cycle.
    radius = max(0,round(min(1,reach*4)*2*scale))
    if not radius:
        return
    if index in (0,1):
        # A tiny contact glint marks intent, not a collected inventory item.
        color=(239,217,145)
        pygame.draw.line(screen,color,(round(x-2*scale),round(y)),(round(x+2*scale),round(y)),max(1,scale))
        pygame.draw.line(screen,color,(round(x),round(y-2*scale)),(round(x),round(y+2*scale)),max(1,scale))
    else:
        # Provisional berry/leaf picking accent. Executor alone awards real food.
        pygame.draw.circle(screen,(159,61,100),(round(x),round(y)),radius)
        pygame.draw.circle(screen,(235,150,162),(round(x-scale),round(y-scale)),max(1,scale))
        pygame.draw.line(screen,(111,157,77),(round(x),round(y-radius)),(round(x+3*scale),round(y-radius-scale)),max(1,scale))


def draw_preview_target(screen,foot,direction,scale=2):
    """Context prop in the explicitly non-playing preview, never a world resource."""
    dx,dy=CONTACT_POINTS[direction]
    x,y=round(foot[0]+dx*scale),round(foot[1]+dy*scale)
    pygame.draw.ellipse(screen,(42,87,57),(x-9*scale,y-4*scale,18*scale,9*scale))
    pygame.draw.ellipse(screen,(67,115,65),(x-7*scale,y-5*scale,14*scale,8*scale))
    for bx,by in ((-4,0),(0,-2),(4,1)):
        pygame.draw.circle(screen,(159,61,100),(x+bx*scale,y+by*scale),2*scale)
