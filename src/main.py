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

from src.wiki import find_nearby_places, get_page_summary
from src.llm import get_story_from_llm

load_dotenv()

# --- Environment Variables ---
TOKEN = os.getenv("BOT_TOKEN")
OSM_ENDPOINT = os.getenv("OSM_ENDPOINT", "https://nominatim.openstreetmap.org")
SEARCH_RADIUS_M = int(os.getenv("SEARCH_RADIUS_M", 100))

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


# --- Geocoding Service ---
async def get_address_from_coords(latitude: float, longitude: float, lang: str = "en"):
    """
    Reverse geocode coordinates to get an address using Nominatim.
    """
    headers = {"User-Agent": "TelegramBot/1.0"}
    url = f"{OSM_ENDPOINT}/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "accept-language": f"{lang},en",  # Fallback to english
        "zoom": 18,
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("display_name")
        except aiohttp.ClientError as e:
            logging.error(f"Error fetching address from Nominatim: {e}")
            return None


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
    Handles receiving a location, gets data, and generates a story.
    """
    lat, lon = message.location.latitude, message.location.longitude
    user_lang = message.from_user.language_code or "en"

    await message.answer(
        "Получил координаты. Собираю исторические данные...",
        reply_markup=location_keyboard,
    )

    # 1. Get Address
    address = await get_address_from_coords(lat, lon, user_lang)
    if not address:
        await message.answer("Не удалось определить ваш адрес. Попробуйте еще раз.")
        return

    # 2. Find nearby places from Wikipedia
    places = await find_nearby_places(lat, lon, SEARCH_RADIUS_M, user_lang)
    if not places:
        logging.info(f"No places found in {SEARCH_RADIUS_M}m, expanding to 300m.")
        places = await find_nearby_places(lat, lon, 300, user_lang)

    if not places:
        await message.answer("К сожалению, не нашел ничего интересного в окрестностях.")
        return

    # 3. Get summaries for found places
    places_data = []
    for place in places:
        summary = await get_page_summary(place.get("pageid"), user_lang)
        if summary:
            places_data.append({"title": place.get("title"), "summary": summary})

    if not places_data:
        await message.answer("Нашел несколько объектов, но не смог получить для них описание.")
        return

    # 4. Generate story with LLM
    await message.answer("Все данные собраны. Отправляю запрос краеведу-нейросети...")
    story = await get_story_from_llm(address, places_data, user_lang)

    # 5. Send response (LLM story or fallback)
    if story:
        await message.answer(story)
    else:
        # Fallback to simple list if LLM fails
        await message.answer("Не удалось сгенерировать историю. Вот краткая справка:")
        response_parts = ["📜 *Что я нашел поблизости:*"]
        for place in places_data:
            response_parts.append(
                f"\n🏛️ *{escape_markdown(place['title'])}*\n{escape_markdown(place['summary'])}"
            )
        await message.answer("\n".join(response_parts))


# --- Main Application Logic ---
async def main() -> None:
    bot = Bot(TOKEN, parse_mode=ParseMode.MARKDOWN_V2)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
