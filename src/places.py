import logging
import aiohttp
import os
from typing import List, Dict, Optional

# --- Configuration ---
OSM_ENDPOINT = os.getenv("OSM_ENDPOINT", "https://nominatim.openstreetmap.org")
OVERPASS_ENDPOINT = os.getenv("OVERPASS_ENDPOINT", "https://overpass-api.de/api/interpreter")

async def get_place_info(latitude: float, longitude: float, radius: int = 100) -> List[Dict]:
    """
    Получает информацию о местах в радиусе через OpenStreetMap Overpass API.
    Возвращает список словарей с информацией о зданиях и местах.
    """
    # Overpass query для поиска зданий и интересных мест
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](around:{radius},{latitude},{longitude});
      way["amenity"](around:{radius},{latitude},{longitude});
      way["historic"](around:{radius},{latitude},{longitude});
      way["tourism"](around:{radius},{latitude},{longitude});
      way["shop"](around:{radius},{latitude},{longitude});
      node["amenity"](around:{radius},{latitude},{longitude});
      node["historic"](around:{radius},{latitude},{longitude});
      node["tourism"](around:{radius},{latitude},{longitude});
      node["shop"](around:{radius},{latitude},{longitude});
    );
    out body;
    >>;
    out skel qt;
    """
    
    headers = {"User-Agent": "TelegramLocationBot/1.0"}
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(OVERPASS_ENDPOINT, data=query) as response:
                response.raise_for_status()
                data = await response.json()
                return _process_overpass_data(data, latitude, longitude)
    except aiohttp.ClientError as e:
        logging.error(f"Error fetching data from Overpass API: {e}")
        return []

def _process_overpass_data(data: Dict, lat: float, lon: float) -> List[Dict]:
    """
    Обрабатывает данные от Overpass API и извлекает информацию о местах.
    """
    places = []
    
    if "elements" not in data:
        return places
    
    for element in data["elements"]:
        if element.get("type") in ["way", "node"]:
            place_info = _extract_place_info(element)
            if place_info:
                places.append(place_info)
    
    # Сортируем по расстоянию и берем первые 5
    places.sort(key=lambda x: x.get("distance", float("inf")))
    return places[:5]

def _extract_place_info(element: Dict) -> Optional[Dict]:
    """
    Извлекает информацию о месте из элемента Overpass API.
    """
    tags = element.get("tags", {})
    
    # Определяем тип места
    place_type = None
    if "building" in tags:
        place_type = "building"
    elif "amenity" in tags:
        place_type = "amenity"
    elif "historic" in tags:
        place_type = "historic"
    elif "tourism" in tags:
        place_type = "tourism"
    elif "shop" in tags:
        place_type = "shop"
    
    if not place_type:
        return None
    
    # Получаем название
    name = tags.get("name") or tags.get("name:ru") or tags.get("name:en")
    if not name:
        # Генерируем название на основе типа
        if place_type == "building":
            building_type = tags.get("building", "здание")
            name = f"{building_type.title()}"
        elif place_type == "amenity":
            amenity_type = tags.get("amenity", "место")
            name = f"{amenity_type.title()}"
        else:
            name = f"{place_type.title()}"
    
    # Создаем описание
    description = _generate_place_description(tags, place_type)
    
    return {
        "name": name,
        "type": place_type,
        "description": description,
        "tags": tags
    }

def _generate_place_description(tags: Dict, place_type: str) -> str:
    """
    Генерирует описание места на основе тегов.
    """
    if place_type == "building":
        building_type = tags.get("building", "здание")
        if building_type == "house":
            return "Жилой дом"
        elif building_type == "commercial":
            return "Коммерческое здание"
        elif building_type == "industrial":
            return "Промышленное здание"
        else:
            return f"Здание типа {building_type}"
    
    elif place_type == "amenity":
        amenity_type = tags.get("amenity", "")
        if amenity_type == "restaurant":
            return "Ресторан"
        elif amenity_type == "cafe":
            return "Кафе"
        elif amenity_type == "school":
            return "Школа"
        elif amenity_type == "hospital":
            return "Больница"
        else:
            return f"Объект инфраструктуры: {amenity_type}"
    
    elif place_type == "historic":
        historic_type = tags.get("historic", "")
        return f"Исторический объект: {historic_type}"
    
    elif place_type == "tourism":
        tourism_type = tags.get("tourism", "")
        return f"Туристический объект: {tourism_type}"
    
    elif place_type == "shop":
        shop_type = tags.get("shop", "")
        return f"Магазин: {shop_type}"
    
    return "Интересное место"

async def get_address_details(latitude: float, longitude: float, lang: str = "ru") -> Dict:
    """
    Получает детальную информацию об адресе через Nominatim.
    """
    headers = {"User-Agent": "TelegramLocationBot/1.0"}
    url = f"{OSM_ENDPOINT}/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "accept-language": f"{lang},en",
        "zoom": 18,
        "addressdetails": 1
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data
    except aiohttp.ClientError as e:
        logging.error(f"Error fetching address details: {e}")
        return {} 