"""Builds weekly plans, handles swaps and creates the shopping list."""
import random
from collections import Counter, defaultdict

from .generator import SHARE_NO_SNACK, SHARE_WITH_SNACK, STAPLES, _match, fmt_qty, portion_for
from .nutrition import daily_target, macro_targets, total

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CATEGORIES = {
    "Fresh produce": {"onion", "tomato", "carrot", "green peas", "spinach", "capsicum", "cucumber", "lettuce",
                      "zucchini", "broccoli", "mushrooms", "mixed vegetables", "cherry tomatoes", "avocado",
                      "banana", "apple", "mixed berries", "lemon", "coriander", "mint", "basil", "parsley",
                      "curry leaves"},
    "Grains, pulses and bread": {"oats", "poha", "rice", "brown rice", "quinoa", "pasta", "toor dal", "moong dal",
                                 "masoor dal", "rajma", "chickpeas", "black beans", "whole wheat flour",
                                 "whole wheat bread", "multigrain bread", "whole wheat wrap", "idli batter"},
    "Dairy and eggs": {"eggs", "paneer", "yogurt", "greek yogurt", "parmesan"},
    "Meat, fish and tofu": {"chicken", "chicken breast", "white fish", "smoked salmon", "tuna", "tofu"},
    "Nuts, seeds and spreads": {"almonds", "walnuts", "peanuts", "pine nuts", "chia seeds", "tahini",
                                "peanut butter"},
    "Pantry and sauces": {"soy sauce", "soy milk", "coconut milk", "tamarind", "honey"},
}
CATEGORY_OF = {name: cat for cat, names in CATEGORIES.items() for name in names}


def slots_for(profile):
    base = ["breakfast", "lunch", "dinner"]
    return base + ["snack"] if profile.include_snacks else base


def shares_for(profile):
    return SHARE_WITH_SNACK if profile.include_snacks else SHARE_NO_SNACK


def build_plan(profile, gen, rng=None):
    target, source = daily_target(profile)
    rng = rng or random.Random(profile.seed)
    shares = shares_for(profile)
    used, spec, notes = Counter(), [], []
    for _ in range(profile.days):
        row, day_ids = [], []
        for slot in slots_for(profile):
            tk = target * shares[slot]
            recipe, relaxed = gen.pick(profile, slot, tk, used, rng, exclude=day_ids)
            if recipe is None:
                notes.append(f"No safe {slot} recipe matches your restrictions.")
                continue
            if relaxed:
                notes.append(f"No low-carb {slot} option fits your diet, so the closest choice was used.")
            used[recipe["id"]] += 1
            day_ids.append(recipe["id"])
            row.append({"id": recipe["id"], "slot": slot, "portion": portion_for(recipe, tk)})
        spec.append(row)
    return assemble(profile, gen, spec, notes)


def validate_spec(gen, spec):
    """Reject malformed or tampered specs (unknown recipe, bad slot or portion)."""
    if not isinstance(spec, list) or not spec or len(spec) > 7:
        raise ValueError("'spec' must be a list of 1-7 days.")
    for row in spec:
        if not isinstance(row, list) or len(row) > 6:
            raise ValueError("Each day in 'spec' must be a list of meals.")
        for m in row:
            if not isinstance(m, dict) or m.get("id") not in gen.by_id:
                raise ValueError("Unknown recipe id in 'spec'.")
            if m.get("slot") not in SHARE_WITH_SNACK:
                raise ValueError("Unknown meal slot in 'spec'.")
            try:
                ok = 0.5 <= float(m.get("portion", 1)) <= 2
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise ValueError("Portion must be between 0.5 and 2.")


def swap_meal(profile, gen, spec, day, index, rng=None):
    """Replace one meal with a different safe recipe and return the rebuilt plan."""
    validate_spec(gen, spec)
    if not (0 <= day < len(spec) and 0 <= index < len(spec[day])):
        raise ValueError("Invalid day or meal index.")
    rng = rng or random.Random()
    target, _ = daily_target(profile)
    cur = spec[day][index]
    slot = cur["slot"]
    used = Counter(m["id"] for row in spec for m in row)
    exclude = {m["id"] for m in spec[day]}
    tk = target * shares_for(profile).get(slot, 0.3)
    recipe, _ = gen.pick(profile, slot, tk, used, rng, exclude=exclude)
    if recipe is None:
        raise LookupError("No other safe recipe is available for this meal.")
    new_spec = [list(row) for row in spec]
    new_spec[day][index] = {"id": recipe["id"], "slot": slot, "portion": portion_for(recipe, tk)}
    return assemble(profile, gen, new_spec, [])


def assemble(profile, gen, spec, notes):
    target, source = daily_target(profile)
    days, all_meals = [], []
    for i, row in enumerate(spec):
        meals = []
        for m in row:
            recipe = gen.by_id.get(m["id"])
            if recipe is None:
                raise ValueError(f"Unknown recipe id '{m['id']}'.")
            portion = float(m.get("portion", 1))
            if not 0.5 <= portion <= 2:
                raise ValueError("Portion must be between 0.5 and 2.")
            meals.append(gen.make_meal(recipe, m["slot"], portion, profile.pantry))
        all_meals.extend(meals)
        days.append({"day": DAY_NAMES[i % 7], "meals": meals, "totals": total(x["nutrition"] for x in meals)})
    n = max(len(days), 1)
    avg = {k: round(sum(d["totals"][k] for d in days) / n) for k in ("kcal", "protein", "carbs", "fat")}
    notes = list(dict.fromkeys(notes))
    if days and target and abs(avg["kcal"] - target) / target > 0.12:
        notes.append(f"Average intake ({avg['kcal']} kcal) differs from your target ({target} kcal) "
                     "because the safe recipe pool is limited.")
    summary = {"target_kcal": target, "target_source": source, "average": avg,
               "macro_targets": macro_targets(target, profile.low_carb, profile.goal)}
    return {"days": days, "spec": spec, "summary": summary, "notes": notes,
            "shopping": shopping_list(all_meals, profile.pantry)}


def shopping_list(meals, pantry):
    agg = defaultdict(float)
    for meal in meals:
        for ing in meal["ingredients"]:
            agg[(ing["name"], ing["unit"])] += ing["qty"]
    items = []
    for (name, unit), qty in agg.items():
        items.append({
            "name": name, "quantity": fmt_qty(qty, unit),
            "category": "Pantry staples" if name in STAPLES else CATEGORY_OF.get(name, "Other"),
            "have": any(_match(p, name) for p in pantry),
        })
    items.sort(key=lambda x: (x["category"], x["name"]))
    return items
