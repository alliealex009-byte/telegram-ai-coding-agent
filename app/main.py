import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from app.agent import CodingAgent
from app.config import Settings, load_settings
from app.llm import OllamaClient
from app.sandbox import SandboxRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

router = Router()


def is_authorized(message: Message, settings: Settings) -> bool:
    if message.chat.type != ChatType.PRIVATE:
        return False
    if not settings.allowed_user_ids:
        return True
    return bool(message.from_user and message.from_user.id in settings.allowed_user_ids)


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    if not is_authorized(message, settings):
        return
    await message.answer(
        "Send me a project specification in private DM.\n"
        "I will generate the files using local Ollama, verify them in an isolated Docker sandbox, "
        "attempt automated repairs if needed, and send you a .zip archive.\n\n"
        "Commands: /help, /about"
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    if not is_authorized(message, settings):
        return
    await message.answer(
        "Send any coding prompt in DM (for example: 'Create a FastAPI TODO app with SQLite and tests').\n"
        "The output is delivered as a .zip file."
    )


@router.message(Command("about"))
async def cmd_about(message: Message, settings: Settings) -> None:
    if not is_authorized(message, settings):
        return
    await message.answer(
        f"Model: {settings.ollama_model}\n"
        f"Sandbox: {settings.sandbox_image}\n"
        f"Max repair rounds: {settings.max_repair_rounds}"
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_prompt(
    message: Message,
    settings: Settings,
    agent: CodingAgent,
    job_semaphore: asyncio.Semaphore,
) -> None:
    if not is_authorized(message, settings):
        return
    assert message.from_user is not None
    prompt = message.text.strip()
    if not prompt:
        return

    status_msg = await message.answer("Queued build job...")

    async def update_status(text: str) -> None:
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    try:
        async with asyncio.timeout(settings.max_job_seconds):
            async with job_semaphore:
                zip_path, summary, passed, check_log = await agent.build_project_zip(
                    user_id=message.from_user.id,
                    prompt=prompt,
                    progress_cb=update_status,
                )

        status_label = "Passed sandbox checks" if passed else "Completed with sandbox warnings"
        caption = f"{summary[:700]}\nStatus: {status_label}"
        await message.answer_document(document=FSInputFile(zip_path), caption=caption[:1024])
        if not passed and check_log:
            await message.answer(f"Sandbox log:\n<pre>{check_log[-3000:]}</pre>", parse_mode="HTML")
    except TimeoutError:
        await message.answer("Build timed out before finishing.")
    except Exception as exc:
        logger.exception("Build failed")
        await message.answer(f"Build failed: {exc}")


async def main() -> None:
    settings = load_settings()
    llm = OllamaClient(settings)
    sandbox = SandboxRunner(settings)
    agent = CodingAgent(settings, llm, sandbox)
    job_semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(
        bot,
        settings=settings,
        agent=agent,
        job_semaphore=job_semaphore,
    )


if __name__ == "__main__":
    asyncio.run(main())
