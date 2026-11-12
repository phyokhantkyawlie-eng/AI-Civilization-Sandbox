"""Responsive parchment/bronze portrait modal, paging and input focus only."""
from collections import OrderedDict
import math
import pygame
from .characters import CHARACTERS
from .portraits import PortraitManager

INK=(63,48,40);BRONZE=(107,73,46);GOLD=(198,157,84);CREAM=(247,235,207)


def wrap(text,font,width):
    lines=[];line=''
    for word in text.split():
        if font.size(word)[0]>width:
            if line:lines.append(line);line=''
            piece=''
            for char in word:
                if font.size(piece+char)[0]>width and piece:lines.append(piece);piece=''
                piece+=char
            line=piece
        elif font.size((line+' '+word).strip())[0]>width and line:
            lines.append(line);line=word
        else:line=(line+' '+word).strip()
    return lines+[line] if line or not lines else lines


class DialogueView:
    def __init__(self,portraits=None):
        self.portraits=portraits or PortraitManager();self.fonts={};self.panels=OrderedDict()
        self.token=None;self.page=0;self.shown=0.;self.pages=[];self.rows=[]
        self.selected=0;self.scroll=0;self.visible_count=5;self.open_age=0.;self.last_choices=()
        self.veil=None;self.layout={};self.active_seen=False

    def font(self,size,serif=False):
        key=(size,serif)
        if key not in self.fonts:
            self.fonts[key]=pygame.font.SysFont('georgia',size) if serif else pygame.font.Font(None,size)
        return self.fonts[key]

    def panel(self,size):
        key=tuple(size)
        if key not in self.panels:
            surface=pygame.Surface(key,pygame.SRCALPHA)
            pygame.draw.rect(surface,BRONZE,surface.get_rect(),border_radius=12)
            inner=surface.get_rect().inflate(-6,-6)
            pygame.draw.rect(surface,CREAM,inner,border_radius=9)
            pygame.draw.rect(surface,GOLD,surface.get_rect().inflate(-12,-12),1,border_radius=7)
            for x,y,sx,sy in ((15,15,1,1),(key[0]-16,15,-1,1),(15,key[1]-16,1,-1),(key[0]-16,key[1]-16,-1,-1)):
                pygame.draw.line(surface,GOLD,(x,y),(x+sx*12,y),2)
                pygame.draw.line(surface,GOLD,(x,y),(x,y+sy*12),2)
                pygame.draw.circle(surface,GOLD,(x+sx*3,y+sy*3),2)
            self.panels[key]=surface
            if len(self.panels)>12:self.panels.popitem(last=False)
        self.panels.move_to_end(key);return self.panels[key]

    def geometry(self,size):
        w,h=size;margin=max(12,round(min(w,h)*.028))
        bottom=pygame.Rect(margin,round(h*.72),w-2*margin,h-round(h*.72)-margin)
        portrait=pygame.Rect(margin,margin+32,round(w*.43),bottom.top-margin*2-32)
        choices=pygame.Rect(round(w*.49),round(h*.14),w-round(w*.49)-margin,bottom.top-round(h*.14)-margin)
        close=pygame.Rect(w-margin-max(108,min(140,round(w*.14))),margin,max(108,min(140,round(w*.14))),32)
        return {'panel':bottom,'portrait':portrait,'choices':choices,'margin':margin,'close':close}

    def sync(self,controller,size):
        if not controller.active:
            self.active_seen=False;return
        if not self.active_seen:self.open_age=0;self.active_seen=True
        self.layout=self.geometry(size)
        font=self.font(max(22,round(size[1]*.037)))
        text=controller.current.text if controller.current else 'A moment, please...'
        token=(controller.serial,size,text)
        if token!=self.token:
            self.token=token;self.page=0;self.shown=0
            height=font.get_linesize();available=self.layout['panel'].height-80
            count=max(1,available//height)
            lines=wrap(text,font,self.layout['panel'].width-48)
            self.pages=[lines[i:i+count] for i in range(0,len(lines),count)]
        return font

    @property
    def complete(self):
        return bool(self.pages) and self.shown>=sum(len(line) for line in self.pages[self.page])

    def advance(self,seconds,controller):
        if controller.active:self.open_age+=seconds;self.shown+=max(0,seconds)*48
        else:self.active_seen=False

    def proceed(self,controller,sim):
        if not self.complete:self.shown=float('inf');return
        if self.page+1<len(self.pages):self.page+=1;self.shown=0;return
        controller.continue_line(sim)

    def handle(self,event,controller,sim):
        if not controller.active:return False
        if event.type==pygame.QUIT:return False
        choices=controller.choices(sim)
        if event.type==pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE,pygame.K_BACKSPACE):controller.close(sim,canceled=bool(controller.owner));return True
            if event.key in (pygame.K_UP,pygame.K_w,pygame.K_DOWN,pygame.K_s) and choices and self.complete:
                delta=-1 if event.key in (pygame.K_UP,pygame.K_w) else 1
                self.selected=(self.selected+delta)%len(choices)
                if self.selected<self.scroll:self.scroll=self.selected
                elif self.selected>=self.scroll+self.visible_count:self.scroll=self.selected-self.visible_count+1
            elif pygame.K_1<=event.key<=pygame.K_9 and choices and self.complete:
                index=event.key-pygame.K_1
                if index<len(choices):controller.choose(choices[index].key,sim)
            elif event.key in (pygame.K_RETURN,pygame.K_SPACE):
                if choices and self.complete:controller.choose(choices[min(self.selected,len(choices)-1)].key,sim)
                else:self.proceed(controller,sim)
            return True
        if event.type==pygame.MOUSEWHEEL and choices:
            self.scroll=max(0,min(max(0,len(choices)-self.visible_count),self.scroll-event.y));return True
        if event.type==pygame.MOUSEMOTION:
            for rect,index in self.rows:
                if rect.collidepoint(event.pos):self.selected=index
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            if self.layout.get('close') and self.layout['close'].collidepoint(event.pos):
                controller.close(sim,canceled=bool(controller.owner));return True
            if not self.complete:self.proceed(controller,sim)
            else:
                hit=next((i for rect,i in self.rows if rect.collidepoint(event.pos)),None)
                if hit is not None and hit<len(choices):controller.choose(choices[hit].key,sim)
                else:self.proceed(controller,sim)
            return True
        return True  # Modal focus consumes movement, world clicks and shortcuts.

    def draw(self,screen,controller,sim,assets):
        if not controller.active:return
        size=screen.get_size();font=self.sync(controller,size)
        w,h=size;layout=self.layout;panel=layout['panel'];box=layout['portrait'];menu=layout['choices']
        if self.veil is None or self.veil.get_size()!=size:
            self.veil=pygame.Surface(size,pygame.SRCALPHA);self.veil.fill((23,17,20,140))
        screen.blit(self.veil,(0,0))
        # Hide the game's HUD lettering beneath a quiet conversation header;
        # the actual world remains visible and the portrait is drawn above it.
        pygame.draw.rect(screen,(29,25,26),(0,0,w,min(80,round(h*.105))))
        speaker=controller.current.speaker_id if controller.current else controller.peer_id
        actor=sim.social.agents.get(speaker)
        name=actor.name if actor else CHARACTERS.get(speaker,('Traveler',''))[0]
        portrait=self.portraits.fit(speaker,box.size)
        shift=round((1-min(1,self.open_age/.24))**2*12)
        self.portrait_rect=None
        if portrait:
            rect=portrait.get_rect(midbottom=(box.centerx-shift,box.bottom))
            screen.blit(portrait,rect);self.portrait_rect=rect
        else:
            a=sim.social.agents.get(speaker)
            if a and a.id in CHARACTERS:
                sprite=assets.for_agent(a)[a.facing][0]
                key=('fallback',speaker,a.facing)
                if key not in self.portraits.scaled:
                    self.portraits.scaled[key]=pygame.transform.scale(sprite,(120,150))
                screen.blit(self.portraits.scaled[key],self.portraits.scaled[key].get_rect(center=box.center))
            small=self.font(24);screen.blit(small.render(name,True,CREAM),(box.x+12,box.bottom-32))
        shadow=panel.move(4,5);pygame.draw.rect(screen,(32,25,24),shadow,border_radius=12)
        screen.blit(self.panel(panel.size),panel)
        title_size=max(23,round(h*.034))
        title_font=self.font(title_size,True)
        while title_size>18 and title_font.size(name)[0]>panel.width-80:
            title_size-=1;title_font=self.font(title_size,True)
        while title_font.size(name)[0]>panel.width-80 and len(name)>4:name=name[:-4]+'...'
        self.displayed_name=name
        plate=pygame.Rect(panel.x+18,panel.y-25,min(panel.width-36,max(160,title_font.size(name)[0]+46)),42)
        pygame.draw.rect(screen,BRONZE,plate,border_radius=8);pygame.draw.rect(screen,GOLD,plate,1,border_radius=8)
        screen.blit(title_font.render(name,True,CREAM),(plate.x+19,plate.y+7))
        budget=int(self.shown) if math.isfinite(self.shown) else 100000
        y=panel.y+32
        for line in self.pages[self.page]:
            visible=line[:max(0,budget)];budget-=len(line)
            screen.blit(font.render(visible,True,INK),(panel.x+24,y));y+=font.get_linesize()
        small=self.font(max(18,round(h*.025)))
        choices=controller.choices(sim);keys=tuple((c.key,c.enabled) for c in choices)
        if keys!=self.last_choices:self.selected=0;self.scroll=0;self.last_choices=keys
        self.rows=[]
        if choices:
            row_h=max(44,round(h*.067));visible_count=max(1,(menu.height-70)//row_h);self.visible_count=visible_count
            self.scroll=max(0,min(max(0,len(choices)-visible_count),self.scroll))
            for i,choice in enumerate(choices[self.scroll:self.scroll+visible_count],self.scroll):
                row=pygame.Rect(menu.x,menu.y+(i-self.scroll)*row_h,menu.width,row_h-6)
                self.rows.append((row,i))
                color=(250,237,205) if i==self.selected else (228,216,190)
                if not choice.enabled:color=(169,165,153)
                pygame.draw.rect(screen,(42,32,30),row.move(3,3),border_radius=8)
                pygame.draw.rect(screen,color,row,border_radius=8)
                pygame.draw.rect(screen,GOLD if i==self.selected else BRONZE,row,2,border_radius=8)
                label=f'{i+1}. '+choice.label
                # Wrap choices without ever changing hit geometry.
                labels=wrap(label,self.font(max(21,round(h*.031))),row.width-30)
                for j,text in enumerate(labels[:2]):
                    screen.blit(self.font(max(21,round(h*.031))).render(text,True,INK),(row.x+13,row.y+9+j*21))
            selected=choices[min(self.selected,len(choices)-1)]
            if not selected.enabled:
                lines=wrap(selected.reason,small,menu.width-12)
                for i,text in enumerate(lines[:2]):screen.blit(small.render(text,True,CREAM),(menu.x+4,menu.y+min(visible_count,len(choices)-self.scroll)*row_h+2+i*18))
            if len(choices)>visible_count:
                cue='More choices: scroll or press Down' if self.scroll+visible_count<len(choices) else 'Earlier choices: scroll or press Up'
                screen.blit(small.render(cue,True,CREAM),(menu.x+4,menu.bottom-22))
        hint=('Choose with arrows / Enter or click' if choices else 'Listening...' if controller.waiting else 'Click / Enter: continue')
        if not self.complete:hint='Click / Enter: reveal line'
        if len(self.pages)>1:hint+=f'  {self.page+1}/{len(self.pages)}'
        hint+='   Esc: leave'
        screen.blit(small.render(hint,True,(110,85,60)),(panel.x+24,panel.bottom-32))
        a,b=controller.actors(sim)
        caption=(a.name+'  /  '+b.name) if a and b else 'Conversation'
        caption+='  /  Authored offline'
        while small.size(caption)[0]>w-2*layout['margin']-layout['close'].width-40 and len(caption)>4:caption=caption[:-4]+'...'
        caption_image=small.render(caption,True,CREAM)
        caption_box=pygame.Rect(layout['margin'],layout['margin']-3,caption_image.get_width()+22,29)
        pygame.draw.rect(screen,(46,34,30),caption_box,border_radius=7)
        pygame.draw.rect(screen,GOLD,caption_box,1,border_radius=7)
        screen.blit(caption_image,(caption_box.x+11,caption_box.y+6))
        close=layout['close']
        pygame.draw.rect(screen,BRONZE,close,border_radius=7)
        pygame.draw.rect(screen,GOLD,close,1,border_radius=7)
        label=small.render('Leave',True,CREAM)
        screen.blit(label,label.get_rect(center=close.center))
