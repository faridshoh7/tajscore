"""Проверка вёрстки числами: переполнения, размеры, контраст, наличие блоков."""
import asyncio, sys
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
PAGES = sys.argv[1:] or ["/"]
SIZES = [("ПК 1500", 1500, 950), ("Планшет 900", 900, 900), ("Телефон 390", 390, 844)]

JS = """() => {
  const de = document.documentElement;
  const over = [...document.querySelectorAll('*')]
      .filter(e => e.getBoundingClientRect().right > de.clientWidth + 1)
      .map(e => e.tagName + '.' + (e.className || '').toString().slice(0,40));
  const cs = getComputedStyle(document.body);
  const q = s => document.querySelector(s);
  const box = s => { const e = q(s); if (!e) return null;
      const r = e.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height)}; };
  const small = [...document.querySelectorAll('button, a')]
      .filter(e => { const r = e.getBoundingClientRect();
                     return r.width > 0 && r.height > 0 && r.height < 28; }).length;
  return {
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    overflow: [...new Set(over)].slice(0,5),
    bg: cs.backgroundColor, color: cs.color, font: cs.fontFamily.split(',')[0],
    header: box('.hdr'), left: box('.col--left'), center: box('.col--center'), right: box('.col--right'),
    leagues: document.querySelectorAll('.league-item').length,
    matches: document.querySelectorAll('.match').length,
    blocks: document.querySelectorAll('.league-block').length,
    smallTargets: small,
    mobnav: getComputedStyle(q('.mobnav')).display,
    brandSize: q('.brand__name') ? getComputedStyle(q('.brand__name')).fontSize : null,
  };
}"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for path in PAGES:
            print(f"\n══════ {path} ══════")
            for label, w, h in SIZES:
                page = await b.new_page(viewport={"width": w, "height": h})
                # внешние картинки не грузим: проверяем вёрстку, а не сеть
                await page.route("**://media.api-sports.io/**", lambda r: asyncio.ensure_future(r.abort()))
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                await page.goto(BASE + path, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                r = await page.evaluate(JS)
                flag = "ПЕРЕПОЛНЕНИЕ" if r["scrollW"] > r["clientW"] + 1 else "ок"
                print(f"  {label:12} ширина {r['clientW']}/{r['scrollW']} {flag} | "
                      f"лиг {r['leagues']} матчей {r['matches']} блоков {r['blocks']} | "
                      f"колонки {r['left']} {r['center']} {r['right']} | мобнав {r['mobnav']}")
                if r["overflow"]: print("      вылезает:", r["overflow"])
                if errs: print("      JS-ошибки:", errs[:2])
                await page.close()
        await b.close()

asyncio.run(main())
