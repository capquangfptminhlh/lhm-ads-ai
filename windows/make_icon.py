"""Generate LHM orange-black Windows icon for EXE."""
from pathlib import Path
from PIL import Image, ImageDraw

im=Image.new('RGBA',(256,256),(0,0,0,0))
d=ImageDraw.Draw(im)
d.rounded_rectangle((5,5,251,251),radius=58,fill=(21,20,20,255))
d.ellipse((51,50,205,204),fill=(236,125,65,255))
d.ellipse((70,69,186,185),fill=(21,20,20,255))
d.rounded_rectangle((117,65,139,191),radius=11,fill=(246,194,152,255))
d.rounded_rectangle((65,117,191,139),radius=11,fill=(246,194,152,255))
d.ellipse((113,113,143,143),fill=(255,235,210,255))
path=Path(__file__).with_name('lhm-ads-ai.ico')
im.save(path,format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(f'Windows icon ready: {path}')
