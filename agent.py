from tools import get_ingredients_for_dish # This is now a LangChain tool
import sys
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

def create_dish_identifier_chain(llm):
    """Creates a LangChain chain to identify dish names from text."""
    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are an expert kitchen assistant. Your task is to identify and extract the dish names from the user's request.
Strictly follow these rules:
1. Only identify specific, cookable dish names (e.g., "tomato soup", "creamy pasta", "menemen").
2. Do not extract general food categories or single ingredients (e.g., "pasta", "salad", "tomato").
3. Return the dish names as a comma-separated list.
4. If no specific dish name can be found, return an empty string.""",
            ),
            ("human", "User's request: \"{user_input}\"\n\nDish names:"),
        ]
    )
    return prompt_template | llm | StrOutputParser()

class ShoppingListConsolidatorAgent:
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

class OrchestratorAgent:
    """
    The orchestrator agent that runs a workflow using LangChain chains and tools.
    """
    def __init__(self, model='gemma3'):
        try:
            # Use ChatOllama for conversational models
            self.llm = ChatOllama(model=model)
            self.llm.invoke("Test connection") # Check for Ollama service
        except Exception as e:
            print(f"Error: Could not connect to the Ollama service. Is it running? Details: {e}")
            sys.exit(1)

        # The orchestrator holds instances of the specialized chains it needs.
        self.dish_identifier_chain = create_dish_identifier_chain(self.llm)
        print("Recipe Assistant (LangChain Edition) started. How can I help you?")

    def run(self, user_input: str) -> tuple[list[str], dict[str, list[str]]]:
        """
        Runs the full workflow using LangChain:
        1. Identify dishes from user input.
        2. For each dish, use the `get_ingredients_for_dish` tool to find,
           scrape, and clean a list of ingredients.
        3. Return the identified dishes and a dictionary of results.
        """
        print("Understanding your request...")
        # 1. Identify dishes
        dish_names_str = self.dish_identifier_chain.invoke({"user_input": user_input})
        
        if not dish_names_str:
            return [], {}
        
        dish_names = [name.strip() for name in dish_names_str.split(',') if name.strip()]
        if not dish_names:
            return [], {}

        print(f"Found dishes: {', '.join(dish_names)}. Fetching ingredients and creating shopping lists...")
        
        results = {}
        # For each dish, invoke the tool which now handles the entire process
        # of finding and cleaning ingredients.
        for dish_name in dish_names:
            try:
                # The tool now returns a clean list of ingredients directly.
                clean_ingredients = get_ingredients_for_dish.invoke(dish_name)
                results[dish_name] = clean_ingredients

            except Exception as exc:
                # If the tool raises an exception (e.g., recipe not found),
                # we catch it and store the error message.
                error_message = str(exc)
                print(f"An error occurred while processing '{dish_name}': {error_message}")
                results[dish_name] = [error_message]

        return dish_names, results
