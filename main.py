import datetime
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes, PicklePersistence, \
    ConversationHandler, CallbackQueryHandler, JobQueue
from os import environ
import ebooklib
from ebooklib import epub

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

UPLOAD_BOOK, SET_N_CHARS, SET_TIME, SET_TIMEZONE = range(4)

next_bite_keyboard = [[InlineKeyboardButton("Следующий ломтик", callback_data="1")]]
next_bite_markup = InlineKeyboardMarkup(next_bite_keyboard)

BOT_TOKEN = environ.get('BOT_TOKEN', '')
if len(BOT_TOKEN) == 0:
    logging.error("BOT_TOKEN variable is missing! Exiting now.")
    exit(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_text = "Привет! Я не буду читать книжки за тебя, " \
                 "но могу помочь.\n\nДля начала, рекомендую " \
                 "установить твой часовой пояс с помощью " \
                 "команды /settings. После этого, " \
                 "можешь загружать книжку с помощью команды " \
                 "/newbook."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=reply_text)


async def newbook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Теперь пошли мне новую книжку (формат epub)."
    )

    return UPLOAD_BOOK


async def upload_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    file_id = document.file_id
    new_file = await update.get_bot().getFile(file_id)
    filepath = str(update.message.from_user.id) + " download.epub"
    await new_file.download_to_drive(custom_path=filepath)

    book = epub.read_epub(filepath)
    context.user_data["book_path"] = filepath
    await update.message.reply_text(
        f"Получил книжку \"{book.title}\".\nТеперь напиши, по сколько символов мне тебе посылать.")

    return SET_N_CHARS


async def set_n_chars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    n_chars = int(text)
    context.user_data["n_chars"] = n_chars
    if "timezone" in context.user_data:
        await update.message.reply_text(f"Хорошо. Я буду посылать книжку по {n_chars} символов.\nТеперь напиши, в какое "
                                    f"время посылать, в формате чч:мм.")

        return SET_TIME
    else:
        await update.message.reply_text(f"У тебя ещё не установлен часовой пояс. Введи его сейчас.")

        return SET_TIMEZONE


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    timelist = re.split(r':', text)
    timezone = context.user_data["timezone"]
    time = datetime.time(int(timelist[0]), int(timelist[1]), tzinfo=timezone)
    context.user_data["time"] = time
    job = context.job_queue.run_daily(next_bite_scheduled, time, chat_id=update.effective_message.chat_id)

    context.user_data["last_bite"] = await update.message.reply_text(
        f"Хорошо. Я буду посылать книжку в {job.next_t}.",
        reply_markup=next_bite_markup)

    return ConversationHandler.END


async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        timezone = datetime.timezone(datetime.timedelta(hours=float(text)))
        context.user_data["timezone"] = timezone
        await update.message.reply_text(
            f"Хорошо. Часовой пояс установлен.\nТеперь напиши, в какое "
            f"время посылать, в формате чч:мм.")
    except ValueError:
        await update.message.reply_text("Неправильное значение! Попробуй ещё раз.")
        return SET_TIMEZONE
    return SET_TIME


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask the user about their UTC offset"""
    if context.user_data.get("timezone"):
        reply_text = (f"Согласно моим данным, твой часовой пояс - {context.user_data['timezone']}."
                      f"")
    else:
        reply_text = "Пожалуйста, введи свой часовой пояс."
    await update.message.reply_text(reply_text)


async def next_bite_scheduled(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    last_bite = context.application.user_data[job.chat_id]["last_bite"]
    await  context.bot.edit_message_text(chat_id=job.chat_id, message_id=last_bite.message_id, text=last_bite.text)


async def next_bite_immediate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=query.message.text)


# async def next_bite(context: ContextTypes.DEFAULT_TYPE) -> None:


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    await  update.message.reply_text(
        "Процесс настройки новой книжки прерван."
    )
    return ConversationHandler.END


if __name__ == '__main__':
    persistence = PicklePersistence(filepath="bitewisebooksbot.pickle")
    application = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(False).persistence(persistence).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    settings_handler = CommandHandler('settings', settings)
    application.add_handler(settings_handler)

    newbook_handler = ConversationHandler(
        entry_points=[CommandHandler("newbook", newbook)],
        states={
            UPLOAD_BOOK: [MessageHandler(filters.Document.MimeType("application/epub+zip"), upload_book)],
            SET_N_CHARS: [MessageHandler(filters.Regex(r'^\d+$'), set_n_chars)],
            SET_TIME: [MessageHandler(filters.Regex(r'^\d{1,2}:\d{1,2}$'), set_time)],
            SET_TIMEZONE: [MessageHandler(filters.Regex(r'^[+]?\d{1,2}$'), set_timezone)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(newbook_handler)

    application.add_handler(CallbackQueryHandler(next_bite_immediate))

    application.run_polling()
