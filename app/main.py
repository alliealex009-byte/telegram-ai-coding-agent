import asyncio, logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatType
from app.config import cfg
from app.agent import Agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
bot, dp, agent = Bot(cfg.bot_token), Dispatcher(), Agent()
jobs, locks = {}, {}

async def permitted(m):
    if m.chat.type != ChatType.PRIVATE:
        await m.answer("Please use me in a private DM.")
        return False
    if cfg.allow_ids and m.from_user.id not in cfg.allow_ids:
        await m.answer("This bot is restricted to authorized users.")
        return False
    return True

@dp.message(Command("start"))
async def start(m):
    if await permitted(m):
        await m.answer("Hi! I'm your VPS AI Coding Agent. Send a project description and I'll generate files, run isolated checks, attempt fixes, and return a ZIP. Use /help.")

@dp.message(Command("help"))
async def help_cmd(m):
    if await permitted(m):
        await m.answer("/new — start a build\n/status — current build\n/cancel — cancel\n/about — model details\n\nDescribe the language, features, database, APIs and deployment target.")

@dp.message(Command("new"))
async def new(m):
    if await permitted(m): await m.answer("Now send your detailed project description.")

@dp.message(Command("about"))
async def about(m):
    if await permitted(m):
        await m.answer(f"Primary model: {cfg.model}\nInference: local Ollama on VPS\nExecution: restricted Docker sandbox\nDelivery: ZIP in this DM")

@dp.message(Command("status"))
async def status(m):
    if await permitted(m):
        await m.answer("Build running." if jobs.get(m.from_user.id) else "No active build.")

@dp.message(Command("cancel"))
async def cancel(m):
    if await permitted(m):
        task = jobs.get(m.from_user.id)
        if task and not task.done():
            task.cancel()
            await m.answer("Cancellation requested.")
        else: await m.answer("No active build.")

@dp.message(F.text)
async def build(m):
    if not await permitted(m): return
    spec = (m.text or "").strip()
    if spec.startswith("/"): return
    if len(spec) < 20:
        await m.answer("Please describe the project in more detail (at least 20 characters).")
        return
    if len(spec) > 10000:
        await m.answer("Please keep your request under 10,000 characters.")
        return
    uid = m.from_user.id
    lock = locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        await m.answer("You already have a build running. Use /status or /cancel.")
        return
    async with lock:
        msg = await m.answer("Request accepted. Starting coding agent…")
        async def progress(s):
            try: await msg.edit_text(s)
            except Exception: pass
        task = asyncio.current_task()
        jobs[uid] = task
        try:
            result = await agent.build(uid, spec, progress)
            passed = result["check"] and result["check"]["ok"]
            await m.answer_document(
                FSInputFile(result["zip"], filename=f"project_{result['job']}.zip"),
                caption=f"ZIP ready 📦\nJob: {result['job']}\nFiles: {len(result['files'])}\nPython syntax check: {'PASSED' if passed else 'NOT PASSED'}\nReview BUILD_REPORT.md and source before deployment."
            )
            await progress("Completed. ZIP delivered.")
        except asyncio.CancelledError:
            await progress("Build cancelled.")
            raise
        except Exception as e:
            logging.exception("Build failed")
            await progress("Build failed: " + str(e)[:700])
        finally:
            jobs.pop(uid, None)

async def main():
    cfg.workspace.mkdir(parents=True, exist_ok=True)
    logging.info("Starting Telegram AI Coding Agent with %s", cfg.model)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
