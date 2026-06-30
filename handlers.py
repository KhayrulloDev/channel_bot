"""
Telegram bot uchun barcha buyruqlar.

Istalgan foydalanuvchi botga shaxsiy chatda yozib, o'z kanalini /connect orqali
ulashi va keyin uni mustaqil boshqarishi mumkin. Gemini API kaliti umumiy
(bot egasi tomonidan taqdim etilgan), shuning uchun foydalanuvchidan API
kalit so'ralmaydi.
"""
import logging
from functools import wraps

from telegram import InlineKeyboardButton as IKB
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from config import SUPER_ADMIN_IDS
from gemini_client import generate_post, generate_post_idea_list
import db
import scheduler as sched

logger = logging.getLogger(__name__)

# ConversationHandler states
AWAITING_VALUE = 1   # settings text input
POST_CHOOSING = 20   # post preview — waiting for user action
POST_UPLOADING = 21  # waiting for photo upload

_POST_LENGTHS = ["qisqa (1-2 jumla)", "o'rta (3-6 jumla)", "uzun (7-10 jumla)"]
_LANGUAGES = ["o'zbek", "rus", "ingliz"]


def _settings_keyboard(ch: dict) -> InlineKeyboardMarkup:
    cid = ch["channel_id"]
    topic_lbl = ch["topic"][:28] + "…" if len(ch["topic"]) > 28 else ch["topic"]
    tone_lbl = ch["tone"][:28] + "…" if len(ch["tone"]) > 28 else ch["tone"]
    auto_lbl = "🔁 Avtopost: ✅" if ch["autopost_enabled"] else "⏸ Avtopost: ❌"
    return InlineKeyboardMarkup([
        [IKB(f"📌 Mavzu: {topic_lbl}", callback_data=f"s:topic:{cid}")],
        [IKB(f"🎨 Uslub: {tone_lbl}", callback_data=f"s:tone:{cid}")],
        [
            IKB(f"🌐 Til: {ch['language']}", callback_data=f"s:language:{cid}"),
            IKB(f"📏 {ch['post_length']}", callback_data=f"s:post_length:{cid}"),
        ],
        [
            IKB(f"#️⃣ {'✅' if ch['hashtags'] else '❌'} Hashtag", callback_data=f"t:hashtags:{cid}"),
            IKB(f"😀 {'✅' if ch['emoji'] else '❌'} Emoji", callback_data=f"t:emoji:{cid}"),
        ],
        [
            IKB(auto_lbl, callback_data=f"t:autopost:{cid}"),
            IKB(f"⏱ Har {ch['interval_hours']}s", callback_data=f"s:interval:{cid}"),
        ],
    ])


def _post_keyboard(has_image: bool) -> InlineKeyboardMarkup:
    if has_image:
        # Rasm preview — photo xabari ustida, edit_message_text ishlamaydi,
        # shuning uchun "Qayta yozish" yo'q (caption'ni o'zgartirib bo'lmaydi)
        return InlineKeyboardMarkup([
            [IKB("🖼 Rasmni o'zgartirish", callback_data="post:add_image"),
             IKB("✅ Kanalga yuborish", callback_data="post:publish")],
            [IKB("❌ Bekor", callback_data="post:cancel")],
        ])
    return InlineKeyboardMarkup([
        [IKB("📸 Rasm qo'shish", callback_data="post:add_image"),
         IKB("🔄 Qayta yozish", callback_data="post:regen")],
        [IKB("✅ Kanalga yuborish", callback_data="post:publish"),
         IKB("❌ Bekor", callback_data="post:cancel")],
    ])


# ---------- Yordamchi funksiyalar ----------

def requires_channel(func):
    """Foydalanuvchining faol (active) kanali borligini tekshiradi."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        channel = db.get_active_channel(user_id)
        if not channel:
            await update.message.reply_text(
                "📡 Sizda hali ulangan kanal yo'q.\n\n"
                "Avval /connect @kanal_username buyrug'i bilan kanalingizni ulang, "
                "yoki agar bir nechta kanalingiz bo'lsa /mychannels orqali tanlang."
            )
            return
        return await func(update, context, channel)
    return wrapper


def channel_owner_only(channel: dict, user_id: int) -> bool:
    return channel["owner_user_id"] == user_id


HELP_TEXT = (
    "🤖 <b>Kanal AI-Admin Bot</b>\n\n"
    "Gemini AI yordamida kanalingizni avtomatik yuritadi.\n\n"
    "<b>Boshlash — 2 qadam:</b>\n"
    "1) Botni kanalingizga <b>admin</b> qiling (Post Messages huquqi bilan)\n"
    "2) /connect @kanal_username\n\n"
    "<b>Asosiy buyruqlar:</b>\n"
    "/settings — barcha sozlamalar (tugmalar orqali)\n"
    "/post — AI post yaratib kanalga joylash\n"
    "/post mavzu — berilgan mavzu asosida post\n"
    "/preview — kanalga joylamay ko'rish\n"
    "/ideas — kontent g'oyalari\n"
    "/history — oxirgi postlar\n"
    "/mychannels — kanallar ro'yxati\n"
    "/select @kanal — faol kanalni tanlash\n"
    "/disconnect @kanal — kanalni chiqarish"
)


# ---------- Umumiy buyruqlar ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.ensure_user(update.effective_user.id)
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


# ---------- Kanalni ulash / boshqarish ----------

async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.ensure_user(user_id)

    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("⚠️ Iltimos, bu buyruqni bot bilan shaxsiy chatda yuboring.")
        return

    if not context.args:
        await update.message.reply_text(
            "Foydalanish: /connect @kanal_username\n"
            "(yoki kanal ID, masalan -1001234567890)\n\n"
            "Eslatma: avval botni kanalingizga admin qilib, xabar joylash huquqini berishingiz kerak."
        )
        return

    channel_ref = context.args[0]

    try:
        chat = await context.bot.get_chat(channel_ref)
    except TelegramError as exc:
        await update.message.reply_text(
            f"❌ Kanal topilmadi yoki bot unga hali qo'shilmagan: {exc}"
        )
        return

    if chat.type != ChatType.CHANNEL:
        await update.message.reply_text("❌ Bu kanal emas. Faqat Telegram kanallari qo'llab-quvvatlanadi.")
        return

    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    except TelegramError as exc:
        await update.message.reply_text(f"❌ Kanal a'zoligini tekshirib bo'lmadi: {exc}")
        return

    if bot_member.status != "administrator" or not getattr(bot_member, "can_post_messages", False):
        await update.message.reply_text(
            "❌ Bot ushbu kanalga admin sifatida qo'shilmagan yoki unda \"Post Messages\" "
            "(xabar joylash) huquqi yo'q.\n\n"
            "Kanal → Administrators → botni admin qiling va \"Post Messages\" huquqini bering, "
            "so'ng /connect buyrug'ini qaytadan yuboring."
        )
        return

    try:
        user_member = await context.bot.get_chat_member(chat.id, user_id)
    except TelegramError as exc:
        await update.message.reply_text(f"❌ Sizning kanal a'zoligingizni tekshirib bo'lmadi: {exc}")
        return

    if user_member.status not in ("administrator", "creator"):
        await update.message.reply_text(
            "❌ Siz ushbu kanalning admini emassiz. Faqat kanal adminlari uni ulashi mumkin."
        )
        return

    existing = db.get_channel(chat.id)
    if existing and existing["owner_user_id"] != user_id:
        await update.message.reply_text(
            "⚠️ Bu kanal allaqachon boshqa foydalanuvchi tomonidan ulangan. "
            "Agar bu xato deb hisoblasangiz, kanal egasidan /disconnect qilishini so'rang."
        )
        return

    channel = db.add_channel(
        channel_id=chat.id,
        username=f"@{chat.username}" if chat.username else None,
        title=chat.title or "Nomsiz kanal",
        owner_user_id=user_id,
    )
    db.set_active_channel(user_id, chat.id)

    await update.message.reply_text(
        f"✅ <b>{channel['title']}</b> ulandi!\n\n"
        "Endi kanal mavzusi va uslubini sozlang, so'ng /post bilan birinchi postni yarating.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            IKB("⚙️ Sozlamalarni o'rnating", callback_data=f"open_settings:{channel['channel_id']}"),
        ]]),
    )


async def cmd_mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    channels = db.list_user_channels(user_id)
    if not channels:
        await update.message.reply_text(
            "Sizda hali ulangan kanal yo'q. /connect @kanal_username bilan boshlang."
        )
        return

    active = db.get_active_channel(user_id)
    active_id = active["channel_id"] if active else None

    lines = ["📡 <b>Sizning kanallaringiz:</b>\n"]
    for c in channels:
        mark = "👉 " if c["channel_id"] == active_id else "    "
        auto = "🔁 auto" if c["autopost_enabled"] else "⏸ qo'lda"
        uname = c["username"] or str(c["channel_id"])
        lines.append(f"{mark}<b>{c['title']}</b> ({uname}) — {auto}")
    lines.append("\nTanlash uchun: /select @kanal_username")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Foydalanish: /select @kanal_username")
        return

    ref = context.args[0].lstrip("@").lower()
    channels = db.list_user_channels(user_id)
    match = None
    for c in channels:
        uname = (c["username"] or "").lstrip("@").lower()
        if uname == ref or str(c["channel_id"]) == context.args[0]:
            match = c
            break

    if not match:
        await update.message.reply_text(
            "❌ Bu kanal sizning ro'yxatingizda topilmadi. /mychannels orqali tekshiring."
        )
        return

    db.set_active_channel(user_id, match["channel_id"])
    await update.message.reply_text(f"✅ Faol kanal o'zgartirildi: <b>{match['title']}</b>", parse_mode=ParseMode.HTML)


async def cmd_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Foydalanish: /disconnect @kanal_username")
        return

    ref = context.args[0].lstrip("@").lower()
    channels = db.list_user_channels(user_id)
    match = None
    for c in channels:
        uname = (c["username"] or "").lstrip("@").lower()
        if uname == ref or str(c["channel_id"]) == context.args[0]:
            match = c
            break

    if not match:
        await update.message.reply_text("❌ Bu kanal sizning ro'yxatingizda topilmadi.")
        return

    removed = db.remove_channel(match["channel_id"], user_id)
    if removed:
        job_id = f"autopost_{match['channel_id']}"
        if sched.scheduler.get_job(job_id):
            sched.scheduler.remove_job(job_id)
        await update.message.reply_text(f"✅ \"{match['title']}\" kanali bot boshqaruvidan chiqarildi.")
    else:
        await update.message.reply_text("❌ Kanalni o'chirishda xatolik yuz berdi.")


# ---------- Kontent buyruqlari (faol kanalga bog'liq) ----------

@requires_channel
async def cmd_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict) -> int:
    custom_prompt = " ".join(context.args) if context.args else None
    msg = await update.message.reply_text("⏳ Post yaratilmoqda...")
    try:
        text = generate_post(channel, custom_prompt, manual=True)
    except Exception as exc:
        logger.exception("Post generatsiyasida xato")
        await msg.edit_text(f"❌ Xatolik: {exc}")
        return ConversationHandler.END

    context.user_data["pending"] = {
        "text": text,
        "channel_id": channel["channel_id"],
        "image_file_id": None,
    }
    await msg.edit_text(
        f"👁 <b>Ko'rinish — {channel['title']}:</b>\n\n{text}\n\n"
        "<i>Tasdiqlang, rasm qo'shing yoki qayta yozing:</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_post_keyboard(has_image=False),
    )
    return POST_CHOOSING


async def cb_post_add_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📸 Rasmni yuboring (photo sifatida), yoki /cancel bekor qilish uchun."
    )
    return POST_UPLOADING


async def cb_post_receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pending = context.user_data.get("pending")
    if not pending:
        await update.message.reply_text("❌ Faol post topilmadi. /post bilan qaytadan boshlang.")
        return ConversationHandler.END

    file_id = update.message.photo[-1].file_id
    pending["image_file_id"] = file_id
    channel = db.get_channel(pending["channel_id"])

    await update.message.reply_photo(
        photo=file_id,
        caption=f"👁 <b>{channel['title']} — ko'rinish:</b>\n\n{pending['text'][:900]}",
        parse_mode=ParseMode.HTML,
        reply_markup=_post_keyboard(has_image=True),
    )
    return POST_CHOOSING


async def cb_post_wrong_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📸 Faqat rasm (photo) yuboring, yoki /cancel.")
    return POST_UPLOADING


async def cb_post_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("⏳ Yuborilmoqda...")

    pending = context.user_data.get("pending")
    if not pending:
        await query.edit_message_text("❌ Post topilmadi. /post bilan qaytadan boshlang.")
        return ConversationHandler.END

    channel = db.get_channel(pending["channel_id"])
    if not channel:
        await query.edit_message_text("❌ Kanal topilmadi.")
        return ConversationHandler.END

    try:
        text = pending["text"]
        image_id = pending.get("image_file_id")

        if image_id:
            caption = text[:1024]
            await context.bot.send_photo(
                chat_id=channel["channel_id"],
                photo=image_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            if len(text) > 1024:
                await context.bot.send_message(
                    chat_id=channel["channel_id"],
                    text=text[1024:],
                    parse_mode=ParseMode.HTML,
                )
        else:
            await context.bot.send_message(
                chat_id=channel["channel_id"],
                text=text,
                parse_mode=ParseMode.HTML,
            )

        db.add_history_entry(channel["channel_id"], text, source="manual")
        success = f"✅ Post <b>{channel['title']}</b> kanaliga joylandi."
        if image_id:
            await query.edit_message_caption(success, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(success, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("Post yuborishda xato")
        err = f"❌ Xatolik: {exc}"
        try:
            await query.edit_message_text(err)
        except Exception:
            await query.edit_message_caption(err)

    context.user_data.pop("pending", None)
    return ConversationHandler.END


async def cb_post_regen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("⏳ Qayta yozilmoqda...")

    pending = context.user_data.get("pending")
    if not pending:
        await query.edit_message_text("❌ Post topilmadi.")
        return ConversationHandler.END

    channel = db.get_channel(pending["channel_id"])
    try:
        text = generate_post(channel, manual=True)
        pending["text"] = text
        pending["image_file_id"] = None
        await query.edit_message_text(
            f"👁 <b>Ko'rinish — {channel['title']}:</b>\n\n{text}\n\n"
            "<i>Tasdiqlang, rasm qo'shing yoki qayta yozing:</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_post_keyboard(has_image=False),
        )
    except Exception as exc:
        await query.edit_message_text(f"❌ Xatolik: {exc}")
        return ConversationHandler.END
    return POST_CHOOSING


async def cb_post_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending", None)
    try:
        await query.edit_message_text("❌ Post bekor qilindi.")
    except Exception:
        await query.edit_message_caption("❌ Post bekor qilindi.")
    return ConversationHandler.END


async def cb_post_cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("pending", None)
    await update.message.reply_text("❌ Post bekor qilindi.")
    return ConversationHandler.END


@requires_channel
async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    custom_prompt = " ".join(context.args) if context.args else None
    msg = await update.message.reply_text("⏳ Namuna tayyorlanmoqda...")
    try:
        text = generate_post(channel, custom_prompt, manual=True)
        await msg.edit_text(
            f"👁 <b>Namuna — {channel['title']} (kanalga joylanmadi):</b>\n\n{text}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        await msg.edit_text(f"❌ Xatolik: {exc}")


@requires_channel
async def cmd_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    msg = await update.message.reply_text("⏳ G'oyalar tayyorlanmoqda...")
    try:
        ideas = generate_post_idea_list(channel)
        await msg.edit_text(f"💡 <b>Kontent g'oyalari:</b>\n\n{ideas}", parse_mode=ParseMode.HTML)
    except Exception as exc:
        await msg.edit_text(f"❌ Xatolik: {exc}")


@requires_channel
async def cmd_autopost(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Foydalanish: /autopost on  yoki  /autopost off")
        return
    enabled = 1 if context.args[0].lower() == "on" else 0
    channel = db.update_channel_settings(channel["channel_id"], autopost_enabled=enabled)
    sched.reschedule_channel(context.application, channel["channel_id"])
    status = "✅ yoqildi" if enabled else "⛔ o'chirildi"
    extra = f"\nHar {channel['interval_hours']} soatda post yuboriladi." if enabled else ""
    await update.message.reply_text(f"Avtopost \"{channel['title']}\" uchun {status}.{extra}")


@requires_channel
async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Foydalanish: /interval 4   (soatlarda, masalan har 4 soatda)")
        return
    hours = max(1, int(context.args[0]))
    channel = db.update_channel_settings(channel["channel_id"], interval_hours=hours)
    sched.reschedule_channel(context.application, channel["channel_id"])
    await update.message.reply_text(f"⏱ \"{channel['title']}\" uchun interval {hours} soatga o'rnatildi.")


@requires_channel
async def cmd_settopic(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args:
        await update.message.reply_text("Foydalanish: /settopic Texnologiya va sun'iy intellekt yangiliklari")
        return
    topic = " ".join(context.args)
    db.update_channel_settings(channel["channel_id"], topic=topic)
    await update.message.reply_text(f"📌 \"{channel['title']}\" mavzusi yangilandi:\n{topic}")


@requires_channel
async def cmd_tone(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args:
        await update.message.reply_text("Foydalanish: /tone hazil-mutoyiba aralash, samimiy uslub")
        return
    tone = " ".join(context.args)
    db.update_channel_settings(channel["channel_id"], tone=tone)
    await update.message.reply_text(f"🎨 \"{channel['title']}\" uslubi yangilandi:\n{tone}")


@requires_channel
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    await update.message.reply_text(
        f"⚙️ <b>{channel['title']} — sozlamalar</b>\n"
        "Tugmaga bosib o'zgartiring:",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(channel),
    )


async def cb_open_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalni ulangandan keyin 'Sozlamalar' tugmasini bosganda."""
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split(":")[1])
    channel = db.get_channel(cid)
    if not channel:
        await query.edit_message_text("❌ Kanal topilmadi.")
        return
    await query.edit_message_text(
        f"⚙️ <b>{channel['title']} — sozlamalar</b>\n"
        "Tugmaga bosib o'zgartiring:",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(channel),
    )


async def cb_toggle_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """hashtags / emoji / autopost ni bir click bilan yoqadi/o'chiradi."""
    query = update.callback_query
    await query.answer()
    _, field, cid_str = query.data.split(":")
    cid = int(cid_str)

    channel = db.get_channel(cid)
    if not channel or channel["owner_user_id"] != query.from_user.id:
        await query.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    new_val = 0 if channel[field] else 1
    channel = db.update_channel_settings(cid, **{field: new_val})

    if field == "autopost":
        sched.reschedule_channel(context.application, cid)

    await query.edit_message_reply_markup(reply_markup=_settings_keyboard(channel))


async def cb_choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split(":")[2])
    buttons = [[IKB(lang, callback_data=f"sl:{lang}:{cid}")] for lang in _LANGUAGES]
    buttons.append([IKB("⬅️ Orqaga", callback_data=f"open_settings:{cid}")])
    await query.edit_message_text("🌐 Tilni tanlang:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, lang, cid_str = query.data.split(":")
    cid = int(cid_str)
    channel = db.update_channel_settings(cid, language=lang)
    await query.edit_message_text(
        f"⚙️ <b>{channel['title']} — sozlamalar</b>\n"
        "Tugmaga bosib o'zgartiring:",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(channel),
    )


async def cb_choose_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split(":")[2])
    buttons = [[IKB(pl, callback_data=f"spl:{i}:{cid}")] for i, pl in enumerate(_POST_LENGTHS)]
    buttons.append([IKB("⬅️ Orqaga", callback_data=f"open_settings:{cid}")])
    await query.edit_message_text("📏 Post uzunligini tanlang:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_set_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, idx_str, cid_str = query.data.split(":")
    cid = int(cid_str)
    post_length = _POST_LENGTHS[int(idx_str)]
    channel = db.update_channel_settings(cid, post_length=post_length)
    await query.edit_message_text(
        f"⚙️ <b>{channel['title']} — sozlamalar</b>\n"
        "Tugmaga bosib o'zgartiring:",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(channel),
    )


async def cb_edit_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """topic / tone / interval ni tahrirlash uchun matn so'raydi."""
    query = update.callback_query
    await query.answer()
    _, field, cid_str = query.data.split(":")
    cid = int(cid_str)

    channel = db.get_channel(cid)
    if not channel or channel["owner_user_id"] != query.from_user.id:
        await query.answer("❌ Ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END

    context.user_data["edit_field"] = field
    context.user_data["edit_cid"] = cid

    prompts = {
        "topic": "📌 Yangi mavzuni yozing:\n(masalan: Python dasturlash va texnologiya yangiliklari)",
        "tone": "🎨 Yangi uslubni yozing:\n(masalan: qiziqarli, samimiy, yosh auditoriya uchun)",
        "interval": "⏱ Necha soatda bir post yuborilsin? (1–168)\n(masalan: 4)",
    }
    await query.edit_message_text(
        prompts[field] + "\n\n/cancel — bekor qilish",
    )
    return AWAITING_VALUE


async def cb_edit_field_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get("edit_field")
    cid = context.user_data.get("edit_cid")
    text = update.message.text.strip()

    if field == "interval":
        if not text.isdigit() or not (1 <= int(text) <= 168):
            await update.message.reply_text("❌ 1 dan 168 gacha raqam kiriting.")
            return AWAITING_VALUE
        channel = db.update_channel_settings(cid, interval_hours=int(text))
        sched.reschedule_channel(context.application, cid)
    else:
        channel = db.update_channel_settings(cid, **{field: text})

    await update.message.reply_text(
        f"⚙️ <b>{channel['title']} — sozlamalar</b>\n"
        "Tugmaga bosib o'zgartiring:",
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_keyboard(channel),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cb_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi. /settings orqali qaytishingiz mumkin.")
    return ConversationHandler.END


@requires_channel
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    entries = db.get_history(channel["channel_id"], 5)
    if not entries:
        await update.message.reply_text("Hozircha post tarixi bo'sh.")
        return
    lines = [f"🗂 <b>\"{channel['title']}\" — oxirgi postlar:</b>\n"]
    for e in reversed(entries):
        snippet = e["text"][:120].replace("\n", " ")
        lines.append(f"• [{e['timestamp']}] ({e['source']}) {snippet}...")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@requires_channel
async def cmd_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Foydalanish: /hashtags on  yoki  /hashtags off")
        return
    enabled = 1 if context.args[0].lower() == "on" else 0
    db.update_channel_settings(channel["channel_id"], hashtags=enabled)
    status = "yoqildi" if enabled else "o'chirildi"
    await update.message.reply_text(f"#️⃣ Hashtag {status}.")


@requires_channel
async def cmd_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: dict):
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Foydalanish: /emoji on  yoki  /emoji off")
        return
    enabled = 1 if context.args[0].lower() == "on" else 0
    db.update_channel_settings(channel["channel_id"], emoji=enabled)
    status = "yoqildi" if enabled else "o'chirildi"
    await update.message.reply_text(f"😀 Emoji {status}.")


# ---------- Bot egasi uchun global buyruq (ixtiyoriy) ----------

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("⛔ Bu buyruq faqat bot egasi uchun.")
        return
    s = db.stats()
    await update.message.reply_text(
        "📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: {s['users']}\n"
        f"📡 Ulangan kanallar: {s['channels']}\n"
        f"🔁 Avtopost yoqilgan: {s['autopost_on']}\n"
        f"📝 Jami postlar: {s['posts']}",
        parse_mode=ParseMode.HTML,
    )

