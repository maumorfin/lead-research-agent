"""
Keyword rule engine — pure Python, no LLM, no network.
Decides whether a live race diff is worth sending to the Groq judge.

Design principle: fast and cheap. Any diff that passes here costs one
Groq call (~$0.0001). Any diff that fails here costs nothing.
"""
import re
from dataclasses import dataclass


# ── Keyword lists ─────────────────────────────────────────────────────────────

# High-signal racing events — almost always worth a notification
HIGH_SIGNAL_KEYWORDS = [
    "attack",
    "attacks",
    "attacked",
    "breakaway",
    "break",
    "crash",
    "crashed",
    "fall",
    "abandon",
    "abandons",
    "dropped",
    "gap opening",
    "gap is",
    "time gap",
    "solo",
    "alone",
    "caught",
    "bridge",
    "bridged",
    "counter",
    "accelerat",      # covers acceleration, accelerates, accelerating
    "distanc",        # covers distance, distances, distancing
]

# Medium-signal events — worth checking against user profile
MEDIUM_SIGNAL_KEYWORDS = [
    "km to go",
    "kilometers to go",
    "summit",
    "peak",
    "col",
    "descent",
    "sprint",
    "sprinting",
    "peloton",
    "grupetto",
    "chasing",
    "chase group",
    "time trial",
    "jersey",
    "maglia",
    "virtual",
    "gc",
    "general classification",
    "stage win",
    "wins the stage",
    "winner",
]

# Low-signal — ignore even if user follows the race
LOW_SIGNAL_PATTERNS = [
    r"\d+ km done",           # routine km markers
    r"average speed",
    r"statistics",
    r"most riders",
    r"weather",
    r"temperature",
    r"wind",
    r"family active",         # PCS sidebar widgets
    r"longest streak",
    r"most wins",
    r"request statistic",
]


# ── Rule result ───────────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    passes:           bool
    reason:           str        # human-readable explanation for logging
    signal_level:     str        # "high", "medium", "low", "none"
    matched_keywords: list[str]  # which keywords triggered
    rider_match:      bool       # True if a followed rider was mentioned


# ── Main rule function ────────────────────────────────────────────────────────

def evaluate(diff: str, user_profile: dict | None = None) -> RuleResult:
    """
    Evaluate a diff string against the rule set.

    Args:
        diff:         The changed content extracted by the poller
        user_profile: Optional user profile dict with "riders_mentioned" list
                      If None, only keyword rules apply (no rider matching)

    Returns:
        RuleResult with passes=True if the diff should go to the Groq judge
    """
    if not diff or len(diff.strip()) < 20:
        return RuleResult(
            passes=False,
            reason="Diff too short to be meaningful",
            signal_level="none",
            matched_keywords=[],
            rider_match=False,
        )

    diff_lower = diff.lower()

    # ── Rule 1: Low-signal filter — reject immediately ────────────────────────
    for pattern in LOW_SIGNAL_PATTERNS:
        if re.search(pattern, diff_lower):
            # Only reject if there are NO high-signal keywords present too
            high_matches = [kw for kw in HIGH_SIGNAL_KEYWORDS if kw in diff_lower]
            if not high_matches:
                return RuleResult(
                    passes=False,
                    reason=f"Low-signal pattern matched: '{pattern}'",
                    signal_level="low",
                    matched_keywords=[],
                    rider_match=False,
                )

    # ── Rule 2: High-signal keywords — always pass ────────────────────────────
    high_matches = [kw for kw in HIGH_SIGNAL_KEYWORDS if kw in diff_lower]
    if high_matches:
        return RuleResult(
            passes=True,
            reason=f"High-signal keywords: {high_matches}",
            signal_level="high",
            matched_keywords=high_matches,
            rider_match=_check_rider_match(diff_lower, user_profile),
        )

    # ── Rule 3: Medium-signal + rider match — pass ────────────────────────────
    medium_matches = [kw for kw in MEDIUM_SIGNAL_KEYWORDS if kw in diff_lower]
    rider_match    = _check_rider_match(diff_lower, user_profile)

    if medium_matches and rider_match:
        return RuleResult(
            passes=True,
            reason=f"Medium-signal keywords {medium_matches} + followed rider mentioned",
            signal_level="medium",
            matched_keywords=medium_matches,
            rider_match=True,
        )

    # ── Rule 4: Medium-signal only — pass if strong enough ───────────────────
    if len(medium_matches) >= 2:
        return RuleResult(
            passes=True,
            reason=f"Multiple medium-signal keywords: {medium_matches}",
            signal_level="medium",
            matched_keywords=medium_matches,
            rider_match=rider_match,
        )

    # ── Default: not interesting enough ───────────────────────────────────────
    return RuleResult(
        passes=False,
        reason=f"No significant keywords found (medium: {medium_matches})",
        signal_level="none",
        matched_keywords=medium_matches,
        rider_match=rider_match,
    )


def _check_rider_match(diff_lower: str, user_profile: dict | None) -> bool:
    """
    Check if any rider the user follows is mentioned in the diff.
    Converts slug format to name format for matching:
    "tadej-pogacar" → checks for "pogacar" in diff
    """
    if not user_profile:
        return False

    followed = user_profile.get("riders_mentioned", [])
    if not followed:
        return False

    for rider_slug in followed:
        # Extract last name from slug — most recognizable in race coverage
        parts = rider_slug.split("-")
        last_name = parts[-1] if parts else rider_slug

        # Also try full name without hyphens
        full_name = " ".join(parts)

        if last_name in diff_lower or full_name in diff_lower:
            return True

    return False


def evaluate_for_users(diff: str, user_profiles: dict[int, dict]) -> dict[int, RuleResult]:
    """
    Evaluate a diff against multiple user profiles simultaneously.
    Returns a dict of {chat_id: RuleResult} for users where passes=True.

    Use this when a race has multiple subscribers — avoids re-running
    keyword detection for each user separately.
    """
    if not diff or len(diff.strip()) < 20:
        return {}

    diff_lower = diff.lower()

    # Run keyword detection once, shared across all users
    high_matches   = [kw for kw in HIGH_SIGNAL_KEYWORDS   if kw in diff_lower]
    medium_matches = [kw for kw in MEDIUM_SIGNAL_KEYWORDS if kw in diff_lower]

    # Low-signal filter
    is_low_signal = False
    if not high_matches:
        for pattern in LOW_SIGNAL_PATTERNS:
            if re.search(pattern, diff_lower):
                is_low_signal = True
                break

    if is_low_signal:
        return {}

    results = {}
    for chat_id, profile in user_profiles.items():
        rider_match = _check_rider_match(diff_lower, profile)

        if high_matches:
            results[chat_id] = RuleResult(
                passes=True,
                reason=f"High-signal: {high_matches}",
                signal_level="high",
                matched_keywords=high_matches,
                rider_match=rider_match,
            )
        elif medium_matches and (rider_match or len(medium_matches) >= 2):
            results[chat_id] = RuleResult(
                passes=True,
                reason=f"Medium-signal: {medium_matches}",
                signal_level="medium",
                matched_keywords=medium_matches,
                rider_match=rider_match,
            )

    return results
