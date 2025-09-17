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
        print("Recipe Assistant started. How can I help you?")

    def run_workflow(self, user_input: str) -> tuple[list[str], dict[str, str]]:
        """
        Runs the full workflow: identify dishes, then find ingredients for each in parallel.
        """
        print("Understanding your request...")
        dish_names = self.dish_identifier.run(user_input)

        if not dish_names:
            return [], {}

        print(f"Found dishes: {', '.join(dish_names)}. Fetching ingredients...")
        results = {}
        # Use a thread pool to fetch ingredients in parallel, a key benefit of this structure.
        with ThreadPoolExecutor(max_workers=len(dish_names) or 1) as executor:
            future_to_dish = {executor.submit(self.recipe_scout.run, name): name for name in dish_names}
            for future in as_completed(future_to_dish):
                dish_name = future_to_dish[future]
                try:
                    results[dish_name] = future.result()
                except Exception as exc:
                    results[dish_name] = f"An error occurred while fetching ingredients for '{dish_name}': {exc}"
        return dish_names, results
