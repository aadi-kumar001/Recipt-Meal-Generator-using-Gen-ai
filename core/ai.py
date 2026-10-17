"""Optional AI chef. Uses the Anthropic Messages API through the standard library.
Set ANTHROPIC_API_KEY to enable. Every AI recipe is re-checked against allergies and diet."""
import hashlib
import json
import os
import urllib.error
import urllib.request

from .filters import ingredient_issues

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"


class AINotConfigured(Exception):
    pass


class AIError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _prompt(profile, slot, kcal):
    return f"""Create ONE original {slot} recipe for one person.
Diet: {profile.diet}{' (low carb)' if profile.low_carb else ''}
Strictly avoid allergens: {', '.join(profile.allergies) or 'none'}
Strictly avoid disliked foods: {', '.join(profile.dislikes) or 'none'}
Preferred cuisines: {', '.join(profile.cuisines) or 'any'}
Try to use these pantry items: {', '.join(profile.pantry) or 'any common ingredients'}
Target about {int(kcal)} kcal per serving.
Reply with ONLY a JSON object, no markdown, using exactly these keys:
title (string), minutes (integer), cuisine (string),
ingredients (list of objects with name, qty (number), unit (one of g, ml, tsp, tbsp, cup, or empty string for pieces)),
steps (list of short strings),
nutrition (object with integers kcal, protein, carbs, fat per serving)."""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AIError("The AI reply did not contain JSON.")
    try:
        return json.loads(text[start:end + 1])
    except ValueError as exc:
        raise AIError("The AI reply was not valid JSON.") from exc


def _validate(data: dict) -> dict:
    try:
        ings = [{"name": str(i["name"]).lower()[:60], "qty": float(i["qty"]), "unit": str(i.get("unit", ""))[:6]}
                for i in data["ingredients"]][:25]
        nut = {k: int(data["nutrition"][k]) for k in ("kcal", "protein", "carbs", "fat")}
        steps = [str(s)[:300] for s in data["steps"]][:12]
        if not ings or not steps or not 50 <= nut["kcal"] <= 1500:
            raise ValueError
        return {"title": str(data["title"])[:80], "minutes": int(data.get("minutes", 30)),
                "cuisine": str(data.get("cuisine", "Fusion"))[:30], "ingredients": ings,
                "steps": steps, "nutrition": nut}
    except (KeyError, TypeError, ValueError) as exc:
        raise AIError("The AI recipe was missing required fields.") from exc


def _call(prompt: str) -> str:
    body = json.dumps({"model": os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL), "max_tokens": 1200,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise AIError(f"Could not reach the AI service: {exc}") from exc
    return "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")


def generate_ai_meal(profile, slot, kcal, caller=_call, attempts=2):
    if not is_configured() and caller is _call:
        raise AINotConfigured("Set ANTHROPIC_API_KEY to enable the AI chef.")
    last = "unknown problem"
    for _ in range(attempts):
        recipe = _validate(_extract_json(caller(_prompt(profile, slot, kcal))))
        issues = ingredient_issues([i["name"] for i in recipe["ingredients"]], profile)
        if not issues:
            rid = "ai-" + hashlib.md5(recipe["title"].encode()).hexdigest()[:8]
            return {"slot": slot, "id": rid, "image": "/static/images/ai-chef.svg", "emoji": "👩‍🍳",
                    "diet": profile.diet, "allergens": [], "tags": ["ai-generated"], "portion": 1.0,
                    "pantry_match": 0, **recipe}
        last = "; ".join(issues)
    raise AIError(f"The AI suggested an unsafe recipe ({last}). Please try again.")
