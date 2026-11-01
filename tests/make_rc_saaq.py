"""a SAAQ receipt (registration: no TPS / TVQ) as a phone photo would show it, for the receipt test"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random
random.seed(7)
import sys
L = ["ATELIER BOLDUC", "455 RUE KING OUEST", "", "2026-10-26", "", "BOULONS ET ECROUS", "", "TOTAL          114,98", "", "MERCI"] if 'notax' in sys.argv else ["SAAQ", "SOCIETE DE L'ASSURANCE", "AUTOMOBILE DU QUEBEC", "", "2026-10-27  10:14", "", "IMMATRICULATION", "PLAQUE F1234", "", "TOTAL          312,45", "", "INTERAC        312,45", "", "MERCI"]
f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 34)
W, H = 760, 120 + 52 * len(L)
im = Image.new('L', (W, H), 236); d = ImageDraw.Draw(im)
for i, l in enumerate(L): d.text((60, 60 + 52 * i), l, fill=30, font=f)
im = im.rotate(-1.2, expand=True, fillcolor=120).filter(ImageFilter.GaussianBlur(0.6))
px = im.load()
for _ in range(20000):
    x, y = random.randrange(im.width), random.randrange(im.height); px[x, y] = max(0, min(255, px[x, y] + random.randint(-40, 40)))
im.convert('RGB').save('rc_notax.jpg' if 'notax' in sys.argv else 'rc_saaq.jpg', quality=82)
print(im.size)
