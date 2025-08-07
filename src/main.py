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
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from .places import get_place_info, get_address_details
from .llm import get_story_from_llm

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
    # Escape all special characters for MarkdownV2
    escape_chars = r"[_*\[\]()~`>#+=|{}.!-]"
    return re.sub(f"({escape_chars})", r"\\\1", text)

async def safe_send_message(message: Message, text: str):
    """Safely sends a message with proper markdown escaping."""
    try:
        # First try to send as-is
        return await message.answer(text)
    except Exception as e:
        if "can't parse entities" in str(e):
            # If markdown parsing fails, escape the text and try again
            escaped_text = escape_markdown(text)
            return await message.answer(escaped_text)
        else:
            # If other error, just send plain text
            return await message.answer(text.replace("*", "").replace("_", "").replace("`", ""))


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
@dp.message()
async def debug_handler(message: Message):
    """
    Debug handler to see what messages are received.
    """
    logging.info(f"DEBUG: Received message type: {type(message)}")
    logging.info(f"DEBUG: Message content: {message}")
    if hasattr(message, 'location') and message.location:
        logging.info(f"DEBUG: Location found: {message.location}")
        # Call the location handler
        await location_handler(message)
    elif hasattr(message, 'text') and message.text:
        logging.info(f"DEBUG: Text message: {message.text}")
        if message.text == "/start":
            await command_start_handler(message)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Handles the /start command and shows the location button.
    """
    await message.answer(
        f"Здравствуйте, {escape_markdown(message.from_user.full_name)}\!\n\n"
        "Нажмите кнопку ниже, чтобы поделиться вашим местоположением и получить историческую справку\\.",
        reply_markup=location_keyboard,
    )


@dp.message(F.location)
async def location_handler(message: Message):
    """
    Handles receiving a location, gets data, and generates a story.
    """
    logging.info(f"Received location from user {message.from_user.id}: {message.location}")
    
    lat, lon = message.location.latitude, message.location.longitude
    user_lang = message.from_user.language_code or "en"
    
    logging.info(f"Processing location: lat={lat}, lon={lon}, lang={user_lang}")

    await message.answer(
        "Получил координаты\\. Собираю исторические данные\\.\\.\\.",
        reply_markup=location_keyboard,
    )

    # 1. Get Address and Details
    logging.info("Getting address from coordinates...")
    address = await get_address_from_coords(lat, lon, user_lang)
    if not address:
        logging.error("Failed to get address from coordinates")
        await message.answer("Не удалось определить ваш адрес\\. Попробуйте еще раз\\.")
        return
    
    logging.info(f"Found address: {address}")
    
    # Get detailed address information
    address_details = await get_address_details(lat, lon, user_lang)

    # 2. Find nearby places from OpenStreetMap
    logging.info("Searching for nearby places...")
    places = await get_place_info(lat, lon, SEARCH_RADIUS_M)
    if not places:
        logging.info(f"No places found in {SEARCH_RADIUS_M}m, expanding to 500m.")
        places = await get_place_info(lat, lon, 500)
    if not places:
        logging.info("No places found in 500m, expanding to 1000m.")
        places = await get_place_info(lat, lon, 1000)

    if not places:
        logging.warning("No places found in vicinity")
        await message.answer("К сожалению, не нашел ничего интересного в окрестностях\\.")
        return

    logging.info(f"Found {len(places)} places")

    # 3. Prepare places data for LLM
    places_data = []
    for place in places:
        places_data.append({
            "title": place.get("name", "Неизвестное место"),
            "type": place.get("type", "place"),
            "description": place.get("description", "Интересное место"),
            "tags": place.get("tags", {})
        })

    logging.info(f"Prepared data for {len(places_data)} places")

    # 4. Generate story with LLM
    await message.answer("Все данные собраны\\. Отправляю запрос краеведу\\-нейросети\\.\\.\\.")
    story = await get_story_from_llm(address, places_data, address_details, user_lang)

    # 5. Send response (LLM story or fallback)
    if story:
        await safe_send_message(message, story)
    else:
        # Fallback to simple list if LLM fails
        await message.answer("Не удалось сгенерировать историю\\. Вот краткая справка:")
        response_parts = ["📜 *Что я нашел поблизости:*"]
        for place in places_data:
            response_parts.append(
                f"\n🏛️ *{escape_markdown(place['title'])}*\n{escape_markdown(place['description'])}"
            )
        await message.answer("\n".join(response_parts))


# --- Main Application Logic ---
async def main() -> None:
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
