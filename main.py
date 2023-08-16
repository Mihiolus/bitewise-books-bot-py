import logging
import re

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes, PicklePersistence, \
    ConversationHandler
from os import environ

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

UPLOAD_BOOK, SET_N_CHARS, SET_TIME = range(3)

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


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask the user about their UTC offset"""
    if (context.user_data.get("timezone")):
        reply_text = (f"Согласно моим данным, твой часовой пояс - {context.user_data['timezone']}."
                      f"")
    else:
        reply_text = "Пожалуйста, введи свой часовой пояс."
    await update.message.reply_text(reply_text)


async def newbook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Теперь пошли мне новую книжку (формат epub)."
    )

    return UPLOAD_BOOK


async def upload_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    await update.message.reply_text(
        f"Получил документ {document.mime_type}.\nТеперь напиши, по сколько символов мне тебе посылать.")

    return SET_N_CHARS


async def set_n_chars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    n_chars = int(text)
    await update.message.reply_text(f"Хорошо. Я буду посылать книжку по {n_chars} символов.\nТеперь напиши, в какое "
                                    f"время посылать, в формате чч:мм.")

    return SET_TIME


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    time = re.split(r':', text)
    await update.message.reply_text(f"Хорошо. Я буду посылать книжку в {time[0]}:{time[1]}")

    return ConversationHandler.END


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
            SET_TIME: [MessageHandler(filters.Regex(r'^\d{1,2}:\d{1,2}$'), set_time)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(newbook_handler)

    application.run_polling()
