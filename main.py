import os
import re
import time
import asyncio
import random
import secrets
from dotenv import load_dotenv
from dataclasses import dataclass, field
from collections import deque
from typing import Dict, Optional, Deque

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ButtonStyle

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN env variable qo'ying!")

WORDS_FILE = os.getenv("WORDS_FILE", "words.txt")
HOST_LOCK_SECONDS = 5 * 60

def load_words(path: str) -> list[str]:
    if not os.path.exists(path):
        raise RuntimeError(f"{path} topilmadi. words.txt faylini yarating.")
    with open(path, "r", encoding="utf-8") as f:
        words = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    if len(words) < 20:
        print("Word list juda kichik (kamida 200+ so'z bo'lsa qiziqroq bo'ladi).")
    return words

WORDS = load_words(WORDS_FILE)
PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
SPACE_RE = re.compile(r"\s+", flags=re.UNICODE)

def normalize(text: str) -> str:
    """Taxminlarni solishtirish uchun oddiy normalizatsiya"""
    t = text.strip().lower()
    t = PUNCT_RE.sub(" ", t)
    t = PUNCT_RE.sub(" ", t).strip()
    return t



@dataclass
class ChatState:
    active: bool = False
    round_id: Optional[str] = None
    host_id: Optional[int] = None
    host_name: str = ""
    word: Optional[str] = None
    panel_msg_id: Optional[int] = None
    lock_until: float = 0.0
    recent: Deque[str] = field(default_factory=lambda: deque(maxlen=30))
    claim_token: Optional[str] = None
    claimed_by: Optional[int] = None

CHAT: Dict[int, ChatState] = {}
CHAT_LOCKS: Dict[int, asyncio.Lock] = {}

def get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in CHAT_LOCKS:
        CHAT_LOCKS[chat_id] = asyncio.Lock()
    return CHAT_LOCKS[chat_id]

def get_state(chat_id: int) -> ChatState:
    if chat_id not in CHAT:
        CHAT[chat_id] = ChatState()
    return CHAT[chat_id]

def pick_word(state: ChatState) -> str:
    candidates = [w for w in WORDS if w not in state.recent]
    if not candidates:
        state.recent.clear()
        candidates = WORDS[:]
    w = random.choice(candidates)
    state.recent.append(w)
    return w

def panel_kb(round_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="👀 So'zni ko'rish",
        callback_data=f"sw:{round_id}",
        style=ButtonStyle.PRIMARY
    )
    kb.button(
        text="⏭️ Yangi so'z",
        callback_data=f"nw:{round_id}",
        style=ButtonStyle.SUCCESS
    )
    kb.adjust(2)  # 1 qatorda 2ta tugma
    return kb.as_markup()


def claim_kb(token: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✋ Boshlovchi bo'lishni xohlayman!",
        callback_data=f"cl:{token}",
        style=ButtonStyle.PRIMARY
    )
    kb.adjust(1)
    return kb.as_markup()


bot = Bot(TOKEN)
dp = Dispatcher()

async def start_round(chat_id: int, host_user, reply_to: Optional[Message] = None):
    state = get_state(chat_id)
    state.active = True
    state.round_id = secrets.token_hex(4)
    state.host_id = host_user.id
    state.host_name = host_user.full_name

    state.word = pick_word(state)
    state.lock_until = time.time() + HOST_LOCK_SECONDS

    state.claim_token = None
    state.claimed_by = None

    text = (
        f"🔥 <b>{state.host_name}</b> so'zni tushuntiradi.\n\n"
        f"Boshlovchi uchun tugmalar 👇"
    )
    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=panel_kb(state.round_id),
        parse_mode="HTML",
    )
    state.panel_msg_id = msg.message_id

    if reply_to:
        await reply_to.answer("✅ O'yin boshlandi!")



@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == "private":
        me = await bot.get_me()
        url = f"https://t.me/{me.username}?startgroup=true"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Guruhga qo'shish", url=url)]
        ])
        await message.answer(
            "Salom! Men so'z topish o'yini botiman.\n\n"
            "Guruhga qo'shing va guruhda /start yozib o'yinni boshlang.",
            reply_markup=kb
        )
        return
    
    chat_id = message.chat.id
    async with get_lock(chat_id):
        state = get_state(chat_id)

        now = time.time()
        if state.active and now < state.lock_until and message.from_user.id != state.host_id:
            await message.reply(
                f"⛔ Hozir o'yin ketyapti.\n"
                f"Boshlovchi: <b>{state.host_name}</b>\n"
                f"Qoidaga ko'ra, 5 daqiqa ichida faqat boshlovchi /start qila oladi.",
                parse_mode="HTML"
            )
            return
        
        await start_round(chat_id, message.from_user, reply_to=message)


@dp.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(
        "📜 <b>Qoidalar</b>\n"
        "1) Guruhda /start - o'yinni boshlaydi.\n"
        "2) Boshlovchi 'So'zni ko'rish' orqali so'zni faqat o'zi ko'radi.\n"
        "3) 'Yangi so'z' bilan so'zni almashtirishi mumkin.\n"
        "4) Kim so'zni to'g'ri yozsa g'olib bo'ladi.\n"
        "5) G'olib xabari ostidagi tugma orqali keyngi boshlovchi tanlanadi.\n"
        "6) Boshlovchini 5 daqiqa ichida /start bilan almashtirib bo'lmaydi.",
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 Buyruqlar:\n"
        "/start - o'yinni boshlash\n"
        "/rules - qoidalar\n"
        "/help - yordam"
    )

@dp.callback_query(F.data.startswith("sw:"))
async def cb_show_word(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    async with get_lock(chat_id):
        state = get_state(chat_id)
        rid = cb.data.split(":", 1)[1]

        if not state.active or state.round_id != rid:
            await cb.answer("⌛ Bu tugma eskirgan.", show_alert=True)
            return
        
        if cb.from_user.id != state.host_id:
            await cb.answer("❌ Bu so'z siz uchun emas.", show_alert=True)
            return
        
        await cb.answer(f"✅ So'z: {state.word}", show_alert=True)


@dp.callback_query(F.data.startswith("nw:"))
async def cb_new_word(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    async with get_lock(chat_id):
        state = get_state(chat_id)
        rid = cb.data.split(":", 1)[1]

        if not state.active or state.round_id != rid:
            await cb.answer("⌛ Bu tugma eskirgan.", show_alert=True)
            return
        
        if cb.from_user.id != state.host_id:
            await cb.answer("❌ Bu tugma siz uchun emas.", show_alert=True)
            return
        
        state.word = pick_word(state)
        await cb.answer(f"🔄️ Yangi so'z: {state.word}", show_alert=True)


@dp.callback_query(F.data.startswith("cl:"))
async def cb_claim_host(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    async with get_lock(chat_id):
        state = get_state(chat_id)
        token = cb.data.split(":", 1)[1]

        if state.claim_token != token:
            await cb.answer("⌛ Bu tugma eskirgan.", show_alert=True)
            return
        
        if state.claimed_by is None:
            state.claimed_by = cb.from_user.id
            await cb.answer("✅ Siz boshlovchi bo'ldingiz!", show_alert=True)

            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

            await start_round(chat_id, cb.from_user)
            return
        
        if state.claimed_by != cb.from_user.id:
            await cb.answer("⛔ Boshlovchi allaqachon tanlangan.", show_alert=True)
            return
        
        await cb.answer("Siz allaqachon boshlovchisiz 🙂", show_alert=True)




@dp.message(F.text)
async def on_text(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        return
    
    chat_id = message.chat.id
    async with get_lock(chat_id):
        state = get_state(chat_id)
        if not state.active or not state.word:
            return
        
        if message.from_user and state.host_id == message.from_user.id:
            return
        
        guess = normalize(message.text)
        answer = normalize(state.word)

        if guess != answer:
            return
        
        winner_name = message.from_user.full_name
        word = state.word

        state.active = False
        state.round_id = None
        state.word = None
        state.panel_msg_id = None

        state.claim_token = secrets.token_hex(4)
        state.claimed_by = None

        await message.answer(
            f"🎉 <b>{winner_name}</b> so'zni topdi!\n"
            f"✅ So'z: <code>{word}</code>\n\n"
            f"Keyingi boshlovchini tanlang:",
            parse_mode="HTML",
            reply_markup=claim_kb(state.claim_token)
        )





async def main():
    await dp.start_polling(bot, polling_timeout=60)

if __name__ == "__main__":
    asyncio.run(main())