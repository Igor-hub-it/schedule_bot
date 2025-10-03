import logging
import asyncio
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
        self.application.add_handler(CommandHandler("my_id", self.get_my_id))
        self.application.add_handler(CommandHandler("group_id", self.get_group_id))
        
        # Команды только для админов
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CommandHandler("add_slot", self.add_slot))
        self.application.add_handler(CommandHandler("remove_slot", self.remove_slot))
        self.application.add_handler(CommandHandler("add_user", self.add_user))
        self.application.add_handler(CommandHandler("remove_user", self.remove_user))
        self.application.add_handler(CommandHandler("set_group", self.set_group))
        
        # Обработчики callback'ов
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def get_message_object(self, update: Update):
        """Получить объект сообщения для ответа"""
        return update.message or update.callback_query.message
    
    def get_user_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """Получить клавиатуру в зависимости от прав пользователя"""
        if user_id in ADMIN_IDS:
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
    
    async def is_user_in_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        """Проверить, состоит ли пользователь в группе"""
        try:
            # Получаем информацию о пользователе
            chat_member = await context.bot.get_chat_member(ALLOWED_GROUP_ID, user_id)
            
            # Проверяем статус пользователя в группе
            if chat_member.status in ['member', 'administrator', 'creator']:
                return True
            else:
                return False
                
        except Exception as e:
            # Если не удалось проверить (пользователь не в группе или ошибка)
            logger.warning(f"Не удалось проверить членство в группе для пользователя {user_id}: {e}")
            return False
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        # Проверяем, что команда пришла в личном чате, а не в группе
        if update.message.chat.type != 'private':
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Неизвестно"
        
        # Проверяем, есть ли пользователь в базе
        if not db.is_user_allowed(user_id):
            # Временно добавляем всех пользователей (можно изменить позже)
            db.add_user(user_id, username)
            await update.message.reply_text(
                f"✅ Добро пожаловать! Вы добавлены в систему.\n"
                f"Теперь вы можете записываться на занятия."
            )
        else:
            # Пользователь уже в базе
            pass
        
        # Получаем клавиатуру в зависимости от прав пользователя
        reply_keyboard = self.get_user_keyboard(user_id)
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {update.effective_user.first_name}!\n\n"
            "Это бот для записи на занятия.\n"
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
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
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
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        # Устанавливаем текущую дату если не указана
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        # Получаем все слоты за месяц
        slots = db.get_slots_by_month(year, month)
        
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
        
        if user_id not in ADMIN_IDS:
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        # Получаем слоты за день
        target_date = date(year, month, day)
        slots = db.get_slots_by_month(year, month)
        day_slots = [slot for slot in slots if slot[1].date() == target_date]
        
        # Создаем текст сообщения
        message_text = f"📅 **Слоты на {day:02d}.{month:02d}.{year}**\n\n"
        
        if day_slots:
            message_text += "**Доступные слоты:**\n"
            for slot in day_slots:
                slot_id = slot[0]
                # Получаем записи на этот слот
                bookings = db.get_bookings_by_slot(slot_id)
                active_bookings = [b for b in bookings if b[4] is None]  # cancelled_at is None
                
                message_text += f"• {slot[1].strftime('%H:%M')} - {slot[2]}\n"
                
                if active_bookings:
                    # Показываем username первого активного пользователя
                    username = active_bookings[0][5] or active_bookings[0][6] or f"ID:{active_bookings[0][1]}"
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
        action_buttons = [
            InlineKeyboardButton("➕ Добавить слот", callback_data=f"add_slot_{year}_{month}_{day}"),
            InlineKeyboardButton("🗑️ Удалить слот", callback_data=f"remove_slot_{year}_{month}_{day}")
        ]
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
        
        if user_id not in ADMIN_IDS:
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        # Получаем слоты за день
        target_date = date(year, month, day)
        slots = db.get_slots_by_month(year, month)
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
        
        if user_id not in ADMIN_IDS:
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
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        selected_date = date(year, month, day)
        date_str = selected_date.strftime('%d.%m.%Y')
        
        # Создаем кнопки с популярными временами
        keyboard = []
        
        # Утренние часы
        morning_times = ["08:00", "09:00", "10:00", "11:00", "12:00"]
        morning_buttons = []
        for time in morning_times:
            morning_buttons.append(InlineKeyboardButton(time, callback_data=f"time_select_{year}_{month}_{day}_{time}"))
        keyboard.append(morning_buttons)
        
        # Дневные часы
        afternoon_times = ["13:00", "14:00", "15:00", "16:00", "17:00"]
        afternoon_buttons = []
        for time in afternoon_times:
            afternoon_buttons.append(InlineKeyboardButton(time, callback_data=f"time_select_{year}_{month}_{day}_{time}"))
        keyboard.append(afternoon_buttons)
        
        # Вечерние часы
        evening_times = ["18:00", "19:00", "20:00"]
        evening_buttons = []
        for time in evening_times:
            evening_buttons.append(InlineKeyboardButton(time, callback_data=f"time_select_{year}_{month}_{day}_{time}"))
        keyboard.append(evening_buttons)
        
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
        
        if user_id not in ADMIN_IDS:
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
            [InlineKeyboardButton("🔙 Назад к выбору времени", callback_data=f"cal_select_{year}_{month}_{day}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            f"🕐 **Введите время для {date_str}**\n\n"
            "Отправьте время в формате ЧЧ:ММ\n"
            "Например: 14:30\n\n"
            "Или используйте кнопку 'Назад' для выбора из списка.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def create_slot_from_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, year, month, day, time, description):
        """Создать слот из календаря"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет прав администратора.")
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
                await update.callback_query.edit_message_text(
                    "❌ Нельзя создать слот в прошлом времени.",
                    parse_mode='Markdown'
                )
                return
            
            # Проверяем, нет ли уже слота на это время
            existing_slots = db.get_slots_by_month(year, month)
            for slot in existing_slots:
                if slot[1] == slot_datetime:
                    date_str = date(year, month, day).strftime('%d.%m.%Y')
                    await update.callback_query.edit_message_text(
                        f"❌ **Слот уже существует!**\n\n"
                        f"📅 Дата: {date_str}\n"
                        f"🕐 Время: {time}\n\n"
                        f"На это время уже есть слот. Выберите другое время.",
                        parse_mode='Markdown'
                    )
                    return
            
            # Добавляем слот в базу данных
            slot_id = db.add_slot(slot_datetime, description)
            
            if slot_id:
                date_str = date(year, month, day).strftime('%d.%m.%Y')
                await update.callback_query.edit_message_text(
                    f"✅ **Слот успешно создан!**\n\n"
                    f"📅 Дата: {date_str}\n"
                    f"🕐 Время: {time}\n\n"
                    "Слот добавлен в календарь и доступен для записи.",
                    parse_mode='Markdown'
                )
            else:
                await update.callback_query.edit_message_text(
                    "❌ Ошибка при создании слота. Попробуйте еще раз.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка при создании слота: {e}")
            await update.callback_query.edit_message_text(
                "❌ Ошибка при создании слота. Проверьте правильность данных.",
                parse_mode='Markdown'
            )
    
    async def show_slot_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot_id: int):
        """Показать детали слота с возможностью удаления"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        try:
            # Получаем информацию о слоте
            slots = db.get_all_slots()
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
            bookings = db.get_bookings_by_slot(slot_id)
            active_bookings = [b for b in bookings if b[4] is None]  # cancelled_at is None
            
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
        
        if user_id not in ADMIN_IDS:
            await update.callback_query.answer("❌ У вас нет прав администратора.")
            return
        
        try:
            # Удаляем слот
            success, message = db.delete_slot(slot_id)
            
            if success:
                await update.callback_query.answer("✅ Слот успешно удален!")
                # Возвращаемся к календарю
                await self.show_admin_calendar(update, context)
            else:
                await update.callback_query.answer(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"Ошибка при удалении слота: {e}")
            await update.callback_query.answer("❌ Произошла ошибка при удалении слота.")
    
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
    
    async def set_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настроить группу для автоматического доступа"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
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
        
        elif data == "cal_empty":
            # Игнорируем пустые кнопки
            pass
        
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
        # Проверяем, что сообщение пришло в личном чате, а не в группе
        if update.message.chat.type != 'private':
            return
            
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Проверяем, ожидается ли ввод описания слота
        
        # Проверяем, ожидается ли ввод времени
        if 'pending_time' in context.user_data:
            time_text = update.message.text
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
                        "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 14:30)"
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 14:30)"
                )
                return
        
        # Обработка кнопок клавиатуры
        if message_text == "📅 Расписание":
            await self.show_schedule(update, context)
        elif message_text == "📋 Мои записи":
            await self.show_my_bookings(update, context)
        elif message_text == "📅 Календарь слотов" and user_id in ADMIN_IDS:
            await self.show_admin_calendar(update, context)
        else:
            # Обычное сообщение
            await update.message.reply_text(
                "Не понимаю эту команду. Используйте кнопки ниже для навигации."
            )
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = ScheduleBot()
    bot.run()
