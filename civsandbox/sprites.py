"""Cached Pygame assets; all frames share a uniform scale and foot anchor."""
from pathlib import Path
import pygame
import json
import logging

from .animation import DIRECTIONS
from .characters import CHARACTERS

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
FRAME_SIZE = (40, 50)
FOOT_ANCHOR = (20, 48)


class CharacterAssets:
    def __init__(self, root=ASSET_ROOT):
        self.frames = {}
        self.idle_frames = {}
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
            # Optional metadata declares exact counts and a source digest. No guessed frames.
            manifest = Path(root)/"processed"/key/"idle"/"manifest.json"
            idle = None
            try:
                data = json.loads(manifest.read_text())
                if not isinstance(data, dict) or data.get("character") != key or set(data["counts"]) != set(DIRECTIONS):
                    raise ValueError("Idle character/directions mismatch")
                idle = {}
                for direction in DIRECTIONS:
                    count = data["counts"][direction]
                    if type(count) is not int or not 1 <= count <= 32:
                        raise ValueError("Invalid idle frame count")
                    idle[direction] = []
                    for column in range(count):
                        path = manifest.parent/direction/f"{column}.png"
                        image = pygame.image.load(str(path)).convert_alpha()
                        if image.get_size() != (160, 200):
                            raise ValueError("Unexpected idle dimensions")
                        idle[direction].append(pygame.transform.smoothscale(image, FRAME_SIZE))
            except (OSError, ValueError, KeyError, TypeError, pygame.error) as error:
                logging.getLogger(__name__).debug("Optional idle unavailable for %s; using static directional poses: %s", key, error)
                idle = {d: [rows[d][0]] for d in DIRECTIONS}
            self.idle_frames[key] = idle

    def for_agent(self, agent):
        if agent.id not in CHARACTERS:
            raise ValueError("No supplied character artwork mapped to this NPC ID")
        return self.frames[CHARACTERS[agent.id][1]]

    def idle_for_agent(self, agent):
        if agent.id not in CHARACTERS:
            raise ValueError("No supplied character artwork mapped to this NPC ID")
        return self.idle_frames[CHARACTERS[agent.id][1]]
