"""Flask app: JSON API + static web UI for the Personalized Recipe & Meal Generator."""
import os
import random
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from core import ai
from core.generator import Generator, SHARE_NO_SNACK, SHARE_WITH_SNACK
from core.nutrition import bmi, daily_target, macro_targets
from core.planner import build_plan, swap_meal
from core.profile import ACTIVITY, ALLERGENS, CUISINES, DIETS, GOALS, Profile
from core.store import FeedbackStore, load_recipes

ROOT = Path(__file__).resolve().parent


def create_app(feedback_path=None):
    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    store = FeedbackStore(feedback_path)
    gen = Generator(load_recipes(), store)

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Send a JSON object in the request body.")
        return data

    @app.errorhandler(ValueError)
    def bad_request(err):
        return jsonify(error=str(err)), 400

    @app.errorhandler(LookupError)
    def not_found(err):
        return jsonify(error=str(err.args[0] if err.args else err)), 404

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/meta")
    def meta():
        return jsonify(diets=DIETS, allergens=ALLERGENS, cuisines=CUISINES, activity=ACTIVITY,
                       goals=GOALS, recipe_count=len(gen.recipes), ai_enabled=ai.is_configured())

    @app.post("/api/target")
    def target():
        profile = Profile.from_dict(body().get("profile", {}))
        kcal, source = daily_target(profile)
        out = {"kcal": kcal, "source": source,
               "macros": macro_targets(kcal, profile.low_carb, profile.goal)}
        if profile.weight_kg and profile.height_cm:
            out["bmi"] = bmi(profile.weight_kg, profile.height_cm)
        return jsonify(out)

    @app.post("/api/plan")
    def plan():
        profile = Profile.from_dict(body().get("profile", {}))
        return jsonify(build_plan(profile, gen))

    @app.post("/api/swap")
    def swap():
        data = body()
        profile = Profile.from_dict(data.get("profile", {}))
        spec = data.get("spec")
        if not isinstance(spec, list):
            raise ValueError("'spec' must be a list.")
        try:
            day, index = int(data["day"]), int(data["index"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("'day' and 'index' are required integers.")
        return jsonify(swap_meal(profile, gen, spec, day, index, random.Random()))

    @app.post("/api/feedback")
    def feedback():
        data = body()
        rid = str(data.get("recipe_id", ""))
        if rid not in gen.by_id:
            raise ValueError("Unknown recipe_id.")
        try:
            store.add(rid, int(data.get("rating")))
        except (TypeError, ValueError):
            raise ValueError("'rating' must be an integer from 1 to 5.")
        return jsonify(ok=True, average=store.average(rid))

    @app.post("/api/ai-recipe")
    def ai_recipe():
        data = body()
        profile = Profile.from_dict(data.get("profile", {}))
        slot = data.get("slot", "dinner")
        if slot not in SHARE_WITH_SNACK:
            raise ValueError("Unknown meal slot.")
        shares = SHARE_WITH_SNACK if profile.include_snacks else SHARE_NO_SNACK
        kcal = daily_target(profile)[0] * shares.get(slot, 0.15)
        try:
            return jsonify(ai.generate_ai_meal(profile, slot, kcal))
        except ai.AINotConfigured as exc:
            return jsonify(error=str(exc)), 503
        except ai.AIError as exc:
            return jsonify(error=str(exc)), 502

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
