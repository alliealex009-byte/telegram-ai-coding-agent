import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from app.agent import CodingAgent
from app.config import Settings, load_settings
from app.llm import OllamaClient
from app.sandbox import SandboxRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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
        "I will generate the files using your local Ollama model, verify them in an isolated "
        "Docker sandbox, attempt automated repairs if needed, and send you a .zip archive.\n\n"
        "Commands: /help, /about"
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    if not is_authorized(message, settings):
        return
    await message.answer(
        "Send any coding prompt in a private DM "
        "(for example: 'Create a Python FastAPI task manager with SQLite and unit tests').\n"
        "The finished project is delivered as a .zip file."
    )


@router.message(Command("about"))
async def cmd_about(message: Message, settings: Settings) -> None:
    if not is_authorized(message, settings):
        return
    await message.answer(
        f"Model: {settings.ollama_model}\n"
        f"Sandbox image: {settings.sandbox_image}\n"
        f"Max repair rounds: {settings.max_repair_rounds}\n"
        f"Job timeout: {settings.max_job_seconds}s"
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
    if message.from_user is None or message.text is None:
        return

    prompt = message.text.strip()
    if not prompt:
        return

    user_id = message.from_user.id
    status_msg = await message.answer("Queued build job...")

    async def update_status(text: str) -> None:
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    async def _run_job() -> tuple[Path, str, bool, str]:
        async with job_semaphore:
            return await agent.build_project_zip(
                user_id=user_id,
                prompt=prompt,
                progress_cb=update_status,
            )

    try:
        zip_path, summary, passed, check_log = await asyncio.wait_for(
            _run_job(),
            timeout=settings.max_job_seconds,
        )

        status_label = "Passed sandbox checks" if passed else "Completed with sandbox warnings"
        caption = f"{summary[:700]}\nStatus: {status_label}"
        await message.answer_document(
            document=FSInputFile(zip_path),
            caption=caption[:1024],
        )

        if not passed and check_log:
            await message.answer(
                f"Sandbox log:\n<pre>{check_log[-3000:]}</pre>",
                parse_mode="HTML",
            )
    except asyncio.TimeoutError:
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

    logger.info("Starting Telegram AI Coding Agent with model %s", settings.ollama_model)
    await dp.start_polling(
        bot,
        settings=settings,
        agent=agent,
        job_semaphore=job_semaphore,
    )


if __name__ == "__main__":
    asyncio.run(main())
