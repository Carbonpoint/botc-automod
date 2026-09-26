"""Browser check: agents answer the chat (fixed lines, or a chat model if the server has one).

A human storyteller hosts a game of agents, then asks the town, names an
agent, and sends an agent a private message.
Usage: uv run python scripts/agent_chat_check.py OUTDIR [PORT]
"""
import asyncio
import sys

from playwright.async_api import async_playwright

OUT = sys.argv[1]
BASE = f"http://127.0.0.1:{sys.argv[2] if len(sys.argv) > 2 else '8777'}"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 390, "height": 844})).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(BASE)
        await pg.fill("#name", "Hana")
        await pg.click('[data-act="host"]')
        await pg.wait_for_selector(".top .code")
        await pg.click('[data-act="pref"][data-k="mode"][data-v="human"]')
        await pg.wait_for_timeout(300)
        await pg.click('[data-act="toggle"][data-k="narrator"][data-v="0"]')
        await pg.click('[data-act="fillagents"]')
        await pg.wait_for_timeout(500)
        await pg.click('[data-act="start"]')
        await pg.wait_for_selector('[data-act="begin"]')
        await pg.click('[data-act="begin"]')
        for _ in range(240):                       # the storyteller confirms each night stage
            if "Discussion" in await pg.inner_text(".top"):
                break
            send = pg.locator('[data-act="sendpending"]')
            if await send.count():
                await send.first.click()
            await pg.wait_for_timeout(500)
        await pg.click('[data-act="tab"][data-v="chat"]')
        await pg.wait_for_timeout(8000)            # let the agents make their claims first

        async def ask(text, to=None, wait=16000):
            await pg.click(f'[data-act="thread"][data-v="{to or ""}"]')
            before = await pg.evaluate("S.chat.length")
            await pg.fill("#chat-text", text)
            await pg.click('[data-act="sendchat"]')
            await pg.wait_for_timeout(wait)
            new = await pg.evaluate(f"S.chat.slice({before} + 1).map(m => [S.players.find(p => p.id === m.from)?.name, m.to ? 'private' : 'group', m.text])")
            print(f"Hana: {text!r}", *(f"\n   {n} ({w}): {t}" for n, w, t in new))
            return new

        agents_ = await pg.evaluate("S.players.filter(p => p.agent).map(p => [p.id, p.name])")
        await ask("Anyone learn anything last night?")
        await ask(f"{agents_[0][1]}, what's your character?")
        r = await ask("hey, who do you suspect?", to=agents_[1][0])
        print("private answer came back privately:", any(w == "private" and n == agents_[1][1] for n, w, _ in r))
        await pg.screenshot(path=f"{OUT}/agent_chat.png", full_page=True)
        print("page errors:", errors or "none")
        await b.close()

asyncio.run(main())
