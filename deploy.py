#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для подготовки проекта к деплою
"""

import os
import sys
import subprocess

def check_requirements():
    """Проверить наличие необходимых файлов"""
    required_files = [
        'main.py',
        'database.py', 
        'config.py',
        'start.py',
        'requirements.txt'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    print("✅ Все необходимые файлы найдены")
    return True

def create_git_repo():
    """Создать Git репозиторий"""
    try:
        # Инициализация Git
        subprocess.run(['git', 'init'], check=True)
        print("✅ Git репозиторий инициализирован")
        
        # Добавление файлов
        subprocess.run(['git', 'add', '.'], check=True)
        print("✅ Файлы добавлены в Git")
        
        # Первый коммит
        subprocess.run(['git', 'commit', '-m', 'Initial commit for deployment'], check=True)
        print("✅ Первый коммит создан")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка Git: {e}")
        return False

def show_deployment_instructions():
    """Показать инструкции по деплою"""
    print("\n" + "="*60)
    print("🚀 ИНСТРУКЦИИ ПО ДЕПЛОЮ")
    print("="*60)
    
    print("\n1️⃣ RAILWAY (Рекомендуется):")
    print("   • Зайдите на railway.app")
    print("   • Создайте новый проект")
    print("   • Подключите GitHub репозиторий")
    print("   • Добавьте переменные окружения:")
    print("     - BOT_TOKEN")
    print("     - ADMIN_IDS") 
    print("     - ALLOWED_GROUP_ID")
    
    print("\n2️⃣ HEROKU:")
    print("   • Установите Heroku CLI")
    print("   • Выполните: heroku create ваш-бот-название")
    print("   • Выполните: git push heroku main")
    
    print("\n3️⃣ VPS:")
    print("   • Загрузите файлы на сервер")
    print("   • Установите Python и зависимости")
    print("   • Настройте systemd сервис")
    
    print("\n📋 Переменные окружения:")
    print("   BOT_TOKEN=ваш_токен_бота")
    print("   ADMIN_IDS=ваш_telegram_id")
    print("   ALLOWED_GROUP_ID=id_группы")
    
    print("\n📖 Подробная инструкция в файле: ДЕПЛОЙ_ИНСТРУКЦИЯ.md")

def main():
    """Основная функция"""
    print("🤖 Подготовка Telegram бота к деплою")
    print("="*50)
    
    # Проверка файлов
    if not check_requirements():
        sys.exit(1)
    
    # Создание Git репозитория
    if not os.path.exists('.git'):
        create_git_repo()
    else:
        print("✅ Git репозиторий уже существует")
    
    # Показать инструкции
    show_deployment_instructions()
    
    print("\n✅ Проект готов к деплою!")
    print("📁 Создайте репозиторий на GitHub и загрузите код")

if __name__ == "__main__":
    main()
