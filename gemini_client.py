"""
Gemini API orqali kanal posti matnini generatsiya qilish.
Bu versiya har bir kanal uchun alohida sozlamalar (mavzu, uslub, til) bilan ishlaydi.
"""
import logging
import re

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL
import db

logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)


def _build_system_instruction(channel: dict) -> str:
    base = (
        "Sen tajribali Telegram kanal kontent-menejerisan va o'quvchini birinchi qatordanoq "
        "ushlab qoladigan, o'qilishi yengil postlar yozasan.\n\n"
        f"Kanal mavzusi: {channel['topic']}.\n"
        f"Yozish uslubi: {channel['tone']}.\n"
        f"Til: {channel['language']}.\n"
        f"Post uzunligi: {channel['post_length']}.\n\n"
        "=== FORMATLASH QOIDALARI (JUDA MUHIM) ===\n"
        "Telegram'da uzun, qatorlarga bo'linmagan matn o'qilmaydi va o'quvchini zeriktiradi. "
        "Shuning uchun quyidagi tuzilishga QAT'IY rioya qil:\n\n"
        "1. Birinchi qator — KUCHLI sarlavha/ilgak (hook): diqqatni darhol tortadigan savol, "
        "ajablantiruvchi fakt yoki qisqa bayonot. <b>qalin</b> qilib yoz va undan keyin bo'sh qator qo'y.\n"
        "2. Asosiy matn 2-4 ta QISQA abzasga bo'linsin (har biri 1-3 jumla). Abzaslar orasida "
        "ALBATTA bitta bo'sh qator (\\n\\n) bo'lsin — hech qachon hammasini bitta katta blok "
        "qilib yozma.\n"
        "3. Agar matnda bir nechta fikr/nuqta sanab o'tilsa, ularni emoji-belgi bilan har birini "
        "alohida qatorga yoz (masalan: ⚡, ✅, 🔹, ➜) — uzun ro'yxatni bitta jumlaga sig'dirib "
        "yozma.\n"
        "4. Eng muhim raqam, atama yoki xulosani <b>qalin</b> tegi bilan ajratib ko'rsat — "
        "o'quvchi tez ko'z yugurtirganda ham asosiy fikrni ilg'asin.\n"
        "5. Oxirgi qator — qisqa xulosa, fikr-mulohaza uyg'otuvchi savol yoki harakatga undash "
        "(masalan: o'z fikrini izohda yozishni taklif qilish). Bu qatorni oldingi matndan "
        "bo'sh qator bilan ajrat.\n"
        "6. Faqat <b>, <i>, <u>, <code> HTML teglaridan foydalan, boshqa teglarni "
        "(<p>, <div>, <ul>, <li> va h.k.) ishlatma. Markdown belgilarini (** __ # - va h.k.) "
        "umuman ishlatma — faqat HTML teglar.\n"
        "7. Yulduzcha (*) yoki tire (-) bilan ro'yxat yasama — buning o'rniga emoji-belgidan "
        "foydalan (qoida 3 ga qara).\n\n"
    )
    if channel["emoji"]:
        base += (
            "Emoji ishlatishga ruxsat berilgan — faqat bazi kerekli joylarda, matnni yengillashtirish va vizual ajratish uchun. "
            "mos emoji ishlat, lekin haddan tashqari ko'paytirib yubormа (har qatorda 1 tadan yetarli)."
        )
    else:
        base += "Postda emoji ishlatma, lekin baribir abzaslarga bo'lish va <b>qalin</b> ajratish qoidalariga rioya qil."
    return base


_MANUAL_QUALITY = (
    "\n⚠️ BU QOIDA MUTLAQ: Markdown belgisi (*,**,#,-,_) ishlatma — FAQAT HTML teglar. "
    "Har abzas orasida bo'sh qator bo'lsin. Bitta blok matn — YO'Q. "
    "Sarlavha ALBATTA <b>qalin</b>. Ro'yxat elementlari emoji bilan alohida qatorda. "
    "Professional kontent-menejer darajasida yoz."
)


def _clean_text(text: str) -> str:
    # markdown → HTML
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.*?)__", r"<u>\1</u>", text, flags=re.DOTALL)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # <br> variants → newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # strip unsupported tags (p, div, ul, li, span, h1-h6, …) but keep their inner text
    text = re.sub(r"<(?!/?(?:b|i|u|s|code|pre|a|tg-spoiler)\b)[^>]+>", "", text, flags=re.IGNORECASE)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_post(channel: dict, custom_prompt: str | None = None, manual: bool = False) -> str:
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=_build_system_instruction(channel),
    )

    recent = db.get_recent_topics_text(channel["channel_id"], 8)
    hashtag_rule = (
        "Post oxirida (xulosa qatoridan keyin, alohida qatorda) mavzuga mos 2-4 ta hashtag qo'sh "
        "(#misol ko'rinishida)."
        if channel["hashtags"] else
        "Hashtag qo'shma."
    )
    quality_note = _MANUAL_QUALITY if manual else (
        "\nPostni abzaslarga bo'lib, har bir abzas orasida bo'sh qator qoldirib yoz."
    )

    if custom_prompt:
        prompt = (
            f"Quyidagi mavzu asosida Telegram kanali uchun bitta tayyor post yoz: "
            f"\"{custom_prompt}\".\n{hashtag_rule}{quality_note}\n"
            "Faqat tayyor post matnini qaytar, hech qanday qo'shimcha izoh yozma."
        )
    else:
        prompt = (
            "Kanal mavzusiga mos, o'quvchilar uchun qiziqarli va foydali bitta yangi post yoz. "
            f"Oxirgi yozilgan postlar (TAKRORLANMASLIK uchun, bunlarni qaytarma):\n{recent}\n\n"
            f"{hashtag_rule}{quality_note}\n"
            "Faqat tayyor post matnini qaytar, hech qanday qo'shimcha izoh yozma."
        )

    try:
        response = model.generate_content(prompt)
        text = response.text or ""
    except Exception as exc:
        logger.exception("Gemini API xatosi")
        raise RuntimeError(f"Gemini API xatosi: {exc}") from exc

    text = _clean_text(text)
    if not text:
        raise RuntimeError("Gemini bo'sh javob qaytardi, qaytadan urinib ko'ring.")
    return text


def generate_post_idea_list(channel: dict, count: int = 5) -> str:
    """Kanal egasi uchun mavzular ro'yxatini taklif qiladi (post yozmasdan, faqat g'oyalar)."""
    model = genai.GenerativeModel(model_name=GEMINI_MODEL)
    prompt = (
        f"Telegram kanali mavzusi: {channel['topic']}. Til: {channel['language']}. "
        f"Shu mavzuga mos {count} ta qisqa va qiziqarli post g'oyasini ro'yxat qilib yoz, "
        "har birini bitta qatorda, raqamlab."
    )
    try:
        response = model.generate_content(prompt)
        return _clean_text(response.text or "")
    except Exception as exc:
        logger.exception("Gemini API xatosi")
        raise RuntimeError(f"Gemini API xatosi: {exc}") from exc