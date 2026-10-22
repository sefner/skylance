#!/usr/bin/env python3
"""Build the standalone, installable Skylance web app from the artifact source.

src/skylance.html is the page exactly as published to Claude (no <html>/<head> wrapper).
This wraps it into a full document with home-screen/full-screen metadata, writes a web app
manifest, app icons and an offline service worker into docs/, which GitHub Pages serves.
"""
import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src' / 'skylance.html'
DIST = ROOT / 'docs'  # GitHub Pages serves from /docs


def draw_icon(size):
    """App icon: a lock-on reticle around a gold lance arc on deep dusk teal."""
    s = size * 4  # supersample, then downscale for smooth edges
    img = Image.new('RGB', (s, s), (14, 42, 51))
    d = ImageDraw.Draw(img)
    for r in range(int(s * 0.75), 0, -max(1, s // 200)):  # warm glow low in the frame
        t = r / (s * 0.75)
        col = tuple(int(a * t + b * (1 - t)) for a, b in zip((14, 42, 51), (120, 70, 40)))
        d.ellipse([s / 2 - r, s * 0.78 - r, s / 2 + r, s * 0.78 + r], fill=col)
    c, R, w = s / 2, s * 0.27, max(2, s // 40)
    cyan, gold = (134, 242, 255), (255, 179, 71)
    for i in range(4):  # bracket corners
        a = i * math.pi / 2 + math.pi / 4
        x, y = c + math.cos(a) * R * 1.25, c + math.sin(a) * R * 1.25
        sx, sy = (1 if math.cos(a) > 0 else -1), (1 if math.sin(a) > 0 else -1)
        L = R * 0.42
        d.line([(x, y), (x - sx * L, y)], fill=cyan, width=w)
        d.line([(x, y), (x, y - sy * L)], fill=cyan, width=w)
    d.ellipse([c - R * 0.55, c - R * 0.55, c + R * 0.55, c + R * 0.55], outline=cyan, width=w)
    pts = [(c - R * 1.1 + i / 40 * R * 2.2, c + R * 0.9 - math.sin(i / 40 * math.pi) * R * 1.6) for i in range(41)]
    glow = Image.new('RGB', (s, s), (0, 0, 0))
    ImageDraw.Draw(glow).line(pts, fill=gold, width=w * 4)
    img = Image.blend(img, Image.composite(glow, img, glow.convert('L')).filter(ImageFilter.GaussianBlur(s / 60)), 0.6)
    d = ImageDraw.Draw(img)
    d.line(pts, fill=gold, width=w)
    d.ellipse([c - w * 1.6, c - w * 1.6, c + w * 1.6, c + w * 1.6], fill=(255, 240, 220))
    return img.resize((size, size), Image.LANCZOS)


def main():
    page = SRC.read_text()
    page = page.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
    cut = page.index('<canvas id="gl">')
    head_part, body_part = page[:cut], page[cut:]
    version = hashlib.sha1(page.encode()).hexdigest()[:10]
    cdn = sorted(set(re.findall(r'<script src="(https://[^"]+)"', body_part)))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Skylance">
<meta name="theme-color" content="#0e2a33">
<meta name="description" content="An on-rails dragon shooter: lock on, release huge volleys, grow your dragon.">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
<style>html{{-webkit-text-size-adjust:100%}}body{{margin:0}}</style>
{head_part.strip()}
</head>
<body>
{body_part.strip()}
<script>if ('serviceWorker' in navigator) addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {{}}));</script>
</body>
</html>
"""
    DIST.mkdir(exist_ok=True)
    (DIST / 'index.html').write_text(html)
    manifest = {
        'name': 'Skylance', 'short_name': 'Skylance', 'start_url': './', 'scope': './',
        'display': 'fullscreen', 'display_override': ['fullscreen', 'standalone'], 'orientation': 'portrait',
        'background_color': '#0e2a33', 'theme_color': '#0e2a33',
        'description': 'An on-rails dragon shooter: lock on, release huge volleys, grow your dragon.',
        'icons': [
            {'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any maskable'},
            {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'},
        ],
    }
    (DIST / 'manifest.webmanifest').write_text(json.dumps(manifest, indent=2))
    for name, size in [('icon-192.png', 192), ('icon-512.png', 512), ('apple-touch-icon.png', 180)]:
        draw_icon(size).save(DIST / name)
    precache = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'] + cdn
    sw = f"""// Offline cache for Skylance. The version changes whenever the game changes, which retires the old cache.
const CACHE = 'skylance-{version}';
const PRECACHE = {json.dumps(precache, indent=2)};
self.addEventListener('install', e => {{ e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())); }});
self.addEventListener('activate', e => {{ e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); }});
self.addEventListener('fetch', e => {{
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  // the game page itself: network first so updates arrive, cache when offline
  if (url.origin === location.origin && (url.pathname.endsWith('/') || url.pathname.endsWith('index.html'))) {{
    e.respondWith(fetch(e.request).then(r => {{ const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; }}).catch(() => caches.match(e.request)));
    return;
  }}
  // everything else (engine scripts, fonts, icons): cache first
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {{
    if (r.ok || r.type === 'opaque') {{ const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }}
    return r;
  }})));
}});
"""
    (DIST / 'sw.js').write_text(sw)
    (DIST / '.nojekyll').write_text('')
    print(f'built docs/ (version {version}, {len(cdn)} CDN scripts precached)')


if __name__ == '__main__':
    main()
