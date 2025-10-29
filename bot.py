#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import random
import re
import logging
import json
import httpx
from typing import Dict, Any, List
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, JobQueue
)
from telegram.constants import ChatAction

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === CONFIG ===
BOT_TOKEN = "8117675754:AAE6AvPtqJrcSobYXGNbrMbX5fUyOQfRWBk"
IMAGES_DIR = "images"
CHANNEL_LINK = "https://t.me/borustar"

# === STATE ===
LAST_IMAGE: Dict[int, Dict[str, Any]] = {}
LAST_STICKER_SENT: Dict[int, str] = {}
ADD_MODE: Dict[int, bool] = {}
USER_SCORES: Dict[str, int] = {}
CURRENT_GAME_IMAGE: Dict[int, Dict[str, str]] = {}

# === STICKER CATEGORY MAP ===
STICKER_CATEGORIES = {
    "zero_two": "Zero Two 🌸",
    "hiro": "Hiro 👑",
    "general": "Umumiy sticker"
}

# === FILE UTILS ===
def load_stickers() -> List[str]:
    try:
        with open("saved_stickers.json", "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_stickers(stickers: List[str]) -> None:
    with open("saved_stickers.json", "w") as f:
        json.dump(stickers, f)
        
def get_character_folders_with_images() -> List[str]:
    """Rasmlar mavjud bo'lgan personaj papkalarini qaytaradi"""
    folders = []
    for folder in os.listdir(IMAGES_DIR):
        folder_path = os.path.join(IMAGES_DIR, folder)
        if os.path.isdir(folder_path):
            # Papkada rasm bor-yo'qligini tekshirish
            images = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
            if images:
                folders.append(folder)
    return folders

def normalize_name(name: str) -> str:
    """Personaj nomini solishtirish uchun normalizatsiya qiladi"""
    # Kichik harflarga o'tkazish va bo'sh joylarni olib tashlash
    return name.lower().strip()

def load_stickers_by_category(category: str) -> List[str]:
    filename = f"stickers_{category}.json"
    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_stickers_by_category(category: str, stickers: List[str]) -> None:
    filename = f"stickers_{category}.json"
    with open(filename, "w") as f:
        json.dump(stickers, f)

def load_user_scores() -> Dict[str, int]:
    try:
        if os.path.exists("user_scores.json"):
            with open("user_scores.json", "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_user_scores(scores: Dict[str, int]) -> None:
    with open("user_scores.json", "w") as f:
        json.dump(scores, f)

# === OWNER UTILS (restrict sticker adding) ===
OWNER_ID_FILE = "owner_id.json"

def load_owner_id() -> int | None:
    try:
        if os.path.exists(OWNER_ID_FILE):
            with open(OWNER_ID_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "owner_id" in data:
                    return int(data["owner_id"]) if data["owner_id"] is not None else None
                if isinstance(data, int):
                    return data
    except Exception:
        pass
    return None

def save_owner_id(owner_id: int) -> None:
    try:
        with open(OWNER_ID_FILE, "w") as f:
            json.dump({"owner_id": owner_id}, f)
    except Exception:
        logger.warning("Owner ID saqlashda xatolik yuz berdi")

# === MENU HELPERS ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Rasm", callback_data="menu_img")],
        [InlineKeyboardButton("🏷 Stickerlar", callback_data="menu_stickers")],
        [InlineKeyboardButton("🎬 Video", callback_data="menu_video")]
    ])

def image_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Zero Two 🌸", callback_data="img_02")],
        [InlineKeyboardButton("Hiro 👑", callback_data="img_hiro")],
       [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_main")]
    ])

def sticker_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Zero Two 🌸", callback_data="stickers_zero_two")],
        [InlineKeyboardButton("Hiro 👑", callback_data="stickers_hiro")],
        [InlineKeyboardButton("Umumiy 🏷", callback_data="stickers_general")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_main")]
    ])

# === COMMAND HANDLERS ===
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Salom! Men Starlizia botman.\n\n"
        "📁 Buyruqlar:\n"
        "/img <papka> — rasm yuboradi (02, hiro)\n"
        "/stickers — saqlangan stickerlardan tasodifiy\n"
        "/video — video havola\n\n"
        "🎮 O'yin buyruqlari:\n"
        "/game — personaj rasmini yuboradi\n"
        "/guess <nom> —  personaj nomi \n"
        "/top — eng yuqori ballarni ko'rsatish\n"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

async def img_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("📸 Papkani tanlang:", reply_markup=image_menu())
        return
    await send_random_image(update.message, args[0])

async def video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎬 Videolarni shu yerdan topasiz:\n{CHANNEL_LINK}")

async def addstick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    owner_id = load_owner_id()
    # Birinchi /addstick qilgan foydalanuvchini avtomatik egasi sifatida belgilaymiz
    if owner_id is None:
        save_owner_id(user_id)
        owner_id = user_id
        await update.message.reply_text("👑 Siz bot egasi sifatida belgilandingiz. Endi sticker qo'shishingiz mumkin.")

    if user_id != owner_id:
        await update.message.reply_text("🔒 Bu funksiya bot egasiga tegishli. Siz sticker qo'sha olmaysiz.")
        return

    kb = [
        [InlineKeyboardButton("Zero Two 🌸", callback_data="add_sticker_zero_two")],
        [InlineKeyboardButton("Hiro 👑", callback_data="add_sticker_hiro")],
        [InlineKeyboardButton("Umumiy 🏷", callback_data="add_sticker_general")]
    ]
    await update.message.reply_text("Qaysi kategoriyaga sticker qo‘shasiz?", reply_markup=InlineKeyboardMarkup(kb))

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADD_MODE:
        del ADD_MODE[user_id]
        await update.message.reply_text("❌ Sticker qo‘shish bekor qilindi.")
    else:
        await update.message.reply_text("Faol jarayon yo‘q.")

async def stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏷 Sticker to'plamini tanlang:", reply_markup=sticker_menu())

async def game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'yinni boshlash uchun buyruq"""
    await send_random_character_image(update.message, context)

async def guess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Personajni taxmin qilish uchun buyruq"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Agar o'yin boshlangan bo'lmasa
    if chat_id not in CURRENT_GAME_IMAGE:
        await update.message.reply_text("🎮 Avval o'yinni boshlang! /game buyrug'ini yuboring.")
        return
    
    # Foydalanuvchi taxminini tekshirish
    args = context.args
    if not args:
        await update.message.reply_text(" Personaj nomini kiriting." )
        return
    # Bir nechta so'zli nomlar uchun normalizatsiya
    guess = normalize_name(" ".join(args))
    correct_character = normalize_name(CURRENT_GAME_IMAGE[chat_id]["character"]) 
    
    # Foydalanuvchi ballarini yuklash
    global USER_SCORES
    if not USER_SCORES:
        USER_SCORES = load_user_scores()
    
    user_key = str(user_id)
    if user_key not in USER_SCORES:
        USER_SCORES[user_key] = {"score": 0, "username": username}
    
    # Taxminni tekshirish
    if guess == correct_character:
        # To'g'ri taxmin
        USER_SCORES[user_key]["score"] += 10
        USER_SCORES[user_key]["username"] = username
        save_user_scores(USER_SCORES)
        
        # Foydalanuvchi taxmin qilgan xabarni o'chirish
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=update.message.message_id
            )
        except Exception as e:
            logger.error(f"Foydalanuvchi xabarini o'chirishda xatolik: {e}")
        
        # O'yin rasmini o'chirish
        try:
            # Agar xabar ID saqlangan bo'lsa (chat_data afzal)
            if hasattr(context, 'chat_data') and 'last_game_message_id' in context.chat_data:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=context.chat_data['last_game_message_id']
                )
            elif hasattr(context, 'user_data') and 'last_game_message_id' in context.user_data:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=context.user_data['last_game_message_id']
                )
        except Exception as e:
            logger.error(f"O'yin rasmini o'chirishda xatolik: {e}")
        
        # To'g'ri javob xabarini yuborish
        success_message = await update.message.reply_text(
            f"✅ {username} to'g'ri topdi! +10 ball qo'shildi!\nUmumiy ball: {USER_SCORES[user_key]['score']}"
        )
        
        # O'yin tugadi, yangi o'yin boshlanmaydi
        # Joriy o'yin ma'lumotlarini o'chirish
        if chat_id in CURRENT_GAME_IMAGE:
            del CURRENT_GAME_IMAGE[chat_id]
        
        # Yangi o'yin boshlanmaydi, shuning uchun xabar ID saqlanmaydi
    else:
        # Noto'g'ri taxmin
        # Foydalanuvchi taxmin qilgan xabarni o'chirish
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=update.message.message_id
            )
        except Exception as e:
            logger.error(f"Foydalanuvchi xabarini o'chirishda xatolik: {e}")
            
        # O'yin rasmini o'chirish
        try:
            # Agar xabar ID saqlangan bo'lsa (chat_data afzal)
            if hasattr(context, 'chat_data') and 'last_game_message_id' in context.chat_data:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=context.chat_data['last_game_message_id']
                )
            elif hasattr(context, 'user_data') and 'last_game_message_id' in context.user_data:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=context.user_data['last_game_message_id']
                )
        except Exception as e:
            logger.error(f"O'yin rasmini o'chirishda xatolik: {e}")
        
        # Noto'g'ri javob xabarini yuborish
        await update.message.reply_text(f"❌ {username} noto'g'ri taxmin qildi! Bu {correct_character} edi.")
        
        # O'yin tugadi, yangi o'yin boshlanmaydi
        # Joriy o'yin ma'lumotlarini o'chirish
        if chat_id in CURRENT_GAME_IMAGE:
            del CURRENT_GAME_IMAGE[chat_id]

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eng yuqori ballarni ko'rsatish"""
    global USER_SCORES
    if not USER_SCORES:
        USER_SCORES = load_user_scores()
    
    if not USER_SCORES:
        await update.message.reply_text("🏆 Hali hech kim o'yinda qatnashmagan!")
        return
    
    # Ballar bo'yicha saralash
    sorted_scores = sorted(USER_SCORES.items(), key=lambda x: x[1]["score"], reverse=True)
    
    # Top 10 ni ko'rsatish
    top_users = sorted_scores[:10]
    
    message = "🏆 TOP O'YINCHILAR 🏆\n\n"
    for i, (user_id, data) in enumerate(top_users, 1):
        message += f"{i}. {data['username']}: {data['score']} ball\n"
    
    await update.message.reply_text(message)

async def auto_game_start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har 1 minutda avtomatik o'yin boshlash"""
    chat_id = update.effective_chat.id
    
    # JobQueue mavjudligini tekshirish
    if not context.job_queue:
        await update.message.reply_text("⚠️ Avtomatik o'yin funksiyasi hozircha ishlamaydi. Oddiy o'yin uchun /game buyrug'ini ishlating.")
        # O'yin boshlash
        await send_random_character_image(update.message, context)
        return
    
    try:
        # Avvalgi avtomatik o'yinni to'xtatish
        current_jobs = context.job_queue.get_jobs_by_name(f"auto_game_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()
        
        # Yangi avtomatik o'yinni boshlash (har 60 sekundda)
        context.job_queue.run_repeating(
            auto_send_character_image,
            interval=60,
            first=5,
            chat_id=chat_id,
            name=f"auto_game_{chat_id}"
        )
        
        await update.message.reply_text("✅ Har 1 minutda avtomatik o'yin boshlandi! To'xtatish uchun /auto_game_stop")
    except Exception as e:
        logger.error(f"Avtomatik o'yin boshlashda xatolik: {e}")
        await update.message.reply_text("⚠️ Avtomatik o'yin boshlashda xatolik yuz berdi. Oddiy o'yin uchun /game buyrug'ini ishlating.")
        # O'yin boshlash
        await send_random_character_image(update.message, context)

async def auto_game_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avtomatik o'yinni to'xtatish"""
    chat_id = update.effective_chat.id
    
    # JobQueue mavjudligini tekshirish
    if not context.job_queue:
        await update.message.reply_text("⚠️ Avtomatik o'yin funksiyasi hozircha ishlamaydi. Oddiy o'yin uchun /game buyrug'ini ishlating.")
        return
    
    try:
        # Avtomatik o'yinni to'xtatish
        current_jobs = context.job_queue.get_jobs_by_name(f"auto_game_{chat_id}")
        if not current_jobs:
            await update.message.reply_text("❌ Avtomatik o'yin ishga tushirilmagan!")
            return
        
        for job in current_jobs:
            job.schedule_removal()
        
        await update.message.reply_text("✅ Avtomatik o'yin to'xtatildi!")
    except Exception as e:
        logger.error(f"Avtomatik o'yinni to'xtatishda xatolik: {e}")
        await update.message.reply_text("⚠️ Avtomatik o'yinni to'xtatishda xatolik yuz berdi.")

# === MESSAGE HANDLERS ===
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Faqat egasi qo'sha oladi
    owner_id = load_owner_id()
    if owner_id is None or user_id != owner_id:
        return
    if user_id not in ADD_MODE:
        return

    category = context.user_data.get("sticker_category", "general")
    sticker_id = update.message.sticker.file_id

    stickers = load_stickers()
    if sticker_id not in stickers:
        stickers.append(sticker_id)
        save_stickers(stickers)

    cat_stickers = load_stickers_by_category(category)
    if sticker_id not in cat_stickers:
        cat_stickers.append(sticker_id)
        save_stickers_by_category(category, cat_stickers)
        await update.message.reply_text(f"✅ Sticker {STICKER_CATEGORIES.get(category)} kategoriyasiga saqlandi!")
    else:
        await update.message.reply_text("Bu sticker allaqachon saqlangan.")
    del ADD_MODE[user_id]

# === IMAGE HANDLER ===
async def send_random_image(message, folder):
    chat_id = message.chat_id
    folder_path = os.path.join(IMAGES_DIR, folder)

    if not os.path.isdir(folder_path):
        await message.reply_text(f"❌ Papka topilmadi: {folder}")
        return

    files = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
    if not files:
        await message.reply_text(f"{folder} papkasida rasm yo'q.")
        return

    last = LAST_IMAGE.get(chat_id, {}).get("file_path")
    available = [f for f in files if os.path.join(folder_path, f) != last] or files

    chosen = random.choice(available)
    file_path = os.path.join(folder_path, chosen)
    kb = [
        [InlineKeyboardButton("🔄 Yana rasm", callback_data=f"img_{folder}")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"back_to_main")]
    ]
    try:
        with open(file_path, "rb") as img:
            await message.reply_photo(photo=img, caption=f"{folder} 🎨", reply_markup=InlineKeyboardMarkup(kb))
        LAST_IMAGE[chat_id] = {"file_path": file_path}
    except Exception as e:
        logger.error(e)
        await message.reply_text("⚠️ Xatolik yuz berdi.")

async def send_random_character_image(message, context):
    chat_id = message.chat_id
    
    # Personajlar papkalarini dinamik tanlash (rasmlari bor papkalar)
    character_folders = get_character_folders_with_images()
    if not character_folders:
        await message.reply_text("❌ Rasmlar topilmadi. 'images/' ichiga rasm qo'shing.")
        return None
    folder = random.choice(character_folders)
    folder_path = os.path.join(IMAGES_DIR, folder)
    
    if not os.path.isdir(folder_path):
        await message.reply_text(f"❌ Papka topilmadi: {folder}")
        return None
    
    files = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
    if not files:
        await message.reply_text(f"{folder} papkasida rasm yo'q.")
        return None
    
    # Oldingi rasmni tekshirish va uni takrorlamaslik
    last_image = CURRENT_GAME_IMAGE.get(chat_id, {}).get("file_path", "")
    last_folder = CURRENT_GAME_IMAGE.get(chat_id, {}).get("character", "")
    
    # Agar oldingi rasm bilan bir xil papka bo'lsa, boshqa rasmni tanlash
    if last_folder == folder:
        available_files = [f for f in files if os.path.join(folder_path, f) != last_image]
        # Agar boshqa rasm qolmagan bo'lsa, boshqa papkani tanlash
        if not available_files:
            # Boshqa papkani tanlash
            folder = [f for f in character_folders if f != folder][0]
            folder_path = os.path.join(IMAGES_DIR, folder)
            files = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
        else:
            files = available_files
    
    chosen = random.choice(files)
    file_path = os.path.join(folder_path, chosen)
    
    kb = [
        [InlineKeyboardButton("🎮 Taxmin qilish (/guess)", callback_data="game_info")]
    ]
    
    try:
        with open(file_path, "rb") as img:
            sent_message = await message.reply_photo(
                photo=img, 
                caption="🎮 Bu qaysi personaj? Taxmin qilish uchun /guess buyrug'idan foydalaning!", 
                reply_markup=InlineKeyboardMarkup(kb)
            )
        # O'yin uchun joriy rasmni saqlash
        CURRENT_GAME_IMAGE[chat_id] = {"character": folder, "file_path": file_path}
        # Xabar ID ni saqlash (chat_data ichida)
        if hasattr(context, 'chat_data'):
            context.chat_data['last_game_message_id'] = sent_message.message_id
        return sent_message
    except Exception as e:
        logger.error(e)
        await message.reply_text("⚠️ Xatolik yuz berdi.")
        return None

# Avtomatik ravishda personaj rasmini yuborish funksiyasi
async def auto_send_character_image(context: ContextTypes.DEFAULT_TYPE):
    """Har 1 minutda avtomatik ravishda personaj rasmini yuboradi"""
    job = context.job
    chat_id = job.chat_id
    
    # Oldingi xabarni o'chirish uchun urinish
    try:
        # Agar xabar ID saqlangan bo'lsa
        if hasattr(context.job, 'data') and 'last_auto_game_message_id' in context.job.data:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=context.job.data['last_auto_game_message_id']
            )
    except Exception as e:
        logger.error(f"Avtomatik o'yin rasmini o'chirishda xatolik: {e}")
    
    # Personajlar papkalarini dinamik tanlash (rasmlari bor papkalar)
    character_folders = get_character_folders_with_images()
    if not character_folders:
        logger.error("Rasmli papkalar topilmadi.")
        return
    folder = random.choice(character_folders)
    folder_path = os.path.join(IMAGES_DIR, folder)
    
    if not os.path.isdir(folder_path):
        logger.error(f"Papka topilmadi: {folder}")
        return
    
    files = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
    if not files:
        logger.error(f"{folder} papkasida rasm yo'q.")
        return
    
    # Oldingi rasmni tekshirish va uni takrorlamaslik
    last_image = CURRENT_GAME_IMAGE.get(chat_id, {}).get("file_path", "")
    last_folder = CURRENT_GAME_IMAGE.get(chat_id, {}).get("character", "")
    
    # Agar oldingi rasm bilan bir xil papka bo'lsa, boshqa rasmni tanlash
    if last_folder == folder:
        available_files = [f for f in files if os.path.join(folder_path, f) != last_image]
        # Agar boshqa rasm qolmagan bo'lsa, boshqa papkani tanlash
        if not available_files:
            # Boshqa papkani tanlash
            folder = [f for f in character_folders if f != folder][0]
            folder_path = os.path.join(IMAGES_DIR, folder)
            files = [f for f in os.listdir(folder_path) if f.endswith((".jpg", ".png", ".webp"))]
        else:
            files = available_files
    
    chosen = random.choice(files)
    file_path = os.path.join(folder_path, chosen)
    
    kb = [
        [InlineKeyboardButton("🎮 Taxmin qilish (/guess)", callback_data="game_info")]
    ]
    
    try:
        with open(file_path, "rb") as img:
            sent_message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=img, 
                caption=f"⏰ Vaqtli o'yin! Bu qaysi personaj?\nTaxmin qilish uchun /guess buyrug'idan foydalaning!", 
                reply_markup=InlineKeyboardMarkup(kb)
            )
        # O'yin uchun joriy rasmni saqlash
        CURRENT_GAME_IMAGE[chat_id] = {"character": folder, "file_path": file_path}
        
        # Xabar ID sini saqlash
        if not hasattr(context.job, 'data'):
            context.job.data = {}
        context.job.data['last_auto_game_message_id'] = sent_message.message_id
    except Exception as e:
        logger.error(f"Avtomatik o'yin rasmini yuborishda xatolik: {e}")

# === CALLBACK HANDLER ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_to_main":
        await query.message.edit_text("🏠 Bosh menyu:", reply_markup=main_menu())

    elif data == "menu_img":
        await query.message.edit_text("📸 Papkani tanlang:", reply_markup=image_menu())

    elif data == "menu_stickers":
        await query.message.edit_text("🏷 Sticker kategoriyasini tanlang:", reply_markup=sticker_menu())

    elif data == "menu_video":
        await query.message.edit_text(f"🎬 Videolarni shu yerdan topasiz:\n{CHANNEL_LINK}", reply_markup=main_menu())

    elif data.startswith("img_"):
        folder = data.split("_")[1]
        await send_random_image(query.message, folder)

    elif data.startswith("stickers_"):
        category = data.split("_", 1)[1]
        stickers = load_stickers_by_category(category)
        if not stickers:
            await query.message.reply_text(f"{category} kategoriyasida sticker yo‘q.")
            return
        last = LAST_STICKER_SENT.get(query.message.chat_id)
        choices = [s for s in stickers if s != last] or stickers
        sticker_id = random.choice(choices)
        await context.bot.send_sticker(query.message.chat_id, sticker=sticker_id)
        LAST_STICKER_SENT[query.message.chat_id] = sticker_id

    elif data.startswith("add_sticker_"):
        category = data.split("_", 2)[2]
        user_id = query.from_user.id
        owner_id = load_owner_id()
        if owner_id is None:
            save_owner_id(user_id)
            owner_id = user_id
        if user_id != owner_id:
            await query.message.reply_text("🔒 Bu funksiya bot egasiga tegishli. Siz sticker qo'sha olmaysiz.")
            return
        ADD_MODE[user_id] = True
        context.user_data["sticker_category"] = category
        await query.message.reply_text(
            f"🩵 Endi menga {STICKER_CATEGORIES.get(category)} stickerini yuboring.\n/cancel — bekor qilish."
        )

# === NEW MEMBER HANDLER ===
async def new_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.message.reply_text("👋 Bot qo‘shildi! Menga media yuborish huquqini bering.")
            continue
        gif_url = "https://i.pinimg.com/originals/c0/61/08/c0610813dadc87d80dffedf6bf68641a.gif"
        await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation=gif_url,
            caption=f"🎉 Xush kelibsiz, {member.mention_html()}!",
            parse_mode="HTML"
        )

# === MAIN ===
def main():
    # Foydalanuvchilar ballarini yuklash
    global USER_SCORES
    USER_SCORES = load_user_scores()
    
    # Oddiy application yaratish
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("img", img_cmd))
    app.add_handler(CommandHandler("addstick", addstick_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("stickers", stickers_cmd))
    app.add_handler(CommandHandler("video", video_cmd))
    
    # Yangi o'yin buyruqlari
    app.add_handler(CommandHandler("game", game_cmd))
    app.add_handler(CommandHandler("guess", guess_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    
    # Avtomatik o'yin buyruqlari
    app.add_handler(CommandHandler("auto_game_start", auto_game_start_cmd))
    app.add_handler(CommandHandler("auto_game_stop", auto_game_stop_cmd))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
# === NAME HELPERS ===
def normalize_name(s: str) -> str:
    """Lowercase, remove spaces/underscores for robust matching."""
    return re.sub(r"[\s_]+", "", (s or "").strip().lower())

def get_character_folders_with_images() -> List[str]:
    """Return image subfolders that contain at least one image file."""
    if not os.path.isdir(IMAGES_DIR):
        return []
    folders: List[str] = []
    for d in os.listdir(IMAGES_DIR):
        dp = os.path.join(IMAGES_DIR, d)
        if os.path.isdir(dp):
            files = [f for f in os.listdir(dp) if f.endswith((".jpg", ".png", ".webp"))]
            if files:
                folders.append(d)
    return folders
