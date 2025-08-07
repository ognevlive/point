import logging
import aiohttp
import os

OVERPASS_ENDPOINT = os.getenv("OVERPASS_ENDPOINT", "https://overpass-api.de/api/interpreter")

def _build_overpass_query(latitude: float, longitude: float, radius: int) -> str:
    """Builds the Overpass QL query string."""
    # This query looks for nodes, ways, and relations with various historical or cultural tags.
    query = f"""
    [out:json][timeout:25];
    (
      node["historic"](around:{radius},{latitude},{longitude});
      way["historic"](around:{radius},{latitude},{longitude});
      relation["historic"](around:{radius},{latitude},{longitude});

      node["tourism"~"^(attraction|museum|artwork|gallery)$"](around:{radius},{latitude},{longitude});
      way["tourism"~"^(attraction|museum|artwork|gallery)$"](around:{radius},{latitude},{longitude});
      relation["tourism"~"^(attraction|museum|artwork|gallery)$"](around:{radius},{latitude},{longitude});

      node["building"~"^(cathedral|chapel|church|monastery|palace)$"](around:{radius},{latitude},{longitude});
      way["building"~"^(cathedral|chapel|church|monastery|palace)$"](around:{radius},{latitude},{longitude});
      relation["building"~"^(cathedral|chapel|church|monastery|palace)$"](around:{radius},{latitude},{longitude});
    );
    out center;
    """
    return query

def _parse_overpass_response(response_json: dict) -> list:
    """Parses the JSON response from Overpass API to extract place names and tags."""
    places = []
    if not response_json or "elements" not in response_json:
        return places

    for element in response_json["elements"]:
        tags = element.get("tags", {})
        name = tags.get("name")
        if name:
            # Simple deduplication by name to avoid multiple entries for the same place
            if not any(p['name'] == name for p in places):
                 places.append({"name": name, "tags": tags})
    return places

async def get_historic_places_from_overpass(latitude: float, longitude: float, radius: int):
    """
    Queries the Overpass API to find historical places near a location.
    """
    query = _build_overpass_query(latitude, longitude, radius)
    headers = {"User-Agent": "TelegramLocationBot/1.0"}

    logging.info(f"Querying Overpass API for places near ({latitude}, {longitude})")
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.post(OVERPASS_ENDPOINT, data=query) as response:
                response.raise_for_status()
                data = await response.json()
                return _parse_overpass_response(data)
        except aiohttp.ClientError as e:
            logging.error(f"Error querying Overpass API: {e}")
            return []
