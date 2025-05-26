import logging
from telegram import Update
from telegram.ext import Updater, MessageHandler, filters, ConversationHandler, CommandHandler
from keyboards import *
from settings import *
from requests_to_server import *
from maps import get_ll_spn, get_address_photo
import base64
import io

# Configure logging
def setup_logger():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    return logging.getLogger(__name__)

logger = setup_logger()

# Conversation states\NAME, SEX, FORM_NUMBER, FORM_LETTER, INTRO, PHOTO, ADDRESS, SEARCH_SEX = range(8)

# --- Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Приветствую! Вы в меню.", reply_markup=main_keyboard
    )


def entry_menu(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Вы в меню.", reply_markup=main_keyboard
    )
    return ConversationHandler.END


def my_profile(update: Update, context: CallbackContext) -> int:
    user = get_user_data(update.effective_user.id)
    if not user:
        update.message.reply_text("Анкета не найдена.", reply_markup=main_keyboard)
        return ConversationHandler.END
    if not all(user.get(k) for k in ("name","sex","photo","form_number","form_char","address","searching_sex","about")):
        update.message.reply_text(
            f"Заполните анкету, нажав {CHANGE_PROFILE}.", reply_markup=main_keyboard
        )
        return ConversationHandler.END
    update.message.reply_text("Вот твоя анкета:", reply_markup=main_keyboard)
    send_form(update, context, user["id_tg"])
    return ConversationHandler.END


def bad_input(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Неверный ввод, попробуйте ещё раз.")


def bad_server_connection(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Ошибка сервера, попробуйте позже.")

# --- Profile filling ---
def ask_name(update: Update, context: CallbackContext) -> int:
    uid = update.effective_user.id
    if not is_registred(uid):
        if not update.effective_user.username:
            update.message.reply_text("Установите username в настройках Телеграма.")
            return ConversationHandler.END
        if not add_user(uid, update.effective_chat.id, update.effective_user.username):
            bad_server_connection(update, context)
            return ConversationHandler.END
    data = get_user_data(uid)
    if not data:
        bad_server_connection(update, context)
        return ConversationHandler.END
    context.user_data.update(data)
    update.message.reply_text(
        "Как тебя зовут?",
        reply_markup=get_name_choose_keyboard(context.user_data.get("name"))
    )
    return NAME


def ask_sex(update: Update, context: CallbackContext) -> int:
    name = update.message.text
    context.user_data["name"] = name
    if not post_user_data(id_tg=update.effective_user.id, name=name):
        bad_server_connection(update, context)
        return NAME
    update.message.reply_text(
        f"{name}, выбери пол:", reply_markup=choose_sex_keyboard
    )
    return SEX


def ask_form_number(update: Update, context: CallbackContext) -> int:
    txt = update.message.text
    if txt in (MEN, WOMEN):
        val = Men_sex if txt == MEN else Women_sex
        context.user_data["sex"] = val
        if not post_user_data(id_tg=update.effective_user.id, sex=val):
            bad_server_connection(update, context)
            return SEX
        update.message.reply_text(
            "Введите номер класса:", reply_markup=choose_form_number_keyboard
        )
        return FORM_NUMBER
    bad_input(update, context)
    return SEX


def ask_form_letter(update: Update, context: CallbackContext) -> int:
    num = update.message.text
    if num in Forms:
        context.user_data["form_number"] = num
        if not post_user_data(id_tg=update.effective_user.id, form_number=num):
            bad_server_connection(update, context)
            return FORM_NUMBER
        update.message.reply_text(
            "Буква класса:", reply_markup=get_choose_form_letter_keyboard(num)
        )
        return FORM_LETTER
    bad_input(update, context)
    return FORM_NUMBER


def ask_for_introduction(update: Update, context: CallbackContext) -> int:
    about = update.message.text
    context.user_data["about"] = about
    if not post_user_data(id_tg=update.effective_user.id, about=about):
        bad_server_connection(update, context)
        return INTRO
    update.message.reply_text(
        "Расскажите о себе:", reply_markup=get_choose_text_keyboard()
    )
    return INTRO


def ask_for_photo(update: Update, context: CallbackContext) -> int:
    if update.message.text == CHANGE_PROFILE:
        return PHOTO
    about = update.message.text
    context.user_data["about"] = about
    post_user_data(id_tg=update.effective_user.id, about=about)
    update.message.reply_text(
        "Пришлите фото:", reply_markup=get_choose_photo_keyboard()
    )
    return PHOTO


def ask_for_address(update: Update, context: CallbackContext) -> int:
    if update.message.photo:
        f = update.message.photo[-1].get_file()
        bio = io.BytesIO()
        f.download(out=bio)
        context.user_data["photo"] = base64.b64encode(bio.getvalue())
        post_user_data(id_tg=update.effective_user.id, photo=context.user_data["photo"])
    update.message.reply_text(
        "Введите адрес:", reply_markup=get_choose_address_keyboard()
    )
    return ADDRESS


def ask_searching_sex(update: Update, context: CallbackContext) -> int:
    addr = update.message.text
    context.user_data["address"] = addr
    post_user_data(id_tg=update.effective_user.id, address=addr)
    update.message.reply_text(
        "Кого ищем:", reply_markup=choose_searching_sex_keyboard
    )
    return SEARCH_SEX


def end_registration(update: Update, context: CallbackContext) -> int:
    txt = update.message.text
    if txt in (MEN_SEARCHING, WOMEN_SEARCHING, ALL):
        mapping = {MEN_SEARCHING: Men_sex, WOMEN_SEARCHING: Women_sex, ALL: Default_sex}
        context.user_data["searching_sex"] = mapping[txt]
        post_user_data(id_tg=update.effective_user.id, searching_sex=mapping[txt])
        update.message.reply_text(
            "Регистрация завершена!", reply_markup=main_keyboard
        )
        return ConversationHandler.END
    bad_input(update, context)
    return SEARCH_SEX


def send_form(update: Update, context: CallbackContext, uid: int) -> None:
    data = get_user_data(uid)
    if not data:
        return bad_server_connection(update, context)
    update.message.reply_photo(photo=base64.b64decode(data["photo"]))
    update.message.reply_text(
        f"{data['name']}, {data['form_number']}{data['form_char']}\n{data['about']}\nАдрес: {data['address']}"
    )

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f'^{CHANGE_PROFILE}$'), ask_name)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_sex)],
        SEX: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_form_number)],
        FORM_NUMBER: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_form_letter)],
        FORM_LETTER: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_for_introduction)],
        INTRO: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_for_photo)],
        PHOTO: [MessageHandler(filters.PHOTO | filters.Regex(f'^{CHANGE_PROFILE}$'), ask_for_address)],
        ADDRESS: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), ask_searching_sex)],
        SEARCH_SEX: [MessageHandler(filters.TEXT & ~filters.Regex(f'^{BACK_TO_MENU}$'), end_registration)],
    },
    fallbacks=[MessageHandler(filters.Regex(f'^{BACK_TO_MENU}$'), entry_menu)]
)


def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(
        filters.Regex(f'^{MENU}$') | filters.Regex(f'^{BACK_TO_MENU}$'), entry_menu
    ))
    dp.add_handler(MessageHandler(filters.Regex(f'^{MY_PROFILE}$'), my_profile))
    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()