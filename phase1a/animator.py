"""Animation timing has no dependency on rendering or pygame."""
class SpriteAnimator:
    def __init__(self, frames, fps=8):
        if fps <= 0:
            raise ValueError('fps must be positive')
        if any(len(frames[d]) != 5 for d in ('down', 'left', 'right', 'up')):
            raise ValueError('Each direction requires idle plus four walk frames')
        self.frames, self.fps = frames, fps
        self.direction, self.moving, self.elapsed = 'down', False, 0.0

    def update(self, dt, moving, direction=None):
        if dt < 0:
            raise ValueError('dt must be nonnegative')
        if direction is not None:
            if direction not in self.frames:
                raise ValueError(direction)
            self.direction = direction
        if not moving or not self.moving:
            self.elapsed = 0.0
        elif moving:
            self.elapsed += dt
        self.moving = moving

    @property
    def index(self):
        return 1 + int(self.elapsed*self.fps + 1e-9) % 4 if self.moving else 0

    @property
    def frame(self):
        return self.frames[self.direction][self.index]
