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

def create_ingredient_extractor_chain(llm):
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
            (
                "human",
                'Text to process:\n"{ingredient_text}"\n\nComma-separated ingredient names:',
            ),
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
        self.ingredient_extractor_chain = create_ingredient_extractor_chain(self.llm)
        print("Recipe Assistant (LangChain Edition) started. How can I help you?")

    def run(self, user_input: str) -> tuple[list[str], dict[str, list[str]]]:
        """
        Runs the full workflow using LangChain:
        1. Identify dishes from user input.
        2. In parallel, for each dish:
           a. Find ingredients using the `get_ingredients_for_dish` tool.
           b. Extract clean ingredient names from the tool's output.
        3. Return the identified dishes and the structured results.
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
        # Although LCEL supports parallel execution, a simple loop with individual invokes
        # gives us clearer error handling per dish, similar to the original ThreadPoolExecutor logic.
        for dish_name in dish_names:
            try:
                # The tool's output (raw text)
                raw_text = get_ingredients_for_dish.invoke(dish_name)
                
                # Check for errors from the tool
                if "error occurred" in raw_text or "not be clearly found" in raw_text or "No recipe found" in raw_text:
                    results[dish_name] = [raw_text] # Pass error as a list item
                    continue

                # The extractor chain's output (comma-separated string)
                extracted_str = self.ingredient_extractor_chain.invoke({"ingredient_text": raw_text})
                
                # Convert to list
                clean_ingredients = [ing.strip() for ing in extracted_str.split(',') if ing.strip()]
                results[dish_name] = clean_ingredients

            except Exception as exc:
                error_message = f"An error occurred while processing '{dish_name}': {exc}"
                print(error_message)
                results[dish_name] = [error_message]

        return dish_names, results
