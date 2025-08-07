import logging
import aiohttp

async def _wiki_api_request(lang: str, params: dict):
    """Helper function to make requests to the Wikipedia API."""
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    headers = {"User-Agent": "TelegramLocationBot/1.0"}

    # Common params for all requests
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

async def find_nearby_places(latitude: float, longitude: float, radius: int, lang: str = "en"):
    """
    Find nearby places using Wikipedia's geosearch.
    Returns a list of dictionaries with 'pageid', 'title', 'dist'.
    """
    params = {
        "list": "geosearch",
        "gscoord": f"{latitude}|{longitude}",
        "gsradius": radius,
        "gslimit": 5,  # As per spec, 3-5 buildings
    }
    query_result = await _wiki_api_request(lang, params)
    return query_result.get("geosearch", []) if query_result else []

async def get_page_summary(page_id: int, lang: str = "en"):
    """
    Get the summary (lead section) of a Wikipedia page.
    """
    params = {
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "pageids": page_id,
    }
    query_result = await _wiki_api_request(lang, params)
    if query_result and "pages" in query_result:
        page = query_result["pages"].get(str(page_id))
        if page:
            return page.get("extract")
    return None
