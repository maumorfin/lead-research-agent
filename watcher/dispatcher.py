"""
Dispatcher — receives poll results and routes notifications to users.
Called by run_watcher() via the on_change callback.
"""
import logging
from watcher.poller import PollResult
from watcher.rules import evaluate_for_users
from watcher.judge import judge_event_for_users

logger = logging.getLogger(__name__)


async def dispatch(
    result:            PollResult,
    subscriptions:     dict[str, set[int]],
    user_store,
    send_message_fn,
) -> int:
    """
    Process a poll result and send notifications to subscribed users.

    Args:
        result:          PollResult from the poller (changed=True guaranteed)
        subscriptions:   dict mapping race_key → set of chat_ids watching it
                         race_key format: "{race_slug}_{year}_{stage}"
        user_store:      UserStore instance for fetching user profiles
        send_message_fn: async callable(chat_id, text) that sends a Telegram message

    Returns:
        Number of notifications sent
    """
    race_key = (
        f"{result.race_watch.race_slug}_"
        f"{result.race_watch.year}_"
        f"{result.race_watch.stage}"
    )

    watching = subscriptions.get(race_key, set())
    if not watching:
        logger.debug(f"[dispatcher] No subscribers for {race_key}")
        return 0

    logger.info(
        f"[dispatcher] {race_key} changed — "
        f"checking {len(watching)} subscriber(s)"
    )

    # Fetch user profiles for all watching users
    user_profiles = {}
    for chat_id in watching:
        try:
            profile = user_store.get(chat_id)
            user_profiles[chat_id] = profile or {}
        except Exception as e:
            logger.warning(f"[dispatcher] Could not fetch profile for {chat_id}: {e}")
            user_profiles[chat_id] = {}

    # Gate 1 — rule engine (free, per-user)
    rule_results = evaluate_for_users(result.diff, user_profiles)
    if not rule_results:
        logger.debug(f"[dispatcher] Rule engine blocked all users for {race_key}")
        return 0

    logger.info(
        f"[dispatcher] Rule engine passed {len(rule_results)}/{len(watching)} users"
    )

    # Gate 2 — Groq judge (one call, shared result)
    judge_results = judge_event_for_users(
        diff=result.diff,
        race_slug=result.race_watch.race_slug,
        year=result.race_watch.year,
        stage=result.race_watch.stage,
        user_profiles={
            chat_id: user_profiles[chat_id]
            for chat_id in rule_results
        },
    )
    if not judge_results:
        logger.info(f"[dispatcher] Groq judge blocked notification for {race_key}")
        return 0

    # Send notifications
    sent = 0
    for chat_id, judge_result in judge_results.items():
        if not judge_result.should_notify:
            continue
        try:
            race_name = result.race_watch.race_slug.replace("-", " ").title()
            header    = f"📡 <b>{race_name} — Stage {result.race_watch.stage}</b>\n\n"
            text      = header + judge_result.message
            await send_message_fn(chat_id, text)
            sent += 1
            logger.info(f"[dispatcher] Notified chat {chat_id}: {judge_result.message[:60]}")
        except Exception as e:
            logger.error(f"[dispatcher] Failed to send to {chat_id}: {e}")

    return sent
