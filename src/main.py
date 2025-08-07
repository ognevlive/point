import asyncio
import logging
import os
import re
import sys
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

from src.gis2 import get_places_from_2gis
from src.llm import enrich_place_with_llm, get_story_from_llm

load_dotenv()

# --- Environment Variables ---
TOKEN = os.getenv("BOT_TOKEN")
SEARCH_RADIUS_M = int(os.getenv("SEARCH_RADIUS_M", 500)) # Increased default radius

# --- Bot Setup ---
dp = Dispatcher()

# --- UI Elements ---
location_button = KeyboardButton(text="📍 Поделиться местоположением", request_location=True)
location_keyboard = ReplyKeyboardMarkup(keyboard=[[location_button]], resize_keyboard=True)


# --- Helpers ---
def escape_markdown(text: str) -> str:
    """Escapes characters for Telegram's MarkdownV2 format."""
    if not isinstance(text, str):
        return ""
    # Note: The hyphen must be at the end of the character class to be treated literally.
    escape_chars = r"[_*\[\]()~`>#+=|{}.!-]"
    return re.sub(f"({escape_chars})", r"\\\1", text)


# --- Message Handlers ---
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Handles the /start command and shows the location button.
    """
    await message.answer(
        f"Здравствуйте, {message.from_user.full_name}!\n\n"
        "Нажмите кнопку ниже, чтобы поделиться вашим местоположением и получить историческую справку.",
        reply_markup=location_keyboard,
    )


@dp.message(F.location)
async def location_handler(message: Message):
    """
    Handles the new 2GIS + LLM data processing pipeline.
    """
    lat, lon = message.location.latitude, message.location.longitude
    user_lang = message.from_user.language_code or "en"

    # F-5: Log request with rounded coordinates
    logging.info(f"New request from user {message.from_user.id}. Location: ({lat:.3f}, {lon:.3f})")

    # 1. Get places from 2GIS
    await message.answer("Получил координаты. Ищу интересные места поблизости через 2ГИС...", reply_markup=location_keyboard)
    places = await get_places_from_2gis(lat, lon, SEARCH_RADIUS_M)
    if not places:
        await message.answer("К сожалению, не нашел ничего интересного в окрестностях по данным 2ГИС.")
        return

    # 2. Enrich places with LLM
    await message.answer(f"Нашел {len(places)} потенциально интересных мест. Обогащаю данные с помощью нейросети-историка...")

    enrichment_tasks = [enrich_place_with_llm(place, user_lang) for place in places]
    enriched_places_results = await asyncio.gather(*enrichment_tasks)

    # Filter out places that couldn't be enriched with historical context
    final_places = [p for p in enriched_places_results if p and p.get("historical_context")]

    if not final_places:
        await message.answer("Не удалось найти достаточно исторической информации об этих местах.")
        return

    # 3. Generate final story
    # For the address, we can use the address of the first found object or call Nominatim. Let's use the first object.
    address = final_places[0].get("address_name", "Ваше местоположение")
    await message.answer("Все данные собраны. Отправляю нейросети-рассказчику для написания истории...")
    story = await get_story_from_llm(address, final_places, user_lang)

    if story:
        await message.answer(story)
    else:
        await message.answer("К сожалению, не удалось создать историю. Попробуйте еще раз позже.")


# --- Main Application Logic ---
async def main() -> None:
    # Initialize Bot instance with a default parse mode which will be passed to all API calls
    bot = Bot(TOKEN, parse_mode=ParseMode.MARKDOWN_V2)
    # And the run events dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
