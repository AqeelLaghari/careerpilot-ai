"""The user's profile as every agent sees it: resume entities + questionnaire answers +
skills completed on the roadmap + the account profile (Day 23). Pure function over Blackboard
sections, so agents share it without calling each other."""
from app.services import questionnaire as qn
from app.services.account_profile import profile_answers


def merged_answers(questionnaire: dict | None, account: dict | None = None) -> dict:
    """Questionnaire answers, plus what the account profile already says (career stage,
    graduation year), so those questions aren't asked twice. Real answers win."""
    return profile_answers(account) | (questionnaire or {}).get("answers", {})


def build_profile(entities: dict, questionnaire: dict | None, roadmap: dict | None,
                  account: dict | None = None) -> tuple[dict, dict]:
    answers = merged_answers(questionnaire, account)
    profile = qn.profile_entities(entities, answers)
    learned = (roadmap or {}).get("completed_skills", [])
    have = {s["name"].lower() for s in profile.get("skills", [])}
    profile["skills"] = list(profile.get("skills", [])) + [
        {"name": c["name"], "category": "roadmap", "mentions": 1, "sections": ["roadmap"],
         "learned_on_roadmap": True} for c in learned if c["name"].lower() not in have]
    return profile, answers
