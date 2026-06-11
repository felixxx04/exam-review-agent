---
name: adaptive-quiz-generation
description: Generate adaptive quiz questions grounded in source material with difficulty adjustment, source citation, and distractor quality control. Use this skill when building quiz/test generation systems, adaptive learning features, or when the user mentions "quiz generation", "出题", "test generation", "adaptive difficulty", "exam questions", or "练习题". Critical for preventing hallucinated questions — every question must cite its source.
---

# Adaptive Quiz Generation

Generate quiz questions that are grounded in source material, adapt to student ability, and resist hallucination through mandatory source citation.

Based on patterns from hello-agents LearningAgent (`specialist/quiz_generator.py`) and educational AI best practices.

## Core Principle: Ground Every Question

Every question must be traceable to a specific source chunk. If no supporting chunk exists, the question must not be generated.

```python
@dataclass
class Question:
    id: str
    text: str
    question_type: str  # "multiple_choice" | "fill_blank" | "short_answer"
    options: list[str]  # for multiple choice
    correct_answer: str
    explanation: str
    source_chunk_ids: list[str]  # REQUIRED: link back to source material
    difficulty: float  # 0.0 - 1.0
    topic: str
    concept: str
```

## Difficulty Adjustment

The key insight from LearningAgent: use a float difficulty scale and adjust per-question for diversity within a single quiz.

```python
def generate_quiz(chunks: list[Chunk], base_difficulty: float, count: int) -> list[Question]:
    questions = []
    for i in range(count):
        # Spread difficulty around the base for variety
        # e.g., base=0.5, count=5 → difficulties: [0.3, 0.4, 0.5, 0.6, 0.7]
        adjusted = min(1.0, max(0.0, base_difficulty + (i - count // 2) * 0.1))
        q = generate_one_question(chunks, adjusted)
        questions.append(q)
    return questions
```

### Adaptive Difficulty from Tracker

When the Tracker Agent identifies weak areas, it sends a difficulty signal:

```python
def get_adaptive_difficulty(concept: str, tracker: TrackerService) -> float:
    accuracy = tracker.get_accuracy(concept)
    attempts = tracker.get_attempt_count(concept)

    if accuracy < 0.3 and attempts >= 3:
        return 0.2  # Very wrong, start easy
    elif accuracy < 0.6:
        return 0.4  # Struggling, keep it moderate
    elif accuracy < 0.8:
        return 0.6  # Getting there, push harder
    else:
        return 0.8  # Strong, challenge them
```

## Question Types and Prompt Engineering

### Multiple Choice

```python
QUIZ_PROMPT = """基于以下课程内容生成一道{question_type}题目。

难度等级: {difficulty}/1.0
知识点: {concept}

课程内容:
{chunk_text}

要求:
1. 题目必须基于上述内容，不得编造
2. 正确答案必须有明确来源
3. 错误选项必须是"合理的干扰项"——来自同一领域、相近数值或常见误解
4. 不要出"以下哪个不是"这种否定题

输出JSON格式:
{{
    "question": "题目文本",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "correct": "A",
    "explanation": "为什么A正确，其他选项为什么错",
    "source_chunk_id": "{chunk_id}"
}}"""
```

### Fill-in-Blank

- Mask key terms, not filler words
- Provide a rubric of acceptable answers

### Short Answer

- Generate with a rubric (key points expected), not just a model answer
- Scoring compares student answer against rubric points, not against regenerated answer

## Distractor Quality Rules

Bad distractors make quizzes useless. Follow these rules:

| Rule | Example |
|------|---------|
| Same domain as correct answer | If answer is "线粒体", distractors should be other organelles, not random biology terms |
| Close but wrong values | If answer is "3.14", use "3.41", "2.71" not "100" |
| Common misconceptions | If students often confuse X and Y, make one a distractor for the other |
| Not obviously wrong | A student who doesn't know the answer should genuinely consider each option |

## Scoring with Source Citations

When grading student answers, the explanation must cite source material:

```python
def explain_wrong_answer(question: Question, student_answer: str) -> str:
    return f"""
你的答案 "{student_answer}" 不正确。

正确答案是: {question.correct_answer}

为什么正确: {question.explanation}
来源: {get_source_text(question.source_chunk_ids)}

你可能的误解: 基于你的答案，你可能混淆了...
"""
```

## Source

Derived from hello-agents LearningAgent (`specialist/quiz_generator.py`) and educational AI research on question generation quality.
