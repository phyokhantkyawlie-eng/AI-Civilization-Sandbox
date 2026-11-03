"""Cached Pygame assets; all frames share a uniform scale and foot anchor."""
from pathlib import Path
import pygame

from .animation import DIRECTIONS
from .characters import CHARACTERS

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
FRAME_SIZE = (40, 50)
FOOT_ANCHOR = (20, 48)


class CharacterAssets:
    def __init__(self, root=ASSET_ROOT):
        self.frames = {}
        for _, key in CHARACTERS.values():
            rows = {}
            for direction in DIRECTIONS:
                frames = []
                for column in range(5):
                    path = Path(root)/"processed"/key/f"{direction}_{column}.png"
                    image = pygame.image.load(str(path)).convert_alpha()
                    if image.get_size() != (160, 200):
                        raise ValueError(f"Unexpected normalized frame dimensions: {path.name}")
                    frames.append(pygame.transform.smoothscale(image, FRAME_SIZE))
                rows[direction] = frames
            self.frames[key] = rows

    def for_agent(self, agent):
        if agent.id not in CHARACTERS:
            raise ValueError("No supplied character artwork mapped to this NPC ID")
        return self.frames[CHARACTERS[agent.id][1]]
