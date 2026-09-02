"""Seed Day 4 defaults: prompts, business hours, bot configs, evaluation stub."""

DEFAULT_BUSINESS_HOURS = {
    "timezone": "UTC",
    "schedule": {
        "monday": {"start": "09:00", "end": "18:00"},
        "tuesday": {"start": "09:00", "end": "18:00"},
        "wednesday": {"start": "09:00", "end": "18:00"},
        "thursday": {"start": "09:00", "end": "18:00"},
        "friday": {"start": "09:00", "end": "18:00"},
    },
}

SUPPORT_AGENT_SYSTEM_TEMPLATE = """SYSTEM:
You are a helpful customer support agent for the company.
Rules:
- Answer ONLY using the provided company knowledge. Do not invent policies or actions.
- If knowledge is insufficient, say so briefly and ask for clarification.
- Be concise and professional.
- Reply in the same language as the customer's current message when possible.

COMPANY KNOWLEDGE:
{{knowledge}}

CUSTOMER:
{{customer}}

CONVERSATION SUMMARY:
{{summary}}

CONVERSATION:
{{history}}

CURRENT MESSAGE:
{{message}}
"""

GROUNDING_VALIDATOR_TEMPLATE = """You are a grounding validator. Given retrieved knowledge and a generated answer,
determine if the answer is fully supported by the knowledge.

Knowledge:
{{knowledge}}

Answer:
{{answer}}

Respond with JSON: {"grounded": <bool>, "score": <0.0-1.0>, "unsupported_claims": [<string>]}
"""

EVALUATION_STUB_CASES = [
    {
        "input": "How do I reset my password?",
        "expected_intent": "ACCOUNT_ACCESS",
        "expected_behavior": "ANSWER",
        "expected_answer_contains": ["password"],
        "expected_escalation": False,
        "knowledge_documents": ["Password Reset Guide"],
        "category": "FAQ",
    },
    {
        "input": "Can you change my billing plan?",
        "expected_intent": "BILLING",
        "expected_behavior": "ESCALATE",
        "expected_escalation": True,
        "category": "Billing",
    },
]
