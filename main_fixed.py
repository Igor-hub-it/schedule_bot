import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Database
from config import BOT_TOKEN, ADMIN_IDS, ALLOWED_GROUP_ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

class ScheduleBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Команды для всех пользователей
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("schedule", self.show_schedule))
        self.application.add_handler(CommandHandler("my_bookings", self.show_my_bookings))
        
        # Команды только для админов
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CommandHandler("add_slot", self.add_slot))
        self.application.add_handler(CommandHandler("remove_slot", self.remove_slot))
        self.application.add_handler(CommandHandler("add_user", self.add_user))
        self.application.add_handler(CommandHandler("remove_user", self.remove_user))
        
        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def get_message_object(self, update: Update):
        """Получить объект сообщения для ответа"""
        return update.message or update.callback_query.message
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Неизвестно"
        
        # Проверяем, есть ли пользователь в базе
        if not db.is_user_allowed(user_id):
            await update.message.reply_text(
                "❌ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа."
            )
            return
        
        # Добавляем пользователя в базу, если его там нет
        db.add_user(user_id, username)
        
        keyboard = [
            [InlineKeyboardButton("📅 Показать расписание", callback_data="show_schedule")],
            [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {update.effective_user.first_name}!\n\n"
            "Это бот для записи на занятия.\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🤖 **Команды бота:**

**Для курсантов:**
• `/start` - Начать работу с ботом
• `/schedule` - Показать доступные слоты
• `/my_bookings` - Мои записи
• `/help` - Показать эту справку

**Для администраторов:**
• `/admin` - Панель администратора
• `/add_slot` - Добавить слот времени
• `/remove_slot` - Удалить слот времени
• `/add_user` - Добавить пользователя
• `/remove_user` - Удалить пользователя

**Как записаться:**
1. Нажмите "Показать расписание"
2. Выберите удобную дату и время
3. Подтвердите запись

**Отмена записи:**
Используйте кнопку "Отменить" в разделе "Мои записи"
        """
        message_obj = self.get_message_object(update)
        await message_obj.reply_text(help_text, parse_mode='Markdown')
    
    async def show_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать доступные слоты"""
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        if not db.is_user_allowed(user_id):
            await message_obj.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        slots = db.get_available_slots()
        
        if not slots:
            await message_obj.reply_text("📅 Нет доступных слотов для записи.")
            return
        
        # Группируем слоты по датам
        slots_by_date = {}
        for slot in slots:
            date_str = slot['datetime'].strftime('%d.%m.%Y')
            if date_str not in slots_by_date:
                slots_by_date[date_str] = []
            slots_by_date[date_str].append(slot)
        
        message = "📅 **Доступные слоты для записи:**\n\n"
        
        for date_str, date_slots in sorted(slots_by_date.items()):
            message += f"📆 **{date_str}**\n"
            for slot in date_slots:
                time_str = slot['datetime'].strftime('%H:%M')
                message += f"• {time_str} - {slot['description']}\n"
            message += "\n"
        
        keyboard = []
        for slot in slots[:10]:  # Показываем только первые 10 слотов
            time_str = slot['datetime'].strftime('%d.%m %H:%M')
            keyboard.append([InlineKeyboardButton(
                f"📅 {time_str}",
                callback_data=f"book_{slot['id']}"
            )])
        
        if len(slots) > 10:
            keyboard.append([InlineKeyboardButton("📄 Показать еще", callback_data="show_more")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message_obj.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_my_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать записи пользователя"""
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        if not db.is_user_allowed(user_id):
            await message_obj.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        bookings = db.get_user_bookings(user_id)
        
        if not bookings:
            await message_obj.reply_text("📋 У вас нет активных записей.")
            return
        
        message = "📋 **Ваши записи:**\n\n"
        keyboard = []
        
        for booking in bookings:
            date_str = booking['datetime'].strftime('%d.%m.%Y %H:%M')
            message += f"📅 {date_str}\n"
            message += f"📝 {booking['description']}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"❌ Отменить {date_str}",
                callback_data=f"cancel_{booking['id']}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message_obj.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить слот", callback_data="admin_add_slot")],
            [InlineKeyboardButton("➖ Удалить слот", callback_data="admin_remove_slot")],
            [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📅 Все записи", callback_data="admin_all_bookings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔧 **Панель администратора**\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def add_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить слот времени (команда)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        # Парсим аргументы команды
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неверный формат команды.\n"
                "Используйте: /add_slot ДД.ММ.ГГГГ ЧЧ:ММ Описание\n"
                "Пример: /add_slot 25.12.2024 14:30 Занятие по вождению"
            )
            return
        
        try:
            date_str = context.args[0]
            time_str = context.args[1]
            description = " ".join(context.args[2:]) if len(context.args) > 2 else "Занятие"
            
            # Парсим дату и время
            slot_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            
            # Проверяем, что слот в будущем
            if slot_datetime <= datetime.now():
                await update.message.reply_text("❌ Нельзя добавить слот в прошлом.")
                return
            
            # Добавляем слот
            slot_id = db.add_slot(slot_datetime, description)
            
            await update.message.reply_text(
                f"✅ Слот успешно добавлен!\n"
                f"📅 {slot_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {description}\n"
                f"🆔 ID: {slot_id}"
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты или времени.\n"
                "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ"
            )
    
    async def remove_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить слот времени (команда)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID слота для удаления.\n"
                "Используйте: /remove_slot ID_слота"
            )
            return
        
        try:
            slot_id = int(context.args[0])
            
            if db.remove_slot(slot_id):
                await update.message.reply_text(f"✅ Слот {slot_id} успешно удален.")
            else:
                await update.message.reply_text(f"❌ Слот с ID {slot_id} не найден.")
                
        except ValueError:
            await update.message.reply_text("❌ ID слота должен быть числом.")
    
    async def add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователя (команда)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID пользователя для добавления.\n"
                "Используйте: /add_user USER_ID"
            )
            return
        
        try:
            new_user_id = int(context.args[0])
            username = context.args[1] if len(context.args) > 1 else "Пользователь"
            
            if db.add_user(new_user_id, username):
                await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен.")
            else:
                await update.message.reply_text(f"❌ Пользователь {new_user_id} уже существует.")
                
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")
    
    async def remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить пользователя (команда)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID пользователя для удаления.\n"
                "Используйте: /remove_user USER_ID"
            )
            return
        
        try:
            user_to_remove = int(context.args[0])
            
            if db.remove_user(user_to_remove):
                await update.message.reply_text(f"✅ Пользователь {user_to_remove} удален.")
            else:
                await update.message.reply_text(f"❌ Пользователь {user_to_remove} не найден.")
                
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback'ов от inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "help":
            await self.help(update, context)
        
        elif data == "show_schedule":
            await self.show_schedule(update, context)
        
        elif data == "my_bookings":
            await self.show_my_bookings(update, context)
        
        elif data.startswith("book_"):
            slot_id = int(data.split("_")[1])
            await self.book_slot(update, context, slot_id)
        
        elif data.startswith("cancel_"):
            booking_id = int(data.split("_")[1])
            await self.cancel_booking(update, context, booking_id)
        
        elif data == "admin_add_slot":
            await query.edit_message_text(
                "➕ **Добавление слота**\n\n"
                "Используйте команду:\n"
                "`/add_slot ДД.ММ.ГГГГ ЧЧ:ММ Описание`\n\n"
                "Пример:\n"
                "`/add_slot 25.12.2024 14:30 Занятие по вождению`",
                parse_mode='Markdown'
            )
        
        elif data == "admin_remove_slot":
            await query.edit_message_text(
                "➖ **Удаление слота**\n\n"
                "Используйте команду:\n"
                "`/remove_slot ID_слота`\n\n"
                "Чтобы узнать ID слота, используйте /admin",
                parse_mode='Markdown'
            )
        
        elif data == "admin_users":
            await self.show_users_management(update, context)
        
        elif data == "admin_stats":
            await self.show_stats(update, context)
        
        elif data == "admin_all_bookings":
            await self.show_all_bookings(update, context)
    
    async def book_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Записаться на слот"""
        user_id = update.effective_user.id
        
        if not db.is_user_allowed(user_id):
            await update.callback_query.edit_message_text("❌ У вас нет доступа к этому боту.")
            return
        
        # Проверяем, свободен ли слот
        slot = db.get_slot(slot_id)
        if not slot:
            await update.callback_query.edit_message_text("❌ Слот не найден.")
            return
        
        if slot['is_booked']:
            await update.callback_query.edit_message_text("❌ Этот слот уже занят.")
            return
        
        # Записываем пользователя
        if db.book_slot(slot_id, user_id):
            await update.callback_query.edit_message_text(
                f"✅ Вы успешно записались!\n\n"
                f"📅 {slot['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {slot['description']}\n\n"
                f"Используйте /my_bookings для просмотра ваших записей."
            )
        else:
            await update.callback_query.edit_message_text("❌ Ошибка при записи. Попробуйте еще раз.")
    
    async def cancel_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, booking_id: int):
        """Отменить запись"""
        user_id = update.effective_user.id
        
        if db.cancel_booking(booking_id, user_id):
            await update.callback_query.edit_message_text("✅ Запись успешно отменена.")
        else:
            await update.callback_query.edit_message_text("❌ Ошибка при отмене записи.")
    
    async def show_users_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать управление пользователями"""
        users = db.get_all_users()
        
        message = "👥 **Управление пользователями**\n\n"
        message += f"Всего пользователей: {len(users)}\n\n"
        
        for user in users[:10]:  # Показываем первых 10
            message += f"🆔 {user['user_id']} - @{user['username']}\n"
        
        if len(users) > 10:
            message += f"\n... и еще {len(users) - 10} пользователей"
        
        message += "\n\n**Команды:**\n"
        message += "`/add_user USER_ID username` - Добавить пользователя\n"
        message += "`/remove_user USER_ID` - Удалить пользователя"
        
        await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        stats = db.get_stats()
        
        message = "📊 **Статистика**\n\n"
        message += f"👥 Всего пользователей: {stats['total_users']}\n"
        message += f"📅 Всего слотов: {stats['total_slots']}\n"
        message += f"✅ Записей: {stats['total_bookings']}\n"
        message += f"🆓 Свободных слотов: {stats['available_slots']}\n"
        message += f"📈 Заполненность: {stats['occupancy_rate']:.1f}%"
        
        await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    
    async def show_all_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все записи"""
        bookings = db.get_all_bookings()
        
        if not bookings:
            await update.callback_query.edit_message_text("📋 Нет активных записей.")
            return
        
        message = "📋 **Все записи**\n\n"
        
        for booking in bookings[:15]:  # Показываем первые 15
            date_str = booking['datetime'].strftime('%d.%m.%Y %H:%M')
            message += f"📅 {date_str}\n"
            message += f"👤 @{booking['username']} (ID: {booking['user_id']})\n"
            message += f"📝 {booking['description']}\n\n"
        
        if len(bookings) > 15:
            message += f"... и еще {len(bookings) - 15} записей"
        
        await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        await update.message.reply_text(
            "Не понимаю эту команду. Используйте /help для получения справки."
        )
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = ScheduleBot()
    bot.run()
