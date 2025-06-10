import os
import logging
import sqlite3
import asyncio
import requests
import hashlib
import threading
import time
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('telegram_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# إعدادات البوت
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_PATH = 'bills_system.db'
WEB_APP_URL = 'http://localhost:5000'

# قفل لحماية قاعدة البيانات من التداخل
db_lock = threading.Lock()

# حالات المحادثة
(WAITING_FOR_PHONE, WAITING_FOR_PASSWORD, WAITING_FOR_CUSTOMER_PHONE, 
 WAITING_FOR_CUSTOMER_NAME, WAITING_FOR_PAYMENT_AMOUNT, WAITING_FOR_COMPANY_SELECTION,
 WAITING_FOR_CATEGORY_SELECTION, WAITING_FOR_MOBILE_NUMBER, WAITING_FOR_CUSTOMER_SELECTION,
 WAITING_FOR_PAYMENT_CONFIRMATION) = range(10)

# تخزين بيانات المستخدمين
user_data = {}

# نظام حفظ الحالة لمنع فقدان البيانات
user_sessions = {}

# متغير للتحكم في إعادة التشغيل
restart_bot = False

def save_user_session(user_id, data):
    """حفظ جلسة المستخدم"""
    try:
        user_sessions[user_id] = {
            'data': data.copy(),
            'last_activity': datetime.now().isoformat(),
            'is_active': True
        }
        # حفظ في قاعدة البيانات أيضاً للأمان
        import json
        session_data = json.dumps(data, ensure_ascii=False, default=str)
        safe_db_execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id TEXT PRIMARY KEY,
                session_data TEXT,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        safe_db_execute('''
            INSERT OR REPLACE INTO user_sessions (user_id, session_data, last_activity)
            VALUES (?, ?, ?)
        ''', (str(user_id), session_data, datetime.now().isoformat()))
    except Exception as e:
        logger.error(f"خطأ في حفظ جلسة المستخدم: {e}")

def restore_user_session(user_id):
    """استعادة جلسة المستخدم"""
    try:
        # البحث في الذاكرة أولاً
        if user_id in user_sessions:
            session_info = user_sessions[user_id]
            if session_info.get('is_active'):
                return session_info['data']

        # البحث في قاعدة البيانات
        result = safe_db_execute('''
            SELECT session_data FROM user_sessions WHERE user_id = ?
        ''', (str(user_id),), fetch_one=True)

        if result:
            import json
            restored_data = json.loads(result[0])
            user_sessions[user_id] = {
                'data': restored_data,
                'last_activity': datetime.now().isoformat(),
                'is_active': True
            }
            return restored_data

    except Exception as e:
        logger.error(f"خطأ في استعادة جلسة المستخدم: {e}")

    return None

def clear_user_session(user_id):
    """مسح جلسة المستخدم"""
    try:
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        safe_db_execute('''
            DELETE FROM user_sessions WHERE user_id = ?
        ''', (str(user_id),))
    except Exception as e:
        logger.error(f"خطأ في مسح جلسة المستخدم: {e}")

def check_maintenance_mode():
    """فحص حالة الصيانة من ملف الإعدادات"""
    try:
        import json
        with open('site_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
            is_maintenance = settings.get('is_maintenance', False)
            maintenance_reason = settings.get('maintenance_reason', '')
            
            # التأكد من أن القيمة boolean وليس string
            if isinstance(is_maintenance, str):
                is_maintenance = is_maintenance.lower() == 'true'
                
            return is_maintenance, maintenance_reason
    except (FileNotFoundError, json.JSONDecodeError):
        return False, ''

def safe_db_execute(query, params=None, fetch_one=False, fetch_all=False):
    """تنفيذ آمن لاستعلامات قاعدة البيانات مع إعادة المحاولة"""
    max_retries = 3
    retry_delay = 0.1

    for attempt in range(max_retries):
        try:
            with db_lock:
                conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                cursor = conn.cursor()

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount

                conn.commit()
                conn.close()
                return result

        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                logger.warning(f"قاعدة البيانات مؤقتة، إعادة المحاولة {attempt + 1}")
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(f"خطأ في قاعدة البيانات: {e}")
                return None
        except Exception as e:
            logger.error(f"خطأ في قاعدة البيانات: {e}")
            return None

    return None

def verify_user_credentials(phone, password):
    """التحقق من صحة بيانات المستخدم"""
    try:
        hashed_password = hashlib.md5(password.encode()).hexdigest()
        user = safe_db_execute('''
            SELECT id, name, phone, balance, role, is_active 
            FROM users 
            WHERE phone = ? AND password = ? AND is_active = 1
        ''', (phone, hashed_password), fetch_one=True)
        return user
    except Exception as e:
        logger.error(f"خطأ في التحقق من المستخدم: {e}")
        return None

def is_session_valid(user_id, chat_id):
    """التحقق من صلاحية جلسة المستخدم في التليجرام"""
    try:
        # فحص حالة المستخدم أولاً
        user_result = safe_db_execute('''
            SELECT u.is_active, u.password_changed_at
            FROM users u
            WHERE u.id = ?
        ''', (user_id,), fetch_one=True)
        
        if not user_result:
            return False  # المستخدم غير موجود
            
        is_active, password_changed_at = user_result
        
        # إذا كان المستخدم معطل، الجلسة غير صالحة
        if not is_active:
            return False
        
        # فحص جلسة التليجرام
        telegram_result = safe_db_execute('''
            SELECT tu.session_valid_after, tu.created_at
            FROM telegram_users tu
            JOIN users u ON tu.phone = u.phone
            WHERE u.id = ? AND tu.chat_id = ?
        ''', (user_id, str(chat_id)), fetch_one=True)
        
        if not telegram_result:
            return True  # إذا لم نجد بيانات التليجرام، نعتبر الجلسة صالحة للمستخدمين الجدد
            
        session_valid_after, telegram_created_at = telegram_result
        
        # إذا لم يتم تسجيل أي تغيير في كلمة المرور، فالجلسة صالحة
        if not password_changed_at:
            return True
            
        # إذا لم يكن هناك وقت إبطال محدد، فالجلسة صالحة
        if not session_valid_after:
            return True
            
        # التحقق من صلاحية الجلسة بناءً على آخر تغيير
        from datetime import datetime
        try:
            session_time = datetime.fromisoformat(session_valid_after)
            password_change_time = datetime.fromisoformat(password_changed_at)
            
            # الجلسة صالحة إذا كان وقت صلاحيتها بعد آخر تغيير لكلمة المرور
            return session_time > password_change_time
            
        except ValueError:
            # في حالة خطأ في تحليل التاريخ، اعتبر الجلسة صالحة
            return True
            
    except Exception as e:
        logger.error(f"خطأ في التحقق من صلاحية الجلسة: {e}")
        return True  # في حالة الخطأ، اعتبر الجلسة صالحة لتجنب قطع الخدمة

def get_companies_by_category():
    """جلب الشركات مجمعة حسب الفئات"""
    try:
        categories = safe_db_execute('''
            SELECT cc.id, cc.name, cc.icon
            FROM company_categories cc
            WHERE cc.is_active = 1
            ORDER BY cc.name
        ''', fetch_all=True)
        return categories or []
    except Exception as e:
        logger.error(f"خطأ في جلب الفئات: {e}")
        return []

def get_companies_by_category_id(category_id):
    """جلب الشركات حسب معرف الفئة"""
    try:
        companies = safe_db_execute('''
            SELECT id, name FROM companies 
            WHERE category_id = ? AND is_active = 1 
            ORDER BY name
        ''', (category_id,), fetch_all=True)
        return companies or []
    except Exception as e:
        logger.error(f"خطأ في جلب الشركات: {e}")
        return []

def search_customers_advanced(phone_number):
    """البحث المتقدم عن الزبائن"""
    try:
        customers = safe_db_execute('''
            SELECT c.id, c.phone_number, c.name, c.mobile_number, c.company_id, c.speed_id, c.notes,
                   c.created_at, COALESCE(comp.name, ic.name, 'غير محدد') as company_name, 
                   cc.name as category_name, u.name as added_by_name
            FROM customers c
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN company_categories cc ON comp.category_id = cc.id
            LEFT JOIN users u ON c.added_by = u.id
            WHERE c.phone_number = ?
            ORDER BY c.created_at DESC
        ''', (phone_number,), fetch_all=True)
        return customers or []
    except Exception as e:
        logger.error(f"خطأ في البحث عن الزبائن: {e}")
        return []

def get_user_transactions(user_id, limit=10, status_filter=None, search_term=None, date_filter=None):
    """جلب معاملات المستخدم مع تفاصيل كاملة وخيارات البحث والتصفية المحسنة"""
    try:
        base_query = '''
            SELECT t.id, t.transaction_type, t.amount, t.status, t.notes,
                   strftime('%d/%m/%Y %H:%M', t.created_at) as formatted_date, 
                   c.name as customer_name, c.phone_number,
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name, 
                   COALESCE(cc.name, 'غير محدد') as category_name,
                   t.months,
                   strftime('%d/%m/%Y %H:%M', t.approved_at) as approved_date,
                   t.staff_notes
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN company_categories cc ON comp.category_id = cc.id
            WHERE t.user_id = ?
        '''

        params = [user_id]

        if status_filter:
            base_query += ' AND t.status = ?'
            params.append(status_filter)

        if search_term:
            base_query += ''' AND (
                c.name LIKE ? OR 
                c.phone_number LIKE ? OR 
                comp.name LIKE ? OR 
                ic.name LIKE ? OR 
                cc.name LIKE ? OR
                t.notes LIKE ?
            )'''
            search_pattern = f'%{search_term}%'
            params.extend([search_pattern] * 6)

        if date_filter == 'last_week':
            base_query += " AND t.created_at >= datetime('now', '-7 days')"
        elif date_filter == 'last_month':
            base_query += " AND t.created_at >= datetime('now', '-30 days')"
        elif date_filter == 'last_3_months':
            base_query += " AND t.created_at >= datetime('now', '-90 days')"

        base_query += '''
            ORDER BY 
                CASE t.status 
                    WHEN 'pending' THEN 1 
                    WHEN 'approved' THEN 2 
                    WHEN 'rejected' THEN 3 
                    ELSE 4 
                END,
                t.created_at DESC
            LIMIT ?
        '''
        params.append(limit)

        transactions = safe_db_execute(base_query, tuple(params), fetch_all=True)
        return transactions or []
    except Exception as e:
        logger.error(f"خطأ في جلب المعاملات: {e}")
        return []

def register_telegram_user(phone, chat_id):
    """تسجيل معرف المحادثة للمستخدم"""
    try:
        safe_db_execute('''
            CREATE TABLE IF NOT EXISTS telegram_users (
                phone TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        result = safe_db_execute(
            'INSERT OR REPLACE INTO telegram_users (phone, chat_id) VALUES (?, ?)', 
            (phone, str(chat_id))
        )

        if result is not None:
            logger.info(f"تم تسجيل مستخدم التليجرام: {phone} -> {chat_id}")
            return True
        return False

    except Exception as e:
        logger.error(f"خطأ في تسجيل مستخدم التليجرام: {e}")
        return False

def create_customer_and_payment(user_id, customer_data, payment_data):
    """إنشاء زبون وطلب تسديد في نفس الوقت"""
    try:
        with db_lock:
            conn = sqlite3.connect(DATABASE_PATH, timeout=15.0)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            cursor = conn.cursor()

            cursor.execute('SELECT balance, name FROM users WHERE id = ?', (user_id,))
            user_result = cursor.fetchone()

            if not user_result:
                conn.close()
                return False, "مستخدم غير موجود"

            user_balance, user_name = user_result

            if user_balance < payment_data['amount']:
                conn.close()
                return False, "رصيدك غير كافي"

            cursor.execute('SELECT id FROM customers WHERE phone_number = ?', (customer_data['phone'],))
            customer = cursor.fetchone()

            if not customer:
                cursor.execute('''
                    INSERT INTO customers (phone_number, name, mobile_number, company_id, added_by, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (customer_data['phone'], customer_data['name'], customer_data.get('mobile', ''),
                      payment_data['company_id'], user_id, 'مضاف من التليجرام'))
                customer_id = cursor.lastrowid
            else:
                customer_id = customer[0]
                cursor.execute('''
                    UPDATE customers 
                    SET name = ?, mobile_number = ?, company_id = ?
                    WHERE id = ?
                ''', (customer_data['name'], customer_data.get('mobile', ''), 
                      payment_data['company_id'], customer_id))

            cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', 
                          (payment_data['amount'], user_id))

            cursor.execute('''
                INSERT INTO transactions (user_id, customer_id, transaction_type, amount, 
                                        months, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, customer_id, 'payment', payment_data['amount'], 
                  payment_data.get('months', 1), 'طلب من التليجرام', 'pending'))

            transaction_id = cursor.lastrowid

            cursor.execute('''
                INSERT INTO notifications (user_id, title, message, created_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
            ''', (user_id, 'تم إرسال طلب التسديد', 
                  f'تم إرسال طلب تسديد للعميل {customer_data["name"]} بمبلغ {payment_data["amount"]} ل.س'))

            cursor.execute('SELECT name FROM companies WHERE id = ?', (payment_data['company_id'],))
            company_result = cursor.fetchone()
            company_name = company_result[0] if company_result else 'غير محدد'

            conn.commit()
            conn.close()

            def send_admin_notification():
                try:
                    admin_chats = safe_db_execute('''
                        SELECT tu.chat_id FROM telegram_users tu
                        JOIN users u ON tu.phone = u.phone
                        WHERE u.role = 'admin' AND u.is_active = 1
                    ''', fetch_all=True)

                    if admin_chats:
                        admin_message = (
                            f"🔔 طلب تسديد جديد #{transaction_id}\n\n"
                            f"👤 المستخدم: {user_name}\n"
                            f"📱 رقم الزبون: {customer_data['phone']}\n"
                            f"👨‍💼 اسم الزبون: {customer_data['name']}\n"
                            f"💰 المبلغ: {payment_data['amount']} ل.س\n"
                            f"🏢 الشركة: {company_name}\n"
                            f"📝 ملاحظات: {payment_data.get('notes', 'لا توجد')}\n\n"
                            f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )

                        for admin_chat in admin_chats:
                            chat_id = admin_chat[0]
                            try:
                                payload = {
                                    'chat_id': chat_id,
                                    'text': admin_message,
                                    'parse_mode': 'HTML'
                                }
                                response = requests.post(
                                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', 
                                    json=payload, 
                                    timeout=10
                                )
                                response.raise_for_status()
                                logger.info(f"تم إرسال إشعار للمدير {chat_id}")
                            except requests.RequestException as e:
                                logger.error(f"فشل إرسال إشعار للمدير {chat_id}: {e}")

                except Exception as e:
                    logger.error(f"خطأ في إرسال إشعار للمدير: {e}")

            threading.Thread(target=send_admin_notification, daemon=True).start()

            return True, "تم إرسال طلب التسديد بنجاح"

    except Exception as e:
        logger.error(f"خطأ في إنشاء الزبون والطلب: {e}")
        return False, f"خطأ في النظام: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء المحادثة مع فحص حالة الصيانة واستعادة الجلسة"""
    try:
        user_id = update.effective_user.id
        
        # محاولة استعادة الجلسة أولاً
        restored_session = restore_user_session(user_id)
        if restored_session and restored_session.get('user_id'):
            # استعادة الجلسة بنجاح
            user_data[user_id] = restored_session
            logger.info(f"تم استعادة جلسة المستخدم {user_id}")
            
            # إذا كان المستخدم مسجل دخول، عرض القائمة الرئيسية
            if restored_session.get('user_id'):
                await update.message.reply_text(
                    f"🔄 مرحباً بعودتك {restored_session.get('name', 'المستخدم')}!\n"
                    "تم استعادة جلستك بنجاح."
                )
                return await show_main_menu(update, context)
        
        # إنشاء جلسة جديدة إذا لم تكن موجودة
        user_data[user_id] = {'state': None}

        # فحص حالة الصيانة وصلاحيات المستخدم
        is_maintenance, maintenance_reason = check_maintenance_mode()
        
        # التحقق من كون المستخدم مدير
        is_admin = False
        try:
            # البحث عن المستخدم في قاعدة البيانات لمعرفة صلاحياته
            user_from_telegram = safe_db_execute('''
                SELECT u.role FROM telegram_users tu
                JOIN users u ON tu.phone = u.phone
                WHERE tu.chat_id = ? AND u.is_active = 1
            ''', (str(user_id),), fetch_one=True)
            
            if user_from_telegram and user_from_telegram[0] == 'admin':
                is_admin = True
        except Exception as e:
            logger.error(f"خطأ في التحقق من صلاحيات المستخدم: {e}")
        
        if is_maintenance and not is_admin:
            # إذا كان البوت تحت الصيانة والمستخدم ليس مدير، عرض رسالة الصيانة
            maintenance_message = (
                "🔧 البوت تحت الصيانة حالياً\n\n"
                "نعتذر عن الإزعاج، البوت غير متاح حالياً بسبب أعمال الصيانة.\n\n"
            )
            
            if maintenance_reason:
                maintenance_message += f"📝 سبب الصيانة: {maintenance_reason}\n\n"
            
            maintenance_message += "سيعود البوت للعمل قريباً. شكراً لصبركم. 🙏"
            
            await update.message.reply_text(maintenance_message)
            return

        keyboard = [
            [KeyboardButton("🔑 تسجيل الدخول")],
            [KeyboardButton("📖 أقرأ قبل الاستخدام"), KeyboardButton("🛠️ الدعم الفني")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        welcome_message = (
            "🌟 أهلاً وسهلاً بك في بوت نظام تسديد الفواتير\n\n"
            "📋 الخدمات المتاحة:\n"
            "• 🔍 الاستعلام عن الفواتير\n"
            "• 💰 تسديد الفواتير\n"
            "• 📊 متابعة معاملاتك\n"
            "• 👥 إدارة الزبائن\n"
            "• 💳 متابعة الرصيد\n\n"
            "🔐 للبدء، يرجى تسجيل الدخول"
        )

        # إضافة تنبيه للمديرين إذا كان النظام تحت الصيانة
        if is_maintenance and is_admin:
            welcome_message = (
                "🛡️ وضع المدير - النظام تحت الصيانة\n\n"
                f"⚠️ النظام حالياً تحت الصيانة للمستخدمين العاديين\n"
                f"📝 السبب: {maintenance_reason if maintenance_reason else 'صيانة عامة'}\n\n"
                "👨‍💼 بصفتك مدير، يمكنك الوصول للنظام بشكل طبيعي\n\n"
            ) + welcome_message

        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطأ في بدء المحادثة: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_login_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة طلب تسجيل الدخول"""
    try:
        user_id = update.effective_user.id
        user_data[user_id] = {'state': WAITING_FOR_PHONE}

        keyboard = [
            [KeyboardButton("❌ إلغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "📱 أدخل رقم جوالك المسجل في النظام:\n"
            "(مثال: 0991234567)",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة طلب تسجيل الدخول: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال رقم الهاتف"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        phone = update.message.text.strip()

        if not phone or not phone.isdigit() or len(phone) != 10:
            await update.message.reply_text(
                "❌ رقم الهاتف غير صحيح\n"
                "يجب أن يكون 10 أرقام"
            )
            return

        user_data[user_id]['phone'] = phone
        user_data[user_id]['state'] = WAITING_FOR_PASSWORD

        await update.message.reply_text(
            "🔐 أدخل كلمة المرور:",
            reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة رقم الهاتف: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال كلمة المرور"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        password = update.message.text.strip()
        phone = user_data[user_id].get('phone')

        if not phone:
            await update.message.reply_text("❌ خطأ في البيانات. يرجى البدء من جديد")
            return await start(update, context)

        user = verify_user_credentials(phone, password)

        if not user:
            await update.message.reply_text(
                "❌ بيانات الدخول غير صحيحة\n"
                "تأكد من رقم الجوال وكلمة المرور"
            )
            user_data[user_id]['state'] = WAITING_FOR_PHONE
            await update.message.reply_text("📱 أدخل رقم جوالك مرة أخرى:")
            return

        user_data[user_id].update({
            'user_id': user[0],
            'name': user[1],
            'phone': user[2],
            'balance': user[3],
            'role': user[4],
            'is_active': user[5],
            'state': None,
            'login_time': datetime.now().isoformat()
        })

        # حفظ الجلسة فور تسجيل الدخول
        save_user_session(user_id, user_data[user_id])

        register_success = register_telegram_user(phone, user_id)
        if register_success:
            logger.info(f"تم تسجيل مستخدم التليجرام بنجاح: {phone}")

        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"خطأ في معالجة كلمة المرور: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القائمة الرئيسية"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        if user_id in user_data:
            user_data[user_id]['state'] = None
            temp_keys = ['payment_phone', 'customer_name', 'customer_mobile', 'selected_company', 
                        'selected_category', 'customer_info', 'last_searched_phone', 
                        'customer_phone_for_add', 'available_customers', 'selected_customer_index',
                        'categories', 'companies', 'payment_amount', 'last_search_term']

            for key in temp_keys:
                user_data[user_id].pop(key, None)

        keyboard = [
            [KeyboardButton("💰 تسديد فاتورة")],
            [KeyboardButton("📋 معاملاتي"), KeyboardButton("💳 رصيدي")],
            [KeyboardButton("🚪 تسجيل خروج")]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        current_balance = safe_db_execute(
            'SELECT balance FROM users WHERE id = ?', 
            (user_info['user_id'],), 
            fetch_one=True
        )

        if current_balance:
            user_data[user_id]['balance'] = current_balance[0]
            balance = current_balance[0]
        else:
            balance = user_info.get('balance', 0)

        welcome_msg = (
            f"🌟 أهلاً {user_info.get('name', 'المستخدم')}\n\n"
            f"💰 رصيدك الحالي: {balance} ل.س\n\n"
            "اختر الخدمة المطلوبة:"
        )

        await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطأ في عرض القائمة الرئيسية: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_payment_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة طلب التسديد"""
    try:
        user_id = update.effective_user.id
        user_data[user_id]['state'] = WAITING_FOR_CUSTOMER_PHONE

        keyboard = [
            [KeyboardButton("❌ إلغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "📱 أدخل رقم هاتف الزبون للتسديد:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة طلب التسديد: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_customer_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال رقم هاتف الزبون مع عرض النتائج المتعددة"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        phone = update.message.text.strip()

        # التحقق من صحة رقم الهاتف
        if not ((phone.startswith('09') and len(phone) == 10) or (phone.startswith('011') and len(phone) == 10)) or not phone.isdigit():
            await update.message.reply_text(
                "❌ رقم الهاتف غير صحيح\n"
                "يجب أن يبدأ بـ 09 أو 011 (10 أرقام لكلاهما)"
            )
            return

        # البحث عن الزبائن
        customers = search_customers_advanced(phone)

        if not customers:
            # إذا لم يتم العثور على زبائن، عرض خيار إضافة بيانات جديدة
            keyboard = [
                [KeyboardButton("➕ إضافة بيانات جديدة")],
                [KeyboardButton("❌ إلغاء")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            # حفظ رقم الهاتف للاستخدام لاحقاً
            user_data[user_id]['customer_phone_for_add'] = phone
            user_data[user_id]['state'] = WAITING_FOR_CUSTOMER_SELECTION

            await update.message.reply_text(
                f"❌ لم يتم العثور على بيانات للرقم: {phone}\n\n"
                "هل تريد إضافة بيانات جديدة لهذا الرقم وتسديد له؟",
                reply_markup=reply_markup
            )
            return

        # حفظ النتائج في بيانات المستخدم
        user_data[user_id]['available_customers'] = customers
        user_data[user_id]['last_searched_phone'] = phone
        user_data[user_id]['state'] = WAITING_FOR_CUSTOMER_SELECTION

        # عرض النتائج مع أزرار الاختيار
        result_msg = f"📋 تم العثور على {len(customers)} نتيجة للرقم: {phone}\n\n"

        keyboard = []

        for i, customer in enumerate(customers):
            # تحديد ما يظهر للمستخدم حسب صلاحياته
            user_role = user_data[user_id].get('role', 'user')

            if user_role == 'admin':
                # المدير يرى جميع التفاصيل
                button_text = f"{i + 1}. {customer[2] or 'غير محدد'} - {customer[8] if customer[8] else 'غير محدد'}"
                if customer[7]:  # تاريخ الإضافة
                    button_text += f" ({customer[7][:10]})"
            else:
                # المستخدم العادي يرى معلومات محدودة
                button_text = f"{i + 1}. {customer[2] or 'غير محدد'} - {customer[8] if customer[8] else 'غير محدد'}"

            keyboard.append([KeyboardButton(button_text)])

        # إضافة خيار إضافة بيانات جديدة
        keyboard.append([KeyboardButton("➕ إضافة بيانات جديدة")])
        keyboard.append([KeyboardButton("❌ إلغاء")])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # عرض تفاصيل النتائج
        details_msg = ""
        for i, customer in enumerate(customers, 1):
            details_msg += f"🔹 النتيجة {i}:\n"
            details_msg += f"👤 الاسم: {customer[2] or 'غير محدد'}\n"
            details_msg += f"📞 الجوال: {customer[3] or 'غير محدد'}\n"
            details_msg += f"🏢 الشركة: {customer[8] if customer[8] else 'غير محدد'}\n"
            if customer[6]:  # ملاحظات
                details_msg += f"📝 ملاحظات: {customer[6]}\n"
            details_msg += "\n"

        full_message = result_msg + details_msg + "اختر النتيجة المطلوبة أو أضف بيانات جديدة:"

        await update.message.reply_text(full_message, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في معالجة رقم هاتف الزبون: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_customer_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار زبون محدد من النتائج"""
    try:
        user_id = update.effective_user.id
        text = update.message.text

        if text == "❌ إلغاء":
            return await cancel_operation(update, context)

        if text == "➕ إضافة بيانات جديدة":
            # التأكد من وجود رقم الهاتف
            phone = user_data[user_id].get('customer_phone_for_add') or user_data[user_id].get('last_searched_phone')
            if phone:
                user_data[user_id]['payment_phone'] = phone
                user_data[user_id]['customer_phone_for_add'] = phone

            user_data[user_id]['state'] = WAITING_FOR_CATEGORY_SELECTION
            await show_categories_menu(update, context)
            return

        # استخراج رقم الاختيار من النص
        if text and text[0].isdigit():
            try:
                customer_index = int(text.split('.')[0]) - 1
                available_customers = user_data[user_id].get('available_customers', [])

                if 0 <= customer_index < len(available_customers):
                    selected_customer = available_customers[customer_index]

                    # حفظ بيانات الزبون المختار
                    customer_info = {
                        'id': selected_customer[0],
                        'name': selected_customer[2] or '',
                        'mobile': selected_customer[3] or '',
                        'company_id': selected_customer[4] if selected_customer[4] else None,
                        'phone': selected_customer[1]
                    }

                    user_data[user_id]['customer_info'] = customer_info
                    user_data[user_id]['payment_phone'] = customer_info['phone']
                    user_data[user_id]['customer_name'] = customer_info['name']
                    user_data[user_id]['customer_mobile'] = customer_info['mobile']

                    # إذا كان هناك شركة محددة، استخدمها
                    if customer_info.get('company_id'):
                        user_data[user_id]['selected_company'] = customer_info['company_id']
                        user_data[user_id]['state'] = WAITING_FOR_PAYMENT_AMOUNT

                        current_balance = user_data[user_id].get('balance', 0)

                        keyboard = [
                            [KeyboardButton("❌ إلغاء")]
                        ]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                        await update.message.reply_text(
                            f"💰 التسديد للزبون:\n"
                            f"👤 الاسم: {customer_info.get('name', 'غير محدد')}\n"
                            f"📱 الرقم: {customer_info['phone']}\n\n"
                            f"أدخل المبلغ المطلوب تسديده:\n"
                            f"💳 رصيدك الحالي: {current_balance} ل.س",
                            reply_markup=reply_markup
                        )
                    else:
                        user_data[user_id]['state'] = WAITING_FOR_CATEGORY_SELECTION
                        await show_categories_menu(update, context)
                else:
                    await update.message.reply_text("❌ اختيار غير صحيح")
            except (ValueError, IndexError):
                await update.message.reply_text("❌ اختيار غير صحيح")
        else:
            await update.message.reply_text("❌ اختيار غير صحيح")

    except Exception as e:
        logger.error(f"خطأ في معالجة اختيار الزبون: {e}")
        await update.message.reply_text("❌ حدث خطأ")

async def show_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض فئات الشركات كأزرار مدمجة"""
    try:
        categories = get_companies_by_category()

        if not categories:
            await update.message.reply_text("❌ لا توجد فئات متاحة حالياً")
            return await show_main_menu(update, context)

        keyboard = []
        for category in categories:  # عرض جميع الفئات
            # استخدام اسم الفئة فقط بدون أيقونة لتجنب مشاكل التطابق
            keyboard.append([KeyboardButton(category[1])])

        keyboard.append([KeyboardButton("❌ إلغاء")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # حفظ الفئات لاستخدامها لاحقاً
        user_data[update.effective_user.id]['categories'] = categories

        text = "🏷️ اختر فئة الشركة:"
        await update.message.reply_text(text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في عرض الفئات: {e}")
        await update.message.reply_text("❌ حدث خطأ في تحميل الفئات")

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار الفئة"""
    try:
        user_id = update.effective_user.id
        text = update.message.text

        if text == "❌ إلغاء":
            return await cancel_operation(update, context)

        categories = user_data[user_id].get('categories', [])
        selected_category = None

        # البحث عن الفئة المختارة بالاسم فقط
        for category in categories:
            if text == category[1]:  # مطابقة اسم الفئة مباشرة
                selected_category = category
                break

        if not selected_category:
            await update.message.reply_text("❌ اختيار غير صحيح")
            return

        user_data[user_id]['selected_category'] = selected_category[0]
        user_data[user_id]['state'] = WAITING_FOR_COMPANY_SELECTION

        # جلب شركات الفئة المحددة
        companies = get_companies_by_category_id(selected_category[0])

        if not companies:
            await update.message.reply_text("❌ لا توجد شركات في هذه الفئة")
            return await show_main_menu(update, context)

        keyboard = []
        for company in companies:  # عرض جميع الشركات
            keyboard.append([KeyboardButton(company[1])])

        keyboard.append([KeyboardButton("🔙 العودة للفئات")])
        keyboard.append([KeyboardButton("❌ إلغاء")])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # حفظ الشركات لاستخدامها لاحقاً
        user_data[user_id]['companies'] = companies

        await update.message.reply_text(
            f"🏢 اختر الشركة من فئة: {selected_category[1]}",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"خطأ في معالجة اختيار الفئة: {e}")
        await update.message.reply_text("❌ خطأ في تحميل الشركات")

async def handle_company_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار الشركة"""
    try:
        user_id = update.effective_user.id
        text = update.message.text

        if text == "❌ إلغاء":
            return await cancel_operation(update, context)

        if text == "🔙 العودة للفئات":
            user_data[user_id]['state'] = WAITING_FOR_CATEGORY_SELECTION
            return await show_categories_menu(update, context)

        companies = user_data[user_id].get('companies', [])
        selected_company = None

        # البحث عن الشركة المختارة
        for company in companies:
            if text == company[1]:
                selected_company = company
                break

        if not selected_company:
            await update.message.reply_text("❌ اختيار غير صحيح")
            return

        user_data[user_id]['selected_company'] = selected_company[0]

        # تحديد التدفق التالي حسب السياق
        if user_data[user_id].get('customer_phone_for_add'):
            # إضافة بيانات جديدة
            phone = user_data[user_id]['customer_phone_for_add']
            user_data[user_id]['payment_phone'] = phone
            user_data[user_id]['state'] = WAITING_FOR_CUSTOMER_NAME

            keyboard = [
                [KeyboardButton("❌ إلغاء")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                f"👤 أدخل اسم المشترك للرقم {phone}:",
                reply_markup=reply_markup
            )
        elif user_data[user_id].get('customer_info'):
            # زبون موجود
            user_data[user_id]['state'] = WAITING_FOR_PAYMENT_AMOUNT
            customer_info = user_data[user_id]['customer_info']
            current_balance = user_data[user_id].get('balance', 0)

            keyboard = [
                [KeyboardButton("❌ إلغاء")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                f"💰 التسديد للزبون:\n"
                f"👤 الاسم: {customer_info.get('name', 'غير محدد')}\n"
                f"📱 الرقم: {customer_info['phone']}\n\n"
                f"أدخل المبلغ المطلوب تسديده:\n"
                f"💳 رصيدك الحالي: {current_balance} ل.س",
                reply_markup=reply_markup
            )
        else:
            # طلب اسم الزبون
            user_data[user_id]['state'] = WAITING_FOR_CUSTOMER_NAME
            phone = user_data[user_id].get('payment_phone', 'غير محدد')

            keyboard = [
                [KeyboardButton("❌ إلغاء")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                f"👤 أدخل اسم المشترك للرقم {phone}:",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"خطأ في معالجة اختيار الشركة: {e}")
        await update.message.reply_text("❌ خطأ في اختيار الشركة")

async def handle_customer_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال اسم الزبون"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        customer_name = update.message.text.strip()

        if not customer_name or len(customer_name) < 2:
            await update.message.reply_text("❌ اسم المشترك مطلوب ويجب أن يكون أكثر من حرف واحد.")
            return

        user_data[user_id]['customer_name'] = customer_name
        user_data[user_id]['state'] = WAITING_FOR_MOBILE_NUMBER

        keyboard = [
            [KeyboardButton("تخطي")],
            [KeyboardButton("❌ إلغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"📱 أدخل رقم الجوال للمشترك (اختياري):\n"
            f"أو اضغط تخطي إذا لم يكن متوفراً",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة اسم الزبون: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_mobile_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال رقم الجوال"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        mobile = update.message.text.strip() if update.message.text != "تخطي" else ""

        # التحقق من صحة رقم الجوال إذا تم إدخاله
        if mobile and not ((mobile.startswith('09') and len(mobile) == 10) or (mobile.startswith('011') and len(mobile) == 10)) or (mobile and not mobile.isdigit()):
            await update.message.reply_text(
                "❌ رقم الجوال غير صحيح. يجب أن يبدأ بـ 09 أو 011 (10 أرقام لكلاهما)\n"
                "أو اضغط تخطي لتجاهل هذا الحقل"
            )
            return

        user_data[user_id]['customer_mobile'] = mobile
        user_data[user_id]['state'] = WAITING_FOR_PAYMENT_AMOUNT

        current_balance = user_data[user_id].get('balance', 0)

        keyboard = [
            [KeyboardButton("❌ إلغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"💰 أدخل المبلغ المطلوب تسديده:\n"
            f"💳 رصيدك الحالي: {current_balance} ل.س",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"خطأ في معالجة رقم الجوال: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_payment_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال مبلغ التسديد"""
    try:
        if update.message.text == "❌ إلغاء":
            return await cancel_operation(update, context)

        user_id = update.effective_user.id
        amount_text = update.message.text.strip()

        try:
            amount = float(amount_text)
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
            if amount > 1000000:  # حد أقصى للأمان
                raise ValueError("المبلغ كبير جداً")
        except ValueError:
            await update.message.reply_text("❌ يرجى إدخال مبلغ صالح (أرقام فقط) بين 1 و 1,000,000")
            return

        # التحقق من الرصيد
        user_balance = user_data[user_id].get('balance', 0)
        if user_balance < amount:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي\n"
                f"💰 رصيدك الحالي: {user_balance} ل.س\n"
                f"💳 المبلغ المطلوب: {amount} ل.س"
            )
            return await show_main_menu(update, context)

        # عرض تأكيد المعاملة
        user_data[user_id]['payment_amount'] = amount
        user_data[user_id]['state'] = WAITING_FOR_PAYMENT_CONFIRMATION

        phone = user_data[user_id].get('payment_phone') or user_data[user_id].get('customer_phone_for_add') or user_data[user_id].get('customer_info', {}).get('phone', '')
        customer_name = user_data[user_id].get('customer_name', '')

        keyboard = [
            [KeyboardButton("✅ تأكيد التسديد")],
            [KeyboardButton("❌ إلغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"📋 تأكيد بيانات التسديد:\n\n"
            f"👤 الزبون: {customer_name}\n"
            f"📱 الرقم: {phone}\n"
            f"💰 المبلغ: {amount} ل.س\n"
            f"💳 رصيدك بعد التسديد: {user_balance - amount} ل.س\n\n"
            f"هل تريد تأكيد التسديد؟",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"خطأ في معالجة مبلغ التسديد: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تأكيد التسديد"""
    try:
        user_id = update.effective_user.id
        text = update.message.text

        if text == "❌ إلغاء":
            return await cancel_operation(update, context)

        if text != "✅ تأكيد التسديد":
            await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة")
            return

        # تجميع البيانات وإرسال طلب التسديد
        phone = user_data[user_id].get('payment_phone') or user_data[user_id].get('customer_phone_for_add') or user_data[user_id].get('customer_info', {}).get('phone', '')

        customer_data = {
            'phone': phone,
            'name': user_data[user_id].get('customer_name', ''),
            'mobile': user_data[user_id].get('customer_mobile', '')
        }

        payment_data = {
            'amount': user_data[user_id].get('payment_amount'),
            'company_id': user_data[user_id].get('selected_company'),
            'months': 1
        }

        # التحقق من البيانات المطلوبة
        if not customer_data['phone'] or not customer_data['name'] or not payment_data['company_id']:
            await update.message.reply_text("❌ بيانات غير مكتملة. يرجى البدء من جديد")
            return await show_main_menu(update, context)

        success, message = create_customer_and_payment(
            user_data[user_id]['user_id'], 
            customer_data, 
            payment_data
        )

        if success:
            # تحديث الرصيد في البيانات المحفوظة
            user_data[user_id]['balance'] -= payment_data['amount']

            # تنظيف البيانات المؤقتة
            for key in ['payment_phone', 'customer_name', 'customer_mobile', 'selected_company', 
                       'selected_category', 'customer_info', 'last_searched_phone', 
                       'customer_phone_for_add', 'available_customers', 'selected_customer_index',
                       'categories', 'companies', 'payment_amount']:
                user_data[user_id].pop(key, None)

            user_data[user_id]['state'] = None

            await update.message.reply_text(
                f"✅ {message}\n\n"
                f"👤 الزبون: {customer_data['name']}\n"
                f"📱 الرقم: {customer_data['phone']}\n"
                f"💰 المبلغ: {payment_data['amount']} ل.س\n"
                f"💳 رصيدك الجديد: {user_data[user_id]['balance']} ل.س\n\n"
                f"⏳ سيتم مراجعة الطلب وإشعارك بالنتيجة"
            )
        else:
            # تنظيف البيانات المؤقتة في حالة الفشل أيضاً
            for key in ['payment_phone', 'customer_name', 'customer_mobile', 'selected_company', 
                       'selected_category', 'customer_info', 'last_searched_phone', 
                       'customer_phone_for_add', 'available_customers', 'selected_customer_index',
                       'categories', 'companies', 'payment_amount']:
                user_data[user_id].pop(key, None)

            user_data[user_id]['state'] = None

            await update.message.reply_text(f"❌ {message}")

        await show_main_menu(update, context)

    except Exception as e:
        logger.error(f"خطأ في تأكيد التسديد: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_my_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معاملات المستخدم بشكل احترافي مع خاصية البحث"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        # تعيين حالة البحث في المعاملات
        user_data[user_id]['state'] = 'browsing_transactions'

        transactions = get_user_transactions(user_info['user_id'], limit=50)

        if not transactions:
            keyboard = [
                [KeyboardButton("💰 تسديد فاتورة جديدة")],
                [KeyboardButton("🏠 القائمة الرئيسية")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                "📋 *سجل المعاملات*\n\n"
                "🔍 لا توجد معاملات حتى الآن\n\n"
                "💡 يمكنك البدء بتسديد فاتورة جديدة",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return

        # حساب الإحصائيات المحسنة
        pending_count = sum(1 for t in transactions if t[3] == 'pending')
        approved_count = sum(1 for t in transactions if t[3] == 'approved')
        rejected_count = sum(1 for t in transactions if t[3] == 'rejected')
        total_approved_amount = sum(t[2] for t in transactions if t[3] == 'approved' and t[2])
        total_pending_amount = sum(t[2] for t in transactions if t[3] == 'pending' and t[2])

        # رسالة الإحصائيات المحسنة
        stats_msg = (
            f"📊 *تقرير شامل للمعاملات*\n\n"
            f"📈 *إحصائيات عامة:*\n"
            f"📋 إجمالي المعاملات: {len(transactions)}\n"
            f"⏳ قيد الانتظار: {pending_count} ({total_pending_amount} ل.س)\n"
            f"✅ مقبولة: {approved_count} ({total_approved_amount} ل.س)\n"
            f"❌ مرفوضة: {rejected_count}\n"
            f"💹 معدل القبول: {(approved_count/len(transactions)*100):.1f}%\n"
            f"{'─' * 35}\n\n"
        )

        # عرض آخر 8 معاملات مع تفاصيل محسنة
        transactions_to_show = transactions[:8]

        for i, transaction in enumerate(transactions_to_show, 1):
            status_emoji = {
                'pending': '⏳',
                'approved': '✅', 
                'rejected': '❌'
            }.get(transaction[3], '❓')

            status_color = {
                'pending': '🟡',
                'approved': '🟢',
                'rejected': '🔴'
            }.get(transaction[3], '⚪')

            # إضافة رقم المعاملة الفعلي من قاعدة البيانات
            transaction_id = transaction[0] if transaction[0] else i

            # تنسيق احترافي محسن للمعاملة
            transaction_msg = (
                f"{status_color} *المعاملة #{transaction_id}*\n"
                f"👤 العميل: *{transaction[6] or 'غير محدد'}*\n"
                f"📱 الرقم: {transaction[7] or 'غير محدد'}\n"
                f"🏢 الشركة: {transaction[8] or 'غير محدد'}\n"
                f"🏷️ الفئة: {transaction[9] or 'غير محدد'}\n"
                f"💰 المبلغ: *{transaction[2] or 0} ل.س*\n"
                f"📅 تاريخ الطلب: {transaction[5] or 'غير محدد'}\n"
                f"{status_emoji} الحالة: *{get_arabic_status(transaction[3])}*\n"
            )

            # إضافة معلومات إضافية للمعاملات المقبولة أو المرفوضة
            if transaction[3] == 'approved' and transaction[11]:  # تاريخ الموافقة
                transaction_msg += f"✅ تاريخ الموافقة: {transaction[11]}\n"

            if transaction[4]:  # ملاحظات المستخدم
                transaction_msg += f"📝 ملاحظاتك: {transaction[4]}\n"

            if transaction[12]:  # ملاحظات الإدارة
                transaction_msg += f"🗒️ ملاحظات الإدارة: {transaction[12]}\n"

            transaction_msg += f"{'─' * 30}\n\n"

            stats_msg += transaction_msg

        # إضافة معلومات إضافية إذا كان هناك معاملات أكثر
        if len(transactions) > 8:
            stats_msg += f"📋 عرض آخر 8 معاملات من أصل {len(transactions)} معاملة\n\n"

        # أزرار التفاعل المحسنة مع خاصية البحث
        keyboard = [
            [KeyboardButton("🔍 البحث في المعاملات"), KeyboardButton("📊 إحصائيات مفصلة")],
            [KeyboardButton("✅ المقبولة فقط"), KeyboardButton("⏳ قيد الانتظار")],
            [KeyboardButton("❌ المرفوضة"), KeyboardButton("📈 آخر شهر")],
            [KeyboardButton("💰 تسديد جديد"), KeyboardButton("💳 رصيدي")],
            [KeyboardButton("🔄 تحديث"), KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # تقسيم الرسالة إذا كانت طويلة
        if len(stats_msg) > 4000:
            # إرسال الإحصائيات أولاً
            await update.message.reply_text(
                f"📊 *تقرير شامل للمعاملات*\n\n"
                f"📈 *إحصائيات عامة:*\n"
                f"📋 إجمالي المعاملات: {len(transactions)}\n"
                f"⏳ قيد الانتظار: {pending_count} ({total_pending_amount} ل.س)\n"
                f"✅ مقبولة: {approved_count} ({total_approved_amount} ل.س)\n"
                f"❌ مرفوضة: {rejected_count}\n"
                f"💹 معدل القبول: {(approved_count/len(transactions)*100):.1f}%",
                parse_mode='Markdown'
            )

            # ثم إرسال المعاملات مقسمة
            transactions_msg = stats_msg.split(f"{'─' * 35}\n\n")[1]
            parts = [transactions_msg[i:i+3500] for i in range(0, len(transactions_msg), 3500)]

            for j, part in enumerate(parts):
                if j == len(parts) - 1:  # آخر جزء
                    await update.message.reply_text(part, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(stats_msg, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في عرض المعاملات: {e}")

        keyboard = [
            [KeyboardButton("🔄 إعادة المحاولة")],
            [KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "❌ حدث خطأ في تحميل المعاملات\n\n"
            "💡 يرجى المحاولة مرة أخرى أو التواصل مع الدعم الفني",
            reply_markup=reply_markup
        )

async def handle_balance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم مع تفاصيل إضافية"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        # جلب الرصيد الحالي
        current_balance = safe_db_execute(
            'SELECT balance FROM users WHERE id = ?', 
            (user_info['user_id'],), 
            fetch_one=True
        )

        # جلب إحصائيات المعاملات
        stats = safe_db_execute('''
            SELECT 
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COALESCE(SUM(CASE WHEN status = 'approved' THEN amount END), 0) as total_approved
            FROM transactions 
            WHERE user_id = ?
        ''', (user_info['user_id'],), fetch_one=True)

        if current_balance:
            user_data[user_id]['balance'] = current_balance[0]
            balance = current_balance[0]
        else:
            balance = 0

        if not stats:
            stats = (0, 0, 0, 0)

        balance_msg = (
            f"💳 معلومات حسابك:\n\n"
            f"💰 الرصيد الحالي: {balance} ل.س\n\n"
            f"📊 إحصائيات المعاملات:\n"
            f"⏳ قيد الانتظار: {stats[0]}\n"
            f"✅ مقبولة: {stats[1]}\n"
            f"❌ مرفوضة: {stats[2]}\n"
            f"💵 إجمالي المبلغ المقبول: {stats[3]} ل.س\n"
        )

        await update.message.reply_text(balance_msg)

    except Exception as e:
        logger.error(f"خطأ في عرض الرصيد: {e}")
        await update.message.reply_text("❌ خطأ في جلب الرصيد")

async def handle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إشعارات المستخدم مع تحديث حالة القراءة"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        # جلب الإشعارات
        notifications = safe_db_execute('''
            SELECT id, title, message, strftime('%Y-%m-%d %H:%M', created_at) as formatted_date, is_read
            FROM notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 15
        ''', (user_info['user_id'],), fetch_all=True)

        if not notifications:
            await update.message.reply_text("🔔 لا توجد إشعارات")
            return

        # تعليم جميع الإشعارات كمقروءة
        safe_db_execute(
            'UPDATE notifications SET is_read = 1 WHERE user_id = ?', 
            (user_info['user_id'],)
        )

        result_msg = "🔔 إشعاراتك:\n\n"
        unread_count = 0

        for notification in notifications:
            read_status = "🆕" if not notification[4] else "📋"
            if not notification[4]:
                unread_count += 1

            result_msg += (
                f"{read_status} {notification[1]}\n"
                f"📝 {notification[2]}\n"
                f"📅 {notification[3] or 'غير محدد'}\n"
                f"{'─' * 30}\n\n"
            )

        if unread_count > 0:
            result_msg = f"📩 لديك {unread_count} إشعار جديد!\n\n" + result_msg

        # تقسيم الرسالة إذا كانت طويلة
        if len(result_msg) > 4000:
            parts = [result_msg[i:i+4000] for i in range(0, len(result_msg), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(result_msg)

    except Exception as e:
        logger.error(f"خطأ في عرض الإشعارات: {e}")
        await update.message.reply_text("❌ خطأ في جلب الإشعارات")

async def handle_usage_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تعليمات الاستخدام"""
    try:
        instructions_msg = (
            "📖 *تعليمات الاستخدام*\n\n"
            "🔐 *للبدء:*\n"
            "لاستخدام الخدمات اضغط على تسجيل دخول واتبع التعليمات\n\n"
            
            "💰 *عملية التسديد:*\n"
            "عملية التسديد بسيطة مجرد الضغط على زر تسديد فاتورة تدخل الرقم:\n\n"
            
            "📞 *أنواع الأرقام:*\n"
            "• إذا كانت فاتورة أرضي أو انترنت: ندخل الرقم الأرضي كاملاً\n"
            "• في حال كانت فاتورة جوال أو رصيد كاش: ندخل رقم الجوال\n\n"
            
            "🔍 *البحث في البيانات:*\n"
            "سيبدأ البحث في قواعد البيانات:\n"
            "• في حال وجد بيانات مطابقة: سيطلب منك إتمام عملية التسديد\n"
            "• أو إضافة بيانات جديدة في حال كانت البيانات غير مطابقة لبحثك\n"
            "• في حال لم يجد أي بيانات: سيطلب منك إدخال البيانات يدوياً لأول مرة\n\n"
            
            "⚠️ *ملاحظات هامة:*\n"
            "في حال كنت تستخدم البوت وظهرت لك رسالة:\n"
            "❌ حدث خطأ. يرجى المحاولة مرة أخرى\n"
            "قم بتسجيل الخروج وادخل من جديد.\n\n"
            
            "🛠️ في حال واجهتكم مشاكل يرجى التواصل مع الدعم الفني."
        )

        await update.message.reply_text(instructions_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"خطأ في عرض تعليمات الاستخدام: {e}")
        await update.message.reply_text("❌ حدث خطأ")

async def handle_support_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التواصل مع الدعم الفني"""
    try:
        support_msg = (
            "🛠️ *الدعم الفني*\n\n"
            "للتواصل مع فريق الدعم الفني والحصول على المساعدة:\n\n"
            "👨‍💻 اضغط على الرابط التالي:\n"
            "https://t.me/nourrod\n\n"
            "⏰ أوقات العمل: على مدار الساعة\n"
            "📞 نحن هنا لمساعدتك في حل أي مشكلة قد تواجهها"
        )

        await update.message.reply_text(support_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"خطأ في عرض معلومات الدعم الفني: {e}")
        await update.message.reply_text("❌ حدث خطأ")

def get_arabic_status(status):
    """تحويل حالة المعاملة للعربية"""
    status_map = {
        'pending': 'قيد الانتظار',
        'approved': 'مقبول',
        'rejected': 'مرفوض'
    }
    return status_map.get(status, status)

async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تسجيل خروج المستخدم"""
    try:
        user_id = update.effective_user.id

        # مسح الجلسة المحفوظة
        clear_user_session(user_id)

        if user_id in user_data:
            del user_data[user_id]

        await update.message.reply_text("👋 تم تسجيل الخروج بنجاح")
        await start(update, context)
    except Exception as e:
        logger.error(f"خطأ في تسجيل الخروج: {e}")
        await update.message.reply_text("❌ حدث خطأ")

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية الحالية وتنظيف البيانات المؤقتة مع الحفاظ على الجلسة"""
    try:
        user_id = update.effective_user.id

        if user_id in user_data:
            # الحفاظ على البيانات الأساسية للمستخدم
            essential_data = {
                'user_id': user_data[user_id].get('user_id'),
                'name': user_data[user_id].get('name'),
                'phone': user_data[user_id].get('phone'),
                'balance': user_data[user_id].get('balance'),
                'role': user_data[user_id].get('role'),
                'is_active': user_data[user_id].get('is_active'),
                'login_time': user_data[user_id].get('login_time')
            }

            # تنظيف البيانات المؤقتة فقط
            user_data[user_id] = essential_data
            user_data[user_id]['state'] = None

            # حفظ الجلسة المحدثة
            save_user_session(user_id, user_data[user_id])

        # التأكد من وجود بيانات المستخدم قبل عرض القائمة
        user_info = user_data.get(user_id, {})
        if not user_info.get('user_id'):
            # محاولة استعادة الجلسة
            restored_session = restore_user_session(user_id)
            if restored_session and restored_session.get('user_id'):
                user_data[user_id] = restored_session
                await update.message.reply_text("❌ تم إلغاء العملية")
                return await show_main_menu(update, context)
            else:
                await update.message.reply_text("❌ تم إلغاء العملية. يرجى تسجيل الدخول مرة أخرى")
                return await start(update, context)

        await update.message.reply_text("❌ تم إلغاء العملية")
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"خطأ في إلغاء العملية: {e}")
        await update.message.reply_text("❌ حدث خطأ في إلغاء العملية")

async def handle_transaction_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البحث في المعاملات"""
    try:
        user_id = update.effective_user.id
        user_data[user_id]['state'] = 'search_transactions'

        keyboard = [
            [KeyboardButton("❌ إلغاء البحث")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "🔍 *البحث في المعاملات*\n\n"
            "أدخل كلمة البحث:\n"
            "• اسم العميل\n"
            "• رقم الهاتف\n"
            "• اسم الشركة\n"
            "• أي كلمة في الملاحظات\n\n"
            "مثال: أحمد، 0991234567، سيرياتيل",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"خطأ في بدء البحث: {e}")
        await update.message.reply_text("❌ حدث خطأ في البحث")

async def handle_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات مفصلة للمعاملات"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        # جلب إحصائيات مفصلة
        stats_query = '''
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COALESCE(SUM(CASE WHEN status = 'approved' THEN amount END), 0) as total_approved_amount,
                COALESCE(SUM(CASE WHEN status = 'pending' THEN amount END), 0) as total_pending_amount,
                COALESCE(AVG(CASE WHEN status = 'approved' THEN amount END), 0) as avg_approved_amount,
                COUNT(CASE WHEN status = 'approved' AND DATE(created_at) = DATE('now', 'localtime') THEN 1 END) as today_approved,
                COUNT(CASE WHEN DATE(created_at) >= DATE('now', '-7 days', 'localtime') THEN 1 END) as week_transactions,
                COUNT(CASE WHEN DATE(created_at) >= DATE('now', '-30 days', 'localtime') THEN 1 END) as month_transactions
            FROM transactions 
            WHERE user_id = ?
        '''

        stats = safe_db_execute(stats_query, (user_info['user_id'],), fetch_one=True)

        if not stats:
            await update.message.reply_text("❌ لا توجد بيانات إحصائية")
            return

        success_rate = (stats[2] / stats[0] * 100) if stats[0] > 0 else 0
        avg_amount = stats[6] if stats[6] else 0

        stats_msg = (
            f"📊 *إحصائيات مفصلة للمعاملات*\n\n"
            f"📈 *الإحصائيات العامة:*\n"
            f"📋 إجمالي المعاملات: {stats[0]}\n"
            f"⏳ قيد الانتظار: {stats[1]} ({stats[5]} ل.س)\n"
            f"✅ مقبولة: {stats[2]} ({stats[4]} ل.س)\n"
            f"❌ مرفوضة: {stats[3]}\n"
            f"💹 معدل النجاح: {success_rate:.1f}%\n"
            f"📊 متوسط المبلغ المقبول: {avg_amount:.0f} ل.س\n\n"
            f"📅 *إحصائيات زمنية:*\n"
            f"🌟 معاملات اليوم المقبولة: {stats[7]}\n"
            f"📅 معاملات آخر أسبوع: {stats[8]}\n"
            f"📆 معاملات آخر شهر: {stats[9]}\n\n"
            f"💰 *الرصيد الحالي:* {user_info.get('balance', 0)} ل.س"
        )

        keyboard = [
            [KeyboardButton("📋 عرض المعاملات"), KeyboardButton("💰 تسديد جديد")],
            [KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(stats_msg, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في عرض الإحصائيات المفصلة: {e}")
        await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات")

async def handle_transaction_filter(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_type):
    """تصفية المعاملات حسب النوع"""
    try:
        user_id = update.effective_user.id
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        status_filter = None
        date_filter = None
        filter_name = ""

        if filter_type == 'approved':
            status_filter = 'approved'
            filter_name = "المقبولة"
        elif filter_type == 'pending':
            status_filter = 'pending'
            filter_name = "قيد الانتظار"
        elif filter_type == 'rejected':
            status_filter = 'rejected'
            filter_name = "المرفوضة"
        elif filter_type == 'last_month':
            date_filter = 'last_month'
            filter_name = "آخر شهر"

        transactions = get_user_transactions(
            user_info['user_id'], 
            limit=20, 
            status_filter=status_filter,
            date_filter=date_filter
        )

        if not transactions:
            keyboard = [
                [KeyboardButton("📋 جميع المعاملات")],
                [KeyboardButton("🏠 القائمة الرئيسية")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                f"🔍 *المعاملات {filter_name}*\n\n"
                f"❌ لا توجد معاملات {filter_name.lower()}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return

        result_msg = f"🔍 *المعاملات {filter_name}*\n\n"
        result_msg += f"📊 عدد النتائج: {len(transactions)}\n"
        result_msg += f"{'─' * 35}\n\n"

        for i, transaction in enumerate(transactions[:8], 1):
            status_emoji = {
                'pending': '⏳',
                'approved': '✅', 
                'rejected': '❌'
            }.get(transaction[3], '❓')

            result_msg += (
                f"{status_emoji} *المعاملة #{transaction[0] or i}*\n"
                f"👤 العميل: *{transaction[6] or 'غير محدد'}*\n"
                f"📱 الرقم: {transaction[7] or 'غير محدد'}\n"
                f"🏢 الشركة: {transaction[8] or 'غير محدد'}\n"
                f"💰 المبلغ: {transaction[2] or 0} ل.س\n"
                f"📅 التاريخ: {transaction[5] or 'غير محدد'}\n"
            )

            if transaction[4]:  # ملاحظات
                result_msg += f"📝 ملاحظات: {transaction[4]}\n"

            result_msg += f"{'─' * 30}\n\n"

        keyboard = [
            [KeyboardButton("🔍 البحث"), KeyboardButton("📊 إحصائيات")],
            [KeyboardButton("📋 جميع المعاملات"), KeyboardButton("💰 تسديد جديد")],
            [KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if len(result_msg) > 4000:
            parts = [result_msg[i:i+3800] for i in range(0, len(result_msg), 3800)]
            for j, part in enumerate(parts):
                if j == len(parts) - 1:
                    await update.message.reply_text(part, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(result_msg, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في تصفية المعاملات: {e}")
        await update.message.reply_text("❌ حدث خطأ في التصفية")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الرئيسي مع فحص حالة الصيانة وصلاحية الجلسة"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text

        # فحص حالة الصيانة وصلاحيات المستخدم
        is_maintenance, maintenance_reason = check_maintenance_mode()
        
        # التحقق من كون المستخدم مدير
        is_admin = False
        try:
            user_from_telegram = safe_db_execute('''
                SELECT u.role FROM telegram_users tu
                JOIN users u ON tu.phone = u.phone
                WHERE tu.chat_id = ? AND u.is_active = 1
            ''', (str(user_id),), fetch_one=True)
            
            if user_from_telegram and user_from_telegram[0] == 'admin':
                is_admin = True
        except Exception as e:
            logger.error(f"خطأ في التحقق من صلاحيات المستخدم: {e}")
        
        if is_maintenance and not is_admin:
            # إذا كان النظام تحت الصيانة والمستخدم ليس مدير، عرض رسالة الصيانة
            maintenance_message = (
                "🔧 النظام تحت الصيانة حالياً\n\n"
                "نعتذر عن الإزعاج، النظام غير متاح حالياً بسبب أعمال الصيانة.\n\n"
            )
            
            if maintenance_reason:
                maintenance_message += f"📝 سبب الصيانة: {maintenance_reason}\n\n"
            
            maintenance_message += "سيعود النظام للعمل قريباً. شكراً لصبركم. 🙏"
            
            await update.message.reply_text(maintenance_message)
            return

        # التحقق من حالة المستخدم مع استعادة الجلسة إذا لزم الأمر
        user_info = user_data.get(user_id, {})
        
        # فحص صلاحية الجلسة إذا كان المستخدم مسجل دخول
        if user_info.get('user_id'):
            try:
                if not is_session_valid(user_info['user_id'], user_id):
                    # الجلسة غير صالحة، إجبار تسجيل الخروج
                    clear_user_session(user_id)
                    if user_id in user_data:
                        del user_data[user_id]
                    
                    # فحص سبب عدم صلاحية الجلسة
                    user_status = safe_db_execute('''
                        SELECT is_active FROM users WHERE id = ?
                    ''', (user_info['user_id'],), fetch_one=True)
                    
                    if user_status and not user_status[0]:
                        await update.message.reply_text(
                            "🚫 تم تعطيل حسابك\n\n"
                            "⚠️ لا يمكنك الوصول للنظام\n"
                            "📞 للاستفسار، يرجى التواصل مع الإدارة"
                        )
                    else:
                        await update.message.reply_text(
                            "🔐 تم تغيير إعدادات حسابك\n\n"
                            "🔄 تم إنهاء جلستك لضمان الأمان\n"
                            "📱 يرجى تسجيل الدخول مرة أخرى"
                        )
                    return await start(update, context)
            except Exception as e:
                logger.error(f"خطأ في فحص صلاحية الجلسة: {e}")
                # في حالة خطأ، لا نقطع الجلسة
        
        # إذا لم تكن هناك بيانات، محاولة استعادة الجلسة
        if not user_info.get('user_id'):
            restored_session = restore_user_session(user_id)
            if restored_session and restored_session.get('user_id'):
                # التحقق من صلاحية الجلسة المستعادة
                if is_session_valid(restored_session['user_id'], user_id):
                    user_data[user_id] = restored_session
                    user_info = user_data[user_id]
                    await update.message.reply_text(
                        f"🔄 تم استعادة جلستك {user_info.get('name', 'المستخدم')}"
                    )
                else:
                    # الجلسة المستعادة غير صالحة
                    clear_user_session(user_id)
                    await update.message.reply_text(
                        "🔐 تم تغيير كلمة المرور لحسابك\n\n"
                        "🔄 تم إنهاء جلستك لضمان الأمان\n"
                        "📱 يرجى تسجيل الدخول مرة أخرى بكلمة المرور الجديدة"
                    )
                    return await start(update, context)
        
        state = user_info.get('state')
        
        # حفظ النشاط في كل رسالة
        if user_info.get('user_id'):
            user_data[user_id]['last_activity'] = datetime.now().isoformat()
            save_user_session(user_id, user_data[user_id])

        # معالجة الحالات المختلفة
        if message_text == "🔑 تسجيل الدخول":
            await handle_login_request(update, context)
        elif message_text == "📖 أقرأ قبل الاستخدام":
            await handle_usage_instructions(update, context)
        elif message_text == "🛠️ الدعم الفني":
            await handle_support_contact(update, context)
        elif state == WAITING_FOR_PHONE:
            await handle_phone_input(update, context)
        elif state == WAITING_FOR_PASSWORD:
            await handle_password_input(update, context)
        elif message_text == "💰 تسديد فاتورة":
            await handle_payment_request(update, context)
        elif state == WAITING_FOR_CUSTOMER_PHONE:
            await handle_customer_phone_input(update, context)
        elif state == WAITING_FOR_CUSTOMER_SELECTION:
            await handle_customer_selection(update, context)
        elif state == WAITING_FOR_CATEGORY_SELECTION:
            await handle_category_selection(update, context)
        elif state == WAITING_FOR_COMPANY_SELECTION:
            await handle_company_selection(update, context)
        elif state == WAITING_FOR_CUSTOMER_NAME:
            await handle_customer_name_input(update, context)
        elif state == WAITING_FOR_MOBILE_NUMBER:
            await handle_mobile_number_input(update, context)
        elif state == WAITING_FOR_PAYMENT_AMOUNT:
            await handle_payment_amount_input(update, context)
        elif state == WAITING_FOR_PAYMENT_CONFIRMATION:
            await handle_payment_confirmation(update, context)
        elif message_text == "📋 معاملاتي":
            await handle_my_transactions(update, context)
        elif message_text == "💳 رصيدي":
            await handle_balance_check(update, context)
        elif message_text == "🔄 تحديث المعاملات" or message_text == "🔄 تحديث":
            await handle_my_transactions(update, context)
        elif message_text == "💰 تسديد جديد":
            await handle_payment_request(update, context)
        elif message_text == "🔄 إعادة المحاولة":
            await handle_my_transactions(update, context)
        elif message_text == "🔍 البحث في المعاملات" or message_text == "🔍 البحث":
            await handle_transaction_search(update, context)
        elif message_text == "📊 إحصائيات مفصلة":
            await handle_detailed_stats(update, context)
        elif message_text == "✅ المقبولة فقط":
            await handle_transaction_filter(update, context, 'approved')
        elif message_text == "⏳ قيد الانتظار":
            await handle_transaction_filter(update, context, 'pending')
        elif message_text == "❌ المرفوضة":
            await handle_transaction_filter(update, context, 'rejected')
        elif message_text == "📈 آخر شهر":
            await handle_transaction_filter(update, context, 'last_month')
        elif message_text == "📋 جميع المعاملات":
            await handle_my_transactions(update, context)
        elif message_text == "❌ إلغاء البحث":
            user_data[user_id]['state'] = None
            await handle_my_transactions(update, context)
        elif state == 'search_transactions':
            if message_text == "🏠 القائمة الرئيسية":
                await show_main_menu(update, context)
            else:
                await handle_search_input(update, context)
        elif state == 'browsing_transactions':
            # السماح بالبحث أثناء تصفح المعاملات
            if any(keyword in message_text.lower() for keyword in ['بحث', 'search']):
                await handle_transaction_search(update, context)
            elif message_text == "🏠 القائمة الرئيسية":
                await show_main_menu(update, context)
            else:
                await update.message.reply_text(
                    "🔍 استخدم الأزرار المتاحة للبحث والتصفية\n"
                    "أو اكتب 'بحث' للبحث الحر في المعاملات"
                )
        elif message_text == "🚪 تسجيل خروج":
            await handle_logout(update, context)
        elif message_text == "🏠 القائمة الرئيسية":
            await show_main_menu(update, context)
        else:
            # رسالة افتراضية للنصوص غير المعروفة
            if user_info.get('user_id'):
                # إذا كان المستخدم في حالة انتظار ولكن النص غير مفهوم، أعطه نصيحة
                current_state = user_info.get('state')
                if current_state:
                    await update.message.reply_text(
                        "❓ لم أفهم إجابتك. يرجى استخدام الأزرار المتاحة أو الإجابة بالتنسيق المطلوب"
                    )
                else:
                    await update.message.reply_text(
                        "❓ لم أفهم طلبك. يرجى ارسال❓ لم أفهم طلبك. يرجى ارسال❓ لم أفهم طلبك. يرجى ارسال❓ لم أفهم طلبك. يرجى استخدام الأزرار المتاحة او اضغط على الكلمة التالية /start  او اضغط على الكلمة التالية /start  او اضغط على الكلمة التالية /start "
                    )
            else:
                await start(update, context)

    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}")
        await update.message.reply_text("❌ حدث خطأ. يرجى المحاولة مرة أخرى")

async def handle_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال البحث النصي"""
    try:
        user_id = update.effective_user.id
        search_term = update.message.text.strip()
        user_info = user_data.get(user_id, {})

        if not user_info.get('user_id'):
            return await start(update, context)

        if len(search_term) < 2:
            await update.message.reply_text(
                "🔍 يجب أن يكون النص أكثر من حرف واحد\n"
                "أدخل كلمة البحث مرة أخرى:"
            )
            return

        # البحث في المعاملات
        transactions = get_user_transactions(
            user_info['user_id'], 
            limit=30, 
            search_term=search_term
        )

        if not transactions:
            keyboard = [
                [KeyboardButton("🔍 بحث جديد"), KeyboardButton("📋 جميع المعاملات")],
                [KeyboardButton("🏠 القائمة الرئيسية")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                f"🔍 *نتائج البحث عن: '{search_term}'*\n\n"
                f"❌ لم يتم العثور على نتائج مطابقة\n\n"
                f"💡 جرب البحث بكلمات أخرى أو تحقق من الإملاء",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return

        # عرض نتائج البحث
        result_msg = f"🔍 *نتائج البحث عن: '{search_term}'*\n\n"
        result_msg += f"📊 تم العثور على {len(transactions)} نتيجة\n"
        result_msg += f"{'─' * 35}\n\n"

        for i, transaction in enumerate(transactions[:10], 1):
            status_emoji = {
                'pending': '⏳',
                'approved': '✅', 
                'rejected': '❌'
            }.get(transaction[3], '❓')

            # تمييز النص المطابق
            customer_name = transaction[6] or 'غير محدد'
            company_name = transaction[8] or 'غير محدد'

            result_msg += (
                f"{status_emoji} *المعاملة #{transaction[0] or i}*\n"
                f"👤 العميل: *{customer_name}*\n"
                f"📱 الرقم: {transaction[7] or 'غير محدد'}\n"
                f"🏢 الشركة: *{company_name}*\n"
                f"💰 المبلغ: {transaction[2] or 0} ل.س\n"
                f"📅 التاريخ: {transaction[5] or 'غير محدد'}\n"
                f"🔖 الحالة: *{get_arabic_status(transaction[3])}*\n"
            )

            if transaction[4]:  # ملاحظات
                result_msg += f"📝 ملاحظات: {transaction[4]}\n"

            result_msg += f"{'─' * 30}\n\n"

        # أزرار إضافية للبحث
        keyboard = [
            [KeyboardButton("🔍 بحث جديد"), KeyboardButton("📊 إحصائيات النتائج")],
            [KeyboardButton("✅ المقبولة من النتائج"), KeyboardButton("⏳ قيد الانتظار من النتائج")],
            [KeyboardButton("📋 جميع المعاملات"), KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # تنظيف حالة البحث
        user_data[user_id]['state'] = 'browsing_transactions'
        user_data[user_id]['last_search_term'] = search_term

        if len(result_msg) > 4000:
            # تقسيم الرسالة الطويلة
            parts = [result_msg[i:i+3800] for i in range(0, len(result_msg), 3800)]
            for j, part in enumerate(parts):
                if j == len(parts) - 1:
                    await update.message.reply_text(part, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(result_msg, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"خطأ في معالجة البحث: {e}")
        await update.message.reply_text("❌ حدث خطأ في البحث. يرجى المحاولة مرة أخرى")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء"""
    logger.error(f"تسبب التحديث {update} في خطأ {context.error}")

def load_telegram_users():
    """تحميل مستخدمي التليجرام من قاعدة البيانات"""
    try:
        users = safe_db_execute('SELECT phone, chat_id FROM telegram_users', fetch_all=True)

        if users:
            for phone, chat_id in users:
                logger.info(f"تم تحميل مستخدم تليجرام: {phone} -> {chat_id}")

        logger.info(f"تم تحميل {len(users) if users else 0} مستخدم تليجرام من قاعدة البيانات")

    except Exception as e:
        logger.error(f"خطأ في تحميل مستخدمي التليجرام: {e}")

def check_bot_health():
    """فحص صحة البوت"""
    try:
        response = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getMe', timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            if bot_info.get('ok'):
                logger.info("البوت متصل ويعمل بشكل طبيعي")
                return True
    except Exception as e:
        logger.error(f"خطأ في فحص صحة البوت: {e}")

    return False

def main():
    """تشغيل البوت مع نظام إعادة التشغيل التلقائي محسن"""
    global restart_bot

    # التحقق من وجود التوكين
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN في Secrets")
        print("يرجى إضافة TELEGRAM_BOT_TOKEN في إعدادات Secrets")
        logger.error("❌ BOT_TOKEN غير موجود في Secrets")
        return

    while True:
        application = None
        try:
            print("🤖 بدء تشغيل بوت التليجرام...")
            logger.info("🤖 بدء تشغيل بوت التليجرام...")

            if not os.path.exists(DATABASE_PATH):
                print(f"❌ قاعدة البيانات غير موجودة: {DATABASE_PATH}")
                logger.error(f"❌ قاعدة البيانات غير موجودة: {DATABASE_PATH}")
                time.sleep(30)
                continue

            # فحص صحة البوت قبل البدء
            if not check_bot_health():
                print("❌ فشل في الاتصال بـ Telegram API")
                logger.error("❌ فشل في الاتصال بـ Telegram API")
                time.sleep(30)
                continue

            load_telegram_users()

            # تنظيف حلقة الأحداث بطريقة آمنة
            try:
                # التحقق من وجود حلقة أحداث نشطة
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop and not current_loop.is_closed():
                        # إلغاء جميع المهام المعلقة
                        pending = asyncio.all_tasks(current_loop)
                        for task in pending:
                            if not task.done():
                                task.cancel()
                        
                        # انتظار قصير لإنهاء المهام
                        if pending:
                            try:
                                current_loop.run_until_complete(
                                    asyncio.wait_for(
                                        asyncio.gather(*pending, return_exceptions=True),
                                        timeout=5.0
                                    )
                                )
                            except asyncio.TimeoutError:
                                logger.warning("انتهت مهلة انتظار إنهاء المهام")
                        
                        current_loop.close()
                        
                except RuntimeError:
                    # لا توجد حلقة أحداث نشطة
                    pass
                
                # إنشاء حلقة أحداث جديدة
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                
            except Exception as e:
                logger.warning(f"تحذير في إعداد حلقة الأحداث: {e}")
                # إنشاء حلقة جديدة كخيار احتياطي
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                except Exception as fallback_error:
                    logger.error(f"فشل في إنشاء حلقة أحداث جديدة: {fallback_error}")
                    time.sleep(10)
                    continue

            # إنشاء تطبيق البوت
            application = Application.builder().token(BOT_TOKEN).build()

            # إضافة معالجات الأوامر
            application.add_handler(CommandHandler("start", start))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            application.add_error_handler(error_handler)

            print("✅ تم تشغيل البوت بنجاح")
            logger.info("✅ تم تشغيل البوت بنجاح")

            # بدء البوت مع إعدادات محسنة
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,  # لا نغلق الحلقة تلقائياً
                timeout=30,
                read_timeout=20,
                write_timeout=20,
                connect_timeout=20,
                pool_timeout=10
            )

        except KeyboardInterrupt:
            print("🛑 تم إيقاف البوت بواسطة المستخدم")
            logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
            
            # إيقاف آمن للتطبيق
            if application:
                try:
                    application.stop()
                except Exception as stop_error:
                    logger.warning(f"خطأ في إيقاف التطبيق: {stop_error}")
            break
            
        except Exception as e:
            print(f"❌ خطأ في تشغيل البوت: {e}")
            logger.error(f"❌ خطأ في تشغيل البوت: {e}")

            # إيقاف آمن للتطبيق
            if application:
                try:
                    application.stop()
                    logger.info("تم إيقاف التطبيق بنجاح")
                except Exception as stop_error:
                    logger.warning(f"خطأ في إيقاف التطبيق: {stop_error}")

            # تنظيف حلقة الأحداث بطريقة آمنة
            try:
                current_loop = asyncio.get_event_loop()
                if current_loop and not current_loop.is_closed():
                    # إلغاء جميع المهام المعلقة
                    pending = asyncio.all_tasks(current_loop)
                    if pending:
                        for task in pending:
                            if not task.done():
                                task.cancel()
                        
                        # انتظار محدود لإنهاء المهام
                        try:
                            current_loop.run_until_complete(
                                asyncio.wait_for(
                                    asyncio.gather(*pending, return_exceptions=True),
                                    timeout=3.0
                                )
                            )
                        except (asyncio.TimeoutError, RuntimeError):
                            logger.warning("انتهت مهلة انتظار تنظيف المهام")
                    
                    current_loop.close()
                    logger.info("تم إغلاق حلقة الأحداث")
                    
            except Exception as cleanup_error:
                logger.warning(f"خطأ في تنظيف حلقة الأحداث: {cleanup_error}")

            # التحكم في إعادة التشغيل
            if restart_bot:
                print("🔄 إعادة تشغيل البوت...")
                logger.info("🔄 إعادة تشغيل البوت...")
                restart_bot = False
                time.sleep(5)
                continue
            else:
                print("⏳ انتظار 15 ثانية قبل إعادة المحاولة...")
                logger.info("⏳ انتظار 15 ثانية قبل إعادة المحاولة...")
                time.sleep(15)
                continue

if __name__ == '__main__':
    main()
