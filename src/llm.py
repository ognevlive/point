import logging
import os
import json
from openai import AsyncOpenAI, OpenAIError

# --- LLM Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- System Prompts ---
ENRICHMENT_SYSTEM_PROMPT = """
You are a historian and a data enrichment specialist.
You will be given a JSON object with data about a place from the 2GIS mapping service.
Your task is to add a new field to this JSON called "historical_context".
Based on the place's name, address, and categories, use your knowledge to write a brief (2-3 sentences) historical summary or an interesting fact about this place.
If the place is a modern business with no historical significance (e.g., a standard shop or cafe), or if you have no confident information, set the value of "historical_context" to null.
Your response MUST be the original JSON object with the "historical_context" field added. Do not add any other text.
"""

STORYTELLER_SYSTEM_PROMPT = """
You are a local historian and a talented storyteller.
You will be given a JSON object containing the user's approximate address and a list of nearby places.
Each place in the list is a JSON object from 2GIS, enriched with a "historical_context" field.

Your task is to weave this information into a compelling story.
Focus only on the places that have a non-null "historical_context". Ignore the others.
Describe the most interesting 2-3 places, using their name and the historical context provided.
Your response MUST be in the language specified in the `language` field.
Use Telegram's MarkdownV2 formatting.
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


async def enrich_place_with_llm(place_data: dict, lang: str = "en"):
    """
    Takes a place data dict from 2GIS and enriches it with a historical_context field using an LLM.
    """
    if not client:
        logging.warning("LLM client not available, skipping enrichment.")
        place_data["historical_context"] = None
        return place_data

    try:
        logging.info(f"Enriching place: {place_data.get('name')}")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(place_data, ensure_ascii=False)}
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        enriched_data_json = response.choices[0].message.content
        return json.loads(enriched_data_json)
    except (OpenAIError, json.JSONDecodeError) as e:
        logging.error(f"Error enriching place '{place_data.get('name')}' with LLM: {e}")
        place_data["historical_context"] = None
        return place_data


async def get_story_from_llm(address: str, enriched_places_data: list, lang: str = "en"):
    """
    Generates a historical story using an LLM from enriched 2GIS data.
    """
    if not client:
        logging.error("OpenAI client not initialized.")
        return None

    prompt_data = {
        "language": lang,
        "current_address": address,
        "enriched_places": enriched_places_data,
    }

    try:
        logging.info("Sending enriched data to storyteller LLM.")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": STORYTELLER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)}
            ],
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except OpenAIError as e:
        logging.error(f"Error calling storyteller LLM: {e}")
        return None
