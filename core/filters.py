"""Hard safety filters. Allergies and diet rules are never relaxed."""
import re

DIET_ALLOWED = {
    "vegan": {"vegan"},
    "vegetarian": {"vegan", "vegetarian"},
    "non-veg": {"vegan", "vegetarian", "non-veg"},
}

# Used to double-check AI generated recipes, which carry no allergen tags.
ALLERGEN_KEYWORDS = {
    "peanut": ["peanut", "groundnut"],
    "tree-nut": ["almond", "cashew", "walnut", "pistachio", "pine nut", "hazelnut", "pecan"],
    "dairy": ["milk", "paneer", "yogurt", "yoghurt", "curd", "cheese", "butter", "ghee", "cream", "parmesan", "whey"],
    "gluten": ["wheat", "bread", "pasta", "roti", "flour", "oats", "tortilla", "wrap", "semolina", "barley", "couscous", "noodle"],
    "egg": ["egg", "mayonnaise"],
    "soy": ["soy", "tofu", "tempeh", "edamame", "miso"],
    "fish": ["fish", "salmon", "tuna", "cod", "anchovy", "sardine", "mackerel"],
    "shellfish": ["prawn", "shrimp", "crab", "lobster", "mussel", "oyster", "clam"],
    "sesame": ["sesame", "tahini"],
}
NON_VEG_WORDS = ["chicken", "mutton", "lamb", "beef", "pork", "fish", "salmon", "tuna", "prawn", "shrimp", "bacon", "meat", "crab"]
VEGETARIAN_BLOCKED = NON_VEG_WORDS + ["gelatin"]
VEGAN_EXTRA = ["milk", "paneer", "yogurt", "yoghurt", "curd", "cheese", "butter", "ghee", "cream", "egg", "honey", "parmesan", "whey", "mayonnaise"]
PLANT_MILKS = ["coconut milk", "soy milk", "almond milk", "oat milk", "rice milk", "cashew milk"]


def _strip_plant_milks(text: str) -> str:
    for pm in PLANT_MILKS:
        text = text.replace(pm, " ")
    return text


def _words(text: str):
    return re.findall(r"[a-z]+", text.lower())


def violates_dislike(names, title, dislikes) -> bool:
    haystack = " ".join(list(names) + [title]).lower()
    return any(d and d in haystack for d in dislikes)


def is_allowed(recipe: dict, profile) -> bool:
    """Tag-based check for curated recipes."""
    if recipe["diet"] not in DIET_ALLOWED[profile.diet]:
        return False
    if set(recipe["allergens"]) & set(profile.allergies):
        return False
    names = [i["name"] for i in recipe["ingredients"]]
    if violates_dislike(names, recipe["title"], profile.dislikes):
        return False
    return True


def ingredient_issues(ingredient_names, profile) -> list:
    """Keyword-based check for untagged (AI) recipes. Returns a list of problems."""
    issues = []
    text = _strip_plant_milks(" ".join(ingredient_names).lower())
    for allergen in profile.allergies:
        for kw in ALLERGEN_KEYWORDS.get(allergen, []):
            if kw in text:
                issues.append(f"contains '{kw}' ({allergen})")
                break
    if profile.diet in ("vegetarian", "vegan"):
        for kw in VEGETARIAN_BLOCKED:
            if kw in text:
                issues.append(f"contains '{kw}' (not vegetarian)")
                break
    if profile.diet == "vegan":
        for kw in VEGAN_EXTRA:
            if kw in text:
                issues.append(f"contains '{kw}' (not vegan)")
                break
    for d in profile.dislikes:
        if d and d in text:
            issues.append(f"contains disliked item '{d}'")
    return issues
