import asyncio
import html
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from rich.console import Console

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction, ParseMode

from agent.graph import build_graph
from memory.session_manager import SessionManager
from memory.handoff import run_handoff
from memory.user_store import UserStore
from models.answer import CyclingAnswer
from config import AVAILABLE_MODELS, get_model, get_model_key, set_model
from tools.cycling_pcs import get_individual_ranking
from watcher.poller import RaceWatch, PollResult, run_watcher
from watcher.dispatcher import dispatch
from watcher.subscription_store import SubscriptionStore
from watcher.race_store import RaceStore
from watcher.calendar_agent import refresh_calendar

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
console = Console()

bot_app = None  # set in main(), used by _send_message

# ── Shared instances ──────────────────────────────────────────────────────────
_thread_pool = ThreadPoolExecutor(max_workers=4)
app_graph, user_store = build_graph()
session_mgr  = SessionManager()
sub_store    = SubscriptionStore()
race_store   = RaceStore()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline(question: str, chat_id: int, thread_id: str) -> CyclingAnswer:
    result = app_graph.invoke(
        {
            "question":          question,
            "resolved_question": "",
            "chat_id":           chat_id,
            "messages":          [],
            "findings":          {},
            "plan":              None,
            "answer":            None,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["answer"]


def _do_handoff(old_thread_id: str, chat_id: int):
    """Run session handoff synchronously (called from thread pool)."""
    try:
        run_handoff(old_thread_id, chat_id, app_graph, user_store)
        logger.info(f"Handoff complete for chat {chat_id}, thread {old_thread_id}")
    except Exception as e:
        logger.warning(f"Handoff failed for chat {chat_id}: {e}")


async def _send_message(chat_id: int, text: str) -> None:
    """Send a proactive Telegram message to a user."""
    try:
        await bot_app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"[send_message] Failed to send to {chat_id}: {e}")


async def _watcher_loop() -> None:
    """
    Background watcher loop.
    Polls all subscribed races and dispatches notifications.
    Runs as an asyncio task alongside the bot.
    """
    logger.info("[watcher] Background watcher started")

    # Refresh calendar on startup
    await asyncio.get_event_loop().run_in_executor(
        _thread_pool,
        lambda: asyncio.run(refresh_calendar(race_store)),
    )

    while True:
        try:
            # Refresh calendar if data is stale (runs at most once per 20h)
            if race_store.needs_refresh():
                await asyncio.get_event_loop().run_in_executor(
                    _thread_pool,
                    lambda: asyncio.run(refresh_calendar(race_store)),
                )

            subscriptions = sub_store.build_subscriptions_dict()

            if not subscriptions:
                logger.debug("[watcher] No active subscriptions — sleeping")
                await asyncio.sleep(60)
                continue

            watched_races = [
                RaceWatch(race_slug=slug, year=year, stage=stage)
                for slug, year, stage in sub_store.get_all_watched_races()
            ]

            from watcher.poller import poll_once
            for race in watched_races:
                try:
                    result = await poll_once(race)
                    if result.error:
                        logger.warning(f"[watcher] Poll error: {result.error}")
                    elif result.changed:
                        sent = await dispatch(
                            result=result,
                            subscriptions=subscriptions,
                            user_store=user_store,
                            send_message_fn=_send_message,
                        )
                        logger.info(f"[watcher] Sent {sent} notification(s)")
                except Exception as e:
                    logger.error(f"[watcher] Error polling {race.race_slug}: {e}")

            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"[watcher] Unexpected error in watcher loop: {e}")
            await asyncio.sleep(60)


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_answer(answer: CyclingAnswer) -> str:
    parts = [f"🚴 <b>{html.escape(answer.answer)}</b>"]

    if answer.data_points:
        parts.append("\n📊 <b>Key facts:</b>")
        for point in answer.data_points:
            parts.append(f"• {html.escape(point)}")

    if answer.follow_up_suggestions:
        parts.append("\n💡 <b>You might also want to ask:</b>")
        for i, s in enumerate(answer.follow_up_suggestions, 1):
            parts.append(f"{i}. {html.escape(s)}")

    if answer.source_note:
        parts.append(f"\n<i>{html.escape(answer.source_note)}</i>")

    return "\n".join(parts)


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🚴 <b>Pro Cycling Intelligence Agent</b>\n\n"
        "Ask me anything about professional cycling — standings, race results, "
        "rider profiles, stage data, and more.\n\n"
        "<b>Try asking:</b>\n"
        "• Who is leading the WorldTour right now?\n"
        "• What are Tadej Pogačar's results in 2026?\n"
        "• Who won stage 10 of the Giro d'Italia 2026?\n"
        "• Show me the startlist for the Tour de France 2026\n\n"
        "⚙️ Use /model to switch between Claude and Groq\n"
        "📡 Use /watch to subscribe to live race updates\n"
        "👁 Use /watching to see your subscriptions\n"
        "🔕 Use /unwatch to remove all subscriptions\n\n"
        "Just type your question and I'll research it for you."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🚴 <b>Example questions by category</b>\n\n"
        "<b>Standings</b>\n"
        "• Who leads the UCI WorldTour individual ranking?\n"
        "• Show me the top 10 WorldTour teams\n\n"
        "<b>Riders</b>\n"
        "• What are Remco Evenepoel's stats?\n"
        "• Show me Jonas Vingegaard's 2026 results\n\n"
        "<b>Races</b>\n"
        "• Who won the 2026 Giro d'Italia?\n"
        "• What were the GC results at Paris-Roubaix 2026?\n\n"
        "<b>Stages</b>\n"
        "• What happened in stage 3 of the Tour de France 2026?\n"
        "• Who won stage 1 of the Vuelta 2026?\n\n"
        "<b>Live subscriptions</b>\n"
        "/watch — subscribe to live race updates\n"
        "/watching — see your active subscriptions\n"
        "/unwatch — remove all subscriptions\n\n"
        "Use /model to switch models.\n"
        "Use /status for current WorldTour top 5."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    try:
        loop = asyncio.get_event_loop()
        riders = await loop.run_in_executor(_thread_pool, get_individual_ranking, 5)

        if riders and not any("error" in str(r) for r in riders):
            lines = ["🏆 <b>UCI WorldTour Top 5</b>\n"]
            for r in riders[:5]:
                rank  = r.get("rank", "?")
                name  = html.escape(str(r.get("name", r.get("rider_name", "Unknown"))))
                team  = html.escape(str(r.get("team", r.get("team_name", ""))))
                pts   = r.get("points", "")
                lines.append(f"{rank}. <b>{name}</b> ({team}) — {pts} pts")
            lines.append("\n<i>Source: procyclingstats.com</i>")
            text = "\n".join(lines)
        else:
            text = "⚠️ Could not fetch live standings. Try asking: <i>Who leads the WorldTour?</i>"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Status command failed: {e}")
        await update.message.reply_text(
            "⚠️ Could not fetch standings right now. Please try again in a moment."
        )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id     = update.effective_chat.id
    current_key = get_model_key(chat_id)

    keyboard = [
        [InlineKeyboardButton(
            f"{'✅ ' if current_key == key else ''}{model.display_name}",
            callback_data=f"model_{key}",
        )]
        for key, model in AVAILABLE_MODELS.items()
    ]

    current = get_model(chat_id)
    await update.message.reply_text(
        f"Current model: <b>{current.display_name}</b>\n\nChoose a model:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available races with inline buttons to subscribe."""
    chat_id = update.effective_chat.id

    current_subs = {
        f"{s.race_slug}_{s.year}_{s.stage}"
        for s in sub_store.get_subscriptions(chat_id)
    }

    live_races     = race_store.get_live()
    upcoming_races = race_store.get_upcoming()

    keyboard = []

    if live_races:
        keyboard.append([InlineKeyboardButton(
            "── Live now ──", callback_data="watch_header"
        )])
        for race in live_races:
            key        = f"{race.slug}_{race.year}_{race.current_stage}"
            subscribed = key in current_subs
            label = (
                f"{'✅ ' if subscribed else '📡 '}"
                f"{race.name} — Stage {race.current_stage}"
            )
            keyboard.append([InlineKeyboardButton(
                label,
                callback_data=f"watch_{race.slug}_{race.year}_{race.current_stage}",
            )])

    if upcoming_races:
        keyboard.append([InlineKeyboardButton(
            "── Coming up ──", callback_data="watch_header"
        )])
        for race in upcoming_races:
            key        = f"{race.slug}_{race.year}_{race.current_stage}"
            subscribed = key in current_subs
            label = (
                f"{'✅ ' if subscribed else '🔔 '}"
                f"{race.name}"
            )
            keyboard.append([InlineKeyboardButton(
                label,
                callback_data=f"watch_{race.slug}_{race.year}_{race.current_stage}",
            )])

    if not keyboard:
        await update.message.reply_text(
            "No races available to subscribe to right now.\n"
            "Check back during the next race.",
        )
        return

    text = (
        "📡 <b>Live race updates</b>\n\n"
        "Subscribe to get notified when something important happens "
        "during a stage — attacks, crashes, time gaps, stage wins.\n\n"
        "Tap a race to toggle your subscription:"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all subscriptions for this user."""
    chat_id = update.effective_chat.id
    subs    = sub_store.get_subscriptions(chat_id)

    if not subs:
        await update.message.reply_text(
            "You don't have any active subscriptions.\n"
            "Use /watch to subscribe to a race."
        )
        return

    sub_store.unsubscribe(chat_id)
    race_names = ", ".join(
        s.race_slug.replace("-", " ").title() for s in subs
    )
    await update.message.reply_text(
        f"✅ Unsubscribed from: {race_names}\n\n"
        f"Use /watch to subscribe again any time."
    )


async def cmd_watching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show what races the user is currently subscribed to."""
    chat_id = update.effective_chat.id
    subs    = sub_store.get_subscriptions(chat_id)

    if not subs:
        await update.message.reply_text(
            "You're not subscribed to any races.\n"
            "Use /watch to subscribe."
        )
        return

    lines = ["📡 <b>Your live subscriptions:</b>\n"]
    for s in subs:
        race = race_store.get(s.race_slug)
        name = race.name if race else s.race_slug.replace("-", " ").title()
        lines.append(f"• {name} — Stage {s.stage}")

    lines.append(
        "\nYou'll get a message when something important happens.\n"
        "Use /unwatch to remove all subscriptions."
    )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


# ── Callback handlers ─────────────────────────────────────────────────────────

async def handle_model_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query   = update.callback_query
    await query.answer()

    key     = query.data.replace("model_", "")
    chat_id = query.message.chat_id

    try:
        model = set_model(chat_id, key)
        await query.edit_message_text(
            f"✅ Switched to <b>{model.display_name}</b>\n\n"
            f"All questions in this chat will use this model.",
            parse_mode=ParseMode.HTML,
        )
    except ValueError:
        await query.edit_message_text("❌ Unknown model. Please try /model again.")


async def handle_watch_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle inline button press from /watch menu.
    Toggles subscription on/off for the selected race.
    """
    query   = update.callback_query
    await query.answer()

    if query.data == "watch_header":
        return

    chat_id = query.message.chat_id

    # Parse callback data: "watch_{slug}_{year}_{stage}"
    parts = query.data.replace("watch_", "", 1).rsplit("_", 2)
    if len(parts) != 3:
        await query.edit_message_text("❌ Invalid selection.")
        return

    race_slug = parts[0]
    try:
        year  = int(parts[1])
        stage = int(parts[2])
    except ValueError:
        await query.edit_message_text("❌ Invalid selection.")
        return

    race = race_store.get(race_slug)
    if not race:
        await query.edit_message_text("❌ Race not found.")
        return

    existing = sub_store.get_subscribers(race_slug, year, stage)

    if chat_id in existing:
        sub_store.unsubscribe(chat_id, race_slug)
        await query.edit_message_text(
            f"🔕 Unsubscribed from <b>{race.name}</b> Stage {stage}.\n\n"
            f"Use /watch to subscribe again.",
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"[watch] chat {chat_id} unsubscribed from {race_slug} stage {stage}")
    else:
        sub_store.subscribe(chat_id, race_slug, year, stage)
        await query.edit_message_text(
            f"✅ Subscribed to <b>{race.name}</b> Stage {stage}!\n\n"
            f"You'll get a message when something important happens — "
            f"attacks, crashes, time gaps, stage wins.\n\n"
            f"Use /unwatch to remove all subscriptions.",
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"[watch] chat {chat_id} subscribed to {race_slug} stage {stage}")


# ── Main message handler ──────────────────────────────────────────────────────

async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    question = update.message.text.strip()
    chat_id  = update.effective_chat.id

    if not question:
        return

    await context.bot.send_chat_action(
        chat_id=chat_id, action=ChatAction.TYPING
    )

    # ── Session management ────────────────────────────────────────────────────
    session = session_mgr.get_or_create(chat_id)

    # If session just expired, run handoff in background before starting new one
    if session.is_new and session.old_thread_id:
        logger.info(
            f"Session timeout for chat {chat_id} — "
            f"running handoff from {session.old_thread_id}"
        )
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _thread_pool,
            lambda: _do_handoff(session.old_thread_id, chat_id),
        )

    # ── Show user which model is active ──────────────────────────────────────
    current_model = get_model(chat_id)
    await update.message.reply_text(
        f"🔍 Researching with <b>{current_model.display_name}</b>...",
        parse_mode=ParseMode.HTML,
    )

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        loop   = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            _thread_pool,
            lambda: _run_pipeline(question, chat_id, session.thread_id),
        )
        await update.message.reply_text(
            _format_answer(answer),
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"Pipeline failed for chat {chat_id}, question '{question}': {e}")
        console.print_exception()
        await update.message.reply_text(
            "Sorry, I couldn't find data for that question. "
            "Try rephrasing or ask about a specific race or rider.\n\n"
            f"<i>Model: {current_model.display_name}</i>",
            parse_mode=ParseMode.HTML,
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    global bot_app

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        console.print("[red]TELEGRAM_BOT_TOKEN not set in .env[/red]")
        sys.exit(1)

    bot_app = Application.builder().token(token).build()

    bot_app.add_handler(CommandHandler("start",   cmd_start))
    bot_app.add_handler(CommandHandler("help",    cmd_help))
    bot_app.add_handler(CommandHandler("status",  cmd_status))
    bot_app.add_handler(CommandHandler("model",   cmd_model))
    bot_app.add_handler(CommandHandler("watch",    cmd_watch))
    bot_app.add_handler(CommandHandler("unwatch",  cmd_unwatch))
    bot_app.add_handler(CommandHandler("watching", cmd_watching))
    bot_app.add_handler(
        CallbackQueryHandler(handle_model_callback, pattern="^model_")
    )
    bot_app.add_handler(
        CallbackQueryHandler(handle_watch_callback, pattern="^watch_")
    )
    bot_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    async def post_init(_application):
        asyncio.create_task(_watcher_loop())
        logger.info("[bot] Background watcher task started")

    bot_app.post_init = post_init

    console.print("[green]Bot is running with live race watcher. Press Ctrl+C to stop.[/green]")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
