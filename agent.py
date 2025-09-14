from tools import get_ingredients_for_dish

class RecipeAgent:
    """
    An agent designed to provide information about food recipes.
    """
    def __init__(self):
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