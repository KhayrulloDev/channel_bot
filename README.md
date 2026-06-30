# 🤖 Kanal AI-Admin Bot (Gemini API) — ko'p foydalanuvchili versiya

Bu bot orqali **istalgan odam** o'z Telegram kanalini ulab, uni Gemini AI yordamida avtomatik yuritishi mumkin. Gemini API kaliti — bitta, bot egasi tomonidan taqdim etiladi va barcha foydalanuvchilar uchun umumiy ishlatiladi (foydalanuvchidan API kalit so'ralmaydi).

## ✨ Imkoniyatlar

- 👥 **Ko'p foydalanuvchili**: istalgan kishi botga yozib, o'z kanalini `/connect` orqali ulashi mumkin
- 📡 Bir foydalanuvchi **bir nechta kanal**ni ulashi va ular orasida `/select` bilan almashishi mumkin
- 🔒 Xavfsizlik: faqat kanalning haqiqiy admini uni ulay oladi, faqat ulagan kishi (egasi) uni boshqaradi
- 🧠 Gemini AI orqali sifatli, mavzuga mos postlar yaratish
- ⏰ Avtopilot rejimi — har bir kanal o'z intervaliga ega bo'lib, mustaqil avtomatik post joylaydi
- ✍️ `/post mavzu` — istalgan mavzuda darhol post yozdirish
- 👁 `/preview` — postni kanalga joylashdan oldin ko'rib chiqish
- 💡 `/ideas` — kontent g'oyalari ro'yxati
- 🎯 Har bir kanal uchun alohida mavzu, uslub, hashtag/emoji sozlamalari
- 🗂 Post tarixi — Gemini har bir kanal bo'yicha alohida takroriy mavzu yozmasligi uchun eslab qoladi

## 📦 O'rnatish (bot egasi uchun, bir martalik)

### 1. Telegram bot yaratish

1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing
2. `/newbot` buyrug'ini yuboring va ko'rsatmalarga amal qiling
3. Sizga beriladigan **token**ni saqlab qo'ying

### 2. Gemini API kalitini olish

1. [Google AI Studio](https://aistudio.google.com/apikey) ga kiring
2. Yangi API key yarating va saqlang (bepul tarif mavjud)

### 3. `.env` faylini sozlash

```bash
cp .env.example .env
```

`.env` faylini to'ldiring:

```env
BOT_TOKEN=BotFather'dan olingan token
GEMINI_API_KEY=Google AI Studio'dan olingan kalit
SUPER_ADMIN_IDS=sizning_telegram_id    # ixtiyoriy, faqat /stats uchun
```

> `CHANNEL_ID` va `ADMIN_IDS` endi kerak emas — bu versiyada kanal va egalik ma'lumotlari avtomatik ravishda baza ichida saqlanadi.

### 4. Botni ishga tushirish

**Docker bilan (tavsiya etiladi):**
```bash
docker compose up -d --build
```

**Yoki qo'lda:**
```bash
pip install -r requirements.txt
python bot.py
```

Bot shu nuqtada tayyor — endi istalgan foydalanuvchi botga yozib, o'z kanalini ulashi mumkin.

## 👤 Oddiy foydalanuvchi uchun: kanalni qanday ulash kerak

Buni botdan foydalanmoqchi bo'lgan **har bir kishi** o'zi bajaradi (sizning aralashuvingizsiz):

### 1-qadam — Botni shaxsiy chatda ishga tushirish
Telegramda botni toping va `/start` bosing.

### 2-qadam — Botni o'z kanaliga admin qilib qo'shish
1. Kanalingizga o'ting → **Administrators** → **Add Admin**
2. Botni qidirib toping va qo'shing
3. **"Post Messages"** (xabar joylash) huquqini albatta yoqing

### 3-qadam — Kanalni botga ulash
Botga shaxsiy chatda yozing:
```
/connect @kanal_username
```
(agar kanal public bo'lmasa, kanal ID raqamini ishlating, masalan `/connect -1001234567890`)

Bot quyidagilarni avtomatik tekshiradi:
- bot kanalga admin qilib qo'shilganmi va post joylash huquqi bormi
- siz (buyruqni yuborgan kishi) ham shu kanalning admini ekanligingiz

Hammasi to'g'ri bo'lsa — kanal ulanadi va darhol **faol kanal** sifatida belgilanadi.

### 4-qadam — Kanalni sozlash va ishlatish
```
/settopic Sport yangiliklari va tahlillar
/tone qiziqarli, lekin professional uslub
/post
```

Yoki avtopilotni yoqish:
```
/autopost on
/interval 4
```

## 🕹 Buyruqlar ro'yxati

### Kanal ulash / boshqarish
| Buyruq | Tavsif |
|---|---|
| `/connect @kanal` | Kanalni botga ulaydi (admin tekshiruvi bilan) |
| `/mychannels` | Ulangan barcha kanallaringiz ro'yxati |
| `/select @kanal` | Qaysi kanal bilan ishlashni tanlash (faol kanalni almashtirish) |
| `/disconnect @kanal` | Kanalni bot boshqaruvidan chiqarish |

### Kontent (faol kanal uchun)
| Buyruq | Tavsif |
|---|---|
| `/post` | Darhol AI bilan post yaratib kanalga joylaydi |
| `/post <mavzu>` | Berilgan mavzu asosida post yozadi va joylaydi |
| `/preview <mavzu>` | Postni kanalga joylamasdan oldin ko'rsatadi |
| `/ideas` | Kontent g'oyalari ro'yxatini taklif qiladi |

### Avtopilot
| Buyruq | Tavsif |
|---|---|
| `/autopost on/off` | Avtomatik postlashni yoqadi yoki o'chiradi |
| `/interval <soat>` | Har necha soatda avtomatik post yuborilishini belgilaydi |

### Sozlamalar
| Buyruq | Tavsif |
|---|---|
| `/settopic <matn>` | Kanal mavzusini o'zgartiradi |
| `/tone <matn>` | Yozish uslubini o'zgartiradi |
| `/hashtags on/off` | Postlarga hashtag qo'shish/qo'shmaslik |
| `/emoji on/off` | Postlarda emoji ishlatish/ishlatmaslik |
| `/settings` | Faol kanalning joriy sozlamalarini ko'rsatadi |
| `/history` | Faol kanalning oxirgi postlar tarixi |
| `/help` | Yordam matni |

### Bot egasi uchun
| Buyruq | Tavsif |
|---|---|
| `/stats` | Bot bo'yicha umumiy statistika (faqat `SUPER_ADMIN_IDS`dagilar uchun) |

## 🔁 Avtopilot qanday ishlaydi

Har bir kanal o'zining mustaqil rejasiga ega. `/autopost on` + `/interval 4` desangiz, o'sha **aynan shu kanal** uchun har 4 soatda:
1. Gemini'ga o'sha kanalning mavzusi, uslubi va oxirgi postlar tarixi yuboriladi (takror bo'lmasligi uchun)
2. Yangi, original post matni olinadi
3. Post to'g'ridan-to'g'ri o'sha kanalga joylanadi
4. Tarixga yozib qo'yiladi

Boshqa foydalanuvchining boshqa kanali bunga umuman ta'sir qilmaydi — har biri alohida ishlaydi. Xatolik yuz bersa (masalan API limiti), bot shu kanal egasiga shaxsiy xabar yuboradi.

## 🐳 Docker bilan ishga tushirish

```bash
cp .env.example .env
# .env faylini to'ldiring
docker compose up -d --build
```

`data/` papkasi konteynerdan tashqariga **mount** qilingan — bu degani, barcha foydalanuvchilar, kanallar, sozlamalar va post tarixi (`data/bot.sqlite3` faylida) konteyner o'chirilsa yoki qayta build qilinsa ham yo'qolmaydi.

Foydali buyruqlar:
```bash
docker compose logs -f      # loglarni jonli kuzatish
docker compose down         # to'xtatish
docker compose up -d --build   # qayta build qilib ishga tushirish
```

## 🖥 Doimiy ishlashi uchun (server/VPS, Docker'siz)

```bash
# systemd service namunasi: /etc/systemd/system/kanalbot.service
[Unit]
Description=Kanal AI Admin Bot
After=network.target

[Service]
WorkingDirectory=/yo'l/loyihaga
ExecStart=/usr/bin/python3 bot.py
Restart=always
User=sizning_user

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable kanalbot
sudo systemctl start kanalbot
```

## 📁 Loyiha tuzilishi

```
channel_bot/
├── bot.py              # Asosiy ishga tushirish fayli
├── config.py            # .env sozlamalarini o'qish
├── db.py                  # SQLite: foydalanuvchilar, kanallar, tarix (ko'p foydalanuvchili)
├── gemini_client.py        # Gemini API bilan post generatsiya qilish
├── scheduler.py             # Har bir kanal uchun mustaqil avtopost rejasi
├── handlers.py               # Telegram buyruqlari
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── requirements.txt
├── .env.example
└── data/                  # Avtomatik yaratiladi: bot.sqlite3
```

## ⚠️ Eslatmalar

- Gemini bepul tarifida so'rovlar soni cheklangan — barcha foydalanuvchilarning kanallari **bitta umumiy kalit**dan foydalanganligi uchun, juda ko'p kanal ulansa limitlarga e'tibor bering.
- `/connect` faqat kanalning haqiqiy adminlariga ruxsat beradi — begona kishi sizning kanalingizni ulay olmaydi.
- Bitta kanalni faqat bitta foydalanuvchi (birinchi ulagan kishi) boshqaradi. Agar boshqa admin ham boshqarishi kerak bo'lsa, hozircha joriy egadan `/disconnect` qilishini so'rang.

