"""
core/content_generator.py
Generates human-like email content using Faker for subject and body variation.
No links, no HTML tags in plain text. No fixed patterns.
"""
import random
from dataclasses import dataclass
from typing import Optional

try:
    from faker import Faker
    _faker = Faker("en_US")
    _FAKER_AVAILABLE = True
except ImportError:
    _faker = None
    _FAKER_AVAILABLE = False


# ── Subject line templates ─────────────────────────────────────────────────── #

SUBJECT_TEMPLATES = [
    "Following up on {topic}",
    "Quick question about {topic}",
    "Checking in about {topic}",
    "Thoughts on {topic}?",
    "Re: {topic} update",
    "{topic} - a quick note",
    "Regarding {topic}",
    "Quick note on {topic}",
    "Update on {topic}",
    "{topic} - wanted to share something",
    "Just checking in on {topic}",
    "A thought about {topic}",
    "Circling back on {topic}",
    "Any progress on {topic}?",
    "About {topic}",
]

TOPICS = [
    "the project timeline",
    "our last discussion",
    "the upcoming meeting",
    "the proposal",
    "Q4 planning",
    "the draft document",
    "the deliverables",
    "the partnership",
    "your recent feedback",
    "the budget review",
    "the resource allocation",
    "the strategy session",
    "the client presentation",
    "the workflow improvements",
    "the team update",
    "the quarterly goals",
    "the onboarding process",
    "the pending review",
]

# ── Opening lines ──────────────────────────────────────────────────────────── #

OPENERS = [
    "Hope you're doing well.",
    "Thanks for your time earlier.",
    "Just following up as promised.",
    "Wanted to check in quickly.",
    "Hope this finds you well.",
    "Hope your week is going well.",
    "Thanks for getting back to me.",
    "Just a quick note.",
    "I hope things are going smoothly on your end.",
    "Circling back on this.",
    "Wanted to reach out quickly.",
    "Hope you had a good weekend.",
]

# ── Body paragraph starters ────────────────────────────────────────────────── #

PARA_STARTERS = [
    "I wanted to touch base regarding",
    "I've been thinking about",
    "Just wanted to let you know that",
    "Following our last conversation,",
    "I had a few thoughts about",
    "Wanted to share a quick update on",
    "I came across something relevant to",
    "As we discussed,",
    "Building on what we talked about,",
    "I wanted to get your perspective on",
]

# ── Closing lines ──────────────────────────────────────────────────────────── #

CLOSERS = [
    "Let me know your thoughts.",
    "Looking forward to hearing from you.",
    "Happy to discuss further if helpful.",
    "Please let me know if you have any questions.",
    "Feel free to reach out anytime.",
    "Let me know if there's anything I can help with.",
    "Happy to hop on a call if needed.",
    "Let me know how you'd like to proceed.",
    "Looking forward to your response.",
    "Let me know what works best for you.",
]

SIGN_OFFS = [
    "Best regards,",
    "Best,",
    "Thanks,",
    "Warm regards,",
    "Kind regards,",
    "Regards,",
    "Many thanks,",
    "Cheers,",
]


@dataclass
class GeneratedContent:
    subject: str
    body: str           # Plain text, no HTML, no links


def _random_sentence() -> str:
    """Return a random human-sounding sentence."""
    if _FAKER_AVAILABLE:
        return _faker.sentence(nb_words=random.randint(8, 18))
    # Fallback if Faker not available
    fallbacks = [
        "I wanted to make sure we're aligned on the next steps.",
        "There are a few things I'd like your input on.",
        "Let me know if the timeline still works for you.",
        "I've reviewed the materials and have some thoughts.",
        "We may need to revisit a few of the assumptions.",
    ]
    return random.choice(fallbacks)


def _random_name() -> str:
    """Return a random first name."""
    if _FAKER_AVAILABLE:
        return _faker.first_name()
    return random.choice(["Alex", "Jordan", "Sam", "Morgan", "Taylor", "Riley"])


def generate_subject() -> str:
    """Generate a natural-sounding email subject."""
    template = random.choice(SUBJECT_TEMPLATES)
    topic = random.choice(TOPICS)
    return template.format(topic=topic)


def generate_body(
    sender_name: str,
    recipient_name: str = "",
    word_count_range: tuple = (80, 250),
) -> str:
    """
    Generate a human-like plain-text email body.
    No links, no HTML, no fixed patterns.
    """
    greeting_name = recipient_name.split()[0] if recipient_name else _random_name()
    opener = random.choice(OPENERS)
    sign_off = random.choice(SIGN_OFFS)

    # Build paragraphs
    target_words = random.randint(*word_count_range)
    paragraphs = []
    current_words = 0

    while current_words < target_words:
        starter = random.choice(PARA_STARTERS)
        topic = random.choice(TOPICS)
        sentences = [f"{starter} {topic}."]
        for _ in range(random.randint(1, 3)):
            sentences.append(_random_sentence())
        para = " ".join(sentences)
        paragraphs.append(para)
        current_words += len(para.split())

    closer = random.choice(CLOSERS)

    lines = [
        f"Hi {greeting_name},",
        "",
        opener,
        "",
    ]

    for para in paragraphs[:3]:  # max 3 body paragraphs
        lines.append(para)
        lines.append("")

    lines.extend([
        closer,
        "",
        sign_off,
        sender_name,
    ])

    return "\n".join(lines)


def generate_reply_body(
    sender_name: str,
    recipient_name: str,
    original_subject: str,
    original_body_snippet: str = "",
) -> str:
    """
    Generate a brief, natural reply to an email.
    Quotes a small snippet of the original.
    """
    greeting_name = recipient_name.split()[0] if recipient_name else _random_name()
    opener = random.choice([
        "Thanks for reaching out.",
        "Thanks for the update.",
        "Appreciate you getting back to me.",
        "Thanks for the note.",
        "Good to hear from you.",
    ])
    sign_off = random.choice(SIGN_OFFS)

    # Short reply body (2-3 sentences)
    body_sentences = [_random_sentence() for _ in range(random.randint(1, 3))]
    body = " ".join(body_sentences)

    closer = random.choice(CLOSERS)

    lines = [
        f"Hi {greeting_name},",
        "",
        opener,
        "",
        body,
        "",
        closer,
        "",
        sign_off,
        sender_name,
    ]

    # Optionally quote original (50% chance)
    if original_body_snippet and random.random() < 0.5:
        snippet_lines = original_body_snippet.strip().split("\n")[:4]
        quoted = "\n".join(f"> {l}" for l in snippet_lines)
        lines += ["", "---", quoted]

    return "\n".join(lines)


def generate_email(
    sender_name: str,
    recipient_name: str = "",
    is_reply: bool = False,
    original_subject: str = "",
    original_body_snippet: str = "",
) -> GeneratedContent:
    """
    Convenience function: generate complete email content.
    Returns GeneratedContent with subject and body.
    """
    if is_reply and original_subject:
        subject = (original_subject if original_subject.lower().startswith("re:")
                   else f"Re: {original_subject}")
        body = generate_reply_body(
            sender_name=sender_name,
            recipient_name=recipient_name,
            original_subject=original_subject,
            original_body_snippet=original_body_snippet,
        )
    else:
        subject = generate_subject()
        body = generate_body(
            sender_name=sender_name,
            recipient_name=recipient_name,
        )

    return GeneratedContent(subject=subject, body=body)
