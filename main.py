from agent import ManagerAgent

def main():
    """
    Main entry point of the application. Interacts with the user.
    """
    # Create our manager agent, which will coordinate the work.
    manager = ManagerAgent()
    print("-" * 30)

    while True:
        user_input = input("What would you like to cook? (e.g., 'I want to make tomato soup and grilled meatballs') ('exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break

        # Use the manager agent to run the entire workflow.
        # It handles delegation to other specialized agents.
        dish_names, responses = manager.run_workflow(user_input)

        if not dish_names:
            print("Sorry, I couldn't find any dish names in your request. Please try again.")
            print("-" * 30)
            continue

        # The manager now returns a list of clean ingredients for each dish.
        for dish_name in dish_names:
            ingredient_list = responses.get(dish_name)
            
            # Check if the result is a valid list and not empty
            if ingredient_list:
                # Check if the first item is an error message from a previous step
                if "error occurred" in ingredient_list[0] or "not be clearly found" in ingredient_list[0] or "No recipe found" in ingredient_list[0]:
                    print(f"For '{dish_name}': {ingredient_list[0]}")
                else:
                    print(f"Shopping list for '{dish_name}':")
                    for item in ingredient_list:
                        print(f"- {item}")
            else:
                print(f"Could not extract a shopping list for '{dish_name}'.")
            print("-" * 30)

if __name__ == "__main__":
    main()