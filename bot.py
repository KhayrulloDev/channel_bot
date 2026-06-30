"""
Kanal AI-Admin Bot — asosiy ishga tushirish fayli (ko'p foydalanuvchili versiya).

Istalgan foydalanuvchi botga yozib, o'z kanalini ulashi va mustaqil boshqarishi
mumkin. Gemini API kaliti umumiy (bot egasi tomonidan taqdim etiladi).

Ishga tushirish:
    1. .env faylini to'ldiring (.env.example asosida)
    2. pip install -r requirements.txt
    3. python bot.py

    yoki Docker bilan:
    docker compose up -d --build
"""
import logging
import sys

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import db
import handlers
import scheduler as sched

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    errors = config.validate_config()
    if errors:
        print("❌ Konfiguratsiya xatolari topildi:")
        for e in errors:
            print(f"  - {e}")
        print("\n.env faylini to'g'ri to'ldirib qaytadan urinib ko'ring (.env.example ga qarang).")
        sys.exit(1)

    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    # Post ConversationHandler — preview → image → admin approval
    post_conv = ConversationHandler(
        entry_points=[CommandHandler("post", handlers.cmd_post_start)],
        states={
            handlers.POST_CHOOSING: [
                CallbackQueryHandler(handlers.cb_post_add_image, pattern=r"^post:add_image$"),
                CallbackQueryHandler(handlers.cb_post_publish, pattern=r"^post:publish$"),
                CallbackQueryHandler(handlers.cb_post_regen, pattern=r"^post:regen$"),
                CallbackQueryHandler(handlers.cb_post_cancel, pattern=r"^post:cancel$"),
            ],
            handlers.POST_UPLOADING: [
                MessageHandler(filters.PHOTO, handlers.cb_post_receive_image),
                CallbackQueryHandler(handlers.cb_post_cancel, pattern=r"^post:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.cb_post_wrong_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", handlers.cb_post_cancel_cmd)],
        per_message=False,
        name="post_conv",
    )
    app.add_handler(post_conv)

    # Settings ConversationHandler — matn talab qiladigan maydonlar uchun
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handlers.cb_edit_field_start, pattern=r"^s:(topic|tone|interval):\-?\d+$"),
        ],
        states={
            handlers.AWAITING_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.cb_edit_field_receive),
            ],
        },
        fallbacks=[CommandHandler("cancel", handlers.cb_edit_cancel)],
        per_message=False,
        name="settings_conv",
    )
    app.add_handler(settings_conv)

    # Callback handlers — tugmalar uchun
    app.add_handler(CallbackQueryHandler(handlers.cb_open_settings, pattern=r"^open_settings:\-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_toggle_setting, pattern=r"^t:(hashtags|emoji|autopost):\-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_choose_language, pattern=r"^s:language:\-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_set_language, pattern=r"^sl:[^:]+:\-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_choose_length, pattern=r"^s:post_length:\-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_set_length, pattern=r"^spl:\d+:\-?\d+$"))

    # Umumiy
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("stats", handlers.cmd_stats))

    # Kanal ulash / boshqarish
    app.add_handler(CommandHandler("connect", handlers.cmd_connect))
    app.add_handler(CommandHandler("mychannels", handlers.cmd_mychannels))
    app.add_handler(CommandHandler("select", handlers.cmd_select))
    app.add_handler(CommandHandler("disconnect", handlers.cmd_disconnect))

    # Kontent (/post is handled by post_conv above)
    app.add_handler(CommandHandler("preview", handlers.cmd_preview))
    app.add_handler(CommandHandler("ideas", handlers.cmd_ideas))

    # Avtopilot (eski komandalar — orqaga moslik)
    app.add_handler(CommandHandler("autopost", handlers.cmd_autopost))
    app.add_handler(CommandHandler("interval", handlers.cmd_interval))

    # Sozlamalar
    app.add_handler(CommandHandler("settings", handlers.cmd_settings))
    app.add_handler(CommandHandler("history", handlers.cmd_history))
    # Eski komandalar ham ishlaydi (orqaga moslik)
    app.add_handler(CommandHandler("settopic", handlers.cmd_settopic))
    app.add_handler(CommandHandler("tone", handlers.cmd_tone))
    app.add_handler(CommandHandler("hashtags", handlers.cmd_hashtags))
    app.add_handler(CommandHandler("emoji", handlers.cmd_emoji))

    async def on_startup(application: Application):
        sched.start_scheduler(application)
        logger.info("Scheduler ishga tushdi.")

    app.post_init = on_startup

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=["message", "channel_post", "callback_query"])


if __name__ == "__main__":
    main()
