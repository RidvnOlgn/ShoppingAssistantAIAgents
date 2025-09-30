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
            if not ingredient_list:
                print(f"\nCould not get ingredients for '{dish_name}': Unknown error.")
                continue

            # Check if the result is an error (string) or a success (list of dicts)
            if isinstance(ingredient_list[0], str) and "error occurred" in ingredient_list[0]:
                print(f"\nCould not get ingredients for '{dish_name}': {ingredient_list[0]}")
            else:
                has_successful_recipes = True
                print(f"\nIngredients for '{dish_name}':")
                for item in ingredient_list:
                    # Format the output string: "1 cup flour" or "Salt"
                    print(f"- {' '.join(filter(None, [item.get('quantity', ''), item.get('unit', ''), item.get('name', '')]))}")
        
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
            to_remove_input = input("Enter ingredient NAMES to REMOVE (e.g., 'onion, garlic') or press Enter: ").strip().lower()
            if to_remove_input:
                items_to_remove = {item.strip() for item in to_remove_input.split(',')}
                # Filter the list, removing items whose name matches
                shopping_list = [
                    item for item in shopping_list 
                    if not any(name_to_remove in item.lower() for name_to_remove in items_to_remove)
                ]

            # Ask to add items
            to_add_input = input("Enter items to ADD (e.g., 'Olive oil, 1 box pasta') or press Enter: ").strip()
            if to_add_input:
                # For simplicity, we add the user's string directly.
                # A more advanced version could parse this input too.
                items_to_add_raw = [item.strip() for item in to_add_input.split(',')]
                translated_items_to_add = translate_ingredient_list(items_to_add_raw, source='tr')

                for item in translated_items_to_add:
                    # Capitalize for consistency and add
                    shopping_list.append(item.capitalize())
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