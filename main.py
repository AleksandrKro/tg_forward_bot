import asyncio
import time
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, Update
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

#Маршруты
ROUTES = {
    -1004249234744: 11,
    -1004385081341: 2,
    -1004485197368: 12,
}

TARGET_CHAT_ID = -1002290371611

TECH_SUPPORT_USER_ID = 6834098561
PAYMENTS_URL = 'https://t.me/otzvipIati'
REVIEWS_URL = 'https://t.me/otzotzivi'
HOW_TO_URL = 'https://t.me/otzivi_chok/113/114'

CLOSE_DELAY = 3 #seconds
SPAM_COOLDOWN = 300 #seconds

last_posts: dict[tuple[int, int], float] = {}
posts: dict[int, dict[str, float | int]] = {}

TEMPLATES = {
    -1004249234744: [
        ("📢 Платформа:", "platform", "📢 Платформа:"),
        ("💵 Оплата:", "payment", "💵 Оплата:"),
        ("📝 Описание:", "description", "📝 Описание:"),
    ],
    -1004385081341: [
        ("🏷 Платформа:", "platform", "🏷 Платформа:"),
        ("💵 Оплата:", "payment", "💵 Оплата:"),
        ("📌 Количество:", "quantity", "📌 Количество:"),
        ("📝 Описание:", "description", "📝 Описание:"),
        ("💰 Стоимость:", "price", "💰 Стоимость:"),
        ("🤝 Сделка:", "deal", "🤝 Сделка:"),
    ],
    -1004485197368: [
        ("🏷 Платформа:", "platform", "🏷 Платформа:"),
        ("💵 Оплата:", "payment", "💵 Оплата:"),
        ("📌 Количество:", "quantity", "📌 Количество:"),
        ("📝 Описание:", "description", "📝 Описание:"),
        ("💰 Стоимость:", "price", "💰 Стоимость:"),
        ("🤝 Сделка:", "deal", "🤝 Сделка:"),
    ],
}

def parse_post(text: str, rules: list[tuple[str, str, str]]) -> dict[str, str] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) != len(rules):
        return None

    result: dict[str, str] = {}

    for line, (prefix, key, _) in zip(lines, rules):
        if not line.startswith(prefix):
            return None

        value = line[len(prefix):].strip()
        result[key] = value

    return result

def build_post_text(post: dict[str, str], rules: list[tuple[str, str, str]]) -> str:
    parts = []
    for _, key, output_label in rules:
        parts.append(f"{output_label} {post.get(key, '')}")
    return "\n".join(parts)

def open_keyboard(author_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard = [
            [
                InlineKeyboardButton(
                    text="Откликнуться",
                    url=f"tg://user?id={author_id}",
                ),
            ],
            [
                InlineKeyboardButton(text = "Выплаты", url = PAYMENTS_URL),
                InlineKeyboardButton(text = "Отзывы", url = REVIEWS_URL),
            ],
        ]
    )

def closed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard = [
            [
                InlineKeyboardButton(
                    text = "Как брать задание?",
                    url = HOW_TO_URL
                )
            ],
            [
                InlineKeyboardButton(text="Выплаты", url=PAYMENTS_URL),
                InlineKeyboardButton(text="Отзывы", url=REVIEWS_URL),
            ],
        ]
    )

async def close_post(message_id: int):
    try:
        await bot.edit_message_text(
            chat_id=TARGET_CHAT_ID,
            message_id=message_id,
            text="🔒 Данное задание закончилось\nВключи уведомления, чтобы не пропустить следующее задание!",
            reply_markup=closed_keyboard(),
        )
    except TelegramBadRequest:
        pass

async def worker():
    while True:
        now = time.time()

        expired = [
            mid for mid, data in posts.items()
            if now >= data["expire_time"]
        ]

        for mid in expired:
            await close_post(mid)
            posts.pop(mid, None)

        await asyncio.sleep(2)

@router.message(F.text)
async def handle_message(message: Message):
    if message.from_user is None:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    if chat_id not in ROUTES:
        return

    rules = TEMPLATES.get(chat_id)
    if rules is None:
        return

    cooldown_key = (chat_id, user_id)

    now = time.time()
    last_time = last_posts.get(cooldown_key, 0.0)

    if now - last_time < SPAM_COOLDOWN:
        remaining = int(SPAM_COOLDOWN - (now - last_time))
        await message.reply(f"⏳ Подожди ещё {remaining} сек.")
        return

    post = parse_post(text, rules)

    if post is None:
        await message.reply("❌ Неверный шаблон")
        return

    thread_id = ROUTES[chat_id]

    post_text = "\n".join(
        f"{label} {post.get(key, '')}"
        for _, key, label in rules
    )

    sent = await bot.send_message(
        chat_id=TARGET_CHAT_ID,
        message_thread_id=thread_id,
        text=post_text,
        reply_markup=open_keyboard(user_id),
    )

    await message.reply("✅ Опубликовано")

    last_posts[cooldown_key] = now

    posts[sent.message_id] = {
        "expire_time": now + CLOSE_DELAY
    }

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = "https://<твой-сервис-на-render>.onrender.com/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

async def webhook_handler(request: web.Request):
    try:
        if WEBHOOK_SECRET:
            if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
                return web.Response(status=403)

        data = await request.json()
        update = Update.model_validate(data)

        await dp.feed_update(bot, update)

        return web.Response(text="ok")

    except Exception as e:
        logging.exception(e)
        return web.Response(text="error", status=500)



async def health(request):
    return web.Response(text="OK")

async def create_app():
    app = web.Application()

    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/", health)

    return app

async def on_startup():
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True
    )

async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()

async def main():
    await on_startup()

    app = await create_app()

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    asyncio.create_task(worker(), name="post-worker")

    try:
        await asyncio.Event().wait()
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())