"""Intent Predictor — predicts likely user needs before they ask.

Uses time, recent events, and calendar context to pre-fetch tools/memories.
"""

from datetime import datetime

from app.core.runtime.kernel_instance import kernel

PLANNING_KEYWORDS = ("规划", "计划", "安排", "下周", "plan", "schedule", "roadmap")
REVIEW_KEYWORDS = ("复盘", "总结", "回顾", "review", "reflect")


class IntentPredictor:
    """Predicts user intent based on context patterns for proactive assistance."""

    def classify_message(self, message: str) -> dict:
        """Classify a chat message intent for routing."""
        text = message.lower().strip()
        if any(k in message or k in text for k in PLANNING_KEYWORDS):
            return {"intent": "planning", "confidence": 0.85}
        if any(k in message or k in text for k in REVIEW_KEYWORDS):
            return {"intent": "review", "confidence": 0.8}
        if any(w in text for w in ("列文件", "list file", "read file", "打开")):
            return {"intent": "filesystem", "confidence": 0.75}
        return {"intent": "general", "confidence": 0.5}

    def predict(self) -> dict:
        """Predict the most likely user intent right now."""
        now = datetime.utcnow()
        hour = now.hour
        weekday = now.strftime("%A")

        if 6 <= hour < 9:
            intent = "morning_brief"
            confidence = 0.8
        elif 20 <= hour < 22:
            intent = "daily_review"
            confidence = 0.7
        elif weekday == "Sunday" and 19 <= hour < 21:
            intent = "weekly_review"
            confidence = 0.6
        else:
            intent = "general"
            confidence = 0.4

        stagnant = len(
            kernel.query_state(
                "goals",
                status="active",
                last_activity_older_than_days=3,
                limit=500,
            )
        )
        deadlines = len(
            kernel.query_state(
                "goals",
                status="active",
                deadline_within_days=2,
                limit=500,
            )
        )

        if stagnant > 0:
            return {"intent": "check_stagnant_goals", "confidence": 0.9, "stagnant_count": stagnant}
        if deadlines > 0:
            return {"intent": "check_deadlines", "confidence": 0.85, "deadline_count": deadlines}

        return {"intent": intent, "confidence": confidence}

    def pre_fetch(self, predicted_intent: str) -> dict:
        """Pre-fetch data that the user is likely to need."""
        data = {}
        if predicted_intent in ("morning_brief", "check_stagnant_goals"):
            data["top_goals"] = kernel.query_state(
                "goals",
                status="active",
                limit=3,
                order="importance_desc_only",
            )
        if predicted_intent == "check_deadlines":
            data["upcoming_deadlines"] = kernel.query_state(
                "goals",
                status="active",
                deadline_within_days=2,
                limit=50,
            )
        return data


intent_predictor = IntentPredictor()
