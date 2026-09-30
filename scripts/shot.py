"""Скриншоты сайта для проверки вёрстки. Только для разработки."""
import asyncio, sys, pathlib
from playwright.async_api import async_playwright

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8000"

PAGES = [("home", "/", 1500, 1000), ("home-mobile", "/", 400, 860)]
if len(sys.argv) > 2:
    PAGES = [(p.split("=")[0], p.split("=")[1], 1500, 1000) for p in sys.argv[2:]]


async def main():
    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, path, w, h in PAGES:
            page = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.on("console", lambda m: errors.append(f"[{name}] console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"[{name}] JS: {e}"))
            await page.goto(BASE + path, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=(w > 900),
                                  animations="disabled", timeout=60000)
            await page.close()
        await b.close()
    print("\n".join(errors) if errors else "Ошибок в консоли нет")
    print("Скриншоты:", ", ".join(str(p) for p in sorted(OUT.glob("*.png"))))

asyncio.run(main())
