"""Lazy, aspect-preserving portrait caches. Never modifies original artwork."""
from collections import OrderedDict
from pathlib import Path
import pygame
from .characters import CHARACTERS

EXPRESSIONS={'neutral','happy','worried','annoyed','surprised','sad'}


class PortraitManager:
    def __init__(self,root=None):
        self.root=Path(root) if root else Path(__file__).resolve().parent.parent/'assets'/'portraits'
        self.originals={};self.scaled=OrderedDict();self.loads=0

    def original(self,agent_id,expression='neutral'):
        if agent_id not in CHARACTERS:return None
        expression=expression if expression in EXPRESSIONS else 'neutral'
        key=(agent_id,expression)
        if key not in self.originals:
            stem=CHARACTERS[agent_id][1]
            image=None
            names=(stem+'_'+expression+'.png',stem+'.png') if expression=='neutral' else (stem+'_'+expression+'.png',)
            for name in names:
                try:
                    image=pygame.image.load(str(self.root/name)).convert_alpha();self.loads+=1;break
                except (OSError,pygame.error):pass
            if image is None and expression!='neutral':image=self.original(agent_id,'neutral')
            self.originals[key]=image
        return self.originals[key]

    def fit(self,agent_id,box,expression='neutral'):
        expression=expression if expression in EXPRESSIONS else 'neutral'
        image=self.original(agent_id,expression)
        if image is None:return None
        key=(agent_id,expression,max(1,round(box[0])),max(1,round(box[1])))
        if key not in self.scaled:
            ratio=min(key[2]/image.get_width(),key[3]/image.get_height())
            size=(max(1,round(image.get_width()*ratio)),max(1,round(image.get_height()*ratio)))
            self.scaled[key]=pygame.transform.smoothscale(image,size)
            if len(self.scaled)>48:self.scaled.popitem(last=False)
        self.scaled.move_to_end(key)
        return self.scaled[key]
