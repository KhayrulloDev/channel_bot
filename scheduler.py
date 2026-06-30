"""
APScheduler yordamida har bir ulangan kanalga mustaqil ravishda avtomatik post yuborish.
Har bir kanal o'zining interval_hours qiymatiga mos alohida job'ga ega.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application

import db
from gemini_client import generate_post

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _job_id(channel_id: int) -> str:
    return f"autopost_{channel_id}"


async def publish_auto_post(app: Application, channel_id: int):
    """Gemini bilan post yaratib, kanalga joylaydi. Xato bo'lsa kanal egasiga xabar beradi."""
    channel = db.get_channel(channel_id)
    if not channel or not channel["autopost_enabled"]:
        return
    try:
        text = generate_post(channel)
        await app.bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
        db.add_history_entry(channel_id, text, source="auto")
        logger.info("Avtomatik post kanalga joylandi: %s", channel_id)
    except Exception as exc:
        logger.exception("Avtomatik post xatosi (kanal %s)", channel_id)
        try:
            await app.bot.send_message(
                chat_id=channel["owner_user_id"],
                text=(
                    f"⚠️ \"{channel['title']}\" kanaliga avtomatik post yuborishda xatolik:\n{exc}"
                ),
            )
        except TelegramError:
            pass


def reschedule_channel(app: Application, channel_id: int):
    """Bitta kanal uchun jobni joriy sozlamalarga mos qayta o'rnatadi."""
    channel = db.get_channel(channel_id)
    job_id = _job_id(channel_id)

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if channel and channel["autopost_enabled"]:
        scheduler.add_job(
            publish_auto_post,
            "interval",
            hours=channel["interval_hours"],
            args=[app, channel_id],
            id=job_id,
            next_run_time=None,  # birinchi post intervaldan keyin yuboriladi
        )
        logger.info("Kanal %s uchun avtopost yoqildi: har %s soatda.", channel_id, channel["interval_hours"])
    else:
        logger.info("Kanal %s uchun avtopost o'chirilgan.", channel_id)


def start_scheduler(app: Application):
    """Bot ishga tushganda barcha autopost yoqilgan kanallarni rejaga qo'shadi."""
    for channel in db.list_all_autopost_channels():
        reschedule_channel(app, channel["channel_id"])
    scheduler.start()

