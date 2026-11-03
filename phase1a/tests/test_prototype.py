import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from animator import SpriteAnimator
from preprocess import ROOT, NAMES, DIRECTIONS, extract, remove_background

class AnimationTests(unittest.TestCase):
    def make(self):
        return SpriteAnimator({d:list(range(5)) for d in DIRECTIONS})
    def test_idle_and_facing(self):
        a=self.make(); a.update(0,True,'left'); self.assertEqual(a.index,1)
        a.update(.25,True); self.assertEqual(a.index,3)
        a.update(0,False); self.assertEqual(a.index,0); self.assertEqual(a.direction,'left')
    def test_rate_independence_and_wrap(self):
        a,b=self.make(),self.make()
        a.update(0,True); b.update(0,True)
        for _ in range(120): a.update(1/120,True)
        for _ in range(30): b.update(1/30,True)
        self.assertEqual(a.index,b.index); self.assertEqual(a.index,1)
    def test_reject_invalid(self):
        with self.assertRaises(ValueError): SpriteAnimator({},0)
        with self.assertRaises(ValueError): self.make().update(-1,True)
    def test_all_real_sheets(self):
        for name in NAMES:
            frames, records=extract(Image.open(ROOT/'assets'/'characters'/f'{name}.png'))
            self.assertEqual(len(frames),20)
            self.assertEqual(len(records),20)
            for frame in frames:
                self.assertGreater(frame.height,240)
                self.assertLess(frame.height,330)
                self.assertGreater(frame.width,100)
            for d in DIRECTIONS:
                for i in range(5):
                    im=Image.open(ROOT/'assets'/'processed'/name/f'{d}_{i}.png')
                    self.assertEqual(im.size,(160,200))
                    self.assertEqual(im.getbbox()[3],190)
    def test_background_preserves_enclosed_white(self):
        im=Image.new('RGB',(9,9),'white')
        for x in range(2,7):
            for y in range(2,7): im.putpixel((x,y),(0,0,0))
        im.putpixel((4,4),(255,255,255))
        out=remove_background(im)
        self.assertEqual(out.getpixel((0,0))[3],0)
        self.assertEqual(out.getpixel((4,4))[3],255)

if __name__=='__main__': unittest.main()
