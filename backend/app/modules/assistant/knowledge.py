"""Curated site knowledge for the assistant: the pages it may link to and per-page context.

The model never sees page contents. The browser sends only the current path; it is matched here
against known routes and replaced with a short, fixed description. Unknown paths give no context.
Keep this list in sync with the frontend routes (frontend/src/app) and their availability.
This module is the place to plug in knowledge retrieval later.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    pattern: str  # route path; ":id" matches one dynamic segment
    title: str
    description: str
    linkable: bool = True  # listed for the model to link to (dynamic routes are not)

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile("^" + re.sub(r":[a-z_]+", r"[^/]+", self.pattern) + "/?$")


PAGES: tuple[Page, ...] = (
    Page("/", "Home", "IELTS MASTER home page: overview of the platform and its modules."),
    Page(
        "/register", "Create account", "Create a free account to save attempts and get AI feedback."
    ),
    Page("/sign-in", "Sign in", "Sign in to an existing account."),
    Page("/forgot-password", "Forgot password", "Request a password-reset email."),
    Page(
        "/listening",
        "Listening",
        "Listening practice tests with audio, instant scoring and answer review (sign-in needed).",
    ),
    Page("/listening/history", "Listening history", "Past Listening attempts and their scores."),
    Page(
        "/listening/tests/:id",
        "Listening test details",
        "Details of one Listening test before starting it.",
        linkable=False,
    ),
    Page(
        "/listening/attempts/:id",
        "Listening result",
        "The result and answer review of one finished Listening attempt.",
        linkable=False,
    ),
    Page(
        "/reading",
        "Reading",
        "Academic Reading tests with every question type, timing and evidence review.",
    ),
    Page("/reading/history", "Reading history", "Past Reading attempts and their scores."),
    Page(
        "/reading/tests/:id",
        "Reading test details",
        "Details of one Reading test before starting it.",
        linkable=False,
    ),
    Page(
        "/reading/attempts/:id",
        "Reading result",
        "The result and answer review of one finished Reading attempt.",
        linkable=False,
    ),
    Page(
        "/writing",
        "Writing",
        "Writing Task 1 and Task 2 practice with AI-estimated band feedback after submission.",
    ),
    Page(
        "/writing/tests/:id",
        "Writing test details",
        "Details of one Writing test before starting it.",
        linkable=False,
    ),
    Page(
        "/writing/submissions/:id",
        "Writing feedback",
        "AI feedback for one submitted Writing response.",
        linkable=False,
    ),
    Page(
        "/speaking",
        "Speaking",
        "Speaking practice: record answers to Part 1, 2 and 3 questions for AI feedback, or talk "
        "to the AI examiner in a live Speaking room.",
    ),
    Page(
        "/speaking/practice",
        "Speaking practice by question",
        "Practise individual Speaking questions by recording answers.",
    ),
    Page(
        "/speaking/tests/:id",
        "Speaking test details",
        "Details of one Speaking test before starting it.",
        linkable=False,
    ),
    Page("/account/password", "Change password", "Change the account password."),
    Page("/terms", "Terms of Service", "The Terms of Service."),
    Page("/privacy", "Privacy Policy", "How IELTS MASTER handles personal data."),
    Page("/status", "Service status", "Current status of the IELTS MASTER service."),
    # Not built yet: the assistant must say so instead of describing features.
    Page("/dashboard", "Dashboard (coming soon)", "Planned: progress overview. Not available yet."),
    Page(
        "/library", "Book library (coming soon)", "Planned: browse IELTS books. Not available yet."
    ),
    Page(
        "/practice",
        "Practice (coming soon)",
        "Planned: practice by question type. Not available yet.",
    ),
    Page(
        "/mock-tests",
        "Mock tests (coming soon)",
        "Planned: full timed mock exams. Not available yet.",
    ),
    Page("/progress", "Progress (coming soon)", "Planned: band trends. Not available yet."),
    Page("/coach", "AI coach (coming soon)", "Planned: personal study plans. Not available yet."),
)


def site_pages() -> str:
    return "\n".join(f"- {p.pattern} ({p.title}): {p.description}" for p in PAGES if p.linkable)


def page_context(path: str | None) -> str | None:
    if not path:
        return None
    clean = path.split("?", 1)[0].split("#", 1)[0]
    for page in PAGES:
        if page.regex.match(clean):
            return f"{page.title} page. {page.description}"
    return None
