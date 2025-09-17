import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
import json
import re
import os
from translator import translate_ingredient_list
from deep_translator import GoogleTranslator
import ollama

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

def _parse_ingredients_structured(ingredient_strings: list[str]) -> list[dict]:
    """
    Uses an LLM to parse a list of ingredient strings into structured data (quantity, name).
    """
    # Create a string representation of the list for the prompt
    prompt_list = "\n".join(f"- {s}" for s in ingredient_strings)

    prompt = f"""
    You are an expert data parser. Your task is to parse each line of ingredient text into a structured JSON object containing 'quantity' and 'name'.

    Follow these rules precisely:
    1. For each line, separate the quantity/measurement from the ingredient name.
    2. The 'quantity' field should include the number and the unit (e.g., "100 g", "2-3 tbsp", "1 (28-ounce) can"). If there is no quantity, this field should be an empty string.
    3. The 'name' field should contain the rest of the string, which is the core ingredient name, including any preparation notes (e.g., "finely chopped").
    4. Return the result as a JSON array of objects. Do not return any other text, just the JSON.

    Example Input:
    - 1 (28-ounce) can whole San Marzano tomatoes
    - Fresh basil leaves, for garnish

    Example Output:
    [
        {{"quantity": "1 (28-ounce) can", "name": "whole San Marzano tomatoes"}},
        {{"quantity": "", "name": "Fresh basil leaves, for garnish"}}
    ]

    Ingredient text to process:
    {prompt_list}

    JSON Output:
    """
    try:
        # Assuming ollama is configured and available. Using a default model.
        response = ollama.generate(model='gemma3', prompt=prompt, stream=False, format='json')
        parsed_json = json.loads(response['response'])
        
        # Basic validation and ensuring 'quantity' key exists
        if isinstance(parsed_json, list) and all(isinstance(item, dict) and 'name' in item for item in parsed_json):
            for item in parsed_json:
                item.setdefault('quantity', '')
            return parsed_json
        else:
            raise ValueError("LLM parsing did not return the expected list of dicts.")
    except Exception as e:
        print(f"Warning: An error occurred during LLM ingredient parsing: {e}. Falling back to name-only structure.")
        return [{'quantity': '', 'name': s} for s in ingredient_strings]

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
        cached_data = cache[cache_key]

        # Handle both new structured format (list of dicts) and old format (string)
        if isinstance(cached_data, list):
            # New format. Reconstruct the string for the agent chain.
            reconstructed_ingredients = []
            for item in cached_data:
                # Rebuild the line from quantity and name
                full_line = f"{item.get('quantity', '')} {item.get('name', '')}".strip()
                reconstructed_ingredients.append(full_line)
            
            formatted_ingredients = "\n".join([f"- {item}" for item in reconstructed_ingredients])
            return f"Possible ingredients found for '{translated_dish_name}':\n{formatted_ingredients}"
        
        elif isinstance(cached_data, str):
            # Old format, just return it. It will be updated on the next non-cached run.
            return cached_data
        
        # If format is unknown, treat as a cache miss
        print(f"Warning: Unknown cache format for '{translated_dish_name}'. Refetching.")

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
                    
                    # Parse the raw ingredient list into structured data
                    structured_ingredients = _parse_ingredients_structured(translated_ingredients)

                    # Save the new structured format to the cache
                    cache[cache_key] = structured_ingredients
                    _save_cache(cache)

                    # For backward compatibility, reconstruct the original string format to return to the agent.
                    formatted_ingredients = "\n".join([f"- {item}" for item in translated_ingredients])
                    success_result = f"Possible ingredients found for '{translated_dish_name}':\n{formatted_ingredients}"
                    return success_result

            # If the loop finishes and no result is found from any site
            return f"A search was performed for '{translated_dish_name}', but an ingredient list could not be clearly found. Please try a more specific dish name."
    except Exception as e:
        return f"An error occurred with the search service: {e}"