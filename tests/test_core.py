import itertools
import json
import random
import tempfile
import unittest
from pathlib import Path

from app import create_app
from core import ai
from core.filters import ALLERGEN_KEYWORDS, ingredient_issues
from core.generator import Generator, fmt_qty, pantry_overlap, portion_for
from core.nutrition import bmr, daily_target, macro_targets
from core.planner import build_plan, shopping_list, swap_meal
from core.profile import ALLERGENS, DIETS, Profile
from core.store import FeedbackStore, load_recipes

RECIPES = load_recipes()
GEN = Generator(RECIPES)
ROOT = Path(__file__).resolve().parent.parent


def P(**kw):
    kw.setdefault("seed", 1)
    return Profile.from_dict(kw)


class DataTests(unittest.TestCase):
    def test_every_recipe_is_complete_and_has_image(self):
        for r in RECIPES:
            self.assertTrue(r["steps"] and r["ingredients"] and r["meals"], r["id"])
            self.assertTrue((ROOT / r["image"].lstrip("/")).exists(), r["id"])
            self.assertIn(r["diet"], DIETS)
            for a in r["allergens"]:
                self.assertIn(a, ALLERGENS)

    def test_allergen_tags_match_ingredient_keywords(self):
        """Catch data entry mistakes: ingredients that imply an allergen must carry its tag."""
        for r in RECIPES:
            text = " ".join(i["name"] for i in r["ingredients"])
            for allergen, words in ALLERGEN_KEYWORDS.items():
                if allergen in ("dairy", "gluten"):
                    continue  # tested separately (coconut milk, oats etc. need care)
                if any(w in text for w in words):
                    self.assertIn(allergen, r["allergens"], f"{r['id']} missing {allergen}")


class ProfileTests(unittest.TestCase):
    def test_validation(self):
        for bad in ({"diet": "carnivore"}, {"allergies": ["lava"]}, {"days": 20}, {"age": 5}, {"sex": "x"}):
            with self.assertRaises(ValueError):
                Profile.from_dict(bad)

    def test_string_lists_and_blank_numbers(self):
        p = Profile.from_dict({"dislikes": "Mushrooms, Tofu ", "calorie_goal": "", "days": "3"})
        self.assertEqual(p.dislikes, ["mushrooms", "tofu"])
        self.assertIsNone(p.calorie_goal)
        self.assertEqual(p.days, 3)


class NutritionTests(unittest.TestCase):
    def test_bmr_known_value(self):
        self.assertAlmostEqual(bmr("male", 30, 70, 175), 1648.75, places=1)

    def test_target_priority(self):
        self.assertEqual(daily_target(P(calorie_goal=1700))[0], 1700)
        self.assertEqual(daily_target(P())[0], 2000)
        t = daily_target(P(age=30, sex="female", weight_kg=60, height_cm=165, activity="moderate", goal="lose"))[0]
        self.assertTrue(1200 <= t < 2000)

    def test_macros_add_up(self):
        m = macro_targets(2000)
        self.assertAlmostEqual(m["protein"] * 4 + m["carbs"] * 4 + m["fat"] * 9, 2000, delta=30)


class SafetyTests(unittest.TestCase):
    def test_no_plan_ever_contains_a_selected_allergen_or_wrong_diet(self):
        rng = random.Random(7)
        for diet in DIETS:
            for _ in range(15):
                allergies = rng.sample(ALLERGENS, rng.randint(0, 3))
                p = P(diet=diet, allergies=allergies, low_carb=rng.random() < 0.4, seed=rng.randint(0, 999))
                plan = build_plan(p, GEN)
                for day in plan["days"]:
                    for m in day["meals"]:
                        self.assertFalse(set(m["allergens"]) & set(allergies), (m["title"], allergies))
                        if diet == "vegan":
                            self.assertEqual(m["diet"], "vegan", m["title"])
                        if diet == "vegetarian":
                            self.assertNotEqual(m["diet"], "non-veg", m["title"])

    def test_dislikes_are_respected(self):
        plan = build_plan(P(diet="non-veg", dislikes=["chicken", "paneer", "egg"]), GEN)
        for day in plan["days"]:
            for m in day["meals"]:
                blob = (m["title"] + " ".join(i["name"] for i in m["ingredients"])).lower()
                for bad in ("chicken", "paneer", "egg"):
                    self.assertNotIn(bad, blob)

    def test_impossible_restrictions_degrade_gracefully(self):
        every = ALLERGENS
        plan = build_plan(P(diet="vegan", allergies=every), GEN)
        self.assertTrue(plan["notes"])

    def test_ai_keyword_checks(self):
        p = P(diet="vegan", allergies=["peanut"])
        self.assertTrue(ingredient_issues(["peanut butter"], p))
        self.assertTrue(ingredient_issues(["chicken stock"], p))
        self.assertTrue(ingredient_issues(["honey"], p))
        self.assertFalse(ingredient_issues(["coconut milk", "rice", "spinach"], p))


class PlannerTests(unittest.TestCase):
    def test_structure_and_calories(self):
        plan = build_plan(P(calorie_goal=1800, days=5), GEN)
        self.assertEqual(len(plan["days"]), 5)
        for d in plan["days"]:
            self.assertEqual([m["slot"] for m in d["meals"]], ["breakfast", "lunch", "dinner", "snack"])
            self.assertEqual(len({m["id"] for m in d["meals"]}), len(d["meals"]))
        self.assertAlmostEqual(plan["summary"]["average"]["kcal"], 1800, delta=250)

    def test_no_snacks(self):
        plan = build_plan(P(include_snacks=False, days=2), GEN)
        self.assertTrue(all(len(d["meals"]) == 3 for d in plan["days"]))

    def test_seed_is_reproducible(self):
        a = build_plan(P(seed=5), GEN)["spec"]
        self.assertEqual(a, build_plan(P(seed=5), GEN)["spec"])

    def test_pantry_influences_choice(self):
        pantry = ["paneer", "spinach", "onion", "capsicum", "tomato"]
        with_p = build_plan(P(pantry=pantry, days=3), GEN)["days"]
        score = lambda days: sum(m["pantry_match"] for d in days for m in d["meals"])
        self.assertGreater(score(with_p), score(build_plan(P(days=3), GEN)["days"]))

    def test_portion_bounds(self):
        for r in RECIPES:
            self.assertTrue(0.75 <= portion_for(r, 500) <= 1.5)

    def test_swap_changes_meal_and_keeps_rest(self):
        p = P(days=2)
        plan = build_plan(p, GEN)
        new = swap_meal(p, GEN, plan["spec"], 0, 1, random.Random(3))
        self.assertNotEqual(new["spec"][0][1]["id"], plan["spec"][0][1]["id"])
        self.assertEqual(new["spec"][1], plan["spec"][1])
        self.assertEqual(new["spec"][0][0], plan["spec"][0][0])
        with self.assertRaises(ValueError):
            swap_meal(p, GEN, plan["spec"], 9, 0)

    def test_shopping_list_merges_and_flags_pantry(self):
        meals = [GEN.make_meal(GEN.by_id["vegetable-omelette"], "breakfast", 1.0),
                 GEN.make_meal(GEN.by_id["boiled-egg-chaat"], "snack", 1.0)]
        items = {i["name"]: i for i in shopping_list(meals, ["egg"])}
        self.assertEqual(items["eggs"]["quantity"], "4")
        self.assertTrue(items["eggs"]["have"])

    def test_every_shopping_item_is_categorised(self):
        meals = [GEN.make_meal(r, "lunch", 1.0) for r in RECIPES]
        others = {i["name"] for i in shopping_list(meals, []) if i["category"] == "Other"}
        self.assertEqual(others, set())

    def test_fmt_qty(self):
        self.assertEqual(fmt_qty(1.25, "tsp"), "1.25 tsp")
        self.assertEqual(fmt_qty(149.6, "g"), "150 g")
        self.assertEqual(fmt_qty(1.1, ""), "2")

    def test_feedback_lowers_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            fb = FeedbackStore(Path(tmp) / "fb.json")
            for _ in range(3):
                fb.add("poha-with-peanuts", 1)
            g = Generator(RECIPES, fb)
            r = g.by_id["poha-with-peanuts"]
            base = Generator(RECIPES).score(r, P(), 300, {}, random.Random(0))
            self.assertLess(g.score(r, P(), 300, {}, random.Random(0)), base - 3)


class AITests(unittest.TestCase):
    GOOD = json.dumps({"title": "Spinach Rice Bowl", "minutes": 20, "cuisine": "Indian",
                       "ingredients": [{"name": "rice", "qty": 80, "unit": "g"}, {"name": "spinach", "qty": 60, "unit": "g"}],
                       "steps": ["Cook rice.", "Wilt spinach."], "nutrition": {"kcal": 400, "protein": 12, "carbs": 70, "fat": 6}})
    BAD = GOOD.replace("spinach", "peanut", 1)

    def test_accepts_safe_recipe(self):
        meal = ai.generate_ai_meal(P(diet="vegan", allergies=["peanut"]), "dinner", 500, caller=lambda _: "```json\n" + self.GOOD + "\n```")
        self.assertEqual(meal["title"], "Spinach Rice Bowl")

    def test_rejects_unsafe_recipe_even_after_retry(self):
        with self.assertRaises(ai.AIError):
            ai.generate_ai_meal(P(allergies=["peanut"]), "dinner", 500, caller=lambda _: self.BAD)

    def test_retries_then_succeeds(self):
        replies = iter([self.BAD, self.GOOD])
        meal = ai.generate_ai_meal(P(allergies=["peanut"]), "dinner", 500, caller=lambda _: next(replies))
        self.assertEqual(meal["slot"], "dinner")

    def test_bad_json(self):
        with self.assertRaises(ai.AIError):
            ai.generate_ai_meal(P(), "dinner", 500, caller=lambda _: "sorry, no")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = create_app(Path(self.tmp.name) / "fb.json").test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pages_and_meta(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        meta = self.client.get("/api/meta").get_json()
        self.assertEqual(meta["recipe_count"], len(RECIPES))

    def test_plan_swap_feedback_flow(self):
        prof = {"diet": "vegan", "allergies": ["soy"], "days": 2, "seed": 3}
        plan = self.client.post("/api/plan", json={"profile": prof}).get_json()
        self.assertEqual(len(plan["days"]), 2)
        sw = self.client.post("/api/swap", json={"profile": prof, "spec": plan["spec"], "day": 0, "index": 0})
        self.assertEqual(sw.status_code, 200)
        rid = plan["spec"][0][0]["id"]
        fb = self.client.post("/api/feedback", json={"recipe_id": rid, "rating": 5}).get_json()
        self.assertEqual(fb["average"], 5)

    def test_errors_are_clean_json(self):
        r = self.client.post("/api/plan", json={"profile": {"diet": "x"}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())
        self.assertEqual(self.client.post("/api/plan", data="nope").status_code, 400)
        self.assertEqual(self.client.post("/api/feedback", json={"recipe_id": "zzz", "rating": 3}).status_code, 400)
        self.assertEqual(self.client.post("/api/feedback", json={"recipe_id": "vegetable-omelette", "rating": 9}).status_code, 400)
        bad = self.client.post("/api/swap", json={"profile": {}, "spec": [[{"id": "nope", "slot": "lunch", "portion": 1}]], "day": 0, "index": 0})
        self.assertEqual(bad.status_code, 400)

    def test_ai_disabled_without_key(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        r = self.client.post("/api/ai-recipe", json={"profile": {}})
        self.assertEqual(r.status_code, 503)

    def test_target_endpoint(self):
        r = self.client.post("/api/target", json={"profile": {"age": 30, "sex": "male", "weight_kg": 70, "height_cm": 175, "activity": "moderate"}}).get_json()
        self.assertGreater(r["kcal"], 2000)
        self.assertIn("bmi", r)


if __name__ == "__main__":
    unittest.main()
