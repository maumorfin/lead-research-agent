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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
console = Console()

# ── Shared instances ──────────────────────────────────────────────────────────
_thread_pool = ThreadPoolExecutor(max_workers=4)
app_graph, user_store = build_graph()
session_mgr  = SessionManager()


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
        "📡 Use /watch to get live race updates\n\n"
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
        "<b>Live</b>\n"
        "• What is happening right now in the Giro?\n"
        "• Who is leading the current stage?\n\n"
        "Use /model to switch models.\n"
        "Use /watch to subscribe to live race updates.\n"
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
    """Placeholder for Step 7 — /watch command."""
    await update.message.reply_text(
        "📡 <b>Live race updates</b>\n\n"
        "The /watch feature is coming in the next update.\n"
        "For now, ask me directly: <i>\"What is happening right now in the Giro?\"</i>",
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
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        console.print("[red]TELEGRAM_BOT_TOKEN not set in .env[/red]")
        sys.exit(1)

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start",   cmd_start))
    application.add_handler(CommandHandler("help",    cmd_help))
    application.add_handler(CommandHandler("status",  cmd_status))
    application.add_handler(CommandHandler("model",   cmd_model))
    application.add_handler(CommandHandler("watch",   cmd_watch))
    application.add_handler(
        CallbackQueryHandler(handle_model_callback, pattern="^model_")
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    console.print("[green]Bot is running. Press Ctrl+C to stop.[/green]")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
