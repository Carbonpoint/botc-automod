"""Drive 5 phone-sized browsers through lobby, night 1, a nomination and a vote.

Usage: uv run python scripts/ui_check.py OUTDIR [BASE_URL] [human]
With "human", a 6th browser is a human storyteller who checks the deal and
approves the night results.
Screenshots go to OUTDIR. Needs a running server (default port 8765).
"""
import asyncio
import sys

from playwright.async_api import async_playwright

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765"
HUMAN = len(sys.argv) > 3 and sys.argv[3] == "human"
EDITION = sys.argv[4] if len(sys.argv) > 4 else "tb"
NAMES = (["Sam"] if HUMAN else []) + ["Hana", "Ivo", "Jess", "Kofi", "Lena"]


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
        if HUMAN:
            await host.click('[data-act="pref"][data-k="mode"][data-v="human"]')
            await host.wait_for_timeout(300)
        await host.wait_for_selector(f'[data-act="pref"][data-k="edition"][data-v="{EDITION}"]')
        await host.click(f'[data-act="pref"][data-k="edition"][data-v="{EDITION}"]')
        await host.wait_for_timeout(300)
        for pg, n in zip(pages[1:], NAMES[1:]):
            await pg.fill("#name", n)
            await pg.fill("#code", code)
            await pg.click('[data-act="joincode"]')
            await pg.wait_for_selector(".map")
        for _ in range(3):
            await host.click('[data-act="seats"][data-d="-1"]')
            await host.wait_for_timeout(250)
        players = pages[1:] if HUMAN else pages
        for i, pg in enumerate(players):
            await pg.click(f'.seat.empty[data-seat="{i}"]')
            await pg.wait_for_timeout(200)
            await pg.click('[data-act="pref"][data-k="team"][data-v="%s"]' % ("evil" if i == 1 else "good"))
            await pg.wait_for_timeout(200)
        await host.wait_for_timeout(400)
        await host.click('[data-act="toggle"][data-k="show_votes"][data-v="1"]')
        await host.wait_for_timeout(300)
        await host.screenshot(path=f"{OUT}/02_lobby_host.png", full_page=True)
        await host.click('[data-act="start"]')
        if HUMAN:
            await host.wait_for_selector('[data-act="begin"]')
            await host.wait_for_timeout(500)
            await host.screenshot(path=f"{OUT}/h1_setup_grimoire.png", full_page=True)
            await pages[1].screenshot(path=f"{OUT}/h2_player_waiting.png")
            await host.click('[data-act="begin"]')
            host = pages[1]
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
                if await pg.locator('[data-act="narrationdone"].primary').count():   # this phone is the narrator
                    await pg.screenshot(path=f"{OUT}/05b_dawn_narrator.png", full_page=True)
                    listener = pages[(i + 1) % len(pages)]
                    await listener.screenshot(path=f"{OUT}/05c_dawn_listener.png")
                    await pg.click('[data-act="narrationdone"].primary')
                elif await picks.count():
                    if not shot_choose:
                        await pg.screenshot(path=f"{OUT}/04_night_choose.png")
                        shot_choose = True
                    await picks.nth(0).click()
                    if "/2 chosen" in await pg.inner_text(".night"):
                        await picks.nth(1).click()
                    await pg.click('[data-act="submit"]')
                elif await pg.locator('[data-act="submitchar"]').count():
                    await pg.screenshot(path=f"{OUT}/04b_night_character.png")
                    await pg.click('[data-act="submitchar"]')
                elif await pg.locator('[data-act="submitpc"]').count():
                    await pg.screenshot(path=f"{OUT}/04c_night_player_character.png")
                    await pg.click('[data-act="submitpc"]')
                elif await pg.locator('[data-act="decoy"]').count():
                    await pg.locator('[data-act="decoy"]').nth(0).click()
                elif await pg.locator('[data-act="ack"]').count():
                    await pg.screenshot(path=f"{OUT}/05_night_info_{NAMES[i]}.png")
                    await pg.click('[data-act="ack"]')
            reviewing = HUMAN and await pages[0].locator('[data-act="sendpending"]').count()
            if reviewing:
                await pages[0].wait_for_timeout(300)
                await pages[0].screenshot(path=f"{OUT}/h3_review.png", full_page=True)
                await pages[0].click('[data-act="sendpending"]')
            if all_day and not reviewing:
                break
            await asyncio.sleep(1)
        if HUMAN:
            await pages[0].screenshot(path=f"{OUT}/h4_day_grimoire.png", full_page=True)
            print("page errors:", errors or "none")
            await b.close()
            return
        await pages[2].screenshot(path=f"{OUT}/06_day_me.png", full_page=True)
        await pages[2].click('[data-act="tab"][data-v="town"]')
        await pages[2].screenshot(path=f"{OUT}/07_day_town.png", full_page=True)
        act = pages[2].locator('[data-act="dayact"]')
        if await act.count():
            await act.first.click()
            await pages[2].wait_for_timeout(500)
            await pages[2].click('[data-act="tab"][data-v="log"]')
            print("day action logged:", (await pages[2].inner_text(".log li")).replace("\n", " ")[:120])
            await pages[2].click('[data-act="tab"][data-v="town"]')
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
        # Two votes to execute and one no, then look at the seats (host option show_votes is on).
        for i, pg in enumerate(pages[:3]):
            if await pg.locator('[data-act="vote"][data-v="1"]').count():
                await pg.click(f'[data-act="vote"][data-v="{0 if i == 2 else 1}"]')
                await pg.wait_for_timeout(200)
        await pages[3].wait_for_timeout(400)
        await pages[3].screenshot(path=f"{OUT}/09b_vote_marks.png", full_page=True)
        print("vote marks on seats:", await pages[3].locator(".seat .vmark").all_inner_texts())
        for pg in pages[3:]:
            if await pg.locator('[data-act="vote"][data-v="1"]').count():
                await pg.click('[data-act="vote"][data-v="1"]')
                await pg.wait_for_timeout(200)
        await pages[3].wait_for_timeout(500)
        await pages[3].click('[data-act="tab"][data-v="log"]')
        await pages[3].screenshot(path=f"{OUT}/10_log.png", full_page=True)
        print("page errors:", errors or "none")
        await b.close()


asyncio.run(main())
