import logging
import os
import json
from openai import AsyncOpenAI, OpenAIError

# --- LLM Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# --- System Prompts ---
STORYTELLER_SYSTEM_PROMPT = """
You are a local historian and a talented storyteller.
You will be given a JSON object with data about a specific location. This includes the user's approximate address and a list of nearby, historically significant places.
Each place in the list is a JSON object with its name and structured facts like 'year_built', 'architect', 'original_purpose', and 'notable_events'.

Your task is to weave this information into a compelling and informative story for a Telegram bot user.

Your response MUST follow these rules:
1.  **Language:** Write in the language specified in the `language` field of the JSON data.
2.  **Format:** Use Telegram's MarkdownV2 formatting. Use headings, bold text, and italics.
3.  **Content:**
    - Start with a brief, engaging historical overview of the area based on the user's address.
    - Describe the most interesting 2-3 places from the list. For each one, skillfully integrate the structured facts you were given (e.g., "The famous St. Isaac's Cathedral, designed by architect Auguste de Montferrand, was completed in 1858...").
    - If a fact is null, simply omit it gracefully. Do not say "architect is unknown".
    - Do NOT invent information. Base your story ONLY on the data provided.
4.  **Tone:** Be engaging, informative, and slightly informal.
"""

FILTER_SYSTEM_PROMPT = """
You are an expert local guide and historian. Your task is to filter a list of geographic points of interest to identify only the most historically and culturally significant ones.
You will receive a JSON list of places, where each place is an object with 'name' and 'tags'.
Analyze the list and remove any places that are modern, generic, or uninteresting from a tourist's or historian's perspective.
Examples of places to REMOVE:
- Generic retail stores (supermarkets, chain stores, pharmacies).
- Modern residential or office buildings unless they are architecturally famous.
- Everyday services (banks, post offices, regular schools).

Examples of places to KEEP:
- Churches, cathedrals, monasteries.
- Museums, galleries, theaters.
- Monuments, historical buildings, famous houses.
- Parks or squares with historical significance.

Your response MUST be only a valid JSON object in the format {"filtered_places": [...]}, where the list contains the places you decided to keep. The list should contain a maximum of 5 places. Do not add any explanation or introductory text.
"""

FACT_EXTRACTION_SYSTEM_PROMPT = """
You are a meticulous researcher's assistant. Your task is to extract specific historical and architectural facts from a given text about a place.
You will receive a JSON object containing the name of a place and a block of text from a Wikipedia article.
Read the text and extract the following specific details:
- "year_built": The year or century the place was built. Can be a string like "19th century".
- "architect": The name(s) of the architect(s).
- "original_purpose": What the building was originally used for.
- "notable_events": A brief, one-sentence summary of any famous events associated with the place.

Your response MUST be a single, valid JSON object with these keys.
If you cannot find a specific piece of information, the value for that key should be `null`.
Do not add any text outside of the JSON object.
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


async def extract_facts_from_text(text: str, place_name: str, lang: str = "en"):
    """
    Uses an LLM to extract structured facts from a block of text.
    """
    if not client:
        logging.warning("LLM client not available, cannot extract facts.")
        return None

    user_content = {
        "place_name": place_name,
        "text": text,
    }

    try:
        logging.info(f"Sending text for '{place_name}' to LLM for fact extraction.")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)}
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        facts_json = response.choices[0].message.content
        return json.loads(facts_json)
    except (OpenAIError, json.JSONDecodeError) as e:
        logging.error(f"Error extracting facts for '{place_name}' with LLM: {e}")
        return None


async def filter_interesting_places(places: list, lang: str = "en"):
    """
    Uses an LLM to filter a list of places, keeping only the interesting ones.
    """
    if not client:
        logging.warning("LLM client not available, skipping filtering.")
        return places

    try:
        logging.info(f"Sending {len(places)} places to LLM for filtering.")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(places, ensure_ascii=False)}
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        filtered_places_json = response.choices[0].message.content
        filtered_data = json.loads(filtered_places_json)

        # The prompt specifies the key should be "filtered_places"
        return filtered_data.get("filtered_places", places)

    except (OpenAIError, json.JSONDecodeError) as e:
        logging.error(f"Error filtering places with LLM: {e}")
        # Fallback to returning the original list if filtering fails
        return places


async def get_story_from_llm(address: str, structured_places_data: list, lang: str = "en"):
    """
    Generates a historical story using an LLM from structured place data.
    """
    if not client:
        logging.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
        return None

    # Prepare the data payload for the prompt
    prompt_data = {
        "language": lang,
        "current_address": address,
        "places_with_facts": structured_places_data,
    }

    try:
        logging.info(f"Sending structured data for {len(structured_places_data)} places to LLM for story generation.")
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": STORYTELLER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Here is the structured data JSON: {json.dumps(prompt_data, ensure_ascii=False)}"}
            ],
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except OpenAIError as e:
        logging.error(f"Error calling OpenAI API for story generation: {e}")
        return None
