from agent import OrchestratorAgent, ShoppingListConsolidatorAgent
from translator import translate_ingredient_list

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
                # 1. Translate items using the robust translator module.
                # Specify 'tr' as the source language for accurate translation of user input.
                translated_items = translate_ingredient_list(items_to_remove_raw, source='tr')
                # 2. Normalize to lowercase for comparison. The shopping list is already all lowercase.
                normalized_items_to_remove = {item.lower().strip() for item in translated_items}
                shopping_list = [item for item in shopping_list if item not in normalized_items_to_remove]

            # Ask to add items
            to_add_input = input("Enter items to ADD (comma-separated, e.g., 'olive oil, pepper') or press Enter to skip: ").strip()
            if to_add_input:
                items_to_add_raw = [item.strip() for item in to_add_input.split(',') if item.strip()]
                # 1. Translate using the robust translator, specifying 'tr' as the source.
                translated_items = translate_ingredient_list(items_to_add_raw, source='tr')
                # 2. Normalize to lowercase before adding.
                translated_items_to_add = [item.lower().strip() for item in translated_items]
                for item in translated_items_to_add:
                    if item not in shopping_list:
                        shopping_list.append(item)
                shopping_list.sort()  # Re-sort after adding

            # Ask if user is done
            done_input = input("Are you finished with your list? (yes/Enter to confirm): ").lower().strip()
            if done_input == 'yes' or not done_input:
                break
        
        print_shopping_list("✅ Your Final Shopping List ✅", shopping_list)
        print("Happy cooking!")
        print("="*50)

if __name__ == "__main__":
    main()