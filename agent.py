from tools import get_ingredients_for_dish # This is now a LangChain tool
import sys
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

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
    The orchestrator agent that understands user intent, gets meal ideas if needed,
    and runs a workflow using LangChain chains and tools to find ingredients.
    """
    def __init__(self, model='gemma3'):
        try:
            # Use ChatOllama for conversational models
            self.llm = ChatOllama(model=model)
            self.llm.invoke("Test connection") # Check for Ollama service
        except Exception as e:
            print(f"Error: Could not connect to the Ollama service. Is it running? Details: {e}")
            sys.exit(1)

        # --- Create Intent Router Chain ---
        intent_router_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an intent classification expert. Your job is to analyze the user's request and classify it into one of the following categories:
- 'provide_dishes': The user is explicitly stating one or more specific dishes they want to cook. Examples: "I want to make tomato soup and grilled meatballs", "menemen", "carbonara".
- 'request_ideas': The user is asking for suggestions, ideas, or recommendations for meals. Examples: "What should I cook for dinner?", "Give me some ideas for a quick lunch", "I need a vegetarian recipe".
- 'other': The request is not about providing dishes or asking for ideas.

You must return only one of the category names: 'provide_dishes', 'request_ideas', or 'other'.""",
                ),
                ("human", "User's request: \"{user_input}\"\n\nIntent:"),
            ]
        )
        self.intent_router_chain = intent_router_prompt | self.llm | StrOutputParser()

        # --- Create Meal Suggester Chain ---
        meal_suggester_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a creative and helpful chef. Your task is to suggest specific, cookable dish names based on the user's request for ideas.
Follow these rules:
1. Read the user's request for meal ideas.
2. Suggest 2-3 specific and popular dish names that fit the request.
3. Return only the dish names as a comma-separated list. For example: "Spaghetti Carbonara, Chicken Alfredo, Mushroom Risotto".
4. Do not add any other text, explanations, or greetings.""",
                ),
                ("human", "User's request: \"{user_input}\"\n\nSuggested dish names:"),
            ]
        )
        self.meal_suggester_chain = meal_suggester_prompt | self.llm | StrOutputParser()

        # --- Create Dish Identifier Chain (existing) ---
        dish_identifier_prompt = ChatPromptTemplate.from_messages(
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
        # The orchestrator holds instances of the specialized chains it needs.
        self.dish_identifier_chain = dish_identifier_prompt | self.llm | StrOutputParser()
        print("Recipe Assistant (LangChain Edition) started. How can I help you?")

    def get_ingredients(self, dish_names: list[str]) -> dict[str, list[str]]:
        """
        For a given list of dish names, finds ingredients for each.
        This is the core worker function that calls the ingredient tool.
        """
        print(f"Fetching ingredients for: {', '.join(dish_names)}...")
        
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
        return results

    def run(self, user_input: str) -> dict:
        """
        Runs the initial step of the workflow:
        1. Determine user intent (wants ideas vs. has specific dishes).
        2. If ideas are requested, returns suggestions for the user to choose from.
        3. If dishes are provided, fetches ingredients and returns them directly.
        Returns a dictionary with a 'status' and relevant data.
        """
        print("Understanding your request...")
        # 1. Determine user intent
        intent = self.intent_router_chain.invoke({"user_input": user_input}).strip()
        print(f"User intent identified as: '{intent}'")

        if intent == 'provide_dishes':
            # 2a. Identify dishes from user input
            dish_names_str = self.dish_identifier_chain.invoke({"user_input": user_input})
            dish_names = [name.strip() for name in dish_names_str.split(',') if name.strip()]
            if not dish_names:
                return {"status": "error", "message": "Sorry, I couldn't find any dish names in your request. Please try again."}
            
            # 3a. Get ingredients for the identified dishes
            results = self.get_ingredients(dish_names)
            return {"status": "ingredients_found", "dishes": dish_names, "results": results}

        elif intent == 'request_ideas':
            # 2b. Generate dish ideas and return them for user confirmation
            print("Generating some meal ideas for you...")
            dish_names_str = self.meal_suggester_chain.invoke({"user_input": user_input})
            dish_names = [name.strip() for name in dish_names_str.split(',') if name.strip()]
            if not dish_names:
                return {"status": "error", "message": "Sorry, I couldn't come up with any ideas for that."}
            
            return {"status": "suggestions_provided", "suggestions": dish_names}

        else: # 'other' or unexpected
            return {"status": "clarification_needed", "message": "I can help you find ingredients for specific dishes or suggest meal ideas. Please tell me what you'd like to cook!"}
