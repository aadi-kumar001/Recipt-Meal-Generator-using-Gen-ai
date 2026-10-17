"""Calorie targets and nutrition maths."""
ACTIVITY_FACTOR = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "athlete": 1.9}
GOAL_ADJUST = {"lose": -0.18, "maintain": 0.0, "gain": 0.12}


def bmr(sex: str, age: int, weight_kg: float, height_cm: float) -> float:
    """Mifflin-St Jeor equation."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "male" else -161)


def bmi(weight_kg: float, height_cm: float) -> float:
    return round(weight_kg / ((height_cm / 100) ** 2), 1)


def daily_target(profile):
    """Return (kcal, source). Explicit goal wins, then body stats, then default."""
    if profile.calorie_goal:
        return int(profile.calorie_goal), "your goal"
    if all([profile.age, profile.sex, profile.weight_kg, profile.height_cm]):
        tdee = bmr(profile.sex, profile.age, profile.weight_kg, profile.height_cm) * ACTIVITY_FACTOR[profile.activity]
        kcal = tdee * (1 + GOAL_ADJUST[profile.goal])
        floor = 1500 if profile.sex == "male" else 1200
        return int(round(max(kcal, floor) / 10) * 10), "calculated from your body stats"
    return 2000, "default"


def macro_targets(kcal: int, low_carb: bool = False, goal: str = "maintain") -> dict:
    if low_carb:
        split = (0.30, 0.20, 0.50)
    elif goal == "lose":
        split = (0.30, 0.40, 0.30)
    else:
        split = (0.20, 0.50, 0.30)
    p, c, f = split
    return {"protein": round(kcal * p / 4), "carbs": round(kcal * c / 4), "fat": round(kcal * f / 9)}


def scale(nutrition: dict, mult: float) -> dict:
    return {k: round(v * mult) for k, v in nutrition.items()}


def total(nutritions) -> dict:
    out = {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0}
    for n in nutritions:
        for k in out:
            out[k] += n.get(k, 0)
    return out
