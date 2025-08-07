import logging
import os
import json
from openai import AsyncOpenAI, OpenAIError

# --- LLM Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- System Prompt ---
SYSTEM_PROMPT = """
You are a local historian and a talented storyteller with deep knowledge of urban history and local culture.
You will be given data about a specific location including the address and nearby places from OpenStreetMap.
Your task is to create an engaging story about this location, including both historical facts and interesting local details.

Your response MUST follow these rules:
1.  **Language:** Write in the language specified in the `language` field (Russian for 'ru', English for 'en').
2.  **Format:** Use Telegram's MarkdownV2 formatting with headings, bold text, and italics.
3.  **Content:**
    - Start with a brief overview of the area and its character.
    - Describe 3-5 nearby places, including both important landmarks and interesting local spots.
    - For each place, mention its name and add interesting context or historical details.
    - Include local color, cultural references, and interesting facts about the area.
    - You can mention things like: local businesses, architectural details, community spaces, historical events, or cultural significance.
    - The response should be 8-15 sentences total, engaging and informative.
4.  **Tone:** Be engaging, informative, and slightly informal, as if talking to a curious friend.
5.  **Creativity:** You can add interesting local details and cultural context, but base the core information on the provided data.
"""

# --- OpenAI Client ---
if not OPENAI_API_KEY:
    logging.warning("OPENAI_API_KEY is not set. LLM features will be disabled.")
    client = None
else:
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )

async def get_story_from_llm(address: str, places_data: list, address_details: dict = None, lang: str = "en"):
    """
    Generates a historical story using an LLM based on location data.
    """
    if not client:
        logging.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
        return None

    # Prepare the data payload for the prompt
    prompt_data = {
        "language": lang,
        "current_address": address,
        "address_details": address_details or {},
        "nearby_places": places_data,
    }

    try:
        logging.info(f"Sending request to LLM for lang {lang}. Model: {LLM_MODEL}")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Here is the raw data JSON: {json.dumps(prompt_data, ensure_ascii=False)}"}
            ],
            temperature=0.8,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except OpenAIError as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None
