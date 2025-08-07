import logging
import aiohttp

async def _wiki_api_request(lang: str, params: dict):
    """Helper function to make requests to the Wikipedia API."""
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    headers = {"User-Agent": "TelegramLocationBot/1.0"}

    params.update({
        "format": "json",
        "action": "query",
    })

    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(api_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("query")
        except aiohttp.ClientError as e:
            logging.error(f"Error fetching data from Wikipedia API: {e}")
            return None

async def search_place_by_name(place_name: str, lang: str = "en"):
    """
    Searches for a place by name on Wikipedia and returns the page ID of the best match.
    """
    logging.info(f"Searching Wikipedia for '{place_name}' in lang '{lang}'")
    params = {
        "list": "search",
        "srsearch": place_name,
        "srlimit": 1,
        "srprop": "", # We don't need any properties, just the pageid
    }
    query_result = await _wiki_api_request(lang, params)
    if query_result and query_result.get("search"):
        search_results = query_result["search"]
        if search_results:
            return search_results[0].get("pageid")
    logging.warning(f"Could not find a Wikipedia page for '{place_name}'")
    return None

async def get_page_summary(page_id: int, lang: str = "en"):
    """
    Get the summary (lead section) of a Wikipedia page by its page ID.
    """
    if not page_id:
        return None

    logging.info(f"Fetching summary for page_id {page_id} in lang '{lang}'")
    params = {
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "pageids": page_id,
    }
    query_result = await _wiki_api_request(lang, params)
    if query_result and "pages" in query_result:
        page = query_result["pages"].get(str(page_id))
        if page and "extract" in page:
            return page.get("extract")
    return None
