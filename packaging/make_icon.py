"""Draw the app icon (the same mark as the browser tab) and save packaging/icon.ico."""
from pathlib import Path
from PIL import Image, ImageDraw
size=256;image=Image.new('RGBA',(size,size),(0,0,0,0));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((0,0,size-1,size-1),radius=48,fill=(20,49,82,255))
for top in (72,120,168):draw.rectangle((64,top,191,top+31),fill=(255,255,255,255))
image.save(Path(__file__).with_name('icon.ico'),sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
