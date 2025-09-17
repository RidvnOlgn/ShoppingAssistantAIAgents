from agent import ManagerAgent

def main():
    """
    Main entry point of the application. Interacts with the user.
    """
    # Create our manager agent, which will coordinate the work.
    manager = ManagerAgent()
    print("-" * 30)

    while True:
        user_input = input("What would you like to cook? (e.g., 'I want to make tomato soup and pasta') ('exit' to quit): ")
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

        # The manager returns all responses at once. We just need to print them.
        for dish_name in dish_names:
            # The responses dictionary contains the result for each dish.
            print(responses.get(dish_name, f"No response found for {dish_name}."))
            print("-" * 30)

if __name__ == "__main__":
    main()