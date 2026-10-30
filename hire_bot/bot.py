import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import admin, hire, start
from services import verifier
from services.scheduler import init_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set — add it to your .env file.")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(hire.router)

    await init_db()
    scheduler = init_scheduler(bot)
    scheduler.start()

    await hire.resume_pending_verifications(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await verifier.close()


if __name__ == "__main__":
    asyncio.run(main())
