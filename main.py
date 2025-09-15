from agent import RecipeAgent

def main():
    """
    Main entry point of the application. Interacts with the user.
    """
    # Create our agent
    agent = RecipeAgent()
    print("-" * 30)

    while True:
        user_input = input("What would you like to cook? (e.g., 'I want to make tomato soup and pasta') ('exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break

        # Use the agent to extract dish names from the natural language input
        print("Understanding your request...")
        dish_names = agent.extract_dish_names(user_input)

        if not dish_names:
            print("Sorry, I couldn't find any dish names in your request. Please try again.")
            print("-" * 30)
            continue

        print(f"Found dishes: {', '.join(dish_names)}. Fetching ingredients...")

        for dish_name in dish_names:
            response = agent.get_ingredients(dish_name)
            print(response)
            print("-" * 30)

if __name__ == "__main__":
    main()