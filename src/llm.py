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
You are a local historian and a talented storyteller.
You will be given a JSON object with data about a specific location, including the current address and a list of nearby points of interest from Wikipedia.
Your task is to weave this information into a compelling and informative story about the location for a Telegram bot user.

Your response MUST follow these rules:
1.  **Language:** Write in the language specified in the `language` field of the JSON data.
2.  **Format:** Use Telegram's MarkdownV2 formatting. Use headings, bold text, and italics to make the text engaging.
3.  **Content:**
    - Start with a brief historical overview of the area based on the provided data.
    - Describe 3-5 of the most interesting nearby buildings or objects from the list. For each, mention its name and a brief history or fact.
    - Do NOT invent information. Base your story only on the data provided.
    - The entire response should be concise, around 5-10 sentences in total.
4.  **Tone:** Be engaging, informative, and slightly informal, as if talking to a curious friend.
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

async def get_story_from_llm(address: str, places_data: list, lang: str = "en"):
    """
    Generates a historical story using an LLM.
    """
    if not client:
        logging.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
        return None

    # Prepare the data payload for the prompt
    prompt_data = {
        "language": lang,
        "current_address": address,
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
            temperature=0.7,
            max_tokens=2048, # As per spec, 2k context
        )
        return response.choices[0].message.content
    except OpenAIError as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None
