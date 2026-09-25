"""Drive 5 phone-sized browsers through lobby, night 1, a nomination and a vote.

Usage: uv run python scripts/ui_check.py OUTDIR [BASE_URL]
Screenshots go to OUTDIR. Needs a running server (default port 8765).
"""
import asyncio
import sys

from playwright.async_api import async_playwright

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765"
NAMES = ["Hana", "Ivo", "Jess", "Kofi", "Lena"]


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pages, errors = [], []
        for n in NAMES:
            ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e, n=n: errors.append(f"{n}: {e}"))
            pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await pg.goto(BASE)
            pages.append(pg)
        host = pages[0]
        await host.screenshot(path=f"{OUT}/01_home.png")
        await host.fill("#name", NAMES[0])
        await host.click('[data-act="host"]')
        await host.wait_for_selector(".top .code")
        code = (await host.inner_text(".top .code")).strip()
        for pg, n in zip(pages[1:], NAMES[1:]):
            await pg.fill("#name", n)
            await pg.fill("#code", code)
            await pg.click('[data-act="joincode"]')
            await pg.wait_for_selector(".map")
        for _ in range(3):
            await host.click('[data-act="seats"][data-d="-1"]')
            await host.wait_for_timeout(250)
        for i, pg in enumerate(pages):
            await pg.click(f'.seat.empty[data-seat="{i}"]')
            await pg.wait_for_timeout(200)
            await pg.click('[data-act="pref"][data-k="team"][data-v="%s"]' % ("evil" if i == 1 else "good"))
            await pg.wait_for_timeout(200)
        await host.wait_for_timeout(400)
        await host.screenshot(path=f"{OUT}/02_lobby_host.png", full_page=True)
        await host.click('[data-act="start"]')
        await host.wait_for_selector(".night")
        await host.wait_for_timeout(300)
        await host.screenshot(path=f"{OUT}/03_night.png")
        shot_choose = False
        for _ in range(90):
            all_day = True
            for i, pg in enumerate(pages):
                if not await pg.locator(".night").count():
                    continue
                all_day = False
                picks = pg.locator('[data-act="pick"]')
                if await picks.count():
                    if not shot_choose:
                        await pg.screenshot(path=f"{OUT}/04_night_choose.png")
                        shot_choose = True
                    await picks.nth(0).click()
                    if "/2 chosen" in await pg.inner_text(".night"):
                        await picks.nth(1).click()
                    await pg.click('[data-act="submit"]')
                elif await pg.locator('[data-act="decoy"]').count():
                    await pg.locator('[data-act="decoy"]').nth(0).click()
                elif await pg.locator('[data-act="ack"]').count():
                    await pg.screenshot(path=f"{OUT}/05_night_info_{NAMES[i]}.png")
                    await pg.click('[data-act="ack"]')
            if all_day:
                break
            await asyncio.sleep(1)
        await pages[2].screenshot(path=f"{OUT}/06_day_me.png", full_page=True)
        await pages[2].click('[data-act="tab"][data-v="town"]')
        await pages[2].screenshot(path=f"{OUT}/07_day_town.png", full_page=True)
        await host.click('[data-act="tab"][data-v="host"]')
        await host.click('[data-act="advance"]')
        await host.wait_for_timeout(500)
        await host.screenshot(path=f"{OUT}/08_host_panel.png", full_page=True)
        await pages[2].locator(".seat", has_text="Kofi").click()
        await pages[2].click('[data-act="nominate-ok"]')
        await pages[2].wait_for_timeout(400)
        await host.click('[data-act="advance"]')
        await host.wait_for_timeout(500)
        for pg in pages:
            await pg.click('[data-act="tab"][data-v="town"]')
        await pages[3].screenshot(path=f"{OUT}/09_vote.png", full_page=True)
        for pg in pages:
            if await pg.locator('[data-act="vote"][data-v="1"]').count():
                await pg.click('[data-act="vote"][data-v="1"]')
                await pg.wait_for_timeout(200)
        await pages[3].wait_for_timeout(500)
        await pages[3].click('[data-act="tab"][data-v="log"]')
        await pages[3].screenshot(path=f"{OUT}/10_log.png", full_page=True)
        print("page errors:", errors or "none")
        await b.close()


asyncio.run(main())
