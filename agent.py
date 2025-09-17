from tools import get_ingredients_for_dish
import ollama
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

class Agent:
    """
    Base class for all agents. It's a good practice for organization and potential shared functionality.
    """
    def __init__(self, model='gemma3'):
        """
        Initializes the agent with a specific model.
        """
        self.model = model

class DishIdentifierAgent(Agent):
    """An agent that specializes in identifying dish names from text using an LLM."""
    def run(self, text: str) -> list[str]:
        """
        Uses an Ollama-based LLM to extract dish names from natural language text.
        """
        prompt = f"""
        You are an expert kitchen assistant. Your task is to identify and extract the dish names from the user's request.

        Strictly follow these rules:
        1. Only identify specific, cookable dish names (e.g., "tomato soup", "creamy pasta", "menemen").
        2. Do not extract general food categories or single ingredients (e.g., "pasta", "salad", "tomato").
        3. Return the dish names as a comma-separated list.
        4. If no specific dish name can be found, return an empty string.

        User's request: "{text}"
        
        Dish names:
        """
        
        try:
            # Call Ollama to get the response
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                stream=False # We want the full response at once
            )
            extracted_text = response['response'].strip()
            
            if not extracted_text:
                return []
            
            # Convert the comma-separated string to a list and strip whitespace from each element
            dish_names = [name.strip() for name in extracted_text.split(',')]
            return [name for name in dish_names if name] # Clean up any potential empty elements
            
        except Exception as e:
            print(f"An error occurred while extracting dish names: {e}")
            return []

class RecipeScoutAgent(Agent):
    """An agent that finds ingredients for a given dish by using tools."""
    def run(self, dish_name: str) -> str:
        """
        Runs the relevant tool to find the ingredients for the user's requested dish.
        """
        print(f"Searching for ingredients for '{dish_name}'...")
        # This agent's responsibility is to call the right tool.
        # For now, it directly calls the ingredient finding tool.
        result = get_ingredients_for_dish(dish_name)
        return result

class IngredientExtractorAgent(Agent):
    """An agent that extracts a clean list of ingredient names from a block of text."""
    def run(self, ingredient_text: str) -> list[str]:
        """
        Uses an LLM to extract only the core ingredient names from a formatted text block.
        """
        # If the text is not a valid ingredient list, don't process it.
        if not ingredient_text or "ingredients found for" not in ingredient_text:
            return []

        prompt = f"""
        You are a data extraction specialist. Your task is to extract only the core ingredient names from the provided text.

        Follow these rules precisely:
        1. Read the text which contains a list of ingredients.
        2. For each line, identify the main food item.
        3. Ignore quantities (e.g., "100 g", "2-3 tbsp", "1 cup").
        4. Ignore preparation instructions (e.g., "finely chopped", "diced", "skin off").
        5. Ignore packaging details (e.g., "(28-ounce) can").
        6. Return only the clean ingredient names as a comma-separated list. For example, for "- 1 (28-ounce) can whole San Marzano tomatoes", you should extract "San Marzano tomatoes". For "- 100 g Carrot", you should extract "Carrot".

        Text to process:
        "{ingredient_text}"

        Comma-separated ingredient names:
        """
        try:
            response = ollama.generate(model=self.model, prompt=prompt, stream=False)
            extracted_text = response['response'].strip()
            if not extracted_text:
                return []
            
            ingredients = [name.strip() for name in extracted_text.split(',')]
            return [ing for ing in ingredients if ing] # Filter out empty strings

        except Exception as e:
            print(f"An error occurred during ingredient extraction: {e}")
            return []

class ShoppingListConsolidatorAgent(Agent):
    """An agent that consolidates multiple ingredient lists into a single, unique shopping list."""
    def run(self, all_ingredients: dict[str, list[str]]) -> list[str]:
        """
        Takes a dictionary of dish-to-ingredient-lists and returns a single, alphabetized, unique list.
        It performs basic normalization (lowercase, strip) to merge similar items.
        """
        consolidated_set = set()
        for dish, ingredients in all_ingredients.items():
            # Skip if the list contains an error message or is empty
            if not ingredients or ("error occurred" in ingredients[0] or "not be clearly found" in ingredients[0] or "No recipe found" in ingredients[0]):
                continue
            
            for ingredient in ingredients:
                # Basic normalization
                normalized_ingredient = ingredient.lower().strip()
                if normalized_ingredient:
                    consolidated_set.add(normalized_ingredient)
        
        # Return a sorted list for consistent and readable output
        return sorted(list(consolidated_set))

class ManagerAgent(Agent):
    """
    The manager agent that orchestrates the workflow by coordinating other agents.
    """
    def __init__(self, model='gemma3'):
        super().__init__(model)
        try:
            ollama.list() # Check for Ollama service
        except ollama.ResponseError as e:
            print(f"Error: Could not connect to the Ollama service. Details: {e.error}")
            sys.exit(1)

        # The manager holds instances of the specialized agents it needs to delegate tasks to.
        self.dish_identifier = DishIdentifierAgent(model=self.model)
        self.recipe_scout = RecipeScoutAgent(model=self.model)
        self.ingredient_extractor = IngredientExtractorAgent(model=self.model)
        print("Recipe Assistant started. How can I help you?")

    def run_workflow(self, user_input: str) -> tuple[list[str], dict[str, list[str]]]:
        """
        Runs the full workflow: identify dishes, find ingredients, then extract clean ingredient names.
        """
        print("Understanding your request...")
        dish_names = self.dish_identifier.run(user_input)

        if not dish_names:
            return [], {}

        print(f"Found dishes: {', '.join(dish_names)}. Fetching ingredients and creating shopping lists...")
        results = {}
        # Use a thread pool to fetch ingredients in parallel, a key benefit of this structure.
        with ThreadPoolExecutor(max_workers=len(dish_names) or 1) as executor:
            future_to_dish = {executor.submit(self.recipe_scout.run, name): name for name in dish_names}
            for future in as_completed(future_to_dish):
                dish_name = future_to_dish[future]
                try:
                    raw_text = future.result()
                    # Check if the scout agent returned an error/failure message
                    if "error occurred" in raw_text or "not be clearly found" in raw_text or "No recipe found" in raw_text:
                        results[dish_name] = [raw_text] # Pass error as a list item
                    else:
                        # If successful, call the new extractor agent to get a clean list
                        clean_ingredients = self.ingredient_extractor.run(raw_text)
                        results[dish_name] = clean_ingredients
                except Exception as exc:
                    error_message = f"An error occurred while processing '{dish_name}': {exc}"
                    results[dish_name] = [error_message]
        return dish_names, results
