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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatAction, ParseMode

from agent.planner import create_plan
from agent.executor import execute_plan
from agent.synthesizer import synthesize
from models.answer import CyclingAnswer
from tools.cycling_pcs import get_individual_ranking
from config import AVAILABLE_MODELS, set_model, get_model, get_model_key

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
console = Console()

_thread_pool = ThreadPoolExecutor(max_workers=4)


def _run_pipeline(question: str, chat_id: int) -> CyclingAnswer:
    plan = create_plan(question, chat_id=chat_id)
    findings = execute_plan(plan)
    return synthesize(question, findings, chat_id=chat_id)


def _format_answer(answer: CyclingAnswer) -> str:
    parts: list[str] = []

    parts.append(f"🚴 <b>{html.escape(answer.answer)}</b>")

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


_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("⚙️ Change Model")]],
    resize_keyboard=True,
    is_persistent=True,
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🚴 <b>Pro Cycling Intelligence Agent</b>\n\n"
        "Ask me anything about professional cycling — standings, race results, "
        "rider profiles, stage data, and more.\n\n"
        "⚙️ Use the button below to switch between Claude Sonnet, Claude Haiku, and Groq Llama 3.3\n\n"
        "<b>Try asking:</b>\n"
        "• Who is leading the WorldTour right now?\n"
        "• What are Tadej Pogačar's results in 2026?\n"
        "• Who won stage 10 of the Giro d'Italia 2026?\n"
        "• Show me the startlist for the Tour de France 2026\n\n"
        "Just type your question and I'll research it for you."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_REPLY_KEYBOARD)


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
        "<b>Startlists</b>\n"
        "• Who is riding the Tour de France 2026?\n\n"
        "<b>Live</b>\n"
        "• What is happening in the race right now?\n"
        "• Show me the current situation in stage 10\n\n"
        "Use /status for the current WorldTour top 5.\n"
        "Use /model to switch AI models."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        loop = asyncio.get_event_loop()
        riders = await loop.run_in_executor(_thread_pool, get_individual_ranking, 5)

        if riders and not any("error" in r for r in riders):
            lines = ["🏆 <b>UCI WorldTour Top 5</b>\n"]
            for r in riders[:5]:
                rank = r.get("rank", "?")
                name = html.escape(str(r.get("name", "Unknown")))
                team = html.escape(str(r.get("team", "")))
                points = r.get("points", "")
                lines.append(f"{rank}. <b>{name}</b> ({team}) — {points} pts")
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
    chat_id = update.effective_chat.id
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
        f"Current model: <b>{html.escape(current.display_name)}</b>\n\nChoose a model:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def handle_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    key = query.data.replace("model_", "")
    chat_id = query.message.chat_id

    try:
        model = set_model(chat_id, key)
        await query.edit_message_text(
            f"✅ Switched to <b>{html.escape(model.display_name)}</b>\n\n"
            "All future questions in this chat will use this model.",
            parse_mode=ParseMode.HTML,
        )
    except ValueError:
        await query.edit_message_text("❌ Unknown model. Please try again.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text.strip()
    chat_id = update.effective_chat.id
    if not question:
        return

    if question == "⚙️ Change Model":
        await cmd_model(update, context)
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    current_model = get_model(chat_id)
    await update.message.reply_text(
        f"🔍 Researching with <b>{html.escape(current_model.display_name)}</b>...",
        parse_mode=ParseMode.HTML,
    )

    try:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            _thread_pool,
            lambda: _run_pipeline(question, chat_id),
        )
        text = _format_answer(answer)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Pipeline failed for '{question}': {e}")
        console.print_exception()
        await update.message.reply_text(
            "Sorry, I couldn't find data for that question. "
            "Try rephrasing or ask about a specific race or rider.\n\n"
            f"<i>Model used: {html.escape(current_model.display_name)}</i>",
            parse_mode=ParseMode.HTML,
        )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        console.print("[red]TELEGRAM_BOT_TOKEN not set in .env[/red]")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CallbackQueryHandler(handle_model_callback, pattern="^model_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    console.print("[green]Bot is running. Press Ctrl+C to stop.[/green]")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
