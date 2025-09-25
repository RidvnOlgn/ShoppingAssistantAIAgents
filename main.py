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
        user_input = input("\nWhat would you like to cook? (e.g., 'tomato soup', 'ideas for dinner', or 'I have chicken, potatoes') ('exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break

        # Step 1: Run the initial orchestrator step to get intent and either results or suggestions
        response_data = orchestrator.run(user_input)
        status = response_data.get("status")

        dish_names = []
        responses = {}

        # Step 2: Handle the response based on its status
        if status == "suggestions_provided":
            suggestions = response_data.get("suggestions", [])
            print("\nHere are a few ideas for you:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion.capitalize()}")
            
            choice_input = input("\nWhich of these would you like to make? Enter numbers (e.g., '1, 3'), 'all', or 'none': ").strip().lower()

            if choice_input == 'none' or not choice_input:
                print("No problem! Let's try something else.")
                continue
            
            chosen_dishes = []
            if choice_input == 'all':
                chosen_dishes = suggestions
            else:
                choices = [c.strip() for c in choice_input.split(',')]
                selected_indices = set()
                for choice in choices:
                    if choice.isdigit():
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(suggestions):
                                selected_indices.add(idx)
                        except ValueError:
                            pass # Ignore non-numeric parts
                
                chosen_dishes = [suggestions[i] for i in sorted(list(selected_indices))]

            if not chosen_dishes:
                print("I didn't understand your selection. Let's start over.")
                continue

            # Now that we have the user's choice, get the ingredients
            dish_names = chosen_dishes
            responses = orchestrator.get_ingredients(dish_names)
        
        elif status == "ingredients_found":
            # This is the direct path where the user provided dishes
            dish_names = response_data.get("dishes", [])
            responses = response_data.get("results", {})

        elif status == "dish_suggestion_provided":
            suggestion = response_data.get("suggestion")
            print(f"\nBased on your ingredients, how about making: {suggestion.capitalize()}?")
            
            choice_input = input("Would you like to get the ingredient list for this? (yes/no): ").strip().lower()

            if choice_input in ['yes', 'y']:
                # Get ingredients for the single suggested dish
                dish_names = [suggestion]
                responses = orchestrator.get_ingredients(dish_names)
            elif choice_input in ['no', 'n']:
                print("No problem! Let's try something else.")
                continue
            else:
                print("I didn't understand your selection. Let's start over.")
                continue

        elif status in ["error", "clarification_needed"]:
            print(f"\n{response_data.get('message')}")
            continue
        
        else: # No dishes found or other unexpected status
            print("\nSorry, I couldn't process your request. Please try again.")
            continue

        # --- From this point on, the logic is the same for both paths ---
        # We have `dish_names` and `responses` populated.

        # Show individual recipe results for clarity
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
             print("="*50 + "\n")
             continue

        # Consolidate into a single shopping list
        shopping_list = consolidator.run(responses)

        # Interactive modification loop
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