"""The user's profile as every agent sees it: resume entities + questionnaire answers +
skills completed on the roadmap. Pure function over Blackboard sections, so agents share
it without calling each other."""
from app.services import questionnaire as qn


def build_profile(entities: dict, questionnaire: dict | None, roadmap: dict | None) -> tuple[dict, dict]:
    answers = (questionnaire or {}).get("answers", {})
    profile = qn.profile_entities(entities, answers)
    learned = (roadmap or {}).get("completed_skills", [])
    have = {s["name"].lower() for s in profile.get("skills", [])}
    profile["skills"] = list(profile.get("skills", [])) + [
        {"name": c["name"], "category": "roadmap", "mentions": 1, "sections": ["roadmap"],
         "learned_on_roadmap": True} for c in learned if c["name"].lower() not in have]
    return profile, answers
