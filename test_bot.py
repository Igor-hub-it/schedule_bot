#!/usr/bin/env python3
"""
Тестовый скрипт для проверки бота
"""

import sys
import signal
import time
from main import ScheduleBot

def signal_handler(sig, frame):
    print('\nТест завершен успешно!')
    sys.exit(0)

def main():
    """Тест бота"""
    print("Тестирование создания бота...")
    
    try:
        bot = ScheduleBot()
        print("Бот создан успешно")
        
        # Устанавливаем обработчик сигнала для завершения
        signal.signal(signal.SIGINT, signal_handler)
        
        print("Бот готов к запуску")
        print("Нажмите Ctrl+C для завершения теста")
        
        # Ждем 3 секунды
        time.sleep(3)
        
        print("Тест завершен успешно - ошибки не обнаружены")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
