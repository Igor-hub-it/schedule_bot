import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "schedule_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    is_allowed BOOLEAN DEFAULT 1,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Добавляем поле role, если оно не существует (для существующих баз данных)
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
            except sqlite3.OperationalError:
                # Поле уже существует
                pass
            
            # Таблица слотов времени
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS time_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime TIMESTAMP NOT NULL,
                    description TEXT NOT NULL,
                    is_booked BOOLEAN DEFAULT 0,
                    booked_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (booked_by) REFERENCES users (user_id)
                )
            """)
            
            # Таблица записей (для истории)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    FOREIGN KEY (slot_id) REFERENCES time_slots (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            conn.commit()
            logger.info("База данных инициализирована")
    
    def add_user(self, user_id: int, username: str) -> bool:
        """Добавить пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли пользователь
                cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Обновляем только username, сохраняя существующую роль
                    cursor.execute("""
                        UPDATE users 
                        SET username = ?
                        WHERE user_id = ?
                    """, (username, user_id))
                else:
                    # Создаем нового пользователя с ролью 'user' по умолчанию
                    cursor.execute("""
                        INSERT INTO users (user_id, username, role)
                        VALUES (?, ?, 'user')
                    """, (user_id, username))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            return False
    
    def free_user_bookings(self, user_id: int) -> int:
        """Освободить все забронированные слоты пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Сначала подсчитываем количество слотов для освобождения
                cursor.execute("""
                    SELECT COUNT(*) FROM time_slots 
                    WHERE booked_by = ? AND is_booked = 1
                """, (user_id,))
                count = cursor.fetchone()[0]
                
                # Освобождаем все забронированные слоты пользователя
                cursor.execute("""
                    UPDATE time_slots 
                    SET is_booked = 0, booked_by = NULL 
                    WHERE booked_by = ?
                """, (user_id,))
                
                conn.commit()
                logger.info(f"Освобождено {count} слотов пользователя {user_id}")
                return count
        except Exception as e:
            logger.error(f"Ошибка при освобождении слотов пользователя: {e}")
            return 0

    def remove_user(self, user_id: int) -> bool:
        """Удалить пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Отменяем все активные записи пользователя
                cursor.execute("""
                    UPDATE time_slots 
                    SET is_booked = 0, booked_by = NULL 
                    WHERE booked_by = ?
                """, (user_id,))
                
                # Удаляем пользователя
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя: {e}")
            return False
    
    def is_user_allowed(self, user_id: int) -> bool:
        """Проверить, разрешен ли пользователь"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT is_allowed FROM users WHERE user_id = ?
                """, (user_id,))
                result = cursor.fetchone()
                return result is not None and result[0] == 1
        except Exception as e:
            logger.error(f"Ошибка при проверке пользователя: {e}")
            return False
    
    def user_exists(self, user_id: int) -> bool:
        """Проверить, существует ли пользователь в базе"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке существования пользователя: {e}")
            return False

    def get_all_users(self) -> list:
        """Получить всех пользователей из базы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, username FROM users")
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка при получении списка пользователей: {e}")
            return []
    
    def add_slot(self, datetime_obj: datetime, description: str) -> int:
        """Добавить слот времени"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO time_slots (datetime, description)
                    VALUES (?, ?)
                """, (datetime_obj, description))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении слота: {e}")
            return -1
    
    def remove_slot(self, slot_id: int) -> bool:
        """Удалить слот времени"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Отменяем все записи на этот слот
                cursor.execute("""
                    UPDATE bookings 
                    SET cancelled_at = CURRENT_TIMESTAMP 
                    WHERE slot_id = ? AND cancelled_at IS NULL
                """, (slot_id,))
                
                # Удаляем слот
                cursor.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении слота: {e}")
            return False
    
    def get_slot(self, slot_id: int) -> Optional[Dict]:
        """Получить информацию о слоте"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, datetime, description, is_booked, booked_by
                    FROM time_slots WHERE id = ?
                """, (slot_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2],
                        'is_booked': bool(result[3]),
                        'booked_by': result[4]
                    }
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении слота: {e}")
            return None
    
    def get_available_slots(self) -> List[Dict]:
        """Получить доступные слоты (только те, на которые можно записаться за 24+ часов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, datetime, description, is_booked, booked_by
                    FROM time_slots 
                    WHERE datetime > datetime('now', '+24 hours') AND is_booked = 0
                    ORDER BY datetime
                """)
                results = cursor.fetchall()
                
                slots = []
                for result in results:
                    slots.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2],
                        'is_booked': bool(result[3]),
                        'booked_by': result[4]
                    })
                return slots
        except Exception as e:
            logger.error(f"Ошибка при получении доступных слотов: {e}")
            return []
    
    def book_slot(self, slot_id: int, user_id: int) -> bool:
        """Записаться на слот"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, что слот свободен
                cursor.execute("""
                    SELECT is_booked FROM time_slots WHERE id = ?
                """, (slot_id,))
                result = cursor.fetchone()
                
                if not result or result[0]:
                    return False
                
                # Записываем пользователя
                cursor.execute("""
                    UPDATE time_slots 
                    SET is_booked = 1, booked_by = ? 
                    WHERE id = ?
                """, (user_id, slot_id))
                
                # Добавляем запись в историю
                cursor.execute("""
                    INSERT INTO bookings (slot_id, user_id)
                    VALUES (?, ?)
                """, (slot_id, user_id))
                
                # Обновляем username пользователя в таблице users (если изменился)
                cursor.execute("""
                    UPDATE users 
                    SET username = (
                        SELECT username FROM users WHERE user_id = ?
                    )
                    WHERE user_id = ?
                """, (user_id, user_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при записи на слот: {e}")
            return False
    
    def cancel_booking(self, booking_id: int, user_id: int) -> bool:
        """Отменить запись"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о записи
                cursor.execute("""
                    SELECT b.slot_id, b.user_id 
                    FROM bookings b
                    WHERE b.id = ? AND b.user_id = ? AND b.cancelled_at IS NULL
                """, (booking_id, user_id))
                result = cursor.fetchone()
                
                if not result:
                    return False
                
                slot_id = result[0]
                
                # Освобождаем слот
                cursor.execute("""
                    UPDATE time_slots 
                    SET is_booked = 0, booked_by = NULL 
                    WHERE id = ?
                """, (slot_id,))
                
                # Отмечаем запись как отмененную
                cursor.execute("""
                    UPDATE bookings 
                    SET cancelled_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (booking_id,))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при отмене записи: {e}")
            return False
    
    def get_user_bookings(self, user_id: int) -> List[Dict]:
        """Получить записи пользователя (только будущие)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.id, ts.datetime, ts.description
                    FROM bookings b
                    JOIN time_slots ts ON b.slot_id = ts.id
                    WHERE b.user_id = ? AND b.cancelled_at IS NULL
                    AND ts.datetime > datetime('now')
                    ORDER BY ts.datetime
                """, (user_id,))
                results = cursor.fetchall()
                
                bookings = []
                for result in results:
                    bookings.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2]
                    })
                return bookings
        except Exception as e:
            logger.error(f"Ошибка при получении записей пользователя: {e}")
            return []
    
    
    def get_all_bookings(self) -> List[Dict]:
        """Получить все активные записи"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.id, ts.datetime, ts.description, u.username, u.user_id
                    FROM bookings b
                    JOIN time_slots ts ON b.slot_id = ts.id
                    JOIN users u ON b.user_id = u.user_id
                    WHERE b.cancelled_at IS NULL
                    ORDER BY ts.datetime
                """)
                results = cursor.fetchall()
                
                bookings = []
                for result in results:
                    bookings.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2],
                        'username': result[3],
                        'user_id': result[4]
                    })
                return bookings
        except Exception as e:
            logger.error(f"Ошибка при получении всех записей: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Общее количество пользователей
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]
                
                # Общее количество слотов
                cursor.execute("SELECT COUNT(*) FROM time_slots WHERE datetime > datetime('now')")
                total_slots = cursor.fetchone()[0]
                
                # Количество записей
                cursor.execute("""
                    SELECT COUNT(*) FROM bookings 
                    WHERE cancelled_at IS NULL
                """)
                total_bookings = cursor.fetchone()[0]
                
                # Свободные слоты
                cursor.execute("""
                    SELECT COUNT(*) FROM time_slots 
                    WHERE datetime > datetime('now') AND is_booked = 0
                """)
                available_slots = cursor.fetchone()[0]
                
                # Процент заполненности
                occupancy_rate = (total_bookings / total_slots * 100) if total_slots > 0 else 0
                
                return {
                    'total_users': total_users,
                    'total_slots': total_slots,
                    'total_bookings': total_bookings,
                    'available_slots': available_slots,
                    'occupancy_rate': occupancy_rate
                }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {
                'total_users': 0,
                'total_slots': 0,
                'total_bookings': 0,
                'available_slots': 0,
                'occupancy_rate': 0
            }
    
    def get_slots_by_month(self, year, month):
        """Получить все слоты за определенный месяц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем все слоты за месяц
                cursor.execute("""
                    SELECT ts.id, ts.datetime, ts.description, 
                           COUNT(b.id) as booking_count
                    FROM time_slots ts
                    LEFT JOIN bookings b ON ts.id = b.slot_id AND b.cancelled_at IS NULL
                    WHERE strftime('%Y', ts.datetime) = ? 
                    AND strftime('%m', ts.datetime) = ?
                    GROUP BY ts.id, ts.datetime, ts.description
                    ORDER BY ts.datetime
                """, (str(year), f"{month:02d}"))
                
                # Преобразуем строки datetime в объекты datetime
                slots = []
                for row in cursor.fetchall():
                    slot_id, datetime_str, description, booking_count = row
                    slot_datetime = datetime.fromisoformat(datetime_str)
                    slots.append((slot_id, slot_datetime, description, booking_count))
                
                return slots
        except Exception as e:
            logger.error(f"Ошибка при получении слотов за месяц: {e}")
            return []
    
    def delete_slot(self, slot_id):
        """Удалить слот по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, есть ли активные записи на этот слот
                cursor.execute("""
                    SELECT COUNT(*) FROM bookings 
                    WHERE slot_id = ? AND cancelled_at IS NULL
                """, (slot_id,))
                
                active_bookings = cursor.fetchone()[0]
                
                if active_bookings > 0:
                    return False, f"Нельзя удалить слот с {active_bookings} активными записями"
                
                # Удаляем слот
                cursor.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Слот {slot_id} успешно удален")
                    return True, "Слот успешно удален"
                else:
                    return False, "Слот не найден"
                    
        except Exception as e:
            logger.error(f"Ошибка при удалении слота {slot_id}: {e}")
            return False, f"Ошибка при удалении слота: {e}"

    def force_delete_slot(self, slot_id):
        """Принудительно удалить слот с уведомлением пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о слоте
                cursor.execute("""
                    SELECT datetime, description FROM time_slots WHERE id = ?
                """, (slot_id,))
                
                slot_info = cursor.fetchone()
                if not slot_info:
                    return False, "Слот не найден", []
                
                slot_datetime, slot_description = slot_info
                
                # Получаем всех пользователей, забронировавших этот слот
                cursor.execute("""
                    SELECT b.user_id, u.username
                    FROM bookings b
                    JOIN users u ON b.user_id = u.user_id
                    WHERE b.slot_id = ? AND b.cancelled_at IS NULL
                """, (slot_id,))
                
                affected_users = cursor.fetchall()
                
                # Отменяем все активные записи на этот слот
                cursor.execute("""
                    UPDATE bookings 
                    SET cancelled_at = CURRENT_TIMESTAMP
                    WHERE slot_id = ? AND cancelled_at IS NULL
                """, (slot_id,))
                
                # Удаляем слот
                cursor.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
                conn.commit()
                
                logger.info(f"Слот {slot_id} принудительно удален, затронуто пользователей: {len(affected_users)}")
                return True, "Слот принудительно удален", affected_users
                
        except Exception as e:
            logger.error(f"Ошибка при принудительном удалении слота {slot_id}: {e}")
            return False, f"Ошибка при удалении слота: {e}", []
    
    def get_bookings_by_slot(self, slot_id):
        """Получить все записи на определенный слот"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о забронированном слоте из time_slots
                cursor.execute("""
                    SELECT ts.id, ts.datetime, ts.description, ts.is_booked, ts.booked_by,
                           u.username
                    FROM time_slots ts
                    LEFT JOIN users u ON ts.booked_by = u.user_id
                    WHERE ts.id = ? AND ts.is_booked = 1
                """, (slot_id,))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка при получении записей слота {slot_id}: {e}")
            return []
    
    def get_user_bookings_by_month(self, user_id: int, year: int, month: int) -> List[Dict]:
        """Получить записи пользователя за определенный месяц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.id, ts.datetime, ts.description
                    FROM bookings b
                    JOIN time_slots ts ON b.slot_id = ts.id
                    WHERE b.user_id = ? AND b.cancelled_at IS NULL
                    AND strftime('%Y', ts.datetime) = ? AND strftime('%m', ts.datetime) = ?
                    ORDER BY ts.datetime
                """, (user_id, str(year), f"{month:02d}"))
                results = cursor.fetchall()
                
                bookings = []
                for result in results:
                    bookings.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2]
                    })
                
                return bookings
        except Exception as e:
            logger.error(f"Ошибка при получении записей пользователя {user_id} за {month}.{year}: {e}")
            return []
    
    def get_user_bookings_by_day(self, user_id: int, year: int, month: int, day: int) -> List[Dict]:
        """Получить записи пользователя за определенный день"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.id, ts.datetime, ts.description
                    FROM bookings b
                    JOIN time_slots ts ON b.slot_id = ts.id
                    WHERE b.user_id = ? AND b.cancelled_at IS NULL
                    AND strftime('%Y', ts.datetime) = ? 
                    AND strftime('%m', ts.datetime) = ?
                    AND strftime('%d', ts.datetime) = ?
                    ORDER BY ts.datetime
                """, (user_id, str(year), f"{month:02d}", f"{day:02d}"))
                results = cursor.fetchall()
                
                bookings = []
                for result in results:
                    bookings.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2]
                    })
                
                return bookings
        except Exception as e:
            logger.error(f"Ошибка при получении записей пользователя {user_id} за {day}.{month}.{year}: {e}")
            return []
    
    def get_available_slots_by_month(self, year: int, month: int) -> List[Dict]:
        """Получить доступные слоты за определенный месяц (только те, на которые можно записаться за 24+ часов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, datetime, description
                    FROM time_slots
                    WHERE strftime('%Y', datetime) = ? AND strftime('%m', datetime) = ?
                    AND is_booked = 0
                    AND datetime > datetime('now', '+24 hours')
                    ORDER BY datetime
                """, (str(year), f"{month:02d}"))
                results = cursor.fetchall()
                
                slots = []
                for result in results:
                    slots.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2]
                    })
                
                return slots
        except Exception as e:
            logger.error(f"Ошибка при получении доступных слотов за {month}.{year}: {e}")
            return []
    
    def get_available_slots_by_day(self, year: int, month: int, day: int) -> List[Dict]:
        """Получить доступные слоты за определенный день (только те, на которые можно записаться за 24+ часов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, datetime, description
                    FROM time_slots
                    WHERE strftime('%Y', datetime) = ? 
                    AND strftime('%m', datetime) = ?
                    AND strftime('%d', datetime) = ?
                    AND is_booked = 0
                    AND datetime > datetime('now', '+24 hours')
                    ORDER BY datetime
                """, (str(year), f"{month:02d}", f"{day:02d}"))
                results = cursor.fetchall()
                
                slots = []
                for result in results:
                    slots.append({
                        'id': result[0],
                        'datetime': datetime.fromisoformat(result[1]),
                        'description': result[2]
                    })
                
                return slots
        except Exception as e:
            logger.error(f"Ошибка при получении доступных слотов за {day}.{month}.{year}: {e}")
            return []
    
    def get_user_role(self, user_id: int) -> str:
        """Получить роль пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT role FROM users WHERE user_id = ?
                """, (user_id,))
                result = cursor.fetchone()
                
                if result:
                    return result[0] or 'user'
                else:
                    return 'user'  # По умолчанию обычный пользователь
        except Exception as e:
            logger.error(f"Ошибка при получении роли пользователя {user_id}: {e}")
            return 'user'
    
    def set_user_role(self, user_id: int, role: str) -> bool:
        """Установить роль пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли пользователь
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if not cursor.fetchone():
                    # Если пользователя нет, добавляем его
                    cursor.execute("""
                        INSERT INTO users (user_id, username, is_allowed, role)
                        VALUES (?, 'user', 1, ?)
                    """, (user_id, role))
                else:
                    # Обновляем роль существующего пользователя
                    cursor.execute("""
                        UPDATE users SET role = ? WHERE user_id = ?
                    """, (role, user_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при установке роли пользователя {user_id}: {e}")
            return False

