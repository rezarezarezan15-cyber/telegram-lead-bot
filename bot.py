import os
import json
import logging
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GOOGLE_SCRIPT_URL = os.environ.get("GOOGLE_SCRIPT_URL")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]

# ==================== لاگ ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== مراحل مکالمه ====================
(
    CHOOSING,
    ASK_NAME,
    ASK_PHONE,
    ASK_GRADE,
    ASK_QUESTION_TEXT,
    ADMIN_CHOOSE_GRADE,
    ADMIN_SEND_FILE,
    ADMIN_FILE_TITLE,
    ADMIN_FILE_DESC,
    ADMIN_BROADCAST_MSG,
) = range(10)

# ==================== لیست پایه‌ها ====================
GRADES = [
    "هفتم",
    "هشتم",
    "نهم",
    "دهم",
    "یازدهم",
    "دوازدهم",
]

# ==================== ذخیره موقت اطلاعات کاربر ====================
user_data_store = {}


# ==================== توابع کمکی ====================
def send_to_google_sheet(data):
    """ارسال اطلاعات به Google Sheet"""
    try:
        response = requests.post(
            GOOGLE_SCRIPT_URL,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return response.json()
    except Exception as e:
        logger.error(f"Google Sheet Error: {e}")
        return {"status": "error"}


def get_files_from_sheet(grade):
    """دریافت فایل‌ها از Google Sheet"""
    try:
        response = requests.post(
            GOOGLE_SCRIPT_URL,
            json={"action": "get_files", "grade": grade},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        result = response.json()
        return result.get("files", [])
    except Exception as e:
        logger.error(f"Get Files Error: {e}")
        return []


def is_admin(user_id):
    """بررسی ادمین بودن"""
    return user_id in ADMIN_IDS


def main_menu_keyboard():
    """کیبورد منوی اصلی"""
    keyboard = [
        [
            InlineKeyboardButton("📚 دریافت فایل رایگان", callback_data="get_file"),
            InlineKeyboardButton("❓ پرسش سوال", callback_data="ask_question"),
        ],
        [
            InlineKeyboardButton("📞 ارتباط با ما", callback_data="contact_us"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard():
    """کیبورد پنل مدیریت"""
    keyboard = [
        [
            InlineKeyboardButton(
                "📤 آپلود فایل جدید", callback_data="admin_upload"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 آمار کاربران", callback_data="admin_stats"
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 ارسال پیام همگانی", callback_data="admin_broadcast"
            ),
        ],
        [
            InlineKeyboardButton("🏠 بازگشت به خانه", callback_data="go_home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def grade_keyboard(prefix="grade"):
    """کیبورد انتخاب پایه"""
    keyboard = []
    row = []
    for i, grade in enumerate(GRADES):
        row.append(InlineKeyboardButton(grade, callback_data=f"{prefix}_{grade}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [InlineKeyboardButton("🏠 بازگشت به خانه", callback_data="go_home")]
    )
    return InlineKeyboardMarkup(keyboard)


# ==================== هندلرها ====================


async def start(update: Update, context):
    """شروع ربات"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    welcome_text = (
        f"سلام {user.first_name} عزیز! 👋\n\n"
        f"🎓 به ربات آموزشی ما خوش آمدید!\n\n"
        f"از منوی زیر یکی از گزینه‌ها را انتخاب کنید:"
    )

    if is_admin(chat_id):
        welcome_text += "\n\n🔑 شما ادمین هستید! برای پنل مدیریت /admin را بزنید."

    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())
    return CHOOSING


async def admin_panel(update: Update, context):
    """پنل مدیریت"""
    chat_id = update.effective_chat.id

    if not is_admin(chat_id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید!")
        return CHOOSING

    await update.message.reply_text(
        "🔧 *پنل مدیریت*\n\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    return CHOOSING


async def button_handler(update: Update, context):
    """مدیریت دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    # ---- بازگشت به خانه ----
    if data == "go_home":
        await query.edit_message_text(
            "🏠 *صفحه اصلی*\n\nیکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return CHOOSING

    # ---- دریافت فایل رایگان ----
    elif data == "get_file":
        await query.edit_message_text(
            "📚 *دریافت فایل رایگان*\n\nپایه تحصیلی خود را انتخاب کنید:",
            reply_markup=grade_keyboard("getfile"),
            parse_mode="Markdown",
        )
        return CHOOSING

    elif data.startswith("getfile_"):
        grade = data.replace("getfile_", "")
        user_data_store.setdefault(chat_id, {})["selected_grade"] = grade

        # Check if user already registered
        if user_data_store.get(chat_id, {}).get("registered"):
            # Directly show files
            files = get_files_from_sheet(grade)
            if files:
                await query.edit_message_text(
                    f"📁 فایل‌های پایه {grade}:",
                    parse_mode="Markdown",
                )
                for f in files:
                    try:
                        caption = f"📄 {f['title']}\n📝 {f.get('description', '')}"
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f["file_id"],
                            caption=caption,
                        )
                    except Exception as e:
                        logger.error(f"Send file error: {e}")
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"📄 {f['title']}: فایل در دسترس نیست",
                        )

                # Save lead
                user_info = user_data_store.get(chat_id, {})
                send_to_google_sheet(
                    {
                        "action": "save_lead",
                        "chat_id": chat_id,
                        "name": user_info.get("name", ""),
                        "phone": user_info.get("phone", ""),
                        "grade": grade,
                        "request": "دریافت فایل رایگان",
                    }
                )

                # Back to home
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🏠 بازگشت به صفحه اصلی:",
                    reply_markup=main_menu_keyboard(),
                )
            else:
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🏠 بازگشت به خانه", callback_data="go_home"
                        )
                    ]
                ]
                await query.edit_message_text(
                    f"😔 متأسفانه فایلی برای پایه {grade} موجود نیست.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            return CHOOSING
        else:
            # Need registration first
            user_data_store.setdefault(chat_id, {})["request_type"] = "file"
            await query.edit_message_text(
                "📝 برای دریافت فایل، لطفاً ابتدا ثبت‌نام کنید.\n\n"
                "👤 *نام و نام خانوادگی* خود را بنویسید:",
                parse_mode="Markdown",
            )
            return ASK_NAME

    # ---- پرسش سوال ----
    elif data == "ask_question":
        user_data_store.setdefault(chat_id, {})["request_type"] = "question"

        if user_data_store.get(chat_id, {}).get("registered"):
            await query.edit_message_text(
                "📚 پایه تحصیلی خود را انتخاب کنید:",
                reply_markup=grade_keyboard("askgrade"),
            )
            return CHOOSING
        else:
            await query.edit_message_text(
                "📝 برای پرسش سوال، لطفاً ابتدا ثبت‌نام کنید.\n\n"
                "👤 *نام و نام خانوادگی* خود را بنویسید:",
                parse_mode="Markdown",
            )
            return ASK_NAME

    elif data.startswith("askgrade_"):
        grade = data.replace("askgrade_", "")
        user_data_store.setdefault(chat_id, {})["selected_grade"] = grade
        await query.edit_message_text(
            f"📝 پایه {grade} انتخاب شد.\n\n"
            "❓ لطفاً *سوال خود* را بنویسید:\n"
            "(می‌توانید عکس هم بفرستید)",
            parse_mode="Markdown",
        )
        return ASK_QUESTION_TEXT

    # ---- ارتباط با ما ----
    elif data == "contact_us":
        keyboard = [
            [InlineKeyboardButton("🏠 بازگشت به خانه", callback_data="go_home")]
        ]
        await query.edit_message_text(
            "📞 *ارتباط با ما*\n\n"
            "📱 شماره تماس: 09121234567\n"
            "📧 ایمیل: info@example.com\n"
            "🌐 وبسایت: example.com\n\n"
            "💬 همچنین می‌توانید از بخش «پرسش سوال» استفاده کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return CHOOSING

    # ---- پنل ادمین ----
    elif data == "admin_upload":
        if not is_admin(chat_id):
            return CHOOSING
        await query.edit_message_text(
            "📤 *آپلود فایل جدید*\n\nپایه تحصیلی فایل را انتخاب کنید:",
            reply_markup=grade_keyboard("admingrade"),
            parse_mode="Markdown",
        )
        return CHOOSING

    elif data.startswith("admingrade_"):
        if not is_admin(chat_id):
            return CHOOSING
        grade = data.replace("admingrade_", "")
        user_data_store.setdefault(chat_id, {})["admin_file_grade"] = grade
        await query.edit_message_text(
            f"📎 پایه {grade} انتخاب شد.\n\n"
            "لطفاً *فایل مورد نظر* را ارسال کنید (PDF, عکس, ویدیو و...):",
            parse_mode="Markdown",
        )
        return ADMIN_SEND_FILE

    elif data == "admin_stats":
        if not is_admin(chat_id):
            return CHOOSING
        count = len(
            [uid for uid, d in user_data_store.items() if d.get("registered")]
        )
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back")]
        ]
        await query.edit_message_text(
            f"📊 *آمار ربات*\n\n"
            f"👥 تعداد کاربران ثبت‌نام شده: {count}\n\n"
            f"📋 برای آمار دقیق به Google Sheet مراجعه کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return CHOOSING

    elif data == "admin_broadcast":
        if not is_admin(chat_id):
            return CHOOSING
        await query.edit_message_text(
            "📢 *ارسال پیام همگانی*\n\n"
            "پیام خود را بنویسید تا برای همه کاربران ارسال شود:\n"
            "(برای لغو /cancel بزنید)",
            parse_mode="Markdown",
        )
        return ADMIN_BROADCAST_MSG

    elif data == "admin_back":
        if is_admin(chat_id):
            await query.edit_message_text(
                "🔧 *پنل مدیریت*",
                reply_markup=admin_menu_keyboard(),
                parse_mode="Markdown",
            )
        return CHOOSING

    return CHOOSING


# ==================== ثبت‌نام ====================


async def ask_name_handler(update: Update, context):
    """دریافت نام"""
    chat_id = update.effective_chat.id
    name = update.message.text

    user_data_store.setdefault(chat_id, {})["name"] = name

    await update.message.reply_text(
        f"✅ ممنون {name} جان!\n\n"
        "📱 لطفاً *شماره تلفن* خود را وارد کنید:\n"
        "(مثال: 09121234567)",
        parse_mode="Markdown",
    )
    return ASK_PHONE


async def ask_phone_handler(update: Update, context):
    """دریافت شماره تلفن"""
    chat_id = update.effective_chat.id
    phone = update.message.text

    # Simple phone validation
    phone_clean = phone.replace(" ", "").replace("-", "")
    if not phone_clean.isdigit() or len(phone_clean) < 10:
        await update.message.reply_text(
            "⚠️ شماره تلفن نامعتبر است. لطفاً دوباره وارد کنید:\n"
            "(مثال: 09121234567)"
        )
        return ASK_PHONE

    user_data_store.setdefault(chat_id, {})["phone"] = phone_clean

    await update.message.reply_text(
        "📚 لطفاً *پایه تحصیلی* خود را انتخاب کنید:",
        reply_markup=grade_keyboard("reggrade"),
        parse_mode="Markdown",
    )
    return ASK_GRADE


async def registration_grade_handler(update: Update, context):
    """دریافت پایه تحصیلی در ثبت‌نام"""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "go_home":
        await query.edit_message_text(
            "🏠 *صفحه اصلی*\n\nیکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return CHOOSING

    grade = data.replace("reggrade_", "")
    user_info = user_data_store.setdefault(chat_id, {})
    user_info["grade"] = grade
    user_info["registered"] = True
    user_info["selected_grade"] = grade

    request_type = user_info.get("request_type", "file")

    # Save to Google Sheet
    send_to_google_sheet(
        {
            "action": "save_lead",
            "chat_id": chat_id,
            "name": user_info.get("name", ""),
            "phone": user_info.get("phone", ""),
            "grade": grade,
            "request": request_type,
        }
    )

    await query.edit_message_text(
        f"✅ *ثبت‌نام موفق!*\n\n"
        f"👤 نام: {user_info.get('name', '')}\n"
        f"📱 شماره: {user_info.get('phone', '')}\n"
        f"📚 پایه: {grade}\n",
        parse_mode="Markdown",
    )

    if request_type == "file":
        # Show files
        files = get_files_from_sheet(grade)
        if files:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📁 فایل‌های پایه {grade}:"
            )
            for f in files:
                try:
                    caption = f"📄 {f['title']}\n📝 {f.get('description', '')}"
                    await context.bot.send_document(
                        chat_id=chat_id, document=f["file_id"], caption=caption
                    )
                except Exception as e:
                    logger.error(f"Send file error: {e}")
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"😔 فعلاً فایلی برای پایه {grade} آپلود نشده. به زودی اضافه می‌شود!",
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text="🏠 بازگشت به صفحه اصلی:",
            reply_markup=main_menu_keyboard(),
        )
        return CHOOSING

    elif request_type == "question":
        await context.bot.send_message(
            chat_id=chat_id,
            text="❓ لطفاً *سوال خود* را بنویسید:\n(می‌توانید عکس هم بفرستید)",
            parse_mode="Markdown",
        )
        return ASK_QUESTION_TEXT


async def ask_question_text_handler(update: Update, context):
    """دریافت متن سوال"""
    chat_id = update.effective_chat.id
    user_info = user_data_store.get(chat_id, {})

    question_text = update.message.text or update.message.caption or "فایل ارسال شده"

    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            admin_msg = (
                f"❓ *سوال جدید*\n\n"
                f"👤 نام: {user_info.get('name', 'نامشخص')}\n"
                f"📱 شماره: {user_info.get('phone', 'نامشخص')}\n"
                f"📚 پایه: {user_info.get('selected_grade', user_info.get('grade', 'نامشخص'))}\n"
                f"🆔 Chat ID: {chat_id}\n\n"
                f"📝 سوال:\n{question_text}"
            )
            await context.bot.send_message(
                chat_id=admin_id, text=admin_msg, parse_mode="Markdown"
            )

            # If photo was sent
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=update.message.photo[-1].file_id,
                    caption=f"عکس سوال از {user_info.get('name', '')}",
                )
            if update.message.document:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=update.message.document.file_id,
                    caption=f"فایل سوال از {user_info.get('name', '')}",
                )
        except Exception as e:
            logger.error(f"Notify admin error: {e}")

    # Save to sheet
    send_to_google_sheet(
        {
            "action": "save_lead",
            "chat_id": chat_id,
            "name": user_info.get("name", ""),
            "phone": user_info.get("phone", ""),
            "grade": user_info.get("selected_grade", user_info.get("grade", "")),
            "request": f"سوال: {question_text[:100]}",
        }
    )

    await update.message.reply_text(
        "✅ سوال شما با موفقیت ثبت شد!\n\n"
        "📩 به زودی پاسخ شما ارسال خواهد شد.\n\n"
        "🏠 بازگشت به صفحه اصلی:",
        reply_markup=main_menu_keyboard(),
    )
    return CHOOSING


# ==================== پنل ادمین: آپلود فایل ====================


async def admin_receive_file(update: Update, context):
    """دریافت فایل از ادمین"""
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return CHOOSING

    # Get file_id
    file_id = None
    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        file_id = update.message.video.file_id
    elif update.message.audio:
        file_id = update.message.audio.file_id

    if not file_id:
        await update.message.reply_text(
            "⚠️ لطفاً یک فایل، عکس یا ویدیو ارسال کنید."
        )
        return ADMIN_SEND_FILE

    user_data_store.setdefault(chat_id, {})["admin_file_id"] = file_id

    await update.message.reply_text(
        "✅ فایل دریافت شد!\n\n📝 لطفاً *عنوان فایل* را بنویسید:",
        parse_mode="Markdown",
    )
    return ADMIN_FILE_TITLE


async def admin_file_title_handler(update: Update, context):
    """دریافت عنوان فایل"""
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return CHOOSING

    title = update.message.text
    user_data_store.setdefault(chat_id, {})["admin_file_title"] = title

    await update.message.reply_text(
        "📝 لطفاً *توضیحات فایل* را بنویسید:\n(یا بنویسید: بدون توضیح)",
        parse_mode="Markdown",
    )
    return ADMIN_FILE_DESC


async def admin_file_desc_handler(update: Update, context):
    """دریافت توضیحات فایل و ذخیره"""
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return CHOOSING

    desc = update.message.text
    user_info = user_data_store.get(chat_id, {})

    # Save to Google Sheet
    result = send_to_google_sheet(
        {
            "action": "save_file",
            "grade": user_info.get("admin_file_grade", ""),
            "title": user_info.get("admin_file_title", ""),
            "file_id": user_info.get("admin_file_id", ""),
            "description": desc if desc != "بدون توضیح" else "",
        }
    )

    grade = user_info.get("admin_file_grade", "")
    title = user_info.get("admin_file_title", "")

    await update.message.reply_text(
        f"✅ *فایل با موفقیت ذخیره شد!*\n\n"
        f"📚 پایه: {grade}\n"
        f"📄 عنوان: {title}\n"
        f"📝 توضیحات: {desc}\n",
        parse_mode="Markdown",
    )

    await update.message.reply_text(
        "🔧 *پنل مدیریت*",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    return CHOOSING


# ==================== ارسال پیام همگانی ====================


async def admin_broadcast_handler(update: Update, context):
    """ارسال پیام همگانی"""
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return CHOOSING

    message_text = update.message.text
    sent_count = 0
    fail_count = 0

    for uid, udata in user_data_store.items():
        if udata.get("registered") and uid != chat_id:
            try:
                await context.bot.send_message(chat_id=uid, text=message_text)
                sent_count += 1
            except Exception:
                fail_count += 1

    await update.message.reply_text(
        f"📢 *پیام همگانی ارسال شد!*\n\n"
        f"✅ موفق: {sent_count}\n"
        f"❌ ناموفق: {fail_count}",
        parse_mode="Markdown",
    )

    await update.message.reply_text(
        "🔧 *پنل مدیریت*",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    return CHOOSING


# ==================== لغو ====================


async def cancel(update: Update, context):
    """لغو عملیات"""
    await update.message.reply_text(
        "❌ عملیات لغو شد.\n\n🏠 بازگشت به صفحه اصلی:",
        reply_markup=main_menu_keyboard(),
    )
    return CHOOSING


# ==================== پاسخ به سوال کاربر توسط ادمین ====================


async def reply_handler(update: Update, context):
    """ادمین با ریپلای کردن روی پیام سوال، جواب می‌دهد"""
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    if not update.message.reply_to_message:
        return

    # Extract chat_id from the forwarded message
    original_text = update.message.reply_to_message.text or ""
    import re

    match = re.search(r"Chat ID:\s*(\d+)", original_text)
    if match:
        target_chat_id = int(match.group(1))
        reply_text = update.message.text

        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text=f"📩 *پاسخ به سوال شما:*\n\n{reply_text}",
                parse_mode="Markdown",
            )
            await update.message.reply_text("✅ پاسخ ارسال شد!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ارسال: {e}")


# ==================== تابع اصلی ====================


def main():
    """اجرای ربات"""
    application = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                CallbackQueryHandler(button_handler),
            ],
            ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name_handler),
            ],
            ASK_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone_handler),
            ],
            ASK_GRADE: [
                CallbackQueryHandler(registration_grade_handler),
            ],
            ASK_QUESTION_TEXT: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.Document.ALL)
                    & ~filters.COMMAND,
                    ask_question_text_handler,
                ),
            ],
            ADMIN_SEND_FILE: [
                MessageHandler(
                    (
                        filters.Document.ALL
                        | filters.PHOTO
                        | filters.VIDEO
                        | filters.AUDIO
                    )
                    & ~filters.COMMAND,
                    admin_receive_file,
                ),
            ],
            ADMIN_FILE_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, admin_file_title_handler
                ),
            ],
            ADMIN_FILE_DESC: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, admin_file_desc_handler
                ),
            ],
            ADMIN_BROADCAST_MSG: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, admin_broadcast_handler
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("admin", admin_panel),
        ],
    )

    application.add_handler(conv_handler)

    # Reply handler for admin (outside conversation)
    application.add_handler(
        MessageHandler(
            filters.REPLY & filters.TEXT & ~filters.COMMAND, reply_handler
        )
    )

    # Start bot
    logger.info("Bot started!")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
