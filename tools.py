import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
import re
import json
import os
from translator import translate_ingredient_list
from deep_translator import GoogleTranslator
from langchain.tools import tool
from langchain_ollama import ChatOllama
from pymongo import MongoClient
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

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
                """You are a data extraction specialist for recipes. Your task is to extract the quantity, unit, and name for each ingredient from the provided text.
Follow these rules precisely:
1. For each ingredient, extract three fields: 'quantity' (e.g., "1", "2-3", "1/2"), 'unit' (e.g., "cup", "tbsp", "g", "clove", "adet"), and 'name' (the core ingredient, e.g., "San Marzano tomatoes", "Carrot").
2. Ignore preparation instructions (e.g., "finely chopped", "diced").
3. If a quantity or unit is not present, return it as an empty string "". For example, "salt to taste" should be `{{"quantity": "", "unit": "", "name": "salt"}}`.
4. Return the result as a valid JSON array of objects.

Example Input:
- 1 (28-ounce) can whole San Marzano tomatoes
- 2-3 cloves garlic, minced
- 100 g Carrot
- Salt and pepper

Example Output:
[{{"quantity": "1", "unit": "can", "name": "whole San Marzano tomatoes"}}, {{"quantity": "2-3", "unit": "cloves", "name": "garlic"}}, {{"quantity": "100", "unit": "g", "name": "Carrot"}}, {{"quantity": "", "unit": "", "name": "Salt"}}, {{"quantity": "", "unit": "", "name": "pepper"}}]""",
            ),
            ("human", 'Text to process:\n"{ingredient_text}"\n\nJSON Output:'),
        ]
    )
    return prompt_template | _LLM_TEXT_PARSER | JsonOutputParser()

_INGREDIENT_EXTRACTOR_CHAIN = _get_ingredient_extractor_chain()
# --- End Global Setup ---

# --- Database Helper Functions ---
from pymongo.errors import ConnectionFailure, OperationFailure
def _get_db_collection():
    """Connects to MongoDB and returns the recipes collection."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("Warning: MONGO_URI environment variable not set. Database functionality is disabled.")
        return None
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # Use 'ping' to confirm a successful connection and authentication.
        client.admin.command('ping') 
        print("Info: Successfully connected to MongoDB.")
        db = client['shopping_assistant_db']
        return db['recipes']
    except OperationFailure as e:
        print(f"FATAL: MongoDB operation failed. If this is an authentication error, please check your MONGO_URI. Error: {e}")
        return None
    except ConnectionFailure as e:
        print(f"FATAL: Could not connect to MongoDB. Please ensure the server is running and MONGO_URI is correct. Error: {e}")
        return None
    except Exception as e:
        print(f"Warning: An unexpected error occurred with MongoDB. Database functionality is disabled. Error: {e}")
        return None

def _get_recipe_from_db(collection, dish_name: str) -> list[dict] | None:
    """Finds a recipe in the database by its name."""
    if collection is None: return None
    recipe = collection.find_one({"name": dish_name})
    return recipe.get("ingredients") if recipe else None

def _save_recipe_to_db(collection, dish_name: str, ingredients: list[dict]):
    """Saves a new recipe to the database."""
    if collection is None: return
    try:
        collection.update_one({"name": dish_name}, {"$set": {"ingredients": ingredients}}, upsert=True)
    except Exception as e:
        print(f"Warning: Could not save recipe '{dish_name}' to database. Error: {e}")

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
def get_ingredients_for_dish(dish_name: str) -> list[dict]:
    """
    Finds ingredients for a given dish. It first checks a persistent database,
    and if not found, searches the internet. New recipes are saved to the database.
    Raises ValueError if no recipe can be found.
    """
    try:
        translated_dish_name = GoogleTranslator(source='auto', target='en').translate(dish_name.strip())
        if not translated_dish_name:
            translated_dish_name = dish_name.strip()
        cache_key = translated_dish_name.lower()
    except Exception as e:
        print(f"Warning: Could not translate dish name '{dish_name}': {e}. Using original name.")
        cache_key = dish_name.strip().lower()

    recipes_collection = _get_db_collection()
    db_ingredients = _get_recipe_from_db(recipes_collection, cache_key)
    if db_ingredients:
        print(f"Info: '{cache_key}' found in database.")
        return db_ingredients

    print(f"Info: Searching internet for '{dish_name}' (as '{cache_key}') (not found in database)...")

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
                    extracted_json = _INGREDIENT_EXTRACTOR_CHAIN.invoke({"ingredient_text": ingredient_text_block})
                    
                    # The output is now a list of dictionaries
                    clean_ingredients = extracted_json if isinstance(extracted_json, list) else []
                    if not clean_ingredients:
                        # If the extractor returns nothing, try the next URL
                        continue

                    # 3. Save the clean list to the database and return
                    _save_recipe_to_db(recipes_collection, cache_key, clean_ingredients)
                    
                    print(f"Success: Found and processed ingredients for '{cache_key}'.")
                    return clean_ingredients

            # If the loop finishes and no result is found from any site
            raise ValueError(f"A search was performed for '{cache_key}', but an ingredient list could not be clearly found.")
    except Exception as e:
        # Re-raise exceptions to be caught by the orchestrator
        raise e

@tool
def get_price_info(item_name: str) -> dict:
    """
    Searches for an item's price on major online grocery stores (Migros, CarrefourSA).
    Returns a dictionary with prices from each store.
    """
    print(f"   -> Searching for price: {item_name}")
    prices = {}

    # --- Enhanced Cleaning Logic ---
    # Removes known units and numeric expressions to leave only the product name.
    # Example: "1.0 medium Onion" -> "Onion"
    # Example: "200.0 g ground beef" -> "ground beef"
    temp_name = item_name.lower()
    # 1. Remove numbers and dots from the beginning
    temp_name = re.sub(r'^[0-9\s.-]+', '', temp_name).strip()
    # 2. Remove known units (and their plurals)
    units_to_remove = ['cup', 'tablespoon', 'tbsp', 'teaspoon', 'tsp', 'ounce', 'oz', 'gram', 'g', 'kg', 'kilogram', 'pound', 'lb', 'clove', 'can', 'medium', 'large', 'small', 'piece']
    for unit in units_to_remove:
        # Remove singular and plural forms of the unit (with 's') along with a space
        temp_name = re.sub(r'^\b' + re.escape(unit) + r's?\b\s*', '', temp_name)
    
    clean_item_name = temp_name.strip()
    if not clean_item_name:
        clean_item_name = item_name  # If cleaning fails, use the original name

    # --- Query Enhancement ---
    # For simple, single-word items, add keywords to find a product page.
    search_query_item = clean_item_name
    if len(clean_item_name.split()) == 1:
        search_query_item = f'"{clean_item_name}" produce fresh'

    stores = {
        "Walmart": "site:walmart.com"
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    with DDGS(timeout=10) as ddgs:
        for store_name, site_filter in stores.items():
            try:
                query = f'{site_filter} {search_query_item}'
                results = list(ddgs.text(query, max_results=1, headers=headers))
                if not results:
                    prices[store_name] = "Not found"
                    continue

                url = results[0]['href']
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Potential selectors to find the price element. Includes schema.org standard.
                price_selectors = ['[itemprop="price"]', '.pr-bx-item-price', '[class*="price"]', '[id*="price"]', '.product-price', '[class*="prc-"]']
                price_text = "Not found"
                for selector in price_selectors:
                    price_element = soup.select_one(selector)
                    if price_element and re.search(r'\d', price_element.get_text()):
                        # Clean the price text to get a more direct value
                        raw_price = price_element.get_text(strip=True)
                        # Extract the part that looks like a price (e.g., $1.88 from "Now $1.88")
                        match = re.search(r'[\$€£]?\s*\d+[\.,]\d{2}', raw_price)
                        price_text = match.group(0) if match else raw_price
                        break
                prices[store_name] = price_text
            except Exception as e:
                print(f"      ! Error while getting price from {store_name}: {e}")
                prices[store_name] = "Error"
    return prices