import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
import json
import re
import os
from translator import translate_ingredient_list
from deep_translator import GoogleTranslator

CACHE_FILE = "recipe_cache.json"

def _load_cache() -> dict:
    """Loads the cache file."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            # If the file is empty, return an empty dictionary
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_cache(cache: dict):
    """Saves the cache to a file."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Warning: Could not write to cache file: {e}")
        
def _find_ingredients_from_url(url: str) -> list[str] | None:
    """
    Tries to scrape the ingredient list from a given URL.
    It prioritizes structured data (JSON-LD, Microdata) as the most reliable methods,
    then uses smarter HTML tag analysis.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Method 1: Search for JSON-LD structured data (Most reliable)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string.strip())
                # Data can sometimes be in a list
                if isinstance(data, list):
                    data_list = data
                else:
                    data_list = [data]

                for item in data_list:
                    if not isinstance(item, dict):
                        continue
                    # Check for nested schemas in @graph
                    graph = item.get('@graph', [])
                    for node in graph:
                        if isinstance(node, dict) and node.get('@type') == 'Recipe' and 'recipeIngredient' in node:
                            print(f"Info: Structured data (JSON-LD) found: {url}")
                            return [ing for ing in node['recipeIngredient'] if ing.strip()]

                    # Check for Recipe schema at the main level
                    if isinstance(item, dict) and item.get('@type') == 'Recipe' and 'recipeIngredient' in item:
                        print(f"Info: Structured data (JSON-LD) found: {url}")
                        return [ing for ing in item['recipeIngredient'] if ing.strip()]
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        # Method 2: Search for Microdata structured data (Very reliable)
        recipe_scope = soup.find(itemtype=lambda x: x and 'schema.org/Recipe' in x)
        if recipe_scope:
            ingredients_microdata = recipe_scope.find_all(itemprop='recipeIngredient')
            if ingredients_microdata:
                 print(f"Info: Structured data (Microdata) found: {url}")
                 return [item.get_text(strip=True) for item in ingredients_microdata if item.get_text(strip=True)]

        # Method 3: Heading and following list (Quite reliable)
        headings = soup.find_all(['h2', 'h3', 'h4'], string=re.compile(r'ingredients', re.I))
        for heading in headings:
            for sibling in heading.find_next_siblings():
                if sibling.name in ['ul', 'ol']:
                    items = sibling.find_all('li')
                    if len(items) > 1:
                        print(f"Info: List found based on heading: {url}")
                        return [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
                    break
                if sibling.name and sibling.name.startswith('h'):
                    break

        # Method 4: Search by generic class/id names (Fallback)
        keywords = ['ingredient']
        for keyword in keywords:
            # Prioritize more specific class names
            for selector in [f'[class*="{keyword}s-list"]', f'[class*="{keyword}-list"]', f'[id*="{keyword}s-list"]', f'[id*="{keyword}-list"]']:
                ingredient_sections = soup.select(selector)
                for section in ingredient_sections:
                    items = section.find_all('li')
                    if len(items) > 1:
                        print(f"Info: Possible ingredient list (CSS Selector) found: {url}")
                        return [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
        return None
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not reach {url}: {e}")
        return None
    except Exception as e:
        print(f"Warning: An error occurred while processing page '{url}': {e}")
        return None

def get_ingredients_for_dish(dish_name: str) -> str:
    """
    Searches the internet for ingredients for a given dish name.
    Translates the dish name and ingredients to English before caching.
    Caches only successful results for future use.
    """
    # Translate the dish name to English for caching and display
    try:
        # Use a new variable for the translated name
        translated_dish_name = GoogleTranslator(source='auto', target='en').translate(dish_name.strip())
        if not translated_dish_name:
            translated_dish_name = dish_name.strip() # Fallback to original if translation is empty
    except Exception as e:
        print(f"Warning: Could not translate dish name '{dish_name}': {e}. Using original name.")
        translated_dish_name = dish_name.strip()

    cache = _load_cache()
    # Use the translated name for the cache key
    cache_key = translated_dish_name.lower()

    if cache_key in cache:
        print(f"Info: '{translated_dish_name}' found in cache.")
        return cache[cache_key]

    # Search using the original dish name for better accuracy
    print(f"Info: Searching internet for '{dish_name}' (as '{translated_dish_name}') (not found in cache)...")

    try:
        with DDGS() as ddgs:
            search_query = f'"{dish_name}" ingredients recipe'
            results = list(ddgs.text(search_query, max_results=5))
            if not results:
                return f"No recipe found on the internet for '{translated_dish_name}'."

            for result in results:
                ingredients = _find_ingredients_from_url(result['href'])
                if ingredients:
                    # Translate ingredients to English before formatting and caching
                    translated_ingredients = translate_ingredient_list(ingredients)
                    formatted_ingredients = "\n".join([f"- {item}" for item in translated_ingredients])
                    # Use the translated dish name in the success message
                    success_result = f"Possible ingredients found for '{translated_dish_name}':\n{formatted_ingredients}"
                    # Save the successful result to cache and return
                    cache[cache_key] = success_result
                    _save_cache(cache)
                    return success_result

            # If the loop finishes and no result is found from any site
            return f"A search was performed for '{translated_dish_name}', but an ingredient list could not be clearly found. Please try a more specific dish name."
    except Exception as e:
        return f"An error occurred with the search service: {e}"