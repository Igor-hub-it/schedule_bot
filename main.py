import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

class ScheduleBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.database = Database()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Команды для всех пользователей
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("schedule", self.show_schedule))
        self.application.add_handler(CommandHandler("my_bookings", self.show_my_bookings))
        self.application.add_handler(CommandHandler("my_id", self.get_my_id))
        self.application.add_handler(CommandHandler("group_id", self.get_group_id))
        
        # Команды только для админов
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CommandHandler("add_slot", self.add_slot))
        self.application.add_handler(CommandHandler("remove_slot", self.remove_slot))
        self.application.add_handler(CommandHandler("add_user", self.add_user))
        self.application.add_handler(CommandHandler("remove_user", self.remove_user))
        self.application.add_handler(CommandHandler("set_group", self.set_group))
        self.application.add_handler(CommandHandler("make_admin", self.make_admin))
        self.application.add_handler(CommandHandler("remove_admin", self.remove_admin))
        self.application.add_handler(CommandHandler("list_admins", self.list_admins))
        
        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def get_message_object(self, update: Update):
        """Получить объект сообщения для ответа"""
        return update.message or update.callback_query.message
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        # Проверяем статических администраторов из config.py
        if user_id in ADMIN_IDS:
            return True
        
        # Проверяем динамических администраторов из базы данных
        return self.database.get_user_role(user_id) == 'admin'
    
    def get_user_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """Получить клавиатуру в зависимости от прав пользователя"""
        if self.is_admin(user_id):
            # Клавиатура для администраторов
            keyboard = [
                [KeyboardButton("📅 Календарь слотов")]
            ]
        else:
            # Клавиатура для обычных пользователей
            keyboard = [
                [KeyboardButton("📅 Расписание"), KeyboardButton("📋 Мои записи")]
            ]
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    async def is_user_in_group(self, user_id: int, group_id: int) -> bool:
        """Проверить, состоит ли пользователь в группе"""
        try:
            # Получаем информацию о пользователе
            chat_member = await self.application.bot.get_chat_member(group_id, user_id)
            
            # Проверяем статус пользователя в группе
            if chat_member.status in ['member', 'administrator', 'creator']:
                logger.info(f"Пользователь {user_id} найден в группе {group_id} со статусом: {chat_member.status}")
                return True
            else:
                logger.info(f"Пользователь {user_id} не является участником группы {group_id}, статус: {chat_member.status}")
                return False
                
        except Exception as e:
            # Если не удалось проверить (пользователь не в группе или ошибка)
            logger.warning(f"Не удалось проверить членство в группе для пользователя {user_id}: {e}")
            return False
    
    async def check_user_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверить доступ пользователя к боту"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Неизвестно"
        
        # Обновляем username пользователя при каждом обращении
        if self.database.user_exists(user_id):
            self.database.add_user(user_id, username)
        
        # Проверяем, состоит ли пользователь в разрешенной группе
        if ALLOWED_GROUP_ID and not await self.is_user_in_group(user_id, ALLOWED_GROUP_ID):
            # Если пользователь был в базе, но исключен из группы - удаляем его
            if self.database.user_exists(user_id):
                # Освобождаем все забронированные слоты пользователя
                freed_slots = self.database.free_user_bookings(user_id)
                logger.info(f"Освобождено {freed_slots} слотов пользователя {user_id} (@{username})")
                
                # Удаляем пользователя из базы
                self.database.remove_user(user_id)
                logger.info(f"Пользователь {user_id} (@{username}) исключен из группы и удален из базы")
            
            await update.message.reply_text(
                "❌ Доступ запрещен.\n\n"
                "Для использования бота необходимо состоять в группе.\n\n"
                "Обратитесь к администратору для получения доступа."
            )
            return False
        
        return True
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        # Проверяем, что команда пришла в личном чате, а не в группе
        # Исключение: команды администрирования могут работать в группах
        if update.message.chat.type != 'private':
            return
        
        # Проверяем доступ пользователя
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Неизвестно"
        
        # Проверяем, есть ли пользователь в базе
        if not self.database.user_exists(user_id):
            # Добавляем пользователя в базу
            self.database.add_user(user_id, username)
            logger.info(f"Добавлен новый пользователь: {user_id} (@{username})")
        else:
            # Обновляем username, если он изменился
            self.database.add_user(user_id, username)
            logger.info(f"Обновлен username пользователя: {user_id} (@{username})")
        
        # Получаем клавиатуру в зависимости от прав пользователя
        reply_keyboard = self.get_user_keyboard(user_id)
        
        await update.message.reply_text(
            "👋 Добро пожаловать в бот для записи на занятия!\n\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=reply_keyboard
        )
    
    async def get_my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получить ID пользователя"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Неизвестно"
        first_name = update.effective_user.first_name or "Неизвестно"
        
        message = f"""
🆔 **Ваш ID:** `{user_id}`
👤 **Имя:** {first_name}
📝 **Username:** @{username}

**Для получения доступа:**
1. Скопируйте ваш ID: `{user_id}`
2. Отправьте его администратору
3. Администратор добавит вас в систему

**Контакты администратора:**
@Captain_Cobain
        """
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def get_group_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получить ID группы"""
        # Эта команда работает в любом чате (личном или группе)
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        
        if chat_type == 'private':
            message = """
❌ Эта команда работает только в группе!

**Как получить ID группы:**

1. **Добавьте бота в группу** как администратора
2. **В группе напишите:** `/group_id`
3. **Скопируйте ID группы** из ответа
4. **Настройте группу:** `/set_group ID_группы`

**Альтернативные способы:**
• Веб-версия Telegram: web.telegram.org
• Бот @RawDataBot
• Бот @getidsbot

**Текущий ID группы в настройках:** `-3114498461`
            """
        else:
            # Это группа
            message = f"""
🆔 **ID группы:** `{chat_id}`
📝 **Название:** {update.effective_chat.title}
👥 **Тип:** {chat_type}

**Для настройки:**
1. Скопируйте ID: `{chat_id}`
2. Напишите боту лично: `/set_group {chat_id}`
3. Участники группы получат автоматический доступ

**Текущий ID в настройках:** `-3114498461`
            """
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🤖 **Команды бота:**

**Для получения доступа:**
• `/my_id` - Получить ваш ID для регистрации
• `/group_id` - Получить ID группы (только в группе)

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
• `/set_group` - Настроить группу для автоматического доступа

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
        """Показать календарь доступных слотов"""
        # Проверяем доступ пользователя
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        
        # Показываем календарь текущего месяца
        await self.show_schedule_calendar(update, context)
    
    async def show_schedule_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year=None, month=None):
        """Показать календарь доступных слотов"""
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        
        # Устанавливаем текущую дату если не указана
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        # Получаем все слоты за месяц
        slots = self.database.get_slots_by_month(year, month)
        
        # Получаем доступные слоты за месяц
        available_slots = self.database.get_available_slots_by_month(year, month)
        
        # Создаем календарь с датами
        calendar_text = f"📅 **Расписание - {month:02d}.{year}**\n\n"
        
        # Создаем календарную сетку
        import calendar
        cal = calendar.monthcalendar(year, month)
        
        # Заголовки дней недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        calendar_text += " ".join(f"{day:>2}" for day in week_days) + "\n"
        
        # Создаем кнопки для календаря
        keyboard = []
        
        for week in cal:
            week_buttons = []
            for day in week:
                if day == 0:
                    week_buttons.append(InlineKeyboardButton(" ", callback_data="cal_empty"))
                else:
                    # Проверяем, есть ли доступные слоты на этот день
                    day_slots = [slot for slot in available_slots if slot['datetime'].day == day]
                    if day_slots:
                        button_text = f"📅{day}"
                    else:
                        button_text = f"{day:2d}"
                    
                    week_buttons.append(InlineKeyboardButton(
                        button_text, 
                        callback_data=f"schedule_cal_select_{year}_{month}_{day}"
                    ))
            keyboard.append(week_buttons)
        
        # Кнопки навигации по месяцам
        nav_buttons = []
        
        # Предыдущий месяц
        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"schedule_cal_prev_{prev_year}_{prev_month}"))
        
        # Текущий месяц
        current_month = datetime.now().month
        current_year = datetime.now().year
        nav_buttons.append(InlineKeyboardButton(f"{month:02d}.{year}", callback_data=f"schedule_cal_current_{current_year}_{current_month}"))
        
        # Следующий месяц
        next_month = month + 1
        next_year = year
        if next_month == 13:
            next_month = 1
            next_year += 1
        
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"schedule_cal_next_{next_year}_{next_month}"))
        
        keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    calendar_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await message_obj.reply_text(
                    calendar_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Ошибка при показе календаря расписания: {e}")
            await message_obj.reply_text(
                "❌ Произошла ошибка при загрузке календаря. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
    
    async def show_schedule_day_slots(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, day: int):
        """Показать доступные слоты на выбранный день"""
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        

        selected_date = date(year, month, day)
        date_str = selected_date.strftime('%d.%m.%Y')
        
        # Получаем доступные слоты на этот день
        available_slots = self.database.get_available_slots_by_day(year, month, day)
        
        message_text = f"📅 **Доступные слоты на {date_str}:**\n\n"
        
        if available_slots:
            message_text += "**Свободные слоты:**\n"
            keyboard = []
            
            for slot in available_slots:
                time_str = slot['datetime'].strftime('%H:%M')
                message_text += f"• {time_str} - {slot['description']}\n"
                
                # Создаем кнопку для записи
                keyboard.append([InlineKeyboardButton(
                    f"📅 {time_str} - {slot['description']}",
                    callback_data=f"book_{slot['id']}"
                )])
        else:
            message_text += "На этот день нет доступных слотов.\n"
            keyboard = []
        
        # Создаем кнопки
        # Кнопка "Назад к календарю"
        keyboard.append([InlineKeyboardButton("⬅️ Назад к календарю", callback_data=f"schedule_calendar_{year}_{month}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка при показе слотов дня {date_str}: {e}")
            await update.callback_query.edit_message_text(
                "❌ Произошла ошибка при загрузке слотов. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
    
    async def show_my_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать записи пользователя"""
        # Проверяем доступ пользователя
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        
        bookings = self.database.get_user_bookings(user_id)
        
        if not bookings:
            await message_obj.reply_text("📋 У вас нет будущих записей.\n\nВсе прошедшие записи скрыты из списка.")
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
    
    async def show_user_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year=None, month=None):
        """Показать календарь записей пользователя"""
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        
        
        # Устанавливаем текущую дату если не указана
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        # Получаем все слоты за месяц
        slots = self.database.get_slots_by_month(year, month)
        
        # Получаем записи пользователя за месяц
        user_bookings = self.database.get_user_bookings_by_month(user_id, year, month)
        
        # Создаем календарь с датами
        calendar_text = f"📅 **Мои записи - {month:02d}.{year}**\n\n"
        
        # Создаем календарную сетку
        import calendar
        cal = calendar.monthcalendar(year, month)
        
        # Заголовки дней недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        calendar_text += " ".join(f"{day:>2}" for day in week_days) + "\n"
        
        # Создаем кнопки для календаря
        keyboard = []
        
        for week in cal:
            week_buttons = []
            for day in week:
                if day == 0:
                    week_buttons.append(InlineKeyboardButton(" ", callback_data="cal_empty"))
                else:
                    # Проверяем, есть ли записи пользователя на этот день
                    day_bookings = [booking for booking in user_bookings if booking['datetime'].day == day]
                    if day_bookings:
                        button_text = f"📅{day}"
                    else:
                        button_text = f"{day:2d}"
                    
                    week_buttons.append(InlineKeyboardButton(
                        button_text, 
                        callback_data=f"user_cal_select_{year}_{month}_{day}"
                    ))
            keyboard.append(week_buttons)
        
        # Кнопки навигации по месяцам
        nav_buttons = []
        
        # Предыдущий месяц
        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"user_cal_prev_{prev_year}_{prev_month}"))
        
        # Текущий месяц
        current_month = datetime.now().month
        current_year = datetime.now().year
        nav_buttons.append(InlineKeyboardButton(f"{month:02d}.{year}", callback_data=f"user_cal_current_{current_year}_{current_month}"))
        
        # Следующий месяц
        next_month = month + 1
        next_year = year
        if next_month == 13:
            next_month = 1
            next_year += 1
        
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"user_cal_next_{next_year}_{next_month}"))
        
        keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    calendar_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await message_obj.reply_text(
                    calendar_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Ошибка при показе календаря пользователя: {e}")
            await message_obj.reply_text(
                "❌ Произошла ошибка при загрузке календаря. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
    
    async def show_user_day_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, day: int):
        """Показать записи пользователя на выбранный день"""
        user_id = update.effective_user.id
        message_obj = self.get_message_object(update)
        

        selected_date = date(year, month, day)
        date_str = selected_date.strftime('%d.%m.%Y')
        
        # Получаем записи пользователя на этот день
        user_bookings = self.database.get_user_bookings_by_day(user_id, year, month, day)
        
        message_text = f"📅 **Мои записи на {date_str}:**\n\n"
        
        if user_bookings:
            message_text += "**Ваши записи:**\n"
            for booking in user_bookings:
                time_str = booking['datetime'].strftime('%H:%M')
                message_text += f"• {time_str} - {booking['description']}\n"
        else:
            message_text += "На этот день у вас нет записей.\n"
        
        # Создаем кнопки
        keyboard = []
        # Кнопка "Назад к календарю"
        keyboard.append([InlineKeyboardButton("⬅️ Назад к календарю", callback_data=f"user_calendar_{year}_{month}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка при показе записей дня {date_str}: {e}")
            await update.callback_query.edit_message_text(
                "❌ Произошла ошибка при загрузке записей. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        keyboard = [
            [InlineKeyboardButton("📅 Календарь слотов", callback_data="admin_calendar")],
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
    
    async def show_admin_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year=None, month=None):
        """Показать календарь для админа"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        # Устанавливаем текущую дату если не указана
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        # Получаем все слоты за месяц
        slots = self.database.get_slots_by_month(year, month)
        
        # Создаем календарь с датами
        calendar_text = f"📅 **Календарь слотов - {month:02d}.{year}**\n\n"
        
        # Создаем календарную сетку
        import calendar
        cal = calendar.monthcalendar(year, month)
        
        # Заголовки дней недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        calendar_text += " ".join(f"{day:>2}" for day in week_days) + "\n"
        
        # Создаем кнопки для календаря
        keyboard = []
        
        for week in cal:
            week_buttons = []
            for day in week:
                if day == 0:
                    week_buttons.append(InlineKeyboardButton(" ", callback_data="cal_empty"))
                else:
                    # Проверяем, есть ли слоты на этот день
                    day_slots = [slot for slot in slots if slot[1].day == day]
                    if day_slots:
                        button_text = f"📅{day}"
                    else:
                        button_text = f"{day:2d}"
                    
                    week_buttons.append(InlineKeyboardButton(
                        button_text, 
                        callback_data=f"cal_select_{year}_{month}_{day}"
                    ))
            keyboard.append(week_buttons)
        
        # Кнопки навигации по месяцам
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        
        nav_buttons = [
            InlineKeyboardButton("⬅️", callback_data=f"cal_prev_{prev_year}_{prev_month}"),
            InlineKeyboardButton(f"{month:02d}.{year}", callback_data="cal_current"),
            InlineKeyboardButton("➡️", callback_data=f"cal_next_{next_year}_{next_month}")
        ]
        keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем или редактируем сообщение
        if update.callback_query:
            await update.callback_query.edit_message_text(
                calendar_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                calendar_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    async def show_day_slots(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, day: int):
        """Показать слоты конкретного дня"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        # Получаем слоты за день
        target_date = date(year, month, day)
        slots = self.database.get_slots_by_month(year, month)
        day_slots = [slot for slot in slots if slot[1].date() == target_date]
        
        # Создаем текст сообщения
        message_text = f"📅 **Слоты на {day:02d}.{month:02d}.{year}**\n\n"
        
        if day_slots:
            message_text += "**Доступные слоты:**\n"
            for slot in day_slots:
                slot_id = slot[0]
                # Получаем записи на этот слот
                bookings = self.database.get_bookings_by_slot(slot_id)
                active_bookings = bookings  # Все записи активны, так как мы работаем с time_slots
                
                message_text += f"• {slot[1].strftime('%H:%M')} - {slot[2]}\n"
                
                if active_bookings:
                    # Показываем username первого активного пользователя
                    username = active_bookings[0][5] or f"ID:{active_bookings[0][4]}"
                    # Добавляем @ для кликабельности и экранируем специальные символы Markdown
                    if username.startswith('@'):
                        username_escaped = username.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                    else:
                        username_escaped = f"@{username}".replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                    message_text += f"  Записан: {username_escaped}\n"
                else:
                    message_text += f"  Свободен\n"
        else:
            message_text += "На этот день слотов нет.\n"
        
        # Создаем кнопки
        keyboard = []
        
        # Кнопки управления слотами
        action_buttons = [InlineKeyboardButton("➕ Добавить слот", callback_data=f"add_slot_{year}_{month}_{day}")]
        
        # Кнопка удаления только если есть слоты
        if slots:
            action_buttons.append(InlineKeyboardButton("🗑️ Удалить слот", callback_data=f"remove_slot_{year}_{month}_{day}"))
        
        keyboard.append(action_buttons)
        
        # Кнопка назад к календарю
        back_button = [InlineKeyboardButton("🔙 Назад к календарю", callback_data=f"cal_prev_{year}_{month}")]
        keyboard.append(back_button)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_remove_slot_selector(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, day: int):
        """Показать селектор слотов для удаления"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        # Получаем слоты за день
        target_date = date(year, month, day)
        slots = self.database.get_slots_by_month(year, month)
        day_slots = [slot for slot in slots if slot[1].date() == target_date]
        
        if not day_slots:
            await update.callback_query.answer("На этот день нет слотов для удаления.")
            return
        
        # Создаем текст сообщения
        message_text = f"🗑️ **Удаление слотов на {day:02d}.{month:02d}.{year}**\n\n"
        message_text += "Выберите слот для удаления:\n"
        
        # Создаем кнопки для каждого слота
        keyboard = []
        for slot in day_slots:
            slot_text = f"{slot[1].strftime('%H:%M')} - {slot[2]}"
            if slot[3] > 0:  # Если есть записи
                slot_text += f" (⚠️ {slot[3]} записей)"
            
            keyboard.append([InlineKeyboardButton(
                slot_text, 
                callback_data=f"delete_slot_{slot[0]}"
            )])
        
        # Кнопка назад
        back_button = [InlineKeyboardButton("🔙 Назад", callback_data=f"cal_select_{year}_{month}_{day}")]
        keyboard.append(back_button)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_date_selector(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать селектор даты для добавления слота"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        
        # Создаем календарь для выбора даты
        calendar_text = f"📅 **Выберите дату для добавления слота**\n\n"
        calendar_text += f"**{current_month:02d}.{current_year}**\n"
        calendar_text += "Пн Вт Ср Чт Пт Сб Вс\n"
        
        # Получаем первый день месяца и количество дней
        first_day = date(current_year, current_month, 1)
        last_day = date(current_year, current_month + 1, 1) - timedelta(days=1) if current_month < 12 else date(current_year + 1, 1, 1) - timedelta(days=1)
        
        # Находим день недели первого дня (0 = понедельник)
        start_weekday = first_day.weekday()
        
        # Создаем календарную сетку с кнопками
        keyboard = []
        current_row = []
        
        # Добавляем пустые кнопки для выравнивания
        for _ in range(start_weekday):
            current_row.append(InlineKeyboardButton(" ", callback_data="cal_empty"))
        
        for day in range(1, last_day.day + 1):
            current_date = date(current_year, current_month, day)
            
            # Проверяем, не прошедшая ли это дата
            if current_date >= now.date():
                button_text = f"{day:2d}"
                callback_data = f"cal_select_{current_year}_{current_month}_{day}"
            else:
                button_text = f" {day:2d} "
                callback_data = "cal_empty"
            
            current_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            
            # Переходим на новую строку каждые 7 дней
            if len(current_row) == 7:
                keyboard.append(current_row)
                current_row = []
        
        # Добавляем оставшиеся кнопки
        if current_row:
            # Дополняем строку пустыми кнопками
            while len(current_row) < 7:
                current_row.append(InlineKeyboardButton(" ", callback_data="cal_empty"))
            keyboard.append(current_row)
        
        # Кнопки навигации
        prev_month = current_month - 1 if current_month > 1 else 12
        prev_year = current_year if current_month > 1 else current_year - 1
        next_month = current_month + 1 if current_month < 12 else 1
        next_year = current_year if current_month < 12 else current_year + 1
        
        nav_buttons = [
            InlineKeyboardButton("◀️", callback_data=f"cal_prev_{prev_year}_{prev_month}"),
            InlineKeyboardButton(f"{current_month:02d}.{current_year}", callback_data="cal_current"),
            InlineKeyboardButton("▶️", callback_data=f"cal_next_{next_year}_{next_month}")
        ]
        keyboard.append(nav_buttons)
        
        # Кнопка назад
        keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data="admin_calendar")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            calendar_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_time_selector(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year, month, day):
        """Показать селектор времени для добавления слота"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        selected_date = date(year, month, day)
        date_str = selected_date.strftime('%d.%m.%Y')
        
        # Создаем кнопки с временами согласно расписанию
        keyboard = []
        
        # Пн-Пт: 8:00, 9:30, 11:00, 12:30, 14:00, 15:30, 17:00, 18:30
        workday_times = ["08:00", "09:30", "11:00", "12:30", "14:00", "15:30", "17:00", "18:30"]
        
        # Разбиваем на группы по 4 времени для удобства
        for i in range(0, len(workday_times), 4):
            time_buttons = []
            for time in workday_times[i:i+4]:
                time_buttons.append(InlineKeyboardButton(time, callback_data=f"time_select_{year}_{month}_{day}_{time}"))
            keyboard.append(time_buttons)
        
        # Кнопка для ввода произвольного времени
        keyboard.append([InlineKeyboardButton("🕐 Другое время", callback_data=f"custom_time_{year}_{month}_{day}")])
        
        # Кнопка назад
        keyboard.append([InlineKeyboardButton("🔙 Назад к выбору даты", callback_data="cal_add_slot")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            f"🕐 **Выберите время для {date_str}**\n\n"
            "Нажмите на время или выберите 'Другое время' для ввода вручную.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    
    async def show_custom_time_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year, month, day):
        """Показать форму для ввода произвольного времени"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        selected_date = date(year, month, day)
        date_str = selected_date.strftime('%d.%m.%Y')
        
        
        # Сохраняем данные в контексте
        context.user_data['pending_time'] = {
            'year': year,
            'month': month,
            'day': day,
            'date_str': date_str
        }
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к выбору времени", callback_data=f"cal_select_{year}_{month}_{day}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cal_select_{year}_{month}_{day}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            f"🕐 **Введите время для {date_str}**\n\n"
            "Отправьте время в формате ЧЧ:ММ\n"
            "Например: 14:30\n\n"
            "**Для отмены:** напишите 'отмена' или используйте кнопки ниже.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def create_slot_from_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year, month, day, time, description):
        """Создать слот из календаря"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            message_obj = self.get_message_object(update)
            await message_obj.reply_text("❌ У вас нет прав администратора.")
            return
        
        try:
            
            # Создаем datetime объект
            slot_datetime = datetime(
                year,
                month,
                day,
                int(time.split(':')[0]),
                int(time.split(':')[1])
            )
            
            # Проверяем, что время в будущем
            if slot_datetime <= datetime.now():
                message_obj = self.get_message_object(update)
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        "❌ Нельзя создать слот в прошлом времени.",
                        parse_mode='Markdown'
                    )
                else:
                    await message_obj.reply_text(
                        "❌ Нельзя создать слот в прошлом времени.",
                        parse_mode='Markdown'
                    )
                return
            
            # Проверяем, нет ли уже слота на это время
            existing_slots = self.database.get_slots_by_month(year, month)
            for slot in existing_slots:
                if slot[1] == slot_datetime:
                    date_str = date(year, month, day).strftime('%d.%m.%Y')
                    message_obj = self.get_message_object(update)
                    if update.callback_query:
                        await update.callback_query.edit_message_text(
                            f"❌ **Слот уже существует!**\n\n"
                            f"📅 Дата: {date_str}\n"
                            f"🕐 Время: {time}\n\n"
                            f"На это время уже есть слот. Выберите другое время.",
                            parse_mode='Markdown'
                        )
                    else:
                        await message_obj.reply_text(
                            f"❌ **Слот уже существует!**\n\n"
                            f"📅 Дата: {date_str}\n"
                            f"🕐 Время: {time}\n\n"
                            f"На это время уже есть слот. Выберите другое время.",
                            parse_mode='Markdown'
                        )
                    return
            
            # Добавляем слот в базу данных
            slot_id = self.database.add_slot(slot_datetime, description)
            
            if slot_id:
                date_str = date(year, month, day).strftime('%d.%m.%Y')
                message_obj = self.get_message_object(update)
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        f"✅ **Слот успешно создан!**\n\n"
                        f"📅 Дата: {date_str}\n"
                        f"🕐 Время: {time}\n\n"
                        "Слот добавлен в календарь и доступен для записи.",
                        parse_mode='Markdown'
                    )
                else:
                    await message_obj.reply_text(
                        f"✅ **Слот успешно создан!**\n\n"
                        f"📅 Дата: {date_str}\n"
                        f"🕐 Время: {time}\n\n"
                        "Слот добавлен в календарь и доступен для записи.",
                        parse_mode='Markdown'
                    )
            else:
                message_obj = self.get_message_object(update)
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        "❌ Ошибка при создании слота. Попробуйте еще раз.",
                        parse_mode='Markdown'
                    )
                else:
                    await message_obj.reply_text(
                        "❌ Ошибка при создании слота. Попробуйте еще раз.",
                        parse_mode='Markdown'
                    )
                
        except Exception as e:
            logger.error(f"Ошибка при создании слота: {e}")
            message_obj = self.get_message_object(update)
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Ошибка при создании слота. Проверьте правильность данных.",
                    parse_mode='Markdown'
                )
            else:
                await message_obj.reply_text(
                    "❌ Ошибка при создании слота. Проверьте правильность данных.",
                    parse_mode='Markdown'
                )
    
    async def show_slot_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Показать детали слота с возможностью удаления"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        try:
            # Получаем информацию о слоте
            slots = self.database.get_all_slots()
            slot_info = None
            
            for slot in slots:
                if slot[0] == slot_id:  # slot[0] - это ID
                    slot_info = slot
                    break
            
            if not slot_info:
                await update.callback_query.answer("❌ Слот не найден.")
                return
            
            slot_id, slot_datetime, description = slot_info
            
            # Получаем количество записей на этот слот
            bookings = self.database.get_bookings_by_slot(slot_id)
            active_bookings = bookings  # Все записи активны, так как мы работаем с time_slots
            
            # Форматируем дату и время
            date_str = slot_datetime.strftime("%d.%m.%Y")
            time_str = slot_datetime.strftime("%H:%M")
            
            text = f"📅 **Детали слота**\n\n"
            text += f"📆 **Дата:** {date_str}\n"
            text += f"🕐 **Время:** {time_str}\n"
            text += f"📝 **Описание:** {description}\n"
            text += f"👥 **Записей:** {len(active_bookings)}\n\n"
            
            if len(active_bookings) > 0:
                text += "⚠️ **Нельзя удалить слот с активными записями!**\n"
                text += "Сначала отмените все записи на этот слот."
            else:
                text += "✅ **Слот можно удалить**"
            
            keyboard = []
            
            if len(active_bookings) == 0:
                keyboard.append([InlineKeyboardButton("🗑️ Удалить слот", callback_data=f"delete_slot_{slot_id}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data="admin_calendar")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при показе деталей слота: {e}")
            await update.callback_query.answer("❌ Произошла ошибка при загрузке слота.")
    
    async def delete_slot_from_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Удалить слот из календаря"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        try:
            # Сначала пробуем обычное удаление
            success, message = self.database.delete_slot(slot_id)
            
            if success:
                await update.callback_query.answer("✅ Слот успешно удален!")
                # Возвращаемся к календарю
                await self.show_admin_calendar(update, context)
            else:
                # Если есть забронированные слоты, предлагаем принудительное удаление
                if "активными записями" in message:
                    # Создаем кнопку для принудительного удаления
                    keyboard = [
                        [InlineKeyboardButton("🗑️ Удалить принудительно", callback_data=f"force_delete_{slot_id}")],
                        [InlineKeyboardButton("❌ Отмена", callback_data="admin_calendar")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.callback_query.edit_message_text(
                        f"⚠️ **Предупреждение**\n\n"
                        f"На этот слот есть активные записи.\n\n"
                        f"При принудительном удалении:\n"
                        f"• Слот будет удален\n"
                        f"• Все записи будут отменены\n"
                        f"• Пользователи получат уведомление\n\n"
                        f"Продолжить?",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await update.callback_query.answer(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"Ошибка при удалении слота: {e}")
            await update.callback_query.answer("❌ Произошла ошибка при удалении слота.")
    
    async def force_delete_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Принудительно удалить слот с уведомлением пользователей"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        try:
            # Принудительно удаляем слот
            success, message, affected_users = self.database.force_delete_slot(slot_id)
            
            if success:
                # Уведомляем затронутых пользователей
                if affected_users:
                    for user_id_affected, username in affected_users:
                        try:
                            await self.application.bot.send_message(
                                chat_id=user_id_affected,
                                text="⚠️ **Ваша запись была отменена**\n\n"
                                     "Администратор удалил слот, на который вы были записаны.\n"
                                     "Пожалуйста, выберите другое время для записи.",
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logger.error(f"Не удалось уведомить пользователя {user_id_affected}: {e}")
                
                await update.callback_query.edit_message_text(
                    f"✅ **Слот принудительно удален**\n\n"
                    f"Уведомлено пользователей: {len(affected_users)}",
                    parse_mode='Markdown'
                )
                
                # Возвращаемся к календарю через 2 секунды
                await asyncio.sleep(2)
                await self.show_admin_calendar(update, context)
            else:
                await update.callback_query.answer(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"Ошибка при принудительном удалении слота: {e}")
            await update.callback_query.answer("❌ Произошла ошибка при удалении слота.")
    
    async def add_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить слот времени (команда)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
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
            slot_id = self.database.add_slot(slot_datetime, description)
            
            await update.message.reply_text(
                f"✅ Слот успешно добавлен!\n"
                f"📅 {slot_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {description}"
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты или времени.\n"
                "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ"
            )
    
    async def remove_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить слот времени (команда)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
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
            
            if self.database.remove_slot(slot_id):
                await update.message.reply_text(f"✅ Слот {slot_id} успешно удален.")
            else:
                await update.message.reply_text(f"❌ Слот с ID {slot_id} не найден.")
                
        except ValueError:
            await update.message.reply_text("❌ ID слота должен быть числом.")
    
    async def add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователя (команда)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
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
            
            if self.database.add_user(new_user_id, username):
                await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен.")
            else:
                await update.message.reply_text(f"❌ Пользователь {new_user_id} уже существует.")
                
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")
    
    async def remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить пользователя (команда)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
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
            
            if self.database.remove_user(user_to_remove):
                await update.message.reply_text(f"✅ Пользователь {user_to_remove} удален.")
            else:
                await update.message.reply_text(f"❌ Пользователь {user_to_remove} не найден.")
                
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")
    
    async def set_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настроить группу для автоматического доступа"""
        # Эта команда работает в любом чате (личном или группе)
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID группы.\n"
                "Используйте: /set_group GROUP_ID\n\n"
                "Чтобы получить ID группы:\n"
                "1. Добавьте бота в группу\n"
                "2. Напишите в группе: @userinfobot\n"
                "3. Скопируйте ID группы (начинается с -)"
            )
            return
        
        try:
            group_id = int(context.args[0])
            
            # Обновляем конфигурацию
            global ALLOWED_GROUP_ID
            ALLOWED_GROUP_ID = group_id
            
            # Проверяем доступ к группе
            try:
                chat_info = await context.bot.get_chat(group_id)
                await update.message.reply_text(
                    f"✅ Группа настроена!\n"
                    f"📝 Название: {chat_info.title}\n"
                    f"🆔 ID: {group_id}\n\n"
                    f"Теперь участники этой группы могут автоматически получать доступ к боту."
                )
            except Exception as e:
                await update.message.reply_text(
                    f"⚠️ Группа настроена, но не удалось проверить доступ:\n"
                    f"ID: {group_id}\n"
                    f"Ошибка: {str(e)}"
                )
                
        except ValueError:
            await update.message.reply_text("❌ ID группы должен быть числом.")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback'ов от inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        # Проверяем, что callback пришел в личном чате, а не в группе
        # Исключение: команды администрирования могут работать в группах
        if query.message.chat.type != 'private':
            return
        
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
        
        elif data == "admin_calendar":
            await self.show_admin_calendar(update, context)
        
        elif data.startswith("cal_prev_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_admin_calendar(update, context, int(year), month)
        
        elif data.startswith("cal_next_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_admin_calendar(update, context, int(year), month)
        
        elif data == "cal_add_slot":
            await self.show_date_selector(update, context)
        
        elif data.startswith("cal_select_"):
            year, month, day = data.split("_")[2], int(data.split("_")[3]), int(data.split("_")[4])
            await self.show_day_slots(update, context, int(year), month, day)
        
        elif data.startswith("add_slot_"):
            year, month, day = data.split("_")[2], int(data.split("_")[3]), int(data.split("_")[4])
            await self.show_time_selector(update, context, int(year), month, day)
        
        elif data.startswith("remove_slot_"):
            year, month, day = data.split("_")[2], int(data.split("_")[3]), int(data.split("_")[4])
            await self.show_remove_slot_selector(update, context, int(year), month, day)
        
        elif data.startswith("time_select_"):
            year, month, day, time = data.split("_")[2], int(data.split("_")[3]), int(data.split("_")[4]), data.split("_")[5]
            await self.create_slot_from_calendar(update, context, int(year), month, day, time, "Слот")
        
        elif data.startswith("custom_time_"):
            year, month, day = data.split("_")[2], int(data.split("_")[3]), int(data.split("_")[4])
            await self.show_custom_time_input(update, context, int(year), month, day)
        
        
        elif data.startswith("slot_details_"):
            slot_id = int(data.split("_")[2])
            await self.show_slot_details(update, context, slot_id)
        
        elif data.startswith("delete_slot_"):
            slot_id = int(data.split("_")[2])
            await self.delete_slot_from_calendar(update, context, slot_id)
        
        elif data.startswith("force_delete_"):
            slot_id = int(data.split("_")[2])
            await self.force_delete_slot(update, context, slot_id)
        
        # Обработка пользовательского календаря
        elif data.startswith("user_cal_prev_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_user_calendar(update, context, int(year), month)
        
        elif data.startswith("user_cal_next_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_user_calendar(update, context, int(year), month)
        
        elif data.startswith("user_cal_current_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_user_calendar(update, context, int(year), month)
        
        elif data.startswith("user_cal_select_"):
            year, month, day = data.split("_")[3], int(data.split("_")[4]), int(data.split("_")[5])
            await self.show_user_day_bookings(update, context, int(year), month, day)
        
        elif data.startswith("user_calendar_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_user_calendar(update, context, int(year), month)
        
        # Обработка календаря расписания
        elif data.startswith("schedule_cal_prev_"):
            year, month = data.split("_")[3], int(data.split("_")[4])
            await self.show_schedule_calendar(update, context, int(year), month)
        
        elif data.startswith("schedule_cal_next_"):
            year, month = data.split("_")[3], int(data.split("_")[4])
            await self.show_schedule_calendar(update, context, int(year), month)
        
        elif data.startswith("schedule_cal_current_"):
            year, month = data.split("_")[3], int(data.split("_")[4])
            await self.show_schedule_calendar(update, context, int(year), month)
        
        elif data.startswith("schedule_cal_select_"):
            year, month, day = data.split("_")[3], int(data.split("_")[4]), int(data.split("_")[5])
            await self.show_schedule_day_slots(update, context, int(year), month, day)
        
        elif data.startswith("schedule_calendar_"):
            year, month = data.split("_")[2], int(data.split("_")[3])
            await self.show_schedule_calendar(update, context, int(year), month)
        
        elif data == "cal_empty":
            # Игнорируем пустые кнопки
            pass
        
        elif data == "admin_all_bookings":
            await self.show_all_bookings(update, context)
    
    async def book_slot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Записаться на слот"""
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        
        # Проверяем, свободен ли слот
        slot = self.database.get_slot(slot_id)
        if not slot:
            await update.callback_query.edit_message_text("❌ Слот не найден.")
            return
        
        if slot['is_booked']:
            await update.callback_query.edit_message_text("❌ Этот слот уже занят.")
            return
        
        # Проверяем, что до начала занятия остается не менее 24 часов
        from datetime import timedelta
        time_until_slot = slot['datetime'] - datetime.now()
        
        if time_until_slot.total_seconds() < 24 * 3600:  # 24 часа в секундах
            hours_left = int(time_until_slot.total_seconds() / 3600)
            await update.callback_query.edit_message_text(
                f"❌ **Нельзя записаться на этот слот!**\n\n"
                f"📅 Дата: {slot['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
                f"⏰ До начала: {hours_left} часов\n\n"
                f"**Запись возможна только за 24 часа или более до начала занятия.**",
                parse_mode='Markdown'
            )
            return
        
        # Записываем пользователя
        if self.database.book_slot(slot_id, user_id):
            await update.callback_query.edit_message_text(
                f"✅ **Вы успешно записались!**\n\n"
                f"📅 {slot['datetime'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {slot['description']}\n\n"
                f"Используйте кнопку \"📋 Мои записи\" для просмотра ваших записей.",
                parse_mode='Markdown'
            )
        else:
            await update.callback_query.edit_message_text("❌ Ошибка при записи. Попробуйте еще раз.")
    
    async def cancel_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, booking_id: int):
        """Отменить запись"""
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        
        if self.database.cancel_booking(booking_id, user_id):
            await update.callback_query.edit_message_text("✅ Запись успешно отменена.")
        else:
            await update.callback_query.edit_message_text("❌ Ошибка при отмене записи.")
    
    async def show_users_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать управление пользователями"""
        users = self.database.get_all_users()
        
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
        stats = self.database.get_stats()
        
        message = "📊 **Статистика**\n\n"
        message += f"👥 Всего пользователей: {stats['total_users']}\n"
        message += f"📅 Всего слотов: {stats['total_slots']}\n"
        message += f"✅ Записей: {stats['total_bookings']}\n"
        message += f"🆓 Свободных слотов: {stats['available_slots']}\n"
        message += f"📈 Заполненность: {stats['occupancy_rate']:.1f}%"
        
        await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    
    async def show_all_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все записи"""
        bookings = self.database.get_all_bookings()
        
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
        # Проверяем, что сообщение пришло в личном чате, а не в группе
        # Исключение: команды администрирования могут работать в группах
        if update.message.chat.type != 'private':
            # Обрабатываем команды администрирования в группах
            user_id = update.effective_user.id
            message_text = update.message.text
            
            # Проверяем, является ли пользователь администратором
            if self.is_admin(user_id):
                # Обрабатываем команды администрирования
                if message_text.startswith('/set_group'):
                    # Извлекаем аргументы команды
                    args = message_text.split()[1:] if len(message_text.split()) > 1 else []
                    context.args = args
                    await self.set_group(update, context)
                elif message_text.startswith('/make_admin'):
                    args = message_text.split()[1:] if len(message_text.split()) > 1 else []
                    context.args = args
                    await self.make_admin(update, context)
                elif message_text.startswith('/remove_admin'):
                    args = message_text.split()[1:] if len(message_text.split()) > 1 else []
                    context.args = args
                    await self.remove_admin(update, context)
                elif message_text.startswith('/list_admins'):
                    await self.list_admins(update, context)
                elif message_text.startswith('/group_id'):
                    await self.get_group_id(update, context)
            return
            
        # Проверяем доступ пользователя
        if not await self.check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Сначала проверяем кнопки навигации (они должны работать всегда)
        if message_text == "📅 Расписание":
            # Очищаем состояние ввода времени, если оно было активно
            if 'pending_time' in context.user_data:
                context.user_data.pop('pending_time', None)
            await self.show_schedule(update, context)
            return
        elif message_text == "📋 Мои записи":
            # Очищаем состояние ввода времени, если оно было активно
            if 'pending_time' in context.user_data:
                context.user_data.pop('pending_time', None)
            await self.show_my_bookings(update, context)
            return
        elif message_text == "📅 Календарь слотов" and self.is_admin(user_id):
            # Очищаем состояние ввода времени, если оно было активно
            if 'pending_time' in context.user_data:
                context.user_data.pop('pending_time', None)
            await self.show_admin_calendar(update, context)
            return
        
        # Проверяем, ожидается ли ввод времени
        if 'pending_time' in context.user_data:
            time_text = update.message.text
            
            # Проверяем команды отмены
            if time_text.lower() in ['отмена', 'cancel', 'отменить', 'назад']:
                pending_data = context.user_data['pending_time']
                # Очищаем данные о времени
                context.user_data.pop('pending_time', None)
                # Возвращаемся к выбору времени
                await self.show_time_selector(update, context, 
                                            pending_data['year'], 
                                            pending_data['month'], 
                                            pending_data['day'])
                return
            
            try:
                # Парсим время в формате ЧЧ:ММ
                hour, minute = map(int, time_text.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    time_str = f"{hour:02d}:{minute:02d}"
                    pending_data = context.user_data['pending_time']
                    
                    # Создаем слот сразу
                    await self.create_slot_from_calendar(update, context, 
                                                        pending_data['year'], 
                                                        pending_data['month'], 
                                                        pending_data['day'], 
                                                        time_str, 
                                                        "Слот")
                    
                    # Очищаем данные о времени
                    context.user_data.pop('pending_time', None)
                    return
                else:
                    await update.message.reply_text(
                        "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 14:30)\n\n"
                        "Или напишите 'отмена' для отмены создания слота."
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 14:30)\n\n"
                    "Или напишите 'отмена' для отмены создания слота."
                )
                return
        
        # Обычное сообщение
        await update.message.reply_text(
            "Не понимаю эту команду. Используйте кнопки ниже для навигации."
        )
    
    
    async def make_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сделать пользователя администратором"""
        # Эта команда работает в любом чате (личном или группе)
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /make_admin USER_ID\n\n"
                "Пример: /make_admin 123456789"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            if self.database.set_user_role(target_user_id, 'admin'):
                await update.message.reply_text(f"✅ Пользователь {target_user_id} назначен администратором.")
            else:
                await update.message.reply_text("❌ Ошибка при назначении администратора.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя.")
    
    async def remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Убрать права администратора"""
        # Эта команда работает в любом чате (личном или группе)
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /remove_admin USER_ID\n\n"
                "Пример: /remove_admin 123456789"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            if target_user_id == user_id:
                await update.message.reply_text("❌ Нельзя убрать права у самого себя.")
                return
            
            if self.database.set_user_role(target_user_id, 'user'):
                await update.message.reply_text(f"✅ У пользователя {target_user_id} убраны права администратора.")
            else:
                await update.message.reply_text("❌ Ошибка при изменении прав.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя.")
    
    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список администраторов"""
        # Эта команда работает в любом чате (личном или группе)
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        try:
            with sqlite3.connect("schedule_bot.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, username FROM users WHERE role = 'admin'
                """)
                admins = cursor.fetchall()
                
                if admins:
                    message = "👥 **Список администраторов:**\n\n"
                    for admin_id, username in admins:
                        message += f"• ID: {admin_id}\n"
                        if username and username != 'admin':
                            message += f"  Username: @{username}\n"
                        message += "\n"
                else:
                    message = "❌ Администраторы не найдены."
                
                await update.message.reply_text(message, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Ошибка при получении списка администраторов: {e}")
            await update.message.reply_text("❌ Ошибка при получении списка администраторов.")

    async def periodic_group_check(self):
        """Периодическая проверка группы на исключенных пользователей"""
        while True:
            try:
                await asyncio.sleep(300)  # Проверяем каждые 5 минут
                
                # Получаем всех пользователей из базы
                users = self.database.get_all_users()
                
                for user_id, username in users:
                    # Проверяем, состоит ли пользователь в группе
                    if not await self.is_user_in_group(user_id, ALLOWED_GROUP_ID):
                        logger.info(f"Пользователь {user_id} (@{username}) исключен из группы")
                        
                        # Освобождаем слоты
                        freed_slots = self.database.free_user_bookings(user_id)
                        logger.info(f"Освобождено {freed_slots} слотов пользователя {user_id}")
                        
                        # Удаляем пользователя
                        self.database.remove_user(user_id)
                        logger.info(f"Пользователь {user_id} удален из базы")
                        
            except Exception as e:
                logger.error(f"Ошибка при периодической проверке группы: {e}")

    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        
        # Запускаем периодическую проверку в отдельном потоке
        if ALLOWED_GROUP_ID:
            import threading
            def run_periodic_check():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.periodic_group_check())
            
            periodic_thread = threading.Thread(target=run_periodic_check, daemon=True)
            periodic_thread.start()
            logger.info("Запущена периодическая проверка группы")
        
        self.application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = ScheduleBot()
    bot.run()
