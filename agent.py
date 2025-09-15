from tools import get_ingredients_for_dish
import ollama
import sys

class RecipeAgent:
    """
    An agent designed to provide information about food recipes.
    """
    def __init__(self):
        """
        Initializes the agent and checks for the Ollama service.
        """
        self.model = 'gemma3' # You can change this to your preferred Ollama model, e.g., 'gemma'
        try:
            # Check if the Ollama service is running
            ollama.list()
        except ollama.ResponseError as e:
            print("Error: Could not connect to the Ollama service.")
            print(f"Please make sure Ollama is running. Details: {e.error}")
            sys.exit(1) # Exit if Ollama is not available

        print("Recipe Assistant started. How can I help you?")

    def get_ingredients(self, dish_name: str) -> str:
        """
        Runs the relevant tool to find the ingredients for the user's requested dish.
        """
        print(f"Searching for ingredients for '{dish_name}'...")
        # The agent decides which tool to use here.
        # In this simple example, we directly call the ingredient finding tool.
        result = get_ingredients_for_dish(dish_name)
        return result
    
    def extract_dish_names(self, text: str) -> list[str]:
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
