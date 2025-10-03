#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота
"""

import sys
from main import ScheduleBot

def main():
    """Запуск бота"""
    print("Запуск Telegram бота для записи на занятия...")
    print("Нажмите Ctrl+C для остановки")
    
    try:
        bot = ScheduleBot()
        bot.run()
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
