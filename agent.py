from tools import get_ingredients_for_dish # This is now a LangChain tool
import sys
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

def _is_numeric(s):
    """Check if a string can be converted to a float."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False

class ShoppingListConsolidatorAgent:
    """An agent that consolidates multiple ingredient lists into a single, unique shopping list."""
    def run(self, all_ingredients: dict[str, list[dict]]) -> list[str]:
        """
        Takes a dictionary of dish-to-ingredient-lists and returns a single, formatted shopping list.
        It consolidates items by name and attempts to sum quantities if units are compatible.
        """
        consolidated_dict = {}
        for dish, ingredients in all_ingredients.items():
            # Skip if the list contains an error message or is empty
            if not ingredients or isinstance(ingredients[0], str): # Error messages are strings
                continue
            
            for ingredient in ingredients:
                name = ingredient.get("name", "").lower().strip()
                if not name:
                    continue
                
                quantity = ingredient.get("quantity", "")
                unit = ingredient.get("unit", "").lower().strip()

                if name not in consolidated_dict:
                    consolidated_dict[name] = {"quantities": [], "units": set()}

                if _is_numeric(quantity) and unit:
                    consolidated_dict[name]["quantities"].append(float(quantity))
                    consolidated_dict[name]["units"].add(unit)
                elif quantity: # Non-numeric quantity like "to taste" or "a pinch"
                    consolidated_dict[name]["quantities"].append(quantity)
        
        # Format the final list
        final_list = []
        for name, data in sorted(consolidated_dict.items()):
            if len(data["units"]) == 1 and all(_is_numeric(q) for q in data["quantities"]):
                total_quantity = sum(q for q in data["quantities"] if _is_numeric(q))
                unit = list(data["units"])[0]
                final_list.append(f"{total_quantity} {unit} {name.capitalize()}")
            else: # If units are mixed or quantities are not numeric, just list the name
                final_list.append(name.capitalize())

        return sorted(final_list)

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
- 'suggest_dish_from_ingredients': The user is listing ingredients they have and wants a dish suggestion based on them. Examples: "I have chicken, potatoes, and tomatoes, what can I make?", "what to cook with onion and ground beef?".
- 'other': The request does not fit any of the above categories.

You must return only one of the category names: 'provide_dishes', 'request_ideas', 'suggest_dish_from_ingredients', or 'other'.""",
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

        # --- Create Ingredient Extractor from Prompt Chain ---
        ingredient_extractor_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert at identifying food ingredients from a user's message.
Your task is to extract only the ingredient names from the user's request.
Strictly follow these rules:
1. Only identify food ingredients (e.g., "chicken", "potato", "onion").
2. Ignore quantities or other non-ingredient words.
3. Return the ingredient names as a comma-separated list.
4. If no ingredients can be found, return an empty string.""",
                ),
                ("human", "User's request: \"{user_input}\"\n\nIngredients:"),
            ]
        )
        self.ingredient_extractor_chain = ingredient_extractor_prompt | self.llm | StrOutputParser()

        # --- Create Dish Suggester from Ingredients Chain ---
        dish_suggester_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a creative chef. Your task is to suggest a single, specific, and cookable dish name based on a list of ingredients provided.
The suggested dish should be a good fit for the given ingredients, but it does not need to use all of them.
Follow these rules:
1. Read the list of ingredients.
2. Suggest one single, common, and specific dish name. For example, if the ingredients are "ground beef, potatoes, onion", a good suggestion is "Shepherd's Pie".
3. Return only the dish name. Do not add any other text, explanations, or greetings. For example: "Baked Chicken with Potatoes".""",
                ),
                ("human", "Ingredients: \"{ingredients}\"\n\nSuggested dish name:"),
            ]
        )
        self.dish_suggester_chain = dish_suggester_prompt | self.llm | StrOutputParser()

    def get_ingredients(self, dish_names: list[str]) -> dict[str, list[dict]]:
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
                error_message = f"An error occurred: {exc}"
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

        elif intent == 'suggest_dish_from_ingredients':
            # 2c. Extract ingredients from the user's prompt
            print("Identifying ingredients from your message...")
            ingredients_str = self.ingredient_extractor_chain.invoke({"user_input": user_input})
            if not ingredients_str.strip():
                return {"status": "error", "message": "I couldn't identify any ingredients in your message. Please list the ingredients you have."}
            
            # 3c. Suggest a dish based on the extracted ingredients
            print(f"Thinking of a dish for: {ingredients_str}...")
            suggested_dish = self.dish_suggester_chain.invoke({"ingredients": ingredients_str})
            if not suggested_dish.strip():
                return {"status": "error", "message": "Sorry, I couldn't think of a dish with those ingredients."}

            return {"status": "dish_suggestion_provided", "suggestion": suggested_dish.strip()}

        else: # 'other' or unexpected
            return {"status": "clarification_needed", "message": "I can help you find ingredients for specific dishes or suggest meal ideas. Please tell me what you'd like to cook!"}
