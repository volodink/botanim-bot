import re
from typing import cast

import logging
import telegram
from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from .books import (
    get_all_books,
    get_already_read_books,
    get_now_reading_books,
    get_not_started_books,
    get_books_by_numbers,
    build_category_with_books_string,
    calculate_category_books_start_index,
    format_book_name,
)
from .num_to_words import books_to_words
from .votings import save_vote, get_actual_voting, get_leaders
from . import config
from . import message_texts


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


if not config.TELEGRAM_BOT_TOKEN:
    exit("Specify TELEGRAM_BOT_TOKEN env variable")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_response(update, context, message_texts.GREETINGS)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_response(update, context, message_texts.HELP)


async def already(update: Update, context: ContextTypes.DEFAULT_TYPE):
    already_read_books = await get_already_read_books()
    response = "Прочитанные книги:\n\n"
    for index, book in enumerate(already_read_books, 1):
        response += (
            f"{index}. {book.name} "
            f"(читали с {book.read_start} по {book.read_finish})\n"
        )
    await _send_response(update, context, response)


async def now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_read_books = await get_now_reading_books()
    response = "Сейчас мы читаем:\n\n"
    just_one_book = len(now_read_books) == 1
    for index, book in enumerate(now_read_books, 1):
        response += (
            f"{str(index) + '. ' if not just_one_book else ''}"
            f"{book.name} "
            f"(с {book.read_start} по {book.read_finish})\n"
        )
    await _send_response(update, context, response)


async def vote_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_actual_voting() is None:
        await _send_response(update, context, message_texts.NO_ACTUAL_VOTING)
        return

    user_message = update.message.text
    numbers = re.findall(r"\d+", user_message)
    if len(tuple(set(map(int, numbers)))) != config.VOTE_ELEMENTS_COUNT:
        await _send_response(
            update, context, message_texts.VOTE_PROCESS_INCORRECT_INPUT
        )
        return
    books = tuple(await get_books_by_numbers(numbers))
    if len(books) != config.VOTE_ELEMENTS_COUNT:
        await _send_response(
            update, context, message_texts.VOTE_PROCESS_INCORRECT_BOOKS
        )
        return

    # TODO move to message_texts module all hardcoded texts
    await save_vote(update.effective_user.id, books)

    books_formatted = []
    for index, book in enumerate(books, 1):
        books_formatted.append(f"{index}. {book.name}")
    books_count = len(books_formatted)
    await _send_response(
        update,
        context,
        message_texts.SUCCESS_VOTE.format(
            books="\n".join(books_formatted),
            books_count=f"{books_count} {books_to_words(books_count)}",
        ),
    )


async def vote_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaders = await get_leaders()
    if leaders is None:
        await _send_response(update, context, message_texts.NO_VOTE_RESULTS)
        return

    books = []
    for index, book in enumerate(leaders.leaders, 1):
        books.append(
            f"{index}. {format_book_name(book.book_name)}. " f"Рейтинг: {book.score}"
        )
    response = message_texts.VOTE_RESULTS.format(
        books="\n".join(books),
        voting_start=leaders.voting.voting_start,
        voting_finish=leaders.voting.voting_finish,
    )
    await _send_response(update, context, response)


def _get_categories_keyboard(
    current_index: int, overall_count: int, prefix: str
) -> InlineKeyboardMarkup:
    prev_index = current_index - 1
    if prev_index < 0:
        prev_index = overall_count - 1
    next_index = current_index + 1
    if next_index > overall_count - 1:
        next_index = 0
    keyboard = [
        [
            InlineKeyboardButton("<", callback_data=f"{prefix}{prev_index}"),
            InlineKeyboardButton(
                str(current_index + 1) + "/" + str(overall_count), callback_data=" "
            ),
            InlineKeyboardButton(
                ">",
                callback_data=f"{prefix}{next_index}",
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def vote_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.strip():
        return
    categories_with_books = list(await get_not_started_books())

    pattern_prefix_length = len(config.VOTE_BOOKS_CALLBACK_PATTERN)
    current_category_index = int(query.data[pattern_prefix_length:])
    current_category = categories_with_books[current_category_index]

    category_books_start_index = calculate_category_books_start_index(
        categories_with_books, current_category
    )
    await query.edit_message_text(
        text=build_category_with_books_string(
            current_category, category_books_start_index
        ),
        reply_markup=_get_categories_keyboard(
            current_category_index,
            len(categories_with_books),
            config.VOTE_BOOKS_CALLBACK_PATTERN,
        ),
        parse_mode=telegram.constants.ParseMode.HTML,
    )


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_actual_voting() is None:
        await _send_response(update, context, message_texts.NO_ACTUAL_VOTING)
        return

    if not update.message:
        return

    categories_with_books = tuple(await get_not_started_books())
    current_category = categories_with_books[0]

    category_books_start_index = calculate_category_books_start_index(
        categories_with_books, current_category
    )

    await update.message.reply_text(
        build_category_with_books_string(current_category, category_books_start_index),
        reply_markup=_get_categories_keyboard(
            0, len(categories_with_books), config.VOTE_BOOKS_CALLBACK_PATTERN
        ),
        parse_mode=telegram.constants.ParseMode.HTML,
    )


async def all_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories_with_books = list(await get_all_books())
    if not update.message:
        return

    await update.message.reply_text(
        build_category_with_books_string(categories_with_books[0]),
        reply_markup=_get_categories_keyboard(
            0, len(categories_with_books), config.ALL_BOOKS_CALLBACK_PATTERN
        ),
        parse_mode=telegram.constants.ParseMode.HTML,
    )


async def all_books_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.strip():
        return
    categories_with_books = list(await get_all_books())

    pattern_prefix_length = len(config.ALL_BOOKS_CALLBACK_PATTERN)
    current_category_index = int(query.data[pattern_prefix_length:])
    await query.edit_message_text(
        text=build_category_with_books_string(
            categories_with_books[current_category_index]
        ),
        reply_markup=_get_categories_keyboard(
            current_category_index,
            len(categories_with_books),
            config.ALL_BOOKS_CALLBACK_PATTERN,
        ),
        parse_mode=telegram.constants.ParseMode.HTML,
    )


def _get_chat_id(update: Update) -> int | str:
    return cast(Chat, update.effective_chat).id


async def _send_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE, response: str
) -> None:
    await context.bot.send_message(
        chat_id=_get_chat_id(update),
        text=response,
        parse_mode=telegram.constants.ParseMode.HTML,
    )


def main():
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(CommandHandler("help", help))

    application.add_handler(CommandHandler("allbooks", all_books))
    application.add_handler(
        CallbackQueryHandler(
            all_books_button,
            pattern="^" + config.ALL_BOOKS_CALLBACK_PATTERN + r"(\d+)$",
        )
    )

    application.add_handler(CommandHandler("already", already))

    application.add_handler(CommandHandler("now", now))

    application.add_handler(CommandHandler("vote", vote))
    application.add_handler(
        CallbackQueryHandler(
            vote_button,
            pattern="^" + config.VOTE_BOOKS_CALLBACK_PATTERN + r"(\d+)$",
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND),
            vote_process,
        )
    )

    application.add_handler(CommandHandler("voteresults", vote_results))

    application.run_polling()
