from dataclasses import dataclass, field
from typing import List, Optional

DIETS = ["vegan", "vegetarian", "non-veg"]
ALLERGENS = ["peanut", "tree-nut", "dairy", "gluten", "egg", "soy", "fish", "shellfish", "sesame"]
CUISINES = ["Indian", "South Indian", "Mediterranean", "Continental", "Asian"]
ACTIVITY = ["sedentary", "light", "moderate", "active", "athlete"]
GOALS = ["lose", "maintain", "gain"]


def _clean_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        raise ValueError("Expected a list of text values.")
    return [str(v).strip().lower() for v in value if str(v).strip()]


def _num(data, key, lo, hi, cast=float):
    raw = data.get(key)
    if raw in (None, ""):
        return None
    try:
        val = cast(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number.")
    if not lo <= val <= hi:
        raise ValueError(f"'{key}' must be between {lo} and {hi}.")
    return val


@dataclass
class Profile:
    name: str = "Friend"
    diet: str = "vegetarian"
    allergies: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    pantry: List[str] = field(default_factory=list)
    cuisines: List[str] = field(default_factory=list)
    calorie_goal: Optional[int] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    activity: str = "light"
    goal: str = "maintain"
    low_carb: bool = False
    days: int = 7
    include_snacks: bool = True
    seed: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        if not isinstance(data, dict):
            raise ValueError("Profile must be a JSON object.")
        diet = str(data.get("diet", "vegetarian")).lower()
        if diet not in DIETS:
            raise ValueError(f"'diet' must be one of {DIETS}.")
        allergies = _clean_list(data.get("allergies"))
        bad = [a for a in allergies if a not in ALLERGENS]
        if bad:
            raise ValueError(f"Unknown allergen(s): {bad}. Allowed: {ALLERGENS}.")
        cuisines = [c for c in (data.get("cuisines") or []) if c in CUISINES]
        sex = data.get("sex")
        if sex not in (None, "", "male", "female"):
            raise ValueError("'sex' must be 'male' or 'female'.")
        activity = str(data.get("activity") or "light").lower()
        goal = str(data.get("goal") or "maintain").lower()
        if activity not in ACTIVITY:
            raise ValueError(f"'activity' must be one of {ACTIVITY}.")
        if goal not in GOALS:
            raise ValueError(f"'goal' must be one of {GOALS}.")
        days = _num(data, "days", 1, 7, int) or 7
        return cls(
            name=str(data.get("name") or "Friend").strip()[:40] or "Friend",
            diet=diet, allergies=allergies,
            dislikes=_clean_list(data.get("dislikes")),
            pantry=_clean_list(data.get("pantry")),
            cuisines=cuisines,
            calorie_goal=_num(data, "calorie_goal", 800, 5000, int),
            age=_num(data, "age", 12, 100, int),
            sex=sex or None,
            weight_kg=_num(data, "weight_kg", 25, 300),
            height_cm=_num(data, "height_cm", 100, 250),
            activity=activity, goal=goal,
            low_carb=bool(data.get("low_carb", False)),
            days=days,
            include_snacks=bool(data.get("include_snacks", True)),
            seed=_num(data, "seed", 0, 10**9, int),
        )
