import os
from typing import List

# Токен бота (получите у @BotFather)
BOT_TOKEN = "7528733857:AAEKkv_QhLaxXv1IFT3yvzDr8RNVuJnieuo"

# ID администраторов (получите у @userinfobot)
ADMIN_IDS = [
    949435625,  # Captain_Cobain
]

# ID группы, из которой разрешено добавлять пользователей (опционально)
ALLOWED_GROUP_ID = -3114498461

# Настройки базы данных
DATABASE_PATH = "schedule_bot.db"

# Настройки уведомлений
ENABLE_NOTIFICATIONS = True
NOTIFICATION_TIME_BEFORE = 60  # Минуты до начала занятия

# Настройки расписания
DEFAULT_SLOT_DURATION = 60  # Длительность слота в минутах
MAX_SLOTS_PER_DAY = 10  # Максимальное количество слотов в день

# Текстовые сообщения
MESSAGES = {
    "welcome": "👋 Добро пожаловать в бот для записи на занятия!",
    "access_denied": "❌ У вас нет доступа к этому боту.",
    "slot_booked": "✅ Вы успешно записались на занятие!",
    "slot_cancelled": "❌ Запись отменена.",
    "slot_not_found": "❌ Слот не найден.",
    "slot_already_booked": "❌ Этот слот уже занят.",
    "booking_error": "❌ Ошибка при записи. Попробуйте еще раз.",
    "admin_only": "❌ У вас нет прав администратора.",
    "invalid_format": "❌ Неверный формат команды.",
    "help_text": """
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
    """,
    "admin_help": """
🔧 **Панель администратора**

**Управление слотами:**
• `/add_slot ДД.ММ.ГГГГ ЧЧ:ММ Описание` - Добавить слот
• `/remove_slot ID` - Удалить слот

**Управление пользователями:**
• `/add_user USER_ID username` - Добавить пользователя
• `/remove_user USER_ID` - Удалить пользователя

**Примеры:**
• `/add_slot 25.12.2024 14:30 Занятие по вождению`
• `/add_user 123456789 Иван`
• `/remove_slot 5`
    """
}

# Настройки логирования
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "default",
            "filename": "bot.log",
            "mode": "a",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
}

