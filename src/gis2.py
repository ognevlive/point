import logging
import os
import aiohttp

GIS2_API_KEY = os.getenv("GIS2_API_KEY")
GIS2_API_ENDPOINT = "https://catalog.api.2gis.com/3.0/items"

async def get_places_from_2gis(latitude: float, longitude: float, radius: int):
    """
    Queries the 2GIS Places API to find interesting places near a location.
    """
    if not GIS2_API_KEY:
        logging.error("2GIS API key not set. Cannot query 2GIS.")
        return []

    # Note: 2GIS API expects longitude first, then latitude.
    params = {
        "key": GIS2_API_KEY,
        "location": f"{longitude},{latitude}",
        "radius": radius,
        "q": "достопримечательность | памятник | музей | собор | усадьба | театр",
        "fields": "items.adm_div,items.address,items.rubrics,items.context,items.structure_info",
        "sort": "distance",
    }

    headers = {"User-Agent": "TelegramLocationBot/1.0"}

    logging.info(f"Querying 2GIS API for places near ({latitude}, {longitude})")
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(GIS2_API_ENDPOINT, params=params) as response:
                response.raise_for_status()
                data = await response.json()

                if data.get("meta", {}).get("code") == 200:
                    return data.get("result", {}).get("items", [])
                else:
                    logging.error(f"2GIS API returned an error: {data.get('meta')}")
                    return []

        except aiohttp.ClientError as e:
            logging.error(f"Error querying 2GIS API: {e}")
            return []
