"""Phase 1A: manual character rendering and animation only."""
import argparse
import os
from animator import SpriteAnimator
from preprocess import ROOT, NAMES, DIRECTIONS, build


def movement(keys, pygame):
    x = int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT])
    y = int(keys[pygame.K_s] or keys[pygame.K_DOWN])-int(keys[pygame.K_w] or keys[pygame.K_UP])
    vector = pygame.Vector2(x, y)
    if vector.length_squared():
        vector.normalize_ip()
    direction = ('right' if x > 0 else 'left') if x else ('down' if y > 0 else 'up') if y else None
    return vector, direction


def render(screen, font, animator, name, position, inspect, step, background, pygame):
    screen.fill((91, 139, 77))
    lines = [f'{name.title()}   Direction: {animator.direction.upper()}   State: {"WALK" if animator.moving else "IDLE"}   Frame: {animator.index}',
             'WASD / arrows: move   1–4: Mira / Nyra / Kairo / Ren   ESC: quit',
             'Tab: inspector   Inspector: arrows direction/frame, B background, Space play']
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (255,255,240)), (20, 18+i*26))
    if not inspect:
        rect = animator.frame.get_rect(midbottom=(round(position.x), round(position.y)))
        screen.blit(animator.frame, rect)
        return
    for i in range(5):
        rect = pygame.Rect(100+i*180, 190, 160, 200)
        for y in range(0, 200, 10):
            for x in range(0, 160, 10):
                color = ((225,225,225) if (x//10+y//10)%2 else (160,160,160)) if background == 0 else ((30,30,30) if background == 1 else (255,255,255))
                pygame.draw.rect(screen, color, (rect.x+x, rect.y+y,10,10))
        screen.blit(animator.frames[animator.direction][i], rect)
        pygame.draw.line(screen, (255,70,70), (rect.x,rect.y+190), (rect.right,rect.y+190))
        pygame.draw.rect(screen, (255,220,70) if i == step else (50,70,50), rect, 3)
        screen.blit(font.render('IDLE' if i == 0 else f'WALK {i}', True, 'white'), (rect.x,410))
    chosen = animator.frames[animator.direction][step]
    screen.blit(pygame.transform.scale(chosen,(240,300)),(430,440))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--fps', type=float, default=8)
    parser.add_argument('--smoke-test', action='store_true', help='Exercise every character/direction and exit using dummy video')
    args = parser.parse_args()
    if args.smoke_test:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    if not (ROOT/'assets'/'processed'/'ren'/'up_4.png').exists():
        build()
    pygame.init()
    try:
        screen = pygame.display.set_mode((1100,750))
        pygame.display.set_caption('AI Civilization Sandbox — Phase 1A')
        font = pygame.font.Font(None,24)
        animations = [SpriteAnimator({d: [pygame.image.load(str(ROOT/'assets'/'processed'/n/f'{d}_{i}.png')).convert_alpha() for i in range(5)] for d in DIRECTIONS}, args.fps) for n in NAMES]
        clock = pygame.time.Clock()
        position = pygame.Vector2(550,475)
        selected, step, background, ticks = 0, 0, 0, 0
        inspect, playing, running = args.inspect, False, True
        while running:
            dt = clock.tick(60)/1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: running = False
                    elif pygame.K_1 <= event.key <= pygame.K_4:
                        selected = event.key-pygame.K_1
                    elif event.key == pygame.K_TAB: inspect = not inspect
                    elif inspect:
                        if event.key == pygame.K_b: background = (background+1)%3
                        elif event.key == pygame.K_SPACE: playing = not playing
                        elif event.key in (pygame.K_LEFT,pygame.K_RIGHT): step = (step+(1 if event.key == pygame.K_RIGHT else -1))%5
                        elif event.key in (pygame.K_UP,pygame.K_DOWN):
                            a = animations[selected]
                            a.direction = DIRECTIONS[(DIRECTIONS.index(a.direction)+(1 if event.key == pygame.K_DOWN else -1))%4]
            animator = animations[selected]
            if args.smoke_test:
                selected = (ticks//20)%4
                animator = animations[selected]
                animator.update(0.125, ticks%5 != 0, DIRECTIONS[(ticks//5)%4])
                inspect = ticks%2 == 0
            elif inspect:
                animator.update(dt, playing)
                if playing: step = animator.index
            else:
                vector, direction = movement(pygame.key.get_pressed(),pygame)
                animator.update(dt, bool(vector.length_squared()), direction)
                position += vector*230*dt
                position.x = max(80,min(1020,position.x))
                position.y = max(200,min(750,position.y))
            render(screen,font,animator,NAMES[selected],position,inspect,step,background,pygame)
            pygame.display.flip()
            ticks += 1
            if args.smoke_test and ticks >= 80:
                print('PASS: 4 characters × 4 directions; play/idle, inspector, rendering, clean shutdown')
                running = False
    finally:
        pygame.quit()

if __name__ == '__main__':
    main()
