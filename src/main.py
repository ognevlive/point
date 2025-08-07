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

from src.osm import get_historic_places_from_overpass
from src.wiki import search_place_by_name, get_page_summary
from src.llm import filter_interesting_places, extract_facts_from_text, get_story_from_llm

load_dotenv()

# --- Environment Variables ---
TOKEN = os.getenv("BOT_TOKEN")
OSM_ENDPOINT = os.getenv("OSM_ENDPOINT", "https://nominatim.openstreetmap.org")
SEARCH_RADIUS_M = int(os.getenv("SEARCH_RADIUS_M", 300))  # Increased default radius

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
    Handles the new multi-step data processing pipeline.
    """
    lat, lon = message.location.latitude, message.location.longitude
    user_lang = message.from_user.language_code or "en"

    # F-5: Log request with rounded coordinates
    logging.info(f"New request from user {message.from_user.id}. Location: ({lat:.3f}, {lon:.3f})")

    # 1. Get Address
    await message.answer("Получил координаты. Ищу ваш адрес...", reply_markup=location_keyboard)
    address = await get_address_from_coords(lat, lon, user_lang)
    if not address:
        await message.answer("Не удалось определить ваш адрес. Попробуйте еще раз.")
        return

    # 2. Get raw list of places from OpenStreetMap
    await message.answer("Нашел ваш адрес. Ищу поблизости исторические объекты в OpenStreetMap...")
    raw_places = await get_historic_places_from_overpass(lat, lon, SEARCH_RADIUS_M)
    if not raw_places:
        await message.answer("К сожалению, не нашел ничего интересного в окрестностях по данным OSM.")
        return

    # 3. Filter places with LLM
    await message.answer(f"Нашел {len(raw_places)} объектов. Отправляю гиду-нейросети для фильтрации самого интересного...")
    interesting_places = await filter_interesting_places(raw_places, user_lang)
    if not interesting_places:
        await message.answer("После фильтрации нейросетью не осталось интересных мест. Попробуйте другое местоположение.")
        return

    # 4. Enrich data and extract facts
    await message.answer(f"Отобрал {len(interesting_places)} мест. Ищу информацию о них в Wikipedia и извлекаю факты...")
    structured_facts = []
    for place in interesting_places:
        place_name = place.get("name")
        page_id = await search_place_by_name(place_name, user_lang)
        if page_id:
            summary = await get_page_summary(page_id, user_lang)
            if summary:
                facts = await extract_facts_from_text(summary, place_name, user_lang)
                if facts:
                    structured_facts.append({"name": place_name, **facts})

    if not structured_facts:
        await message.answer("Не удалось найти достаточно фактов об этих местах для создания истории.")
        return

    # 5. Generate final story
    await message.answer("Все факты собраны. Отправляю историку-нейросети для написания рассказа...")
    story = await get_story_from_llm(address, structured_facts, user_lang)
    if story:
        await message.answer(story)
    else:
        await message.answer("К сожалению, не удалось создать историю. Попробуйте еще раз позже.")


# --- Main Application Logic ---
async def main() -> None:
    bot = Bot(TOKEN, parse_mode=ParseMode.MARKDOWN_V2)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
