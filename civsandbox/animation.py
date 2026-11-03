"""Reusable animation and observed grid movement; no simulation or Pygame imports."""
from collections import deque
from dataclasses import dataclass
import math

DIRECTIONS = ("down", "left", "right", "up")


class SpriteAnimator:
    def __init__(self, frames, fps=8.0):
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Animation FPS must be finite and positive")
        if any(direction not in frames or len(frames[direction]) != 5 for direction in DIRECTIONS):
            raise ValueError("Each direction needs one idle and four walking frames")
        self.frames = frames
        self.fps = fps
        self.direction = "down"
        self.moving = False
        self.elapsed = 0.0

    def update(self, dt, moving, direction=None):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("Animation delta must be finite and nonnegative")
        direction = direction or self.direction
        if direction not in DIRECTIONS:
            raise ValueError("Unknown direction")
        if not moving or not self.moving or direction != self.direction:
            self.elapsed = 0.0
        self.direction = direction
        self.moving = moving
        if moving:
            self.elapsed += dt

    @property
    def index(self):
        return 1 + int(self.elapsed*self.fps + 1e-9) % 4 if self.moving else 0

    @property
    def frame(self):
        return self.frames[self.direction][self.index]


def facing_between(start, end):
    directions = {(0, 1): "down", (-1, 0): "left", (1, 0): "right", (0, -1): "up"}
    return directions.get((end[0]-start[0], end[1]-start[1]))


@dataclass(frozen=True)
class MovementSegment:
    start: tuple[int, int]
    end: tuple[int, int]
    seconds: float


class CharacterView:
    """Interpolate only cardinal steps actually observed after simulation ticks.

    Queues retain corners when a render frame contains several simulation ticks.
    The renderer never writes back a visual position to the agent.
    """
    def __init__(self, position, animator):
        self.animator = animator
        self.logical_position = position
        self.position = tuple(float(v) for v in position)
        self.segments = deque()
        self.segment_elapsed = 0.0

    def snap(self, position):
        self.logical_position = position
        self.position = tuple(float(v) for v in position)
        self.segments.clear()
        self.segment_elapsed = 0.0
        self.animator.update(0, False)

    def capture(self, position, seconds):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Movement duration must be finite and positive")
        if position == self.logical_position:
            if self.segments:
                self.segments.append(MovementSegment(position, position, seconds))
            else:
                self.animator.update(0, False)
            return
        if facing_between(self.logical_position, position) is None:
            # E.g. an externally restored state: do not invent an unobserved path.
            self.snap(position)
            return
        self.segments.append(MovementSegment(self.logical_position, position, seconds))
        self.logical_position = position
        if len(self.segments) == 1:
            self.animator.update(0, True, facing_between(self.segments[0].start, position))

    def advance(self, dt, paused=False, *, speed=1.0, tick_boundary=False):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("Movement delta must be finite and nonnegative")
        if paused:
            self.animator.update(0, False)
            return
        while self.segments:
            segment = self.segments[0]
            duration = min(dt, segment.seconds-self.segment_elapsed)
            self.animator.update(duration/speed, segment.start != segment.end, facing_between(segment.start, segment.end))
            self.segment_elapsed += duration
            fraction = min(1.0, self.segment_elapsed/segment.seconds)
            self.position = tuple(a+(b-a)*fraction for a, b in zip(segment.start, segment.end))
            dt = max(0.0, dt-duration)
            if self.segment_elapsed+1e-12 < segment.seconds:
                return
            self.position = tuple(float(v) for v in segment.end)
            self.segments.popleft()
            self.segment_elapsed = 0.0
            if dt <= 1e-12:
                break
        if not self.segments:
            if not tick_boundary:
                self.animator.update(0, False)
        else:
            segment = self.segments[0]
            self.animator.update(0, segment.start != segment.end, facing_between(segment.start, segment.end))
