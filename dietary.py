"""Ingredient-based diet and allergen flags for recipes."""
import re


_MEAT = re.compile(
    r'\b(?:beef|bison|bacon|ham|pork|sausage|salami|pepperoni|'
    r'chicken|turkey|duck|goose|quail|lamb|mutton|goat|veal|venison|'
    r'rabbit|meat|meatballs?|offal|gizzards?|livers?|gelatin|gelatine|'
    r'lard|suet|tallow|sausages?)\b'
    r'|(?:chicken|beef|meat)\s+(?:stock|broth)\b',
    re.IGNORECASE,
)
_FISH = re.compile(
    r'\b(?:fish|anchov(?:y|ies)|sardines?|tuna|salmon|tilapia|cod|haddock|'
    r'mackerel|trout|herring|snapper|mahi|prawns?|shrimps?|crabs?|lobsters?|'
    r'crayfish|crawfish|oysters?|mussels?|clams?|scallops?|squid|octopus|'
    r'calamari|seafood)\b'
    r'|(?:fish|oyster|shrimp)\s+(?:sauce|paste|stock|broth)\b'
    r'|\bcaesar dressing\b',
    re.IGNORECASE,
)
_EGGS = re.compile(
    r'\b(?:eggs?|egg whites?|egg yolks?|mayonnaise|mayo|aioli|'
    r'caesar dressing|custard|meringue)\b',
    re.IGNORECASE,
)
_PEANUTS = re.compile(r'\b(?:peanuts?|groundnuts?)\b', re.IGNORECASE)
_DAIRY = re.compile(
    r'\b(?:milk|butter|cheese|feta|parmesan|mozzarella|cheddar|ricotta|'
    r'gouda|brie|cream|yogh?urt|ghee|whey|casein|lactose|'
    r'buttermilk|paneer|curd|mala|dairy|ice cream)\b',
    re.IGNORECASE,
)
_GLUTEN = re.compile(
    r'\b(?:wheat|rye|barley|malt|seitan|couscous|semolina|bulgur|farro|'
    r'spelt|einkorn|durum|triticale|oats?|bread|croutons?|breadcrumbs?|'
    r'pasta|macaroni|spaghetti|noodles?|soy sauce|chapati|'
    r'pancake mix|pizza dough|dough)\b'
    r'|(?<!coconut )(?<!rice )(?<!maize )(?<!corn )(?<!gram )'
    r'(?<!chickpea )(?<!cassava )(?<!almond )(?<!tapioca )'
    r'(?<!sorghum )(?<!millet )(?<!amaranth )(?<!teff )'
    r'(?<!buckwheat )(?<!potato )\bflour\b',
    re.IGNORECASE,
)


def derive_dietary_flags(ingredients):
    """Derive recipe diet/allergen safety flags from its listed ingredients."""
    text = (ingredients or '').lower()
    if not text.strip():
        return {flag: False for flag in CSV_FLAG_COLUMNS.values()}

    # Plant-based milks and creams do not contain lactose or animal products.
    plant_dairy = re.sub(
        r'\b(?:coconut|almond|soy|oat|rice|cashew|hemp|pea)\s+'
        r'(?:milk|cream)\b',
        '',
        text,
    )
    has_meat = bool(_MEAT.search(text))
    has_fish = bool(_FISH.search(text))
    has_eggs = bool(_EGGS.search(text))
    has_dairy = bool(_DAIRY.search(plant_dairy))
    has_honey_or_animal_products = bool(
        re.search(r'\b(?:honey|gelatin|gelatine|collagen|lard|suet|tallow)\b', text)
    )
    has_gluten = bool(_GLUTEN.search(text))

    return {
        'allergy_safe_meat': not has_meat,
        'allergy_safe_eggs': not has_eggs,
        'allergy_safe_fish': not has_fish,
        'allergy_safe_peanuts': not _PEANUTS.search(text),
        'gluten_free': not has_gluten,
        'lactose_free': not has_dairy,
        'vegan': not (
            has_meat or has_fish or has_eggs or has_dairy or has_honey_or_animal_products
        ),
        'vegetarian': not (has_meat or has_fish),
    }


CSV_FLAG_COLUMNS = {
    'Allergies_Meat': 'allergy_safe_meat',
    'Allergies_Eggs': 'allergy_safe_eggs',
    'Allergies_Fish': 'allergy_safe_fish',
    'Allergies_Peanuts': 'allergy_safe_peanuts',
    'Gluten-Free': 'gluten_free',
    'Lactose-Intolerant': 'lactose_free',
    'Vegan': 'vegan',
    'Vegetarian': 'vegetarian',
}
