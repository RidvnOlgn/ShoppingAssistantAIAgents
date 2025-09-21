import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
import json
import re
import os
from translator import translate_ingredient_list
from deep_translator import GoogleTranslator
from langchain.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

CACHE_FILE = "recipe_cache.json"

# --- Global Setup for Efficiency ---
# Create LLM instances and chains once to be reused by tools.
# This is more efficient than creating them on every tool call.
_LLM_TEXT_PARSER = ChatOllama(model='gemma3')

def _get_ingredient_extractor_chain():
    """Creates a LangChain chain to extract clean ingredient names from a block of text."""
    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a data extraction specialist. Your task is to extract only the core ingredient names from the provided text.
Follow these rules precisely:
1. Read the text which contains a list of ingredients.
2. For each line, identify the main food item.
3. Ignore quantities (e.g., "100 g", "2-3 tbsp", "1 cup").
4. Ignore preparation instructions (e.g., "finely chopped", "diced", "skin off").
5. Ignore packaging details (e.g., "(28-ounce) can").
6. Return only the clean ingredient names as a comma-separated list. For example, for "- 1 (28-ounce) can whole San Marzano tomatoes", you should extract "San Marzano tomatoes". For "- 100 g Carrot", you should extract "Carrot".""",
            ),
            ("human", 'Text to process:\n"{ingredient_text}"\n\nComma-separated ingredient names:'),
        ]
    )
    return prompt_template | _LLM_TEXT_PARSER | StrOutputParser()

_INGREDIENT_EXTRACTOR_CHAIN = _get_ingredient_extractor_chain()
# --- End Global Setup ---

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

@tool
def get_ingredients_for_dish(dish_name: str) -> list[str]:
    """
    Searches the internet for ingredients for a given dish name, returning a clean list.
    It translates the dish name for caching and searches for recipes. If found,
    it scrapes, translates, and cleans the ingredient list using an LLM.
    Results are cached.
    Raises ValueError if no recipe can be found.
    """
    try:
        translated_dish_name = GoogleTranslator(source='auto', target='en').translate(dish_name.strip())
        if not translated_dish_name:
            translated_dish_name = dish_name.strip()
    except Exception as e:
        print(f"Warning: Could not translate dish name '{dish_name}': {e}. Using original name.")
        translated_dish_name = dish_name.strip()

    cache = _load_cache()
    cache_key = translated_dish_name.lower()

    if cache_key in cache:
        print(f"Info: '{translated_dish_name}' found in cache.")
        # The cache now directly stores the clean list of strings.
        cached_data = cache[cache_key]
        if isinstance(cached_data, list):
            return cached_data
        else:
            # If the cache has an old format, ignore it and refetch.
            print(f"Warning: Outdated cache format for '{translated_dish_name}'. Refetching.")

    print(f"Info: Searching internet for '{dish_name}' (as '{translated_dish_name}') (not found in cache)...")

    try:
        with DDGS() as ddgs:
            search_query = f'"{dish_name}" ingredients recipe'
            results = list(ddgs.text(search_query, max_results=5))
            if not results:
                raise ValueError(f"No recipe found on the internet for '{translated_dish_name}'.")

            for result in results:
                raw_ingredients = _find_ingredients_from_url(result['href'])
                if raw_ingredients:
                    # 1. Translate the raw list
                    translated_ingredients = translate_ingredient_list(raw_ingredients)
                    
                    # 2. Clean the translated list using the LLM chain
                    ingredient_text_block = "\n".join(translated_ingredients)
                    extracted_str = _INGREDIENT_EXTRACTOR_CHAIN.invoke({"ingredient_text": ingredient_text_block})
                    
                    clean_ingredients = [ing.strip() for ing in extracted_str.split(',') if ing.strip()]
                    
                    if not clean_ingredients:
                        # If the extractor returns nothing, try the next URL
                        continue

                    # 3. Save the clean list to cache and return
                    cache[cache_key] = clean_ingredients
                    _save_cache(cache)
                    
                    print(f"Success: Found and processed ingredients for '{translated_dish_name}'.")
                    return clean_ingredients

            # If the loop finishes and no result is found from any site
            raise ValueError(f"A search was performed for '{translated_dish_name}', but an ingredient list could not be clearly found.")
    except Exception as e:
        # Re-raise exceptions to be caught by the orchestrator
        raise e