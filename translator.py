from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound

# NOTE: To use this module, you need to install the 'deep-translator' library:
# pip install deep-translator

def translate_ingredient_list(ingredients: list[str]) -> list[str]:
    """
    Translates a list of ingredient strings from any detected language to English.
    Uses an external translation service.
    """
    if not ingredients:
        return []

    # Filter out empty or whitespace-only strings to avoid sending them to the translator
    non_empty_items = {item: i for i, item in enumerate(ingredients) if item.strip()}

    if not non_empty_items:
        return ingredients # If all items are empty, return the original list

    try:
        translator = GoogleTranslator(source='auto', target='en')

        # Translate only the non-empty items in a single batch call
        originals = list(non_empty_items.keys())
        translated_batch = translator.translate_batch(originals)

        # Create a result list of the same size as the original
        result_list = list(ingredients)

        # Place the translated items back into their original positions
        for original, translated in zip(originals, translated_batch):
            original_index = non_empty_items[original]
            # If a translation for an item fails, it might return None. In that case, keep the original.
            if translated:
                result_list[original_index] = translated

        return result_list

    except (TranslationNotFound, Exception) as e:
        print(f"Warning: An error occurred during batch translation: {e}. Returning the original list.")
        return ingredients # In case of any error, return the original list