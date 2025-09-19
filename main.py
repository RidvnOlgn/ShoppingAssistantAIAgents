from agent import OrchestratorAgent, ShoppingListConsolidatorAgent
from deep_translator import GoogleTranslator

def print_shopping_list(title: str, shopping_list: list[str]):
    """Helper function to print the shopping list neatly."""
    print("\n" + "-" * 40)
    print(title)
    print("-" * 40)
    if not shopping_list:
        print("The list is empty.")
    else:
        for i, item in enumerate(shopping_list, 1):
            # Capitalize the first letter for better readability
            print(f"{i}. {item.capitalize()}")
    print("-" * 40)

def translate_item_list(items: list[str]) -> list[str]:
    """Translates a list of item strings to English and normalizes them."""
    if not items:
        return []
    try:
        # deep-translator can handle a list of strings directly
        # Using translate_batch is more efficient for multiple items.
        translated_items = GoogleTranslator(source='auto', target='en').translate_batch(items)
        # The result might contain None for failed translations, so filter them and normalize.
        return [item.lower().strip() for item in translated_items if item]
    except Exception as e:
        print(f"\nWarning: Could not translate items: {e}. Using original items.")
        # Fallback to original items, but still normalize them.
        return [item.lower().strip() for item in items]

def main():
    """
    Main entry point of the application. Interacts with the user.
    """
    # Create our orchestrator agent, which will coordinate the work using LangChain.
    orchestrator = OrchestratorAgent()
    consolidator = ShoppingListConsolidatorAgent()
    print("-" * 30)

    while True:
        user_input = input("\nWhat would you like to cook? (e.g., 'I want to make tomato soup and grilled meatballs') ('exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break

        # Use the orchestrator agent to run the entire workflow.
        # It handles delegation to other specialized agents.
        dish_names, responses = orchestrator.run(user_input)

        if not dish_names:
            print("Sorry, I couldn't find any dish names in your request. Please try again.")
            continue

        # --- Interactive Shopping List Creation ---

        # 1. Show individual recipe results for clarity
        print("\n" + "="*50)
        print("RECIPE RESULTS")
        print("="*50)
        has_successful_recipes = False
        for dish_name in dish_names:
            ingredient_list = responses.get(dish_name)
            if ingredient_list:
                if "error occurred" in ingredient_list[0] or "not be clearly found" in ingredient_list[0] or "No recipe found" in ingredient_list[0]:
                    print(f"\nCould not get ingredients for '{dish_name}': {ingredient_list[0]}")
                else:
                    has_successful_recipes = True
                    print(f"\nIngredients for '{dish_name}':")
                    for item in ingredient_list:
                        print(f"- {item}")
            else:
                print(f"\nCould not get ingredients for '{dish_name}': Unknown error.")
        
        if not has_successful_recipes:
             print("\nCould not generate a shopping list as no recipes were successfully found.")
             print("="*50)
             continue

        # 2. Consolidate into a single shopping list
        shopping_list = consolidator.run(responses)

        # 3. Interactive modification loop
        while True:
            print_shopping_list("🛒 Your Consolidated Shopping List 🛒", shopping_list)

            # Ask to remove items
            to_remove_input = input("Enter items to REMOVE (comma-separated, e.g., 'onion, garlic') or press Enter to skip: ").strip()
            if to_remove_input:
                items_to_remove_raw = [item.strip() for item in to_remove_input.split(',')]
                # Translate items before removing
                translated_items_to_remove = set(translate_item_list(items_to_remove_raw))
                shopping_list = [item for item in shopping_list if item not in translated_items_to_remove]

            # Ask to add items
            to_add_input = input("Enter items to ADD (comma-separated, e.g., 'olive oil, pepper') or press Enter to skip: ").strip()
            if to_add_input:
                items_to_add_raw = [item.strip() for item in to_add_input.split(',') if item.strip()]
                # Translate items before adding
                translated_items_to_add = translate_item_list(items_to_add_raw)
                for item in translated_items_to_add:
                    if item not in shopping_list:
                        shopping_list.append(item)
                shopping_list.sort()  # Re-sort after adding

            # Ask if user is done
            done_input = input("Are you finished with your list? (yes/no): ").lower().strip()
            if done_input == 'yes':
                break
        
        print_shopping_list("✅ Your Final Shopping List ✅", shopping_list)
        print("Happy cooking!")
        print("="*50)

if __name__ == "__main__":
    main()