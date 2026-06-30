"""
Bot konfiguratsiyasi. .env faylidan barcha sozlamalarni o'qiydi.

Bu versiya ko'p foydalanuvchili (multi-tenant): istalgan odam botga yozib,
o'z kanalini ulashi va mustaqil boshqarishi mumkin. Gemini API kaliti esa
bitta — bot egasi tomonidan taqdim etiladi va barcha foydalanuvchilar
uchun umumiy ishlatiladi.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Ixtiyoriy: bot egasi/super-adminlar (masalan /broadcast, /stats kabi
# global buyruqlar uchun). Oddiy foydalanuvchilar uchun bu shart emas —
# ular o'z kanallarini /connect orqali ulab, mustaqil boshqaradi.
_super_raw = os.getenv("SUPER_ADMIN_IDS", "")
SUPER_ADMIN_IDS = set()
for part in _super_raw.split(","):
    part = part.strip()
    if part.isdigit():
        SUPER_ADMIN_IDS.add(int(part))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "bot.sqlite3")

DEFAULT_CHANNEL_SETTINGS = {
    "topic": "umumiy qiziqarli va foydali ma'lumotlar",
    "tone": "qiziqarli, do'stona va o'qishga oson",
    "language": "o'zbek",
    "autopost_enabled": 0,
    "interval_hours": 4,
    "hashtags": 1,
    "emoji": 1,
    "post_length": "o'rta (3-6 jumla)",
}


def validate_config():
    """Asosiy sozlamalar to'g'ri kiritilganini tekshiradi."""
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN .env faylida ko'rsatilmagan")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY .env faylida ko'rsatilmagan")
    return errors

