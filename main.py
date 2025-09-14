from agent import RecipeAgent

def main():
    """
    Main entry point of the application. Interacts with the user.
    """
    # Create our agent
    agent = RecipeAgent()
    print("-" * 30)

    while True:
        user_input = input("Enter the name of the dish you want the ingredients for (type 'exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break
        
        response = agent.get_ingredients(user_input)
        print(response)
        print("-" * 30)

if __name__ == "__main__":
    main()