#!/usr/bin/env python3
"""Generate card background: sky banner + angled cut + rounded corners (RGBA).
Output: ~/.cache/sholat-card-bg.png
Usage: python3 gen-card-bg.py [sky_image_path]
"""
import os
import sys
from PIL import Image, ImageDraw

HOME = os.path.expanduser('~')
OUT = os.path.join(HOME, '.cache', 'sholat-card-bg.png')

W, H = 640, 560
CARD_R = 28
SS = 4  # supersampling

# default sky image = sebelah script ini
sky_default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', 'assets', 'sholat-sky.jpg')
sky_path = sys.argv[1] if len(sys.argv) > 1 else sky_default

sky = Image.open(sky_path).convert('RGB')
banner_h = int(H * 0.38)
sw, sh = sky.size
crop_h = min(int(sw * banner_h / W), sh)
sky_c = sky.crop((0, 0, sw, crop_h)).resize((W, banner_h), Image.LANCZOS)

# gradasi gelap di bawah banner biar transisi lembut ke garis potong
grad = Image.new('L', (1, banner_h), 0)
for y in range(banner_h):
    grad.putpixel((0, y), int(140 * (y / banner_h) ** 1.6))
grad = grad.resize((W, banner_h))
dark = Image.new('RGB', (W, banner_h), (10, 10, 14))
sky_c = Image.composite(dark, sky_c, grad)

# card RGBA (alpha channel dipertahankan!)
card = Image.new('RGBA', (W, H), (14, 14, 18, 255))
card.paste(sky_c, (0, 0))

# angled cut body
M_left = banner_h - 20
M_right = banner_h + 25
poly_mask = Image.new('L', (W*SS, H*SS), 0)
d = ImageDraw.Draw(poly_mask)
d.polygon([(0, M_left*SS), (W*SS, M_right*SS), (W*SS, H*SS), (0, H*SS)], fill=255)
poly_mask = poly_mask.resize((W, H), Image.LANCZOS)
body_layer = Image.new('RGBA', (W, H), (14, 14, 18, 255))
card = Image.composite(body_layer, card, poly_mask)

# rounded corner mask (supersampled) -> alpha channel
mask_ss = Image.new('L', (W*SS, H*SS), 0)
d2 = ImageDraw.Draw(mask_ss)
d2.rounded_rectangle([0, 0, W*SS-1, H*SS-1], radius=CARD_R*SS, fill=255)
mask = mask_ss.resize((W, H), Image.LANCZOS)
card.putalpha(mask)

# border emas di layer terpisah
border = Image.new('RGBA', (W, H), (0, 0, 0, 0))
d3 = ImageDraw.Draw(border)
d3.rounded_rectangle([1, 1, W-2, H-2], radius=CARD_R, outline=(210, 170, 55, 230), width=2)
card = Image.alpha_composite(card, border)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
card.save(OUT)
print('card bg saved:', OUT, card.size)
