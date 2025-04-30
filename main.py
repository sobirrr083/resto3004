import os
import logging
import json
import time
import fcntl
import signal
import asyncio
from typing import Any, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.error import Conflict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
SELECTING_ACTION, ADDING_NAME, ADDING_LOCATION, WAITING_FOR_RATING, EDITING_RESTAURANT, EDITING_BOT_INFO = range(6)

# Callback data
ADD_RESTAURANT = "add_restaurant"
VIEW_RESTAURANTS = "view_restaurants"
RECOMMEND_RESTAURANTS = "recommend_restaurants"
DELETE_RESTAURANT = "delete_restaurant"
EDIT_RESTAURANT = "edit_restaurant"
CONFIRM_DELETE = "confirm_delete"
CANCEL = "cancel"
RATE = "rate"
BOT_INFO = "bot_info"
EDIT_BOT_INFO = "edit_bot_info"
DELETE_BOT_INFO = "delete_bot_info"

# Data files
RESTAURANT_DATA_FILE = "restaurants.json"
BOT_INFO_FILE = "bot_info.json"

# Load admin IDs from environment variable
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip().isdigit()]

# Lock file to ensure single instance
LOCK_FILE_PATH = "bot.lock"

# Load restaurant data from file
def load_restaurant_data() -> Dict[str, Any]:
    """Load restaurant data from JSON file."""
    try:
        if os.path.exists(RESTAURANT_DATA_FILE):
            with open(RESTAURANT_DATA_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading restaurant data: {e}")
    return {}

# Save restaurant data to file
def save_restaurant_data(data: Dict[str, Any]) -> None:
    """Save restaurant data to JSON file."""
    try:
        with open(RESTAURANT_DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except IOError as e:
        logger.error(f"Error saving restaurant data: {e}")

# Load bot info from file
def load_bot_info() -> Dict[str, str]:
    """Load bot info from JSON file."""
    try:
        if os.path.exists(BOT_INFO_FILE):
            with open(BOT_INFO_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading bot info: {e}")
    return {"info": "Bot haqida ma'lumot hali kiritilmagan."}

# Save bot info to file
def save_bot_info(data: Dict[str, str]) -> None:
    """Save bot info to JSON file."""
    try:
        with open(BOT_INFO_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except IOError as e:
        logger.error(f"Error saving bot info: {e}")

# Check if user is admin
def is_admin(user_id: int) -> bool:
    """Check if the user is an admin."""
    return user_id in ADMIN_IDS

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send welcome message and show main menu."""
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📋 Restoranlarni ko'rish", callback_data=VIEW_RESTAURANTS)],
        [InlineKeyboardButton("⭐ Tavsiya etilgan restoranlar", callback_data=RECOMMEND_RESTAURANTS)],
        [InlineKeyboardButton("ℹ️ Bot haqida", callback_data=BOT_INFO)],
    ]
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton("🍽️ Restoran qo'shish", callback_data=ADD_RESTAURANT)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = "Assalomu alaykum! Restoran joylashuvi botiga xush kelibsiz!\n"
    if is_admin(user_id):
        welcome_text += "Admin sifatida /admin buyrug'ini ishlatib restoranlarni va bot ma'lumotlarini boshqarishingiz mumkin.\n"
    welcome_text += "Quyidagi amallardan birini tanlang:"

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    return SELECTING_ACTION

# Admin panel command
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show admin panel with options to manage restaurants and bot info."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Sizda admin huquqlari yo'q!")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🍽️ Restoran qo'shish", callback_data=ADD_RESTAURANT)],
        [InlineKeyboardButton("📋 Restoranlarni boshqarish", callback_data=VIEW_RESTAURANTS)],
        [InlineKeyboardButton("ℹ️ Bot ma'lumotini tahrirlash", callback_data=EDIT_BOT_INFO)],
        [InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Admin paneli:\nQuyidagi amallardan birini tanlang:", reply_markup=reply_markup)
    return SELECTING_ACTION

# Handle menu selection
async def menu_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle menu actions based on callback queries."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == ADD_RESTAURANT:
        if not is_admin(user_id):
            await query.edit_message_text("Sizda restoran qo'shish huquqi yo'q!")
            return SELECTING_ACTION
        await query.edit_message_text("Restoran nomini kiriting:")
        return ADDING_NAME

    elif query.data == VIEW_RESTAURANTS:
        restaurants = load_restaurant_data()
        if not restaurants:
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Hech qanday restoran topilmadi.", reply_markup=reply_markup)
            return SELECTING_ACTION

        keyboard = [[InlineKeyboardButton(f"🍽️ {name}", callback_data=f"view:{name}")] for name in restaurants.keys()]
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("Restoranlardan birini tanlang:", reply_markup=reply_markup)
        return SELECTING_ACTION

    elif query.data.startswith("view:"):
        restaurant_name = query.data.split(":", 1)[1]
        restaurants = load_restaurant_data()
        if restaurant_name not in restaurants:
            await query.edit_message_text("Bunday restoran topilmadi.")
            return SELECTING_ACTION

        info = restaurants[restaurant_name]
        avg_rating = info.get("avg_rating", "Baholanmagan")
        rating_count = info.get("rating_count", 0)
        rating_text = f"{avg_rating} ⭐ ({rating_count} baho)" if avg_rating != "Baholanmagan" else "Baholanmagan"

        restaurant_info = (
            f"🍽️ *{restaurant_name}*\n"
            f"📍 Manzil: {info['location']}\n"
            f"⭐ Baho: {rating_text}\n"
        )

        keyboard = [[InlineKeyboardButton("⭐ Baho berish", callback_data=f"{RATE}:{restaurant_name}")]]
        if is_admin(user_id):
            keyboard.append([
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"{EDIT_RESTAURANT}:{restaurant_name}"),
                InlineKeyboardButton("❌ O'chirish", callback_data=f"{DELETE_RESTAURANT}:{restaurant_name}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data=VIEW_RESTAURANTS)])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(restaurant_info, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECTING_ACTION

    elif query.data == RECOMMEND_RESTAURANTS:
        restaurants = load_restaurant_data()
        if not restaurants:
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Hech qanday restoran topilmadi.", reply_markup=reply_markup)
            return SELECTING_ACTION

        rated_restaurants = {
            name: info for name, info in restaurants.items()
            if info.get("avg_rating") and info["avg_rating"] != "Baholanmagan"
        }
        if not rated_restaurants:
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Hech qanday baholangan restoran topilmadi.", reply_markup=reply_markup)
            return SELECTING_ACTION

        sorted_restaurants = sorted(
            rated_restaurants.items(),
            key=lambda x: float(x[1].get("avg_rating", 0)),
            reverse=True
        )

        recommendations = "⭐ Tavsiya etilgan restoranlar:\n\n"
        for name, info in sorted_restaurants[:5]:  # Top 5 restaurants
            rating_count = info.get("rating_count", 0)
            recommendations += (
                f"🏆 *{name}* - {info['avg_rating']}⭐ ({rating_count} baho)\n"
                f"📍 Manzil: {info['location']}\n\n"
            )

        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(recommendations, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECTING_ACTION

    elif query.data == CANCEL:
        keyboard = [
            [InlineKeyboardButton("📋 Restoranlarni ko'rish", callback_data=VIEW_RESTAURANTS)],
            [InlineKeyboardButton("⭐ Tavsiya etilgan restoranlar", callback_data=RECOMMEND_RESTAURANTS)],
            [InlineKeyboardButton("ℹ️ Bot haqida", callback_data=BOT_INFO)],
        ]
        if is_admin(user_id):
            keyboard.insert(0, [InlineKeyboardButton("🍽️ Restoran qo'shish", callback_data=ADD_RESTAURANT)])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("Asosiy menyu:\nQuyidagi amallardan birini tanlang:", reply_markup=reply_markup)
        return SELECTING_ACTION

    elif query.data.startswith(DELETE_RESTAURANT):
        if not is_admin(user_id):
            await query.edit_message_text("Sizda restoran o'chirish huquqi yo'q!")
            return SELECTING_ACTION
        restaurant_name = query.data.split(":", 1)[1]
        keyboard = [
            [
                InlineKeyboardButton("✅ Ha", callback_data=f"{CONFIRM_DELETE}:{restaurant_name}"),
                InlineKeyboardButton("❌ Yo'q", callback_data=CANCEL)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Siz rostdan ham '{restaurant_name}' restoranini o'chirmoqchimisiz?",
            reply_markup=reply_markup
        )
        return SELECTING_ACTION

    elif query.data.startswith(CONFIRM_DELETE):
        if not is_admin(user_id):
            await query.edit_message_text("Sizda restoran o'chirish huquqi yo'q!")
            return SELECTING_ACTION
        restaurant_name = query.data.split(":", 1)[1]
        restaurants = load_restaurant_data()
        if restaurant_name in restaurants:
            del restaurants[restaurant_name]
            save_restaurant_data(restaurants)
            await query.edit_message_text(f"'{restaurant_name}' restoran muvaffaqiyatli o'chirildi!")
        else:
            await query.edit_message_text("Bunday restoran topilmadi.")

        keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Restoran o'chirildi. Asosiy menyuga qaytish uchun tugmani bosing.",
            reply_markup=reply_markup
        )
        return SELECTING_ACTION

    elif query.data.startswith(EDIT_RESTAURANT):
        if not is_admin(user_id):
            await query.edit_message_text("Sizda restoran tahrirlash huquqi yo'q!")
            return SELECTING_ACTION
        restaurant_name = query.data.split(":", 1)[1]
        context.user_data["edit_restaurant_name"] = restaurant_name
        await query.edit_message_text(
            f"'{restaurant_name}' uchun yangi nomni kiriting (eski nomni saqlash uchun /skip):"
        )
        return EDITING_RESTAURANT

    elif query.data.startswith(RATE):
        restaurant_name = query.data.split(":", 1)[1]
        context.user_data["rating_restaurant"] = restaurant_name

        keyboard = [
            [
                InlineKeyboardButton("1⭐", callback_data="rate:1"),
                InlineKeyboardButton("2⭐", callback_data="rate:2"),
                InlineKeyboardButton("3⭐", callback_data="rate:3"),
                InlineKeyboardButton("4⭐", callback_data="rate:4"),
                InlineKeyboardButton("5⭐", callback_data="rate:5"),
            ],
            [InlineKeyboardButton("🔙 Bekor qilish", callback_data=CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"'{restaurant_name}' restorani uchun 1 dan 5 gacha baho bering:",
            reply_markup=reply_markup
        )
        return WAITING_FOR_RATING

    elif query.data.startswith("rate:"):
        rating = int(query.data.split(":", 1)[1])
        restaurant_name = context.user_data.get("rating_restaurant")

        if restaurant_name:
            restaurants = load_restaurant_data()
            if restaurant_name in restaurants:
                if "ratings" not in restaurants[restaurant_name]:
                    restaurants[restaurant_name]["ratings"] = []
                restaurants[restaurant_name]["ratings"].append(rating)
                ratings = restaurants[restaurant_name]["ratings"]
                avg_rating = round(sum(ratings) / len(ratings), 1)
                restaurants[restaurant_name]["avg_rating"] = str(avg_rating)
                restaurants[restaurant_name]["rating_count"] = len(ratings)
                save_restaurant_data(restaurants)
                await query.edit_message_text(
                    f"'{restaurant_name}' restoran {rating}⭐ bilan baholandi! (O'rtacha: {avg_rating}⭐)"
                )
            else:
                await query.edit_message_text("Bunday restoran topilmadi.")

        keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Restoran baholandi. Asosiy menyuga qaytish uchun tugmani bosing.",
            reply_markup=reply_markup
        )
        return SELECTING_ACTION

    elif query.data == BOT_INFO:
        bot_info = load_bot_info()
        info_text = bot_info.get("info", "Bot haqida ma'lumot hali kiritilmagan.")

        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=CANCEL)]]
        if is_admin(user_id):
            keyboard.insert(0, [
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=EDIT_BOT_INFO),
                InlineKeyboardButton("❌ O'chirish", callback_data=DELETE_BOT_INFO)
            ])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(f"ℹ️ Bot haqida:\n\n{info_text}", reply_markup=reply_markup)
        return SELECTING_ACTION

    elif query.data == EDIT_BOT_INFO:
        if not is_admin(user_id):
            await query.edit_message_text("Sizda bot ma'lumotini tahrirlash huquqi yo'q!")
            return SELECTING_ACTION
        await query.edit_message_text("Yangi bot ma'lumotini kiriting:")
        return EDITING_BOT_INFO

    elif query.data == DELETE_BOT_INFO:
        if not is_admin(user_id):
            await query.edit_message_text("Sizda bot ma'lumotini o'chirish huquqi yo'q!")
            return SELECTING_ACTION
        save_bot_info({"info": "Bot haqida ma'lumot hali kiritilmagan."})
        keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Bot ma'lumoti o'chirildi.", reply_markup=reply_markup)
        return SELECTING_ACTION

    return SELECTING_ACTION

# Handle restaurant name input
async def add_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle input of restaurant name."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Sizda restoran qo'shish huquqi yo'q!")
        return SELECTING_ACTION
    context.user_data["restaurant_name"] = update.message.text
    await update.message.reply_text("Endi restoran joylashuvini (manzilini) kiriting:")
    return ADDING_LOCATION

# Handle restaurant location input
async def add_restaurant_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle input of restaurant location."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Sizda restoran qo'shish huquqi yo'q!")
        return SELECTING_ACTION
    name = context.user_data["restaurant_name"]
    location = update.message.text

    restaurants = load_restaurant_data()
    restaurants[name] = {"location": location, "ratings": [], "avg_rating": "Baholanmagan", "rating_count": 0}
    save_restaurant_data(restaurants)

    keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Restoran muvaffaqiyatli qo'shildi!\n\n📝 Nomi: {name}\n📍 Manzil: {location}",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

# Handle restaurant editing
async def edit_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle editing of restaurant name."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Sizda restoran tahrirlash huquqi yo'q!")
        return SELECTING_ACTION

    text = update.message.text
    old_name = context.user_data.get("edit_restaurant_name")
    restaurants = load_restaurant_data()

    if text == "/skip":
        new_name = old_name
    else:
        new_name = text

    if old_name not in restaurants:
        await update.message.reply_text("Bunday restoran topilmadi.")
        return SELECTING_ACTION

    context.user_data["new_restaurant_name"] = new_name
    await update.message.reply_text(f"'{new_name}' uchun yangi manzilni kiriting (eski manzilni saqlash uchun /skip):")
    return ADDING_LOCATION

# Handle restaurant location editing
async def edit_restaurant_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle editing of restaurant location."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Sizda restoran tahrirlash huquqi yo'q!")
        return SELECTING_ACTION

    text = update.message.text
    old_name = context.user_data.get("edit_restaurant_name")
    new_name = context.user_data.get("new_restaurant_name")
    restaurants = load_restaurant_data()

    if old_name not in restaurants:
        await update.message.reply_text("Bunday restoran topilmadi.")
        return SELECTING_ACTION

    new_location = text if text != "/skip" else restaurants[old_name]["location"]

    restaurant_data = restaurants.pop(old_name)
    restaurant_data["location"] = new_location
    restaurants[new_name] = restaurant_data
    save_restaurant_data(restaurants)

    keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Restoran muvaffaqiyatli tahrirlandi!\n\n📝 Nomi: {new_name}\n📍 Manzil: {new_location}",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

# Handle bot info editing
async def edit_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle editing of bot info."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Sizda bot ma'lumotini tahrirlash huquqi yo'q!")
        return SELECTING_ACTION

    new_info = update.message.text
    save_bot_info({"info": new_info})

    keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data=CANCEL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Bot ma'lumoti muvaffaqiyatli yangilandi!\n\nℹ️ Yangi ma'lumot:\n{new_info}",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(context.error, Conflict):
        logger.error("Conflict error: Another bot instance is running. Retrying in 10 seconds...")
        time.sleep(10)
        return
    if update and update.effective_message:
        await update.effective_message.reply_text("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")

# Ensure webhook is deleted
async def ensure_webhook_deleted(bot):
    """Delete webhook and drop pending updates."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")
        raise

# Acquire lock to prevent multiple instances
def acquire_lock():
    """Acquire a file lock to ensure single instance."""
    lock_file = open(LOCK_FILE_PATH, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("Lock acquired successfully.")
        return lock_file
    except IOError:
        logger.error("Another instance is already running.")
        lock_file.close()
        return None

# Main function
def main() -> None:
    """Start the bot."""
    # Acquire lock
    lock = acquire_lock()
    if not lock:
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No token provided. Set TELEGRAM_BOT_TOKEN environment variable.")
        lock.close()
        return

    application = Application.builder().token(token).build()

    # Define the ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("admin", admin_panel),
        ],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(menu_actions),
            ],
            ADDING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_restaurant_name),
            ],
            ADDING_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_restaurant_location),
            ],
            WAITING_FOR_RATING: [
                CallbackQueryHandler(menu_actions),
            ],
            EDITING_RESTAURANT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.COMMAND, edit_restaurant),
            ],
            EDITING_BOT_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_bot_info),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False  # Set to True to eliminate PTBUserWarning, but increases memory usage
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    # Initialize bot and delete webhook
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(ensure_webhook_deleted(application.bot))
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        lock.close()
        return

    # Handle graceful shutdown
    def handle_shutdown(signum, frame):
        logger.info("Received shutdown signal. Stopping bot...")
        application.stop_running()
        loop.run_until_complete(application.stop())
        logger.info("Bot stopped gracefully.")
        lock.close()
        exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Retry polling in case of conflicts
    max_retries = 5
    retry_count = 0
    while retry_count < max_retries:
        try:
            logger.info("Starting polling...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except Conflict as e:
            logger.error(f"Conflict error: {e}. Retrying {retry_count + 1}/{max_retries}...")
            retry_count += 1
            try:
                loop.run_until_complete(ensure_webhook_deleted(application.bot))
            except Exception as e:
                logger.error(f"Failed to delete webhook during retry: {e}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            break
    else:
        logger.error("Max retries reached. Please ensure no other bot instances are running.")
        lock.close()
        return

    lock.close()

if __name__ == "__main__":
    main()
