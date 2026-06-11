INTENT_KEYWORDS: dict[str, list[str]] = {
    "quiz": [
        "出题",
        "考试",
        "测验",
        "quiz",
        "选择题",
        "填空题",
        "测试一下",
        "考考我",
        "出几道",
    ],
    "review": [
        "错题",
        "复习",
        "弱点",
        "review",
        "mistake",
        "薄弱",
        "掌握情况",
    ],
}


def classify_intent(message: str) -> str:
    """Classify the user's intent by scanning the message for keywords.

    Prioritizes quiz over review. Falls back to "qa" if no keywords match.
    """
    lower = message.lower()
    for intent in ("quiz", "review"):
        for kw in INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return "qa"
