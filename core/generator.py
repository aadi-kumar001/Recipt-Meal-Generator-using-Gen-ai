"""Scores curated recipes against a profile and scales portions to calorie targets."""
import math

from .filters import is_allowed
from .nutrition import scale

STAPLES = {"oil", "olive oil", "sesame oil", "salt", "pepper", "turmeric", "cumin", "mustard seeds",
           "garam masala", "chilli powder", "ginger", "garlic"}
SLOTS = ["breakfast", "lunch", "dinner", "snack"]
SHARE_WITH_SNACK = {"breakfast": 0.25, "lunch": 0.30, "dinner": 0.30, "snack": 0.15}
SHARE_NO_SNACK = {"breakfast": 0.28, "lunch": 0.38, "dinner": 0.34}


def _match(pantry_item: str, name: str) -> bool:
    a, b = pantry_item.lower().strip().rstrip("s"), name.lower().rstrip("s")
    return bool(a) and (a in b or b in a)


def pantry_overlap(recipe, pantry) -> float:
    """Fraction of non-staple ingredients the user already has (0..1)."""
    needed = [i["name"] for i in recipe["ingredients"] if i["name"] not in STAPLES]
    if not needed or not pantry:
        return 0.0
    have = sum(1 for n in needed if any(_match(p, n) for p in pantry))
    return have / len(needed)


def portion_for(recipe, target_kcal: float) -> float:
    """Portion multiplier in 0.25 steps, clamped to 0.75-1.5."""
    raw = target_kcal / recipe["nutrition"]["kcal"]
    return max(0.75, min(1.5, round(raw * 4) / 4))


def _qty(value: float) -> float:
    return round(value, 2)


class Generator:
    def __init__(self, recipes, feedback=None):
        self.recipes = recipes
        self.by_id = {r["id"]: r for r in recipes}
        self.feedback = feedback

    def candidates(self, profile, slot, exclude=()):
        """Returns (recipes, relaxed). Allergy and diet filters are never relaxed;
        the low-carb preference is relaxed only when nothing else fits."""
        pool = [r for r in self.recipes
                if slot in r["meals"] and r["id"] not in exclude and is_allowed(r, profile)]
        relaxed = False
        if profile.low_carb:
            keto = [r for r in pool if "keto" in r["tags"]]
            if keto:
                pool = keto
            elif pool:
                relaxed = True
        return pool, relaxed

    def score(self, recipe, profile, target_kcal, used, rng) -> float:
        s = 2.0 * pantry_overlap(recipe, profile.pantry)
        s += 1.0 - min(1.0, abs(recipe["nutrition"]["kcal"] - target_kcal) / max(target_kcal, 1))
        if recipe["cuisine"] in profile.cuisines:
            s += 0.6
        if self.feedback:
            avg = self.feedback.average(recipe["id"])
            if avg is not None:
                s += -4.0 if avg <= 2 else (avg - 3) * 0.4
        s -= 3.0 * used.get(recipe["id"], 0)
        return s + rng.uniform(0, 0.6)

    def pick(self, profile, slot, target_kcal, used, rng, exclude=()):
        pool, relaxed = self.candidates(profile, slot, exclude)
        if not pool:
            return None, relaxed
        best = max(pool, key=lambda r: self.score(r, profile, target_kcal, used, rng))
        return best, relaxed

    def make_meal(self, recipe, slot, portion, pantry=()):
        return {
            "slot": slot, "id": recipe["id"], "title": recipe["title"], "image": recipe["image"],
            "emoji": recipe["emoji"], "cuisine": recipe["cuisine"], "minutes": recipe["minutes"],
            "diet": recipe["diet"], "allergens": recipe["allergens"], "tags": recipe["tags"],
            "portion": portion,
            "nutrition": scale(recipe["nutrition"], portion),
            "ingredients": [{"name": i["name"], "qty": _qty(i["qty"] * portion), "unit": i["unit"]}
                            for i in recipe["ingredients"]],
            "steps": recipe["steps"],
            "pantry_match": round(pantry_overlap(recipe, list(pantry)), 2),
        }


def fmt_qty(qty: float, unit: str) -> str:
    """Human friendly quantity such as '1.5 tsp', '200 g' or '2'."""
    if unit == "":
        q = math.ceil(qty - 1e-9)
        return str(q)
    if qty >= 10:
        return f"{round(qty)} {unit}"
    text = f"{qty:.2f}".rstrip("0").rstrip(".")
    return f"{text} {unit}"
