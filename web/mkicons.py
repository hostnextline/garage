"""Draws the home-screen icons (web/icons/*.png). Usage: python3 mkicons.py [OUT_DIR]"""
import os, sys
from playwright.sync_api import sync_playwright
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{s}" height="{s}"><rect width="64" height="64" rx="{r}" fill="#1E1915"/><g transform="{t}rotate(45 32 32)"><rect x="28.5" y="24" width="7" height="30" rx="3.5" fill="#F7974F"/><circle cx="32" cy="19" r="11" fill="#F7974F"/><rect x="28" y="6" width="8" height="12" rx="1.5" fill="#1E1915"/><circle cx="32" cy="48" r="2" fill="#1E1915"/></g></svg>'''
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, size, r in [('icon-512.png', 512, 14), ('icon-192.png', 192, 14), ('icon-180.png', 180, 0), ('icon-maskable-512.png', 512, 0)]:
        pg = b.new_page(viewport={'width': size, 'height': size})
        pg.set_content('<html><body style="margin:0;background:transparent">' + SVG.format(s=size, r=r, t=('translate(32 32) scale(0.76) translate(-32 -32) ' if 'maskable' in name else '')) + '</body></html>')
        pg.screenshot(path=os.path.join(OUT, '') + name, omit_background=True, clip={'x': 0, 'y': 0, 'width': size, 'height': size})
        pg.close()
    b.close()
