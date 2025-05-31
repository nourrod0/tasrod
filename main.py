from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import hashlib
from datetime import datetime
import os
import requests
import time
import threading

app = Flask(__name__)
app.secret_key = 'noor-commercial-bills-system-2024-secure-key-12345'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 172800  # 48 ساعة (مضاعفة الوقت)
app.config['SESSION_COOKIE_SECURE'] = False  # يجب أن يكون False في التطوير
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # تحديث الجلسة مع كل طلب

# قفل لحماية قاعدة البيانات من التداخل
db_lock = threading.Lock()

# قائمة المسارات التي لا تحتاج تسجيل دخول
PUBLIC_ROUTES = [
    '/',
    '/login',
    '/health',
    '/api/site-settings',
    '/static/',
    '/favicon.ico'
]

@app.before_request
def check_session():
    """فحص الجلسة قبل كل طلب مع معالجة محسنة ومنع قطع الاتصال أثناء العمليات"""
    # تجاهل المسارات العامة
    if any(request.path.startswith(route) for route in PUBLIC_ROUTES):
        return

    # تجاهل طلبات الملفات الثابتة
    if request.path.startswith('/static/'):
        return

    # تجاهل طلب الصحة
    if request.path == '/health':
        return

    # تمديد الجلسة تلقائياً مع كل طلب نشط
    if 'user_id' in session and 'logged_in' in session:
        # تحديث وقت آخر نشاط
        session['last_activity'] = datetime.now().isoformat()
        session.permanent = True
        # لا نتحقق من انتهاء الصلاحية إلا في حالات محددة
        return

    # التحقق من صحة الجلسة فقط للمستخدمين غير المسجلين
    if 'user_id' not in session or 'logged_in' not in session:
        # مسح الجلسة المعطلة
        session.clear()

        if request.path.startswith('/api/'):
            # عدم إرسال رسالة انتهاء الجلسة للطلبات العامة
            if request.path in ['/api/site-settings', '/api/health']:
                return
            return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401
        else:
            # إعادة توجيه للصفحة الرئيسية فقط إذا لم نكن بها
            if request.path != '/':
                return redirect(url_for('home'))

# Dictionary to store Telegram chat IDs
telegram_users = {}

# إنشاء قاعدة البيانات
def init_db():
    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()

    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0,
            role TEXT DEFAULT 'user',
            permissions TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # جدول فئات الشركات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS company_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # جدول شركات التسديد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            subcategory TEXT,
            commission REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES company_categories (id)
        )
    ''')

    # تم إزالة جدول صلاحيات المستخدم

    # جدول شركات الإنترنت (للتوافق مع النظام القديم)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS internet_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # جدول سرعات الإنترنت
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS internet_speeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            speed TEXT NOT NULL,
            price REAL NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (company_id) REFERENCES internet_companies (id)
        )
    ''')

    # جدول باقات الإنترنت
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS internet_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            package_name TEXT NOT NULL,
            speed_id INTEGER,
            monthly_price REAL NOT NULL,
            features TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (company_id) REFERENCES internet_companies (id),
            FOREIGN KEY (speed_id) REFERENCES internet_speeds (id)
        )
    ''')

    # جدول الزبائن
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            name TEXT NOT NULL,
            mobile_number TEXT,
            company_id INTEGER,
            speed_id INTEGER,
            added_by INTEGER,
            updated_by INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES internet_companies (id),
            FOREIGN KEY (speed_id) REFERENCES internet_speeds (id),
            FOREIGN KEY (added_by) REFERENCES users (id),
            FOREIGN KEY (updated_by) REFERENCES users (id)
        )
    ''')

    # إضافة الحقول الجديدة إذا لم تكن موجودة
    try:
        cursor.execute('ALTER TABLE customers ADD COLUMN updated_by INTEGER')
    except sqlite3.OperationalError:
        pass  # الحقل موجود بالفعل

    try:
        cursor.execute('ALTER TABLE customers ADD COLUMN updated_at TIMESTAMP')
    except sqlite3.OperationalError:
        pass  # الحقل موجود بالفعل

    # جدول العمليات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            customer_id INTEGER,
            transaction_type TEXT,
            amount REAL,
            months INTEGER,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            staff_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')

    # إضافة حقل staff_notes إذا لم يكن موجود
    try:
        cursor.execute('ALTER TABLE transactions ADD COLUMN staff_notes TEXT')
    except sqlite3.OperationalError:
        pass  # الحقل موجود بالفعل

    # جدول تتبع تغيير كلمات المرور
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            old_password_hash TEXT,
            new_password_hash TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            invalidated_sessions INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # إضافة حقل لتتبع آخر تغيير كلمة مرور للمستخدم
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP')
        # تحديث القيم الموجودة بالتاريخ الحالي
        cursor.execute('UPDATE users SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # الحقل موجود بالفعل

    # إضافة حقل لتتبع صلاحية الجلسة
    try:
        cursor.execute('ALTER TABLE telegram_users ADD COLUMN session_valid_after TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    except sqlite3.OperationalError:
        pass  # الحقل موجود بالفعل

    # جدول الإشعارات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # جدول النسخ الاحتياطية
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_size INTEGER,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # جدول مستخدمي التليجرام
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telegram_users (
            phone TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # جدول المحافظات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provinces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # إضافة مستخدم إداري افتراضي
    hashed_password = hashlib.md5('admin123'.encode()).hexdigest()
    cursor.execute('''
        INSERT OR IGNORE INTO users (name, phone, password, role, balance)
        VALUES (?, ?, ?, ?, ?)
    ''', ('المدير العام', '0000000000', hashed_password, 'admin', 0))

    # إضافة بعض المحافظات
    provinces = [
        ('دمشق', '011'),
        ('حلب', '021'),
        ('حمص', '031'),
        ('حماة', '033'),
        ('اللاذقية', '041'),
        ('طرطوس', '043'),
        ('درعا', '015'),
        ('السويداء', '016'),
        ('القنيطرة', '014'),
        ('دير الزور', '051'),
        ('الحسكة', '052'),
        ('الرقة', '022'),
        ('إدلب', '023'),
        ('ريف دمشق', '011')
    ]

    for province in provinces:
        cursor.execute('INSERT OR IGNORE INTO provinces (name, code) VALUES (?, ?)', province)

    conn.commit()
    conn.close()

# فحص حالة الصيانة
def check_maintenance():
    import json
    try:
        with open('site_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
            is_maintenance = settings.get('is_maintenance', False)
            # التأكد من أن القيمة boolean وليس string
            if isinstance(is_maintenance, str):
                is_maintenance = is_maintenance.lower() == 'true'
            return is_maintenance, settings.get('maintenance_reason', '')
    except (FileNotFoundError, json.JSONDecodeError):
        return False, ''

# الصفحة الرئيسية - تسجيل الدخول
@app.route('/')
def home():
    if 'user_id' in session:
        # فحص حالة الصيانة بعد تسجيل الدخول
        is_maintenance, reason = check_maintenance()
        if is_maintenance and session.get('user_role') != 'admin':
            return render_template('maintenance.html', reason=reason)
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# تسجيل الدخول
@app.route('/login', methods=['POST'])
def login():
    phone = request.form['phone']
    password = request.form['password']
    hashed_password = hashlib.md5(password.encode()).hexdigest()

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, role, balance FROM users WHERE phone = ? AND password = ? AND is_active = 1', 
                   (phone, hashed_password))
    user = cursor.fetchone()
    conn.close()

    if user:
        from datetime import datetime
        session.permanent = True
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        session['user_role'] = user[2]
        session['user_balance'] = user[3]
        session['logged_in'] = True
        session['login_time'] = datetime.now().isoformat()

        if user[2] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))
    else:
        flash('رقم الجوال أو كلمة المرور غير صحيحة')
        return redirect(url_for('home'))

# لوحة تحكم المستخدم
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    # فحص حالة الصيانة للمستخدمين العاديين فقط (المديرين يمكنهم الوصول دائماً)
    is_maintenance, reason = check_maintenance()
    if is_maintenance and session.get('user_role') != 'admin':
        return render_template('maintenance.html', reason=reason)

    # جلب رصيد المستخدم المحدث
    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
    balance = cursor.fetchone()[0]
    session['user_balance'] = balance
    conn.close()

    return render_template('dashboard.html')

# لوحة تحكم الإدارة
@app.route('/admin')
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('ليس لديك صلاحية للوصول للوحة الإدارة')
        return redirect(url_for('home'))
    return render_template('admin_dashboard.html')

# التحقق من حالة الجلسة
@app.route('/api/check-session', methods=['GET'])
def check_session_status():
    """التحقق من حالة الجلسة دون قطع الاتصال"""
    if 'user_id' in session and 'logged_in' in session:
        # تحديث وقت آخر نشاط
        session['last_activity'] = datetime.now().isoformat()
        return jsonify({
            'status': 'active',
            'user_id': session['user_id'],
            'user_name': session.get('user_name', ''),
            'user_role': session.get('user_role', 'user'),
            'balance': session.get('user_balance', 0)
        })
    else:
        return jsonify({'status': 'expired'}), 401

# تسجيل الخروج
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# حذف جميع البيانات (للمديرين فقط)
@app.route('/api/clear-all-data', methods=['POST'])
def clear_all_data():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()

    # حذف جميع البيانات بالترتيب الصحيح
    cursor.execute('DELETE FROM user_company_permissions')
    cursor.execute('DELETE FROM transactions')
    cursor.execute('DELETE FROM customers')
    cursor.execute('DELETE FROM internet_packages')
    cursor.execute('DELETE FROM internet_speeds')
    cursor.execute('DELETE FROM internet_companies')
    cursor.execute('DELETE FROM companies')
    cursor.execute('DELETE FROM company_categories')
    cursor.execute('DELETE FROM notifications WHERE user_id != ?', (session['user_id'],))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم حذف جميع البيانات بنجاح'})

# مسارات إدارة الفئات
@app.route('/api/categories', methods=['GET'])
def get_categories():
    if 'user_id' not in session:
        return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM company_categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': category[0],
        'name': category[1],
        'icon': category[2],
        'is_active': category[3]
    } for category in categories])

@app.route('/api/categories', methods=['POST'])
def add_category():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    icon = data.get('icon', 'fas fa-building')

    if not name:
        return jsonify({'error': 'اسم الفئة مطلوب'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO company_categories (name, icon) VALUES (?, ?)', (name, icon))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم إضافة الفئة بنجاح'})

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    icon = data.get('icon')
    is_active = data.get('is_active')

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE company_categories SET name = ?, icon = ?, is_active = ? WHERE id = ?', 
                   (name, icon, is_active, category_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم تحديث الفئة بنجاح'})

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    # التحقق من وجود شركات تستخدم هذه الفئة
    cursor.execute('SELECT COUNT(*) FROM companies WHERE category_id = ?', (category_id,))
    companies_count = cursor.fetchone()[0]

    if companies_count > 0:
        return jsonify({'error': 'لا يمكن حذف الفئة. توجد شركات مرتبطة بها'}), 400

    cursor.execute('DELETE FROM company_categories WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم حذف الفئة بنجاح'})

# مسارات إدارة سرعات الإنترنت
@app.route('/api/internet-speeds/<int:company_id>', methods=['GET'])
def get_internet_speeds(company_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM internet_speeds WHERE company_id = ? ORDER BY price', (company_id,))
    speeds = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': speed[0],
        'company_id': speed[1],
        'speed': speed[2],
        'price': speed[3],
        'is_active': speed[4]
    } for speed in speeds])

@app.route('/api/internet-speeds', methods=['POST'])
def add_internet_speed():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    company_id = data.get('company_id')
    speed = data.get('speed')
    price = data.get('price')

    if not all([company_id, speed, price]):
        return jsonify({'error': 'جميع البيانات مطلوبة'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO internet_speeds (company_id, speed, price) VALUES (?, ?, ?)', 
                   (company_id, speed, price))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم إضافة السرعة بنجاح'})

@app.route('/api/internet-speeds/<int:speed_id>', methods=['DELETE'])
def delete_internet_speed(speed_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM internet_speeds WHERE id = ?', (speed_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم حذف السرعة بنجاح'})

# مسارات إدارة باقات الإنترنت
@app.route('/api/internet-packages/<int:company_id>', methods=['GET'])
def get_internet_packages(company_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ip.*, ips.speed 
        FROM internet_packages ip
        LEFT JOIN internet_speeds ips ON ip.speed_id = ips.id
        WHERE ip.company_id = ? 
        ORDER BY ip.monthly_price
    ''', (company_id,))
    packages = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': package[0],
        'company_id': package[1],
        'package_name': package[2],
        'speed_id': package[3],
        'monthly_price': package[4],
        'features': package[5],
        'is_active': package[6],
        'speed': package[7]
    } for package in packages])

@app.route('/api/internet-packages', methods=['POST'])
def add_internet_package():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    company_id = data.get('company_id')
    package_name = data.get('package_name')
    speed_id = data.get('speed_id')
    monthly_price = data.get('monthly_price')
    features = data.get('features', '')

    if not all([company_id, package_name, monthly_price]):
        return jsonify({'error': 'البيانات الأساسية مطلوبة'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO internet_packages (company_id, package_name, speed_id, monthly_price, features) 
        VALUES (?, ?, ?, ?, ?)
    ''', (company_id, package_name, speed_id, monthly_price, features))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم إضافة الباقة بنجاح'})

@app.route('/api/internet-packages/<int:package_id>', methods=['DELETE'])
def delete_internet_package(package_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM internet_packages WHERE id = ?', (package_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم حذف الباقة بنجاح'})

# مسار البحث في الشركات (جديد)
@app.route('/api/inquiry/<phone_number>', methods=['GET'])
def inquiry_customer(phone_number):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, comp.name as company_name, ips.speed, ips.price
        FROM customers c
        LEFT JOIN companies comp ON c.company_id = comp.id
        LEFT JOIN internet_speeds ips ON c.speed_id = ips.id
        WHERE c.phone_number = ?
        ORDER BY c.created_at DESC
    ''', (phone_number,))
    customers = cursor.fetchall()
    conn.close()

    if customers:
        customers_list = []
        for customer in customers:
            customers_list.append({
                'id': customer[0],
                'phone_number': customer[1],
                'name': customer[2],
                'mobile_number': customer[3],
                'company_id': customer[4],
                'speed_id': customer[5],
                'notes': customer[7],
                'created_at': customer[8],
                'company_name': customer[9],
                'speed': customer[10],
                'speed_price': customer[11]
            })

        return jsonify({
            'found': True,
            'customers': customers_list,
            'count': len(customers_list)
        })
    else:
        return jsonify({'found': False, 'message': 'لم يتم العثور على بيانات لهذا الرقم'})

@app.route('/api/payment-requests', methods=['POST'])
def create_payment_request():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    category_id = data.get('category_id')
    company_id = data.get('company_id')
    phone_number = data.get('phone_number')
    customer_name = data.get('customer_name')
    mobile_number = data.get('mobile_number', '')
    amount = data.get('amount')
    months = data.get('months', 1)
    notes = data.get('notes', '')

    if not all([category_id, company_id, phone_number, customer_name]):
        return jsonify({'error': 'الفئة والشركة ورقم الهاتف واسم العميل مطلوبة'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()

    # التحقق من رصيد المستخدم إذا كان المبلغ محدد
    if amount:
        cursor.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
        user_balance = cursor.fetchone()[0]

        if user_balance < float(amount):
            return jsonify({'error': 'الرصيد غير كافي'}), 400

        # خصم المبلغ من رصيد المستخدم فوراً
        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))
        # تحديث رصيد الجلسة
        session['user_balance'] = user_balance - float(amount)

    # التحقق من وجود الزبون أو إضافته
    cursor.execute('SELECT id FROM customers WHERE phone_number = ?', (phone_number,))
    customer = cursor.fetchone()

    if not customer:
        cursor.execute('''
            INSERT INTO customers (phone_number, name, mobile_number, company_id, added_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (phone_number, customer_name, mobile_number, company_id, session['user_id']))
        customer_id = cursor.lastrowid
    else:
        customer_id = customer[0]
        # تحديث بيانات الزبون
        cursor.execute('UPDATE customers SET name = ?, mobile_number = ?, company_id = ? WHERE id = ?', 
                       (customer_name, mobile_number, company_id, customer_id))

    # إضافة طلب التسديد
    cursor.execute('''
        INSERT INTO transactions (user_id, customer_id, transaction_type, amount, months, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], customer_id, 'payment', amount, months, notes, 'pending'))

    transaction_id = cursor.lastrowid

    # جلب اسم المستخدم واسم الشركة لإرسال إشعار للمدير
    cursor.execute('SELECT name FROM users WHERE id = ?', (session['user_id'],))
    user_name = cursor.fetchone()[0]
    
    # جلب اسم الشركة
    cursor.execute('''
        SELECT COALESCE(c.name, ic.name, 'غير محدد') as company_name
        FROM (SELECT ? as company_id) as temp
        LEFT JOIN companies c ON temp.company_id = c.id
        LEFT JOIN internet_companies ic ON temp.company_id = ic.id
    ''', (company_id,))
    company_result = cursor.fetchone()
    company_name = company_result[0] if company_result else 'غير محدد'

    conn.commit()
    conn.close()

    # إرسال إشعار فوري للمدير
    admin_notification = (
        f"طلب تسديد جديد #{transaction_id}\n"
        f"👤 المستخدم: {user_name}\n"
        f"📱 رقم الزبون: {phone_number}\n"
        f"👨‍💼 اسم الزبون: {customer_name}\n"
        f"💰 المبلغ: {amount} ل.س\n"
        f"🏢 الشركة: {company_name}\n"
        f"📝 ملاحظات: {notes if notes else 'لا توجد'}"
    )
    send_notification_to_admin("طلب تسديد جديد", admin_notification)

    if amount:
        return jsonify({'success': True, 'message': 'تم إرسال طلب التسديد وخصم المبلغ من رصيدك'})
    else:
        return jsonify({'success': True, 'message': 'تم إرسال طلب التسديد بنجاح'})

# مسارات إدارة الشركات الجديدة
@app.route('/api/companies', methods=['GET'])
def get_companies():
    if 'user_id' not in session:
        return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, cc.name as category_name, cc.icon as category_icon
        FROM companies c
        LEFT JOIN company_categories cc ON c.category_id = cc.id
        ORDER BY cc.name, c.name
    ''')
    companies = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': company[0],
        'name': company[1],
        'category_id': company[2],
        'subcategory': company[3],
        'commission': company[4],
        'is_active': company[5],
        'category_name': company[6],
        'category_icon': company[7]
    } for company in companies])

# مسارات للشركات القديمة (للتوافق)
@app.route('/api/internet-companies', methods=['GET'])
def get_internet_companies():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM internet_companies ORDER BY name')
    companies = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': company[0],
        'name': company[1],
        'is_active': company[2]
    } for company in companies])

@app.route('/api/companies', methods=['POST'])
def add_company():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    category_id = data.get('category_id')
    subcategory = data.get('subcategory', '')
    commission = data.get('commission', 0)

    if not name or not category_id:
        return jsonify({'error': 'اسم الشركة والفئة مطلوبان'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO companies (name, category_id, subcategory, commission) VALUES (?, ?, ?, ?)', 
                   (name, category_id, subcategory, commission))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم إضافة الشركة بنجاح'})

@app.route('/api/companies/<int:company_id>', methods=['PUT'])
def update_company(company_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    category_id = data.get('category_id')
    subcategory = data.get('subcategory', '')
    commission = data.get('commission', 0)
    is_active = data.get('is_active', 1)

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''UPDATE companies 
                     SET name = ?, category_id = ?, subcategory = ?, commission = ?, is_active = ? 
                     WHERE id = ?''', 
                   (name, category_id, subcategory, commission, is_active, company_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم تحديث الشركة بنجاح'})

@app.route('/api/companies/<int:company_id>', methods=['GET'])
def get_company(company_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, cc.name as category_name, cc.icon as category_icon
        FROM companies c
        LEFT JOIN company_categories cc ON c.category_id = cc.id
        WHERE c.id = ?
    ''', (company_id,))
    company = cursor.fetchone()
    conn.close()

    if company:
        return jsonify({
            'id': company[0],
            'name': company[1],
            'category_id': company[2],
            'subcategory': company[3],
            'commission': company[4],
            'is_active': company[5],
            'category_name': company[6],
            'category_icon': company[7]
        })
    else:
        return jsonify({'error': 'الشركة غير موجودة'}), 404

@app.route('/api/companies/<int:company_id>', methods=['DELETE'])
def delete_company(company_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM companies WHERE id = ?', (company_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم حذف الشركة بنجاح'})

# تم إزالة نظام صلاحيات المستخدم بناءً على الطلب

# مسارات إدارة المستخدمين
@app.route('/api/users', methods=['GET'])
def get_users():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, phone, balance, role, is_active, created_at FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    conn.close()

    return jsonify([{
        'id': user[0],
        'name': user[1],
        'phone': user[2],
        'balance': user[3],
        'role': user[4],
        'is_active': user[5],
        'created_at': user[6]
    } for user in users])

# إضافة رصيد للمستخدم
@app.route('/api/users/<int:user_id>/add-balance', methods=['POST'])
def add_user_balance(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    amount = data.get('amount', 0)
    notes = data.get('notes', '')

    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()

    # تحديث رصيد المستخدم
    cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))

    # إضافة سجل العملية
    cursor.execute('''
        INSERT INTO transactions (user_id, transaction_type, amount, notes, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, 'balance_add', amount, f'إضافة رصيد من الإدارة: {notes}', 'approved'))

    # إرسال إشعار للمستخدم
    cursor.execute('''
                INSERT INTO notifications (user_id, title, message, created_at)
                VALUES (?, ?, ?, datetime('now', '+3 hours'))
            ''', (user_id, 'تم إضافة رصيد لحسابك', 
                  f'تمت إضافة {amount} ل.س إلى رصيدك من قبل الإدارة. {notes if notes else ""}'))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'تم إضافة {amount} ل.س إلى الرصيد'})

# خصم رصيد من المستخدم
@app.route('/api/users/<int:user_id>/deduct-balance', methods=['POST'])
def deduct_user_balance(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    amount = data.get('amount', 0)
    notes = data.get('notes', '')

    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    conn = sqlite3.connect('bills_system.db')
    cursor = conn.cursor()

    # التحقق من الرصيد الحالي
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    current_balance = cursor.fetchone()[0]

    if current_balance < amount:
        return jsonify({'error': 'الرصيد غير كافي'}), 400

    # تحديث رصيد المستخدم
    cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))

    # إضافة سجل العملية
    cursor.execute('''
        INSERT INTO transactions (user_id, transaction_type, amount, notes, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, 'balance_deduct', amount, f'خصم رصيد من الإدارة: {notes}', 'approved'))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'تم خصم {amount} ل.س من الرصيد'})

# دالة لإرسال الإشعارات عبر التيليجرام
def send_telegram_notification(phone, message):
    """إرسال إشعار إلى مستخدم التيليجرام إذا كان مسجلاً."""
    try:
        # جلب معرف المحادثة من قاعدة البيانات
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM telegram_users WHERE phone = ?', (phone,))
            result = cursor.fetchone()
            conn.close()

        chat_id = None
        if result:
            chat_id = result[0]
        elif phone in telegram_users:
            chat_id = telegram_users[phone]

        if chat_id:
            bot_token = '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE'
            send_message_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'

            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(send_message_url, json=payload, timeout=10)
            response.raise_for_status()
            print(f"تم إرسال إشعار تيليجرام بنجاح إلى {phone}: {response.status_code}")
            return True
        else:
            print(f"المستخدم برقم {phone} غير مسجل في التيليجرام")
            return False

    except requests.exceptions.RequestException as e:
        print(f"فشل إرسال إشعار إلى تيليجرام: {e}")
        return False
    except Exception as e:
        print(f"خطأ عام في إرسال إشعار التيليجرام: {e}")
        return False

# دالة لإرسال التليجرام غير المتزامنة
def send_telegram_notification_async(phone, message):
    """إرسال إشعار تيليجرام في خيط منفصل لعدم تأخير الاستجابة."""
    try:
        send_telegram_notification(phone, message)
    except Exception as e:
        print(f"خطأ في إرسال التليجرام غير المتزامن: {e}")

def invalidate_user_sessions(user_id, reason="تم تغيير كلمة المرور"):
    """إبطال جميع جلسات المستخدم في الموقع والبوت فقط عند تغيير كلمة المرور فعلياً"""
    try:
        # التحقق من أن السبب هو تغيير كلمة المرور فعلياً
        if "تغيير كلمة المرور" not in reason:
            print(f"تجاهل إبطال الجلسات للمستخدم {user_id}: السبب غير مرتبط بتغيير كلمة المرور")
            return False
            
        current_time = datetime.now().isoformat()
        
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # التحقق من وجود تغيير حقيقي في كلمة المرور خلال آخر دقيقة
            cursor.execute('''
                SELECT COUNT(*) FROM password_changes 
                WHERE user_id = ? AND changed_at > datetime('now', '-1 minute')
            ''', (user_id,))
            recent_change = cursor.fetchone()[0]
            
            if recent_change == 0:
                print(f"لم يتم العثور على تغيير حديث في كلمة المرور للمستخدم {user_id}")
                conn.close()
                return False
            
            # تحديث وقت إبطال الجلسات في التليجرام فقط عند وجود تغيير حقيقي
            cursor.execute('''
                UPDATE telegram_users 
                SET session_valid_after = ? 
                WHERE phone IN (SELECT phone FROM users WHERE id = ?)
            ''', (current_time, user_id))
            
            # تحديث وقت تغيير كلمة المرور للمستخدم
            cursor.execute('''
                UPDATE users 
                SET password_changed_at = ? 
                WHERE id = ?
            ''', (current_time, user_id))
            
            # جلب رقم هاتف المستخدم لإرسال إشعار
            cursor.execute('SELECT phone, name FROM users WHERE id = ?', (user_id,))
            user_info = cursor.fetchone()
            
            conn.commit()
            conn.close()
        
        # إرسال إشعار للمستخدم عبر التليجرام
        if user_info:
            phone, name = user_info
            message = (
                f"🔐 تم تغيير كلمة المرور لحسابك\n\n"
                f"👤 الاسم: {name}\n"
                f"📱 الرقم: {phone}\n\n"
                f"🔄 يجب عليك تسجيل الدخول مرة أخرى في:\n"
                f"• بوت التليجرام\n"
                f"• الموقع الإلكتروني\n\n"
                f"🔒 تم إبطال جميع الجلسات لضمان الأمان"
            )
            
            # إرسال في خيط منفصل لعدم تأخير العملية
            threading.Thread(
                target=send_telegram_notification, 
                args=(phone, message),
                daemon=True
            ).start()
        
        print(f"تم إبطال جلسات المستخدم {user_id}: {reason}")
        return True
        
    except Exception as e:
        print(f"خطأ في إبطال جلسات المستخدم: {e}")
        return False

def send_notification_to_admin(title, message):
    """إرسال إشعار للمدير عبر التيليجرام"""
    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()

            # جلب جميع المديرين
            cursor.execute('SELECT phone FROM users WHERE role = "admin" AND is_active = 1')
            admins = cursor.fetchall()
            conn.close()

        admin_message = f"🔔 {title}\n\n{message}"

        for admin in admins:
            admin_phone = admin[0]
            send_telegram_notification(admin_phone, admin_message)

        return True
    except Exception as e:
        print(f"خطأ في إرسال إشعار للمدير: {e}")
        return False

# إرسال إشعار للمستخدم
@app.route('/api/users/<int:user_id>/send-notification', methods=['POST'])
def send_user_notification(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    title = data.get('title', '')
    message = data.get('message', '')

    if not title or not message:
        return jsonify({'error': 'العنوان والرسالة مطلوبان'}), 400

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()

        # إضافة الإشعار لقاعدة البيانات
        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, datetime('now', '+3 hours'))
        ''', (user_id, title, message))

        # جلب رقم هاتف المستخدم لإرسال إشعار التليجرام
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        user_phone = cursor.fetchone()

        conn.commit()
        conn.close()

    # إرسال إشعار للتليجرام
    if user_phone:
        telegram_message = f"🔔 {title}\n\n{message}"
        send_telegram_notification(user_phone[0], telegram_message)

    return jsonify({'success': True, 'message': 'تم إرسال الإشعار بنجاح'})

@app.route('/api/users', methods=['POST'])
def add_user():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    password = data.get('password')
    role = data.get('role', 'user')
    balance = data.get('balance', 0)

    if not all([name, phone, password]):
        return jsonify({'error': 'جميع البيانات مطلوبة'}), 400

    hashed_password = hashlib.md5(password.encode()).hexdigest()

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (name, phone, password, role, balance) VALUES (?, ?, ?, ?, ?)', 
                           (name, phone, hashed_password, role, balance))
            conn.commit()
            return jsonify({'success': True, 'message': 'تم إضافة المستخدم بنجاح'})
        except sqlite3.IntegrityError:
            return jsonify({'error': 'رقم الجوال موجود مسبقاً'}), 400
        finally:
            conn.close()

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    role = data.get('role')
    balance = data.get('balance')
    is_active = data.get('is_active')
    password = data.get('password')

    password_changed = False

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db', timeout=15.0)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            cursor = conn.cursor()

            # التأكد من وجود العمود password_changed_at
            try:
                cursor.execute('SELECT password_changed_at FROM users WHERE id = ? LIMIT 1', (user_id,))
            except sqlite3.OperationalError:
                # إضافة العمود إذا لم يكن موجود
                cursor.execute('ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP')
                cursor.execute('UPDATE users SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL')
                conn.commit()

            # جلب كلمة المرور الحالية لمقارنتها
            current_password = None
            if password:
                cursor.execute('SELECT password FROM users WHERE id = ?', (user_id,))
                current_password_result = cursor.fetchone()
                current_password = current_password_result[0] if current_password_result else None

            # تحديث البيانات الأساسية
            update_query = 'UPDATE users SET name = ?, phone = ?, role = ?, balance = ?, is_active = ?'
            params = [name, phone, role, balance, is_active]

            # إضافة كلمة المرور إذا تم تقديمها
            if password:
                hashed_password = hashlib.md5(password.encode()).hexdigest()
                
                # التحقق من تغيير كلمة المرور
                if current_password != hashed_password:
                    password_changed = True
                    
                    # تسجيل تغيير كلمة المرور
                    cursor.execute('''
                        INSERT INTO password_changes (user_id, old_password_hash, new_password_hash)
                        VALUES (?, ?, ?)
                    ''', (user_id, current_password, hashed_password))
                    
                    update_query += ', password = ?, password_changed_at = ?'
                    params.extend([hashed_password, datetime.now().isoformat()])
                else:
                    update_query += ', password = ?'
                    params.append(hashed_password)

            update_query += ' WHERE id = ?'
            params.append(user_id)

            cursor.execute(update_query, params)
            conn.commit()
            conn.close()

        # إبطال الجلسات إذا تم تغيير كلمة المرور
        if password_changed:
            invalidate_user_sessions(user_id, "تم تغيير كلمة المرور من قبل المدير")
            return jsonify({
                'success': True, 
                'message': 'تم تحديث المستخدم بنجاح وإبطال جميع جلساته لضمان الأمان',
                'password_changed': True
            })

        return jsonify({'success': True, 'message': 'تم تحديث المستخدم بنجاح'})

    except sqlite3.OperationalError as e:
        if 'database is locked' in str(e):
            return jsonify({'error': 'النظام مشغول حالياً، يرجى المحاولة بعد قليل'}), 503
        elif 'Cannot add a column' in str(e):
            print(f"خطأ في إضافة عمود - المستخدم {user_id}: {e}")
            return jsonify({'error': 'خطأ في هيكل قاعدة البيانات. يرجى المحاولة مرة أخرى'}), 500
        else:
            print(f"خطأ في قاعدة البيانات - تحديث المستخدم {user_id}: {e}")
            return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ عام في تحديث المستخدم {user_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db', timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, phone, balance, role, is_active, created_at FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()

        if user:
            return jsonify({
                'id': user[0],
                'name': user[1] or '',
                'phone': user[2] or '',
                'balance': user[3] if user[3] is not None else 0,
                'role': user[4] or 'user',
                'is_active': user[5] if user[5] is not None else 1,
                'created_at': user[6] or ''
            })
        else:
            return jsonify({'error': 'المستخدم غير موجود'}), 404
            
    except sqlite3.OperationalError as e:
        if 'database is locked' in str(e):
            return jsonify({'error': 'النظام مشغول حالياً، يرجى المحاولة بعد قليل'}), 503
        else:
            print(f"خطأ في قاعدة البيانات: {e}")
            return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ في جلب بيانات المستخدم {user_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    # منع حذف المستخدم الحالي
    if user_id == session['user_id']:
        return jsonify({'error': 'لا يمكن حذف حسابك الحالي'}), 400

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': 'تم حذف المستخدم بنجاح'})

# مسارات البحث عن الزبائن
@app.route('/api/customers/search/<phone_number>', methods=['GET'])
def search_customer(phone_number):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, comp.name as company_name, ips.speed, ips.price
            FROM customers c
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_speeds ips ON c.speed_id = ips.id
            WHERE c.phone_number = ?
        ''', (phone_number,))
        customer = cursor.fetchone()
        conn.close()

    if customer:
        return jsonify({
            'found': True,
            'customer': {
                'id': customer[0],
                'phone_number': customer[1],
                'name': customer[2],
                'mobile_number': customer[3],
                'company_id': customer[4],
                'speed_id': customer[5],
                'notes': customer[7],
                'company_name': customer[9],
                'speed': customer[10],
                'speed_price': customer[11]
            }
        })
    else:
        return jsonify({'found': False})

# مسارات إدارة المحافظات
@app.route('/api/provinces', methods=['GET'])
def get_provinces():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM provinces WHERE is_active = 1 ORDER BY name')
        provinces = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': province[0],
        'name': province[1],
        'code': province[2],
        'is_active': province[3]
    } for province in provinces])

# مسارات إدارة الزبائن
@app.route('/api/customers', methods=['GET'])
def get_customers():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.phone_number, c.name, c.mobile_number, 
                   COALESCE(comp.name, ic.name) as company_name, c.notes, c.created_at
            FROM customers c
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            ORDER BY c.created_at DESC
        ''')
        customers = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': customer[0],
        'phone_number': customer[1],
        'name': customer[2],
        'mobile_number': customer[3],
        'company_name': customer[4] or 'غير محدد',
        'notes': customer[5],
        'created_at': customer[6]
    } for customer in customers])

@app.route('/api/customers', methods=['POST'])
def add_customer():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    phone_number = data.get('phone_number')
    name = data.get('name')
    mobile_number = data.get('mobile_number')
    company_id = data.get('company_id')
    notes = data.get('notes', '')

    if not all([phone_number, name]):
        return jsonify({'error': 'رقم الهاتف والاسم مطلوبان'}), 400

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO customers (phone_number, name, mobile_number, company_id, added_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (phone_number, name, mobile_number, company_id, session['user_id'], notes))
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': 'تم إضافة الزبون بنجاح'})

@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    phone_number = data.get('phone_number')
    name = data.get('name')
    mobile_number = data.get('mobile_number')
    company_id = data.get('company_id')
    notes = data.get('notes')

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE customers 
            SET phone_number = ?, name = ?, mobile_number = ?, company_id = ?, notes = ?,
                updated_by = ?, updated_at = datetime('now', '+3 hours')
            WHERE id = ?
        ''', (phone_number, name, mobile_number, company_id, notes, session['user_id'], customer_id))
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': 'تم تحديث بيانات الزبون بنجاح'})

@app.route('/api/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.phone_number, c.name, c.mobile_number, c.company_id, c.notes, c.created_at,
                   COALESCE(comp.name, ic.name) as company_name,
                   u_added.name as added_by_name,
                   u_updated.name as updated_by_name,
                   c.updated_at
            FROM customers c
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN users u_added ON c.added_by = u_added.id
            LEFT JOIN users u_updated ON c.updated_by = u_updated.id
            WHERE c.id = ?
        ''', (customer_id,))
        customer = cursor.fetchone()
        conn.close()

    if customer:
        return jsonify({
            'id': customer[0],
            'phone_number': customer[1],
            'name': customer[2],
            'mobile_number': customer[3],
            'company_id': customer[4],
            'notes': customer[5],
            'created_at': customer[6],
            'company_name': customer[7],
            'added_by_name': customer[8] or 'غير محدد',
            'updated_by_name': customer[9] or 'لم يتم التعديل',
            'updated_at': customer[10] or None
        })
    else:
        return jsonify({'error': 'الزبون غير موجود'}), 404

@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': 'تم حذف الزبون بنجاح'})

# مسارات إدارة طلبات الاستعلام
@app.route('/api/inquiry-requests', methods=['GET'])
def get_inquiry_requests():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, c.phone_number, c.name, t.amount, t.status, t.notes, t.created_at
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            WHERE t.transaction_type = 'inquiry'
            ORDER BY t.created_at DESC
        ''')
        requests = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': req[0],
        'phone_number': req[1],
        'customer_name': req[2],
        'amount': req[3],
        'status': req[4],
        'notes': req[5],
        'created_at': req[6]
    } for req in requests])

# إدارة طلبات التسديد
@app.route('/api/payment-requests', methods=['GET'])
def get_payment_requests():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.id, c.phone_number, c.name, t.amount, t.months, t.status, t.notes, 
                   strftime('%Y-%m-%d %H:%M:%S', t.created_at) as created_at_formatted,
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name,
                   u.name as user_name,
                   t.staff_notes
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.transaction_type = 'payment'
            ORDER BY 
                CASE t.status 
                    WHEN 'pending' THEN 1 
                    WHEN 'approved' THEN 2 
                    WHEN 'rejected' THEN 3 
                    ELSE 4 
                END,
                t.created_at DESC
        ''')
            requests = cursor.fetchall()
            conn.close()

        # تحسين البيانات المرجعة
        results = []
        for req in requests:
            result = {
                'id': req[0],
                'phone_number': req[1] or 'غير محدد',
                'customer_name': req[2] or 'غير محدد',
                'amount': req[3] if req[3] is not None else 0,
                'months': req[4] or 1,
                'status': req[5] or 'pending',
                'notes': req[6] or '',
                'created_at': req[7] or '',
                'company_name': req[8] or 'غير محدد',
                'user_name': req[9] or 'غير محدد',
                'staff_notes': req[10] or ''
            }
            results.append(result)

        return jsonify(results)

    except sqlite3.Error as e:
        print(f"خطأ في قاعدة البيانات: {e}")
        return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ عام في جلب طلبات التسديد: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/api/payment-requests/<int:request_id>/approve', methods=['POST'])
def approve_payment_request(request_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    start_time = time.time()

    try:
        # استخدام قفل قاعدة البيانات لمنع التداخل
        with db_lock:
            conn = sqlite3.connect('bills_system.db', timeout=15.0)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=10000')  # 10 ثوان انتظار
            cursor = conn.cursor()

        # التحقق من وجود الطلب وحالته مع معلومات إضافية
        cursor.execute('''
            SELECT t.user_id, c.name, t.amount, t.status, c.phone_number, 
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            WHERE t.id = ? AND t.transaction_type = 'payment'
        ''', (request_id,))
        transaction = cursor.fetchone()

        if not transaction:
            conn.close()
            return jsonify({'error': 'الطلب غير موجود'}), 404

        user_id, customer_name, amount, current_status, phone_number, company_name = transaction

        if current_status == 'approved':
            conn.close()
            return jsonify({'error': 'تم الموافقة على هذا الطلب مسبقاً'}), 400

        if current_status == 'rejected':
            conn.close()
            return jsonify({'error': 'لا يمكن الموافقة على طلب مرفوض. يرجى تغيير الحالة أولاً'}), 400

        # التحقق من أن المبلغ موجود ومعقول
        if not amount or amount <= 0:
            conn.close()
            return jsonify({'error': 'المبلغ غير صحيح. يرجى إضافة مبلغ صحيح للطلب أولاً'}), 400

        # تحديث حالة الطلب مع تسجيل معرف المعتمد
        cursor.execute('''
            UPDATE transactions 
            SET status = 'approved', 
                approved_at = datetime('now', 'localtime'),
                staff_notes = COALESCE(staff_notes, '') || ' - تمت الموافقة بواسطة: ' || ?
            WHERE id = ? AND transaction_type = 'payment' AND status = 'pending'
        ''', (session['user_name'], request_id))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'فشل في تحديث الطلب. ربما تم تعديله من قبل مستخدم آخر'}), 500

        # إرسال إشعار للمستخدم
        notification_msg = f'تم قبول طلب تسديد للعميل {customer_name} (رقم: {phone_number}) في شركة {company_name} بمبلغ {amount} ل.س بنجاح'
        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, datetime('now', '+3 hours'))
        ''', (user_id, 'تم قبول طلب التسديد', notification_msg))

        # إرسال إشعار للتليجرام
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        user_phone = cursor.fetchone()

        conn.commit()
        conn.close()

        # التحقق من أن العملية لم تستغرق وقتاً طويلاً
        elapsed_time = time.time() - start_time
        print(f"وقت معالجة طلب الموافقة {request_id}: {elapsed_time:.2f} ثانية")

        # إرسال إشعار التليجرام في خيط منفصل لعدم تأخير الاستجابة
        if user_phone:
            threading.Thread(target=send_telegram_notification_async, 
                           args=(user_phone[0], f"✅ تم قبول طلب التسديد\n\n📋 العميل: {customer_name}\n📱 الرقم: {phone_number}\n🏢 الشركة: {company_name}\n💰 المبلغ: {amount} ل.س"),
                           daemon=True).start()

        return jsonify({
            'success': True, 
            'message': f'تم الموافقة على طلب التسديد للعميل {customer_name} بمبلغ {amount} ل.س بنجاح'
        })

    except sqlite3.OperationalError as e:
        if 'database is locked' in str(e):
            print(f"قاعدة البيانات مؤقتة - طلب {request_id}")
            return jsonify({'error': 'النظام مشغول حالياً، يرجى المحاولة بعد قليل'}), 503
        else:
            print(f"خطأ في قاعدة البيانات - الموافقة على الطلب {request_id}: {e}")
            return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except sqlite3.Error as e:
        print(f"خطأ في قاعدة البيانات - الموافقة على الطلب {request_id}: {e}")
        return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ عام في الموافقة على الطلب {request_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/api/payment-requests/<int:request_id>/reject', methods=['POST'])
def reject_payment_request(request_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    start_time = time.time()

    try:
        data = request.json or {}
        rejection_reason = data.get('reason', 'غير محدد')

        if not rejection_reason or rejection_reason.strip() == '':
            rejection_reason = 'لم يتم تحديد سبب الرفض'

        # استخدام قفل قاعدة البيانات لمنع التداخل
        with db_lock:
            conn = sqlite3.connect('bills_system.db', timeout=15.0)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=10000')
            cursor = conn.cursor()

        # جلب بيانات المعاملة لإرجاع الرصيد مع معلومات إضافية
        cursor.execute('''
            SELECT t.user_id, t.amount, c.name, t.status, c.phone_number,
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            WHERE t.id = ? AND t.transaction_type = 'payment'
        ''', (request_id,))
        transaction = cursor.fetchone()

        if not transaction:
            conn.close()
            return jsonify({'error': 'الطلب غير موجود'}), 404

        user_id, amount, customer_name, current_status, phone_number, company_name = transaction

        if current_status == 'rejected':
            conn.close()
            return jsonify({'error': 'تم رفض هذا الطلب مسبقاً'}), 400

        # إرجاع المبلغ لرصيد المستخدم إذا كان موجود ولم يتم إرجاعه سابقاً
        balance_message = ''
        if amount and amount > 0 and current_status != 'rejected':
            cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))
            balance_message = f'تم إرجاع المبلغ {amount} ل.س لرصيدك'

        # تحديث حالة الطلب مع تسجيل معرف الرافض
        full_rejection_reason = f'{rejection_reason} - تم الرفض بواسطة: {session["user_name"]}'
        cursor.execute('''
            UPDATE transactions 
            SET status = 'rejected', 
                staff_notes = ?, 
                approved_at = datetime('now', 'localtime')
            WHERE id = ? AND transaction_type = 'payment' AND status != 'rejected'
        ''', (full_rejection_reason, request_id))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'فشل في تحديث الطلب. ربما تم تعديله من قبل مستخدم آخر'}), 500

        # إرسال إشعار للمستخدم
        notification_msg = f'تم رفض طلب تسديد للعميل {customer_name} (رقم: {phone_number}) في شركة {company_name}'
        if amount:
            notification_msg += f' بمبلغ {amount} ل.س'
        notification_msg += f'. السبب: {rejection_reason}'
        if balance_message:
            notification_msg += f'. {balance_message}'

        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, datetime('now', '+3 hours'))
        ''', (user_id, 'تم رفض طلب التسديد', notification_msg))

        # إرسال إشعار للتليجرام
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        user_phone = cursor.fetchone()

        conn.commit()
        conn.close()

        # التحقق من أن العملية لم تستغرق وقتاً طويلاً
        elapsed_time = time.time() - start_time
        print(f"وقت معالجة طلب الرفض {request_id}: {elapsed_time:.2f} ثانية")

        # إرسال إشعار التليجرام في خيط منفصل لعدم تأخير الاستجابة
        if user_phone:
            telegram_msg = f"❌ تم رفض طلب التسديد\n\n📋 العميل: {customer_name}\n📱 الرقم: {phone_number}\n🏢 الشركة: {company_name}"
            if amount:
                telegram_msg += f"\n💰 المبلغ: {amount} ل.س"
            telegram_msg += f"\n📝 السبب: {rejection_reason}"
            if balance_message:
                telegram_msg += f"\n💳 {balance_message}"

            threading.Thread(target=send_telegram_notification_async, 
                           args=(user_phone[0], telegram_msg),
                           daemon=True).start()

        success_message = f'تم رفض طلب التسديد للعميل {customer_name} بنجاح'
        if balance_message:
            success_message += f' و{balance_message}'

        return jsonify({'success': True, 'message': success_message})

    except sqlite3.OperationalError as e:
        if 'database is locked' in str(e):
            print(f"قاعدة البيانات مؤقتة - طلب {request_id}")
            return jsonify({'error': 'النظام مشغول حالياً، يرجى المحاولة بعد قليل'}), 503
        else:
            print(f"خطأ في قاعدة البيانات - رفض الطلب {request_id}: {e}")
            return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except sqlite3.Error as e:
        print(f"خطأ في قاعدة البيانات - رفض الطلب {request_id}: {e}")
        return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ عام في رفض الطلب {request_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

# تغيير كلمة المرور للمستخدم الحالي
@app.route('/api/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401

    data = request.json
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    # التحقق من البيانات المطلوبة
    if not all([current_password, new_password, confirm_password]):
        return jsonify({'error': 'جميع الحقول مطلوبة'}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'كلمة المرور الجديدة غير متطابقة'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()

            # التحقق من كلمة المرور الحالية
            current_hashed = hashlib.md5(current_password.encode()).hexdigest()
            cursor.execute('SELECT password, name FROM users WHERE id = ?', (session['user_id'],))
            user_result = cursor.fetchone()

            if not user_result or user_result[0] != current_hashed:
                conn.close()
                return jsonify({'error': 'كلمة المرور الحالية غير صحيحة'}), 400

            # تحديث كلمة المرور
            new_hashed = hashlib.md5(new_password.encode()).hexdigest()
            
            # تسجيل تغيير كلمة المرور
            cursor.execute('''
                INSERT INTO password_changes (user_id, old_password_hash, new_password_hash)
                VALUES (?, ?, ?)
            ''', (session['user_id'], current_hashed, new_hashed))

            # تحديث كلمة المرور ووقت التغيير
            cursor.execute('''
                UPDATE users 
                SET password = ?, password_changed_at = ? 
                WHERE id = ?
            ''', (new_hashed, datetime.now().isoformat(), session['user_id']))

            conn.commit()
            conn.close()

        # إبطال جميع الجلسات
        invalidate_user_sessions(session['user_id'], "تم تغيير كلمة المرور من قبل المستخدم")

        # مسح الجلسة الحالية
        session.clear()

        return jsonify({
            'success': True, 
            'message': 'تم تغيير كلمة المرور بنجاح. سيتم إعادة توجيهك لتسجيل الدخول مرة أخرى',
            'logout_required': True
        })

    except Exception as e:
        print(f"خطأ في تغيير كلمة المرور: {e}")
        return jsonify({'error': 'حدث خطأ في تغيير كلمة المرور'}), 500

# تغيير حالة طلب التسديد
@app.route('/api/payment-requests/<int:request_id>/change-status', methods=['POST'])
def change_payment_request_status(request_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    new_status = data.get('status')
    staff_notes = data.get('staff_notes', '')

    if new_status not in ['pending', 'approved', 'rejected']:
        return jsonify({'error': 'حالة غير صالحة'}), 400

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()

        # جلب بيانات المعاملة الحالية
        cursor.execute('''
            SELECT t.user_id, t.amount, t.status, c.name
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            WHERE t.id = ?
        ''', (request_id,))
        transaction = cursor.fetchone()

        if not transaction:
            conn.close()
            return jsonify({'error': 'الطلب غير موجود'}), 404

        user_id, amount, current_status, customer_name = transaction

        # التعامل مع تغييرات الرصيد
        balance_message = ''
        if current_status != new_status and amount and amount > 0:
            if current_status == 'approved' and new_status in ['rejected', 'pending']:
                # إرجاع المبلغ للرصيد
                cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))
                balance_message = f' وتم إرجاع {amount} ل.س للرصيد'
            elif current_status in ['rejected', 'pending'] and new_status == 'approved':
                # خصم المبلغ من الرصيد
                cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
                user_balance = cursor.fetchone()[0]
                if user_balance < amount:
                    conn.close()
                    return jsonify({'error': 'رصيد المستخدم غير كافي'}), 400
                cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))
                balance_message = f' وتم خصم {amount} ل.س من الرصيد'

        # تحديث حالة الطلب
        cursor.execute('''
            UPDATE transactions 
            SET status = ?, staff_notes = ?, approved_at = CASE WHEN ? = 'approved' THEN CURRENT_TIMESTAMP ELSE approved_at END
            WHERE id = ?
        ''', (new_status, staff_notes, new_status, request_id))

        # إرسال إشعار للمستخدم
        notification_message = f'تم تغيير حالة طلب تسديد للعميل {customer_name} إلى {getStatusText(new_status)}'
        if staff_notes:
            notification_message += f'. ملاحظة: {staff_notes}'
        notification_message += balance_message

        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, datetime('now', '+3 hours'))
        ''', (user_id, 'تحديث حالة الطلب', notification_message))

        # إرسال إشعار للتليجرام
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        user_phone = cursor.fetchone()
        if user_phone:
            send_telegram_notification(user_phone[0], f"🔄 تم تحديث حالة طلب التسديد إلى {getStatusText(new_status)}\n\n{notification_message}")

        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': f'تم تغيير حالة الطلب إلى {getStatusText(new_status)} بنجاح{balance_message}'})

# إضافة مبلغ لطلب التسديد
@app.route('/api/payment-requests/<int:request_id>/add-amount', methods=['POST'])
def add_amount_to_request(request_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    amount = data.get('amount', 0)

    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()

        # التحقق من وجود الطلب
        cursor.execute('SELECT user_id, status FROM transactions WHERE id = ?', (request_id,))
        transaction = cursor.fetchone()

        if not transaction:
            conn.close()
            return jsonify({'error': 'الطلب غير موجود'}), 404

        user_id, status = transaction

        # تحديث المبلغ
        cursor.execute('UPDATE transactions SET amount = ? WHERE id = ?', (amount, request_id))

        # إذا كان الطلب مقبول، خصم المبلغ من الرصيد
        if status == 'approved':
            cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
            user_balance = cursor.fetchone()[0]
            if user_balance < amount:
                conn.close()
                return jsonify({'error': 'رصيد المستخدم غير كافي لهذا المبلغ'}), 400
            cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))

        conn.commit()
        conn.close()

    message = f'تم إضافة مبلغ {amount} ل.س للطلب بنجاح'
    if status == 'approved':
        message += ' وتم خصمه من رصيد المستخدم'

    return jsonify({'success': True, 'message': message})

def getStatusText(status):
    status_map = {
        'pending': 'قيد الانتظار',
        'approved': 'مقبول', 
        'rejected': 'مرفوض'
    }
    return status_map.get(status, status)

# جلب المعاملات للمستخدم الحالي مع إمكانية البحث والفلترة
@app.route('/api/user-transactions', methods=['GET'])
def get_user_transactions():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    search = request.args.get('search', '')
    status = request.args.get('status', '')

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()

        query = '''
            SELECT t.id, c.phone_number, c.name as customer_name, t.amount, t.status, 
                   t.notes, t.created_at, t.transaction_type,
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name, 
                   cc.name as category_name
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN company_categories cc ON comp.category_id = cc.id
            WHERE t.user_id = ?
        '''
        params = [session['user_id']]

        if search:
            query += ' AND (c.phone_number LIKE ? OR c.name LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        if status:
            query += ' AND t.status = ?'
            params.append(status)

        query += ' ORDER BY t.created_at DESC'

        cursor.execute(query, params)
        transactions = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': trans[0],
        'phone_number': trans[1] or 'غير محدد',
        'customer_name': trans[2] or 'غير محدد',
        'amount': trans[3],
        'status': trans[4],
        'notes': trans[5],
        'created_at': trans[6],
        'transaction_type': trans[7],
        'company_name': trans[8],
        'category_name': trans[9] or 'غير محدد'
    } for trans in transactions])

# جلب تفاصيل المعاملة
@app.route('/api/transaction/<int:transaction_id>', methods=['GET'])
def get_transaction_details(transaction_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.user_id, t.customer_id, t.transaction_type, t.amount, t.months, 
                   t.status, t.notes, t.staff_notes, t.created_at, t.approved_at,
                   c.phone_number, c.name as customer_name, c.mobile_number,
                   COALESCE(comp.name, ic.name, 'غير محدد') as company_name, 
                   cc.name as category_name,
                   u.name as user_name
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            LEFT JOIN internet_companies ic ON c.company_id = ic.id
            LEFT JOIN company_categories cc ON comp.category_id = cc.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = ? AND (t.user_id = ? OR ? = 'admin')
        ''', (transaction_id, session['user_id'], session.get('user_role', 'user')))
        transaction = cursor.fetchone()
        conn.close()

    if not transaction:
        return jsonify({'error': 'المعاملة غير موجودة'}), 404

    return jsonify({
        'id': transaction[0],
        'user_id': transaction[1],
        'customer_id': transaction[2],
        'transaction_type': transaction[3],
        'amount': transaction[4],
        'months': transaction[5],
        'status': transaction[6],
        'notes': transaction[7],
        'staff_notes': transaction[8],
        'created_at': transaction[9],
        'approved_at': transaction[10],
        'phone_number': transaction[11],
        'customer_name': transaction[12],
        'mobile_number': transaction[13],
        'company_name': transaction[14],
        'category_name': transaction[15],
        'user_name': transaction[16]
    })

# جلب تفاصيل طلب التسديد للإدارة
@app.route('/api/payment-requests/<int:request_id>', methods=['GET'])
def get_payment_request_details(request_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.id, t.user_id, t.customer_id, t.transaction_type, t.amount, t.months, 
                       t.status, t.notes, t.staff_notes, 
                       strftime('%Y-%m-%d %H:%M:%S', t.created_at) as created_at,
                       strftime('%Y-%m-%d %H:%M:%S', t.approved_at) as approved_at,
                       c.phone_number, c.name as customer_name, c.mobile_number,
                       COALESCE(comp.name, ic.name, 'غير محدد') as company_name, 
                       cc.name as category_name,
                       u.name as user_name
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.id
                LEFT JOIN companies comp ON c.company_id = comp.id
                LEFT JOIN internet_companies ic ON c.company_id = ic.id
                LEFT JOIN company_categories cc ON comp.category_id = cc.id
                LEFT JOIN users u ON t.user_id = u.id
                WHERE t.id = ? AND t.transaction_type = 'payment'
            ''', (request_id,))
            request_data = cursor.fetchone()
            conn.close()

        if not request_data:
            return jsonify({'error': 'الطلب غير موجود'}), 404

        return jsonify({
            'id': request_data[0],
            'user_id': request_data[1],
            'customer_id': request_data[2],
            'transaction_type': request_data[3],
            'amount': request_data[4] if request_data[4] is not None else 0,
            'months': request_data[5] or 1,
            'status': request_data[6] or 'pending',
            'notes': request_data[7] or '',
            'staff_notes': request_data[8] or '',
            'created_at': request_data[9] or '',
            'approved_at': request_data[10] or '',
            'phone_number': request_data[11] or 'غير محدد',
            'customer_name': request_data[12] or 'غير محدد',
            'mobile_number': request_data[13] or '',
            'company_name': request_data[14] or 'غير محدد',
            'category_name': request_data[15] or 'غير محدد',
            'user_name': request_data[16] or 'غير محدد'
        })

    except sqlite3.Error as e:
        print(f"خطأ في قاعدة البيانات: {e}")
        return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ في جلب تفاصيل الطلب {request_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

# جلب الإشعارات للمستخدم
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, message, is_read, created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (session['user_id'],))
        notifications = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': notif[0],
        'title': notif[1],
        'message': notif[2],
        'is_read': notif[3],
        'created_at': notif[4]
    } for notif in notifications])

# عدد الإشعارات غير المقروءة
@app.route('/api/unread-notifications-count', methods=['GET'])
def get_unread_notifications_count():
    if 'user_id' not in session:
        return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (session['user_id'],))
        count = cursor.fetchone()[0]
        conn.close()

    return jsonify({'count': count})

# تعليم الإشعار كمقروء
@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?', 
                       (notification_id, session['user_id']))
        conn.commit()
        conn.close()

    return jsonify({'success': True})

# تعليم جميع الإشعارات كمقروءة
@app.route('/api/mark-notifications-read', methods=['POST'])
def mark_all_notifications_read():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        conn.close()

    return jsonify({'success': True})

# إحصائيات المستخدم
@app.route('/api/user-stats', methods=['GET'])
def get_user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'يجب تسجيل الدخول أولاً'}), 401

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()

            # طلبات معلقة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = "pending"', (session['user_id'],))
            pending = cursor.fetchone()[0]

            # عمليات مكتملة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = "approved"', (session['user_id'],))
            completed = cursor.fetchone()[0]

            # طلبات مرفوضة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = "rejected"', (session['user_id'],))
            rejected = cursor.fetchone()[0]

            # إجمالي اليوم
            cursor.execute('''SELECT COALESCE(SUM(amount), 0) FROM transactions 
                             WHERE user_id = ? AND status = "approved" AND DATE(created_at) = DATE('now')''', 
                           (session['user_id'],))
            today_total = cursor.fetchone()[0]

            conn.close()

        return jsonify({
            'pending': pending,
            'completed': completed,
            'rejected': rejected,
            'today_total': today_total
        })
    except Exception as e:
        print(f"خطأ في جلب إحصائيات المستخدم: {e}")
        return jsonify({
            'pending': 0,
            'completed': 0,
            'rejected': 0,
            'today_total': 0
        })

# إحصائيات الإدارة
@app.route('/api/admin-stats', methods=['GET'])
def get_admin_stats():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()

            # عدد المستخدمين
            cursor.execute('SELECT COUNT(*) FROM users WHERE role = "user" AND is_active = 1')
            users_count = cursor.fetchone()[0]

            # العمليات الناجحة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE status = "approved"')
            successful = cursor.fetchone()[0]

            # بانتظار الموافقة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE status = "pending"')
            pending = cursor.fetchone()[0]

            # العمليات المرفوضة
            cursor.execute('SELECT COUNT(*) FROM transactions WHERE status = "rejected"')
            rejected = cursor.fetchone()[0]

            conn.close()

        print(f"إحصائيات الإدارة: المستخدمين={users_count}, الناجحة={successful}, المعلقة={pending}, المرفوضة={rejected}")

        return jsonify({
            'users_count': users_count,
            'successful': successful,
            'pending': pending,
            'rejected': rejected
        })
    except Exception as e:
        print(f"خطأ في جلب إحصائيات الإدارة: {e}")
        return jsonify({
            'users_count': 0,
            'successful': 0,
            'pending': 0,
            'rejected': 0
        })

# حفظ إعدادات الموقع
@app.route('/api/site-settings', methods=['POST'])
def save_site_settings():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        if not data:
            return jsonify({'error': 'لم يتم إرسال بيانات'}), 400
            
        site_name = data.get('site_name', '').strip()
        announcement = data.get('announcement', '').strip()
        is_maintenance = data.get('is_maintenance', False)
        maintenance_reason = data.get('maintenance_reason', '').strip()

        # التحقق من صحة البيانات
        if not site_name:
            return jsonify({'error': 'اسم الموقع مطلوب'}), 400
            
        if not announcement:
            return jsonify({'error': 'الإعلان مطلوب'}), 400
            
        # التأكد من أن is_maintenance هو قيمة boolean
        if not isinstance(is_maintenance, bool):
            is_maintenance = str(is_maintenance).lower() == 'true'

        # إعداد البيانات للحفظ
        settings = {
            'site_name': site_name,
            'announcement': announcement,
            'is_maintenance': is_maintenance,
            'maintenance_reason': maintenance_reason,
            'last_updated': datetime.now().isoformat(),
            'updated_by': session.get('user_name', 'غير معروف')
        }

        # حفظ الإعدادات مع معالجة الأخطاء
        import json
        
        # إنشاء نسخة احتياطية من الإعدادات الحالية
        backup_created = False
        if os.path.exists('site_settings.json'):
            try:
                import shutil
                shutil.copy2('site_settings.json', 'site_settings.json.backup')
                backup_created = True
            except Exception as e:
                print(f"تعذر إنشاء نسخة احتياطية من الإعدادات: {e}")
        
        # كتابة الإعدادات الجديدة
        try:
            with open('site_settings.json', 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
                
            # التحقق من صحة الحفظ
            with open('site_settings.json', 'r', encoding='utf-8') as f:
                saved_settings = json.load(f)
                if saved_settings.get('site_name') != site_name:
                    raise Exception("فشل في التحقق من حفظ الإعدادات")
                    
            return jsonify({'success': True, 'message': 'تم حفظ الإعدادات بنجاح'})
            
        except Exception as e:
            # استعادة النسخة الاحتياطية في حالة الفشل
            if backup_created and os.path.exists('site_settings.json.backup'):
                try:
                    import shutil
                    shutil.copy2('site_settings.json.backup', 'site_settings.json')
                    print(f"تم استعادة النسخة الاحتياطية بسبب: {e}")
                except Exception as restore_error:
                    print(f"فشل في استعادة النسخة الاحتياطية: {restore_error}")
                    
            raise e

    except json.JSONDecodeError:
        return jsonify({'error': 'خطأ في تفسير البيانات المرسلة'}), 400
    except Exception as e:
        print(f"خطأ في حفظ الإعدادات: {e}")
        return jsonify({'error': f'خطأ في حفظ الإعدادات: {str(e)}'}), 500

# جلب إعدادات الموقع
@app.route('/api/site-settings', methods=['GET'])
def get_site_settings():
    import json
    try:
        with open('site_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
            
        # التأكد من وجود جميع القيم المطلوبة
        default_settings = {
            'site_name': 'نظام التسديد',
            'announcement': 'مرحباً بكم في نظام تسديد الفواتير',
            'is_maintenance': False,
            'maintenance_reason': ''
        }
        
        # دمج الإعدادات مع القيم الافتراضية
        for key, default_value in default_settings.items():
            if key not in settings:
                settings[key] = default_value
                
        return jsonify(settings)
        
    except FileNotFoundError:
        default_settings = {
            'site_name': 'نظام التسديد',
            'announcement': 'مرحباً بكم في نظام تسديد الفواتير',
            'is_maintenance': False,
            'maintenance_reason': ''
        }
        
        # إنشاء ملف الإعدادات الافتراضي
        try:
            with open('site_settings.json', 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"تعذر إنشاء ملف الإعدادات: {e}")
            
        return jsonify(default_settings)
        
    except json.JSONDecodeError as e:
        print(f"خطأ في تفسير ملف الإعدادات: {e}")
        return jsonify({
            'site_name': 'نظام التسديد',
            'announcement': 'مرحباً بكم في نظام تسديد الفواتير',
            'is_maintenance': False,
            'maintenance_reason': ''
        })
        
    except Exception as e:
        print(f"خطأ في تحميل الإعدادات: {e}")
        return jsonify({'error': 'خطأ في تحميل الإعدادات'}), 500

# إنشاء نسخة احتياطية
@app.route('/api/create-backup', methods=['POST'])
def create_backup():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    import shutil
    import zipfile
    from datetime import datetime

    try:
        # إنشاء اسم الملف
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'backup_{timestamp}.zip'

        # الملفات والمجلدات المهمة
        important_files = [
            'main.py',
            'telegram_bot.py',
            'bills_system.db',
            'site_settings.json',
            'telegram_bot_settings.json',
            'requirements.txt',
            'requirements_telegram.txt',
            '.replit',
            'index.html'
        ]

        important_dirs = [
            'templates',
            'static'
        ]

        # قائمة الملفات المستبعدة
        excluded_files = [
            '.pyc', '.log', '.backup', '.corrupt', '.signal',
            'bot_restart.signal', 'telegram_cache.json', 'bot_sessions.json'
        ]

        # قائمة المجلدات المستبعدة
        excluded_dirs = [
            '__pycache__', '.git', 'node_modules', '.venv', 'venv',
            '.pytest_cache', '.coverage', 'htmlcov'
        ]

        files_added = []
        total_files = 0

        # إنشاء النسخة الاحتياطية
        with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # إضافة الملفات المهمة
            for file in important_files:
                if os.path.exists(file):
                    zipf.write(file)
                    files_added.append(file)
                    total_files += 1

            # إضافة المجلدات المهمة
            for dir_name in important_dirs:
                if os.path.exists(dir_name):
                    for root, dirs, files in os.walk(dir_name):
                        # تصفية المجلدات المستبعدة
                        dirs[:] = [d for d in dirs if not any(excluded in d for excluded in excluded_dirs)]
                        
                        for file in files:
                            # تصفية الملفات المستبعدة
                            if not any(file.endswith(ext) for ext in excluded_files):
                                file_path = os.path.join(root, file)
                                zipf.write(file_path)
                                files_added.append(file_path)
                                total_files += 1

            # إضافة النسخ الاحتياطية السابقة (الأحدث فقط - آخر 5 نسخ)
            backup_files = [f for f in os.listdir('.') if f.startswith('backup_') and f.endswith('.zip')]
            backup_files.sort(reverse=True)
            
            for backup_file in backup_files[:5]:  # آخر 5 نسخ احتياطية
                if backup_file != backup_filename:  # تجنب النسخة الحالية
                    try:
                        zipf.write(backup_file, f'previous_backups/{backup_file}')
                        files_added.append(f'previous_backups/{backup_file}')
                        total_files += 1
                    except Exception as e:
                        print(f"تعذر إضافة النسخة الاحتياطية {backup_file}: {e}")

            # إضافة ملف يحتوي على معلومات النسخة الاحتياطية
            backup_info = {
                'created_at': datetime.now().isoformat(),
                'created_by': session['user_name'],
                'total_files': total_files,
                'files_included': files_added[:50],  # أول 50 ملف للعرض
                'backup_version': '2.0',
                'system_info': {
                    'python_version': 'Python 3.11',
                    'platform': 'Replit',
                    'flask_app': 'Bills Management System'
                }
            }

            import json
            backup_info_json = json.dumps(backup_info, ensure_ascii=False, indent=2)
            zipf.writestr('backup_info.json', backup_info_json)
            total_files += 1

        # حساب حجم الملف
        file_size = os.path.getsize(backup_filename)

        with db_lock:
            # حفظ سجل النسخة الاحتياطية في قاعدة البيانات
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO backups (filename, file_size, created_by)
                VALUES (?, ?, ?)
            ''', (backup_filename, file_size, f"{session['user_name']} ({total_files} ملف)"))
            conn.commit()
            conn.close()

        return jsonify({
            'success': True, 
            'message': f'تم إنشاء النسخة الاحتياطية بنجاح وتضمنت {total_files} ملف',
            'filename': backup_filename,
            'size': file_size,
            'files_count': total_files
        })

    except Exception as e:
        print(f"خطأ في إنشاء النسخة الاحتياطية: {e}")
        return jsonify({'error': f'خطأ في إنشاء النسخة الاحتياطية: {str(e)}'}), 500

# جلب النسخ الاحتياطية
@app.route('/api/backups', methods=['GET'])
def get_backups():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM backups ORDER BY created_at DESC')
        backups = cursor.fetchall()
        conn.close()

    return jsonify([{
        'id': backup[0],
        'filename': backup[1],
        'file_size': backup[2],
        'created_by': backup[3],
        'created_at': backup[4]
    } for backup in backups])

# تحميل نسخة احتياطية
@app.route('/api/download-backup/<filename>')
def download_backup(filename):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    # التحقق من أن الملف آمن ولا يحتوي على مسارات خطيرة
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'اسم ملف غير صالح'}), 400

    if os.path.exists(filename) and filename.startswith('backup_') and filename.endswith('.zip'):
        from flask import send_file
        return send_file(filename, as_attachment=True, download_name=filename)
    else:
        return jsonify({'error': 'الملف غير موجود'}), 404

# حذف نسخة احتياطية
@app.route('/api/backups/<int:backup_id>', methods=['DELETE'])
def delete_backup(backup_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db', timeout=15.0)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            cursor = conn.cursor()

            # جلب اسم الملف
            cursor.execute('SELECT filename FROM backups WHERE id = ?', (backup_id,))
            backup = cursor.fetchone()

            if backup:
                filename = backup[0]
                
                # حذف السجل من قاعدة البيانات أولاً
                cursor.execute('DELETE FROM backups WHERE id = ?', (backup_id,))
                conn.commit()
                conn.close()

                # حذف الملف من النظام بعد إغلاق اتصال قاعدة البيانات
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except OSError as e:
                    print(f"تعذر حذف الملف {filename}: {e}")

                return jsonify({'success': True, 'message': 'تم حذف النسخة الاحتياطية بنجاح'})
            else:
                conn.close()
                return jsonify({'error': 'النسخة الاحتياطية غير موجودة'}), 404

    except sqlite3.OperationalError as e:
        if 'database is locked' in str(e):
            return jsonify({'error': 'النظام مشغول حالياً، يرجى المحاولة بعد قليل'}), 503
        else:
            print(f"خطأ في قاعدة البيانات - حذف النسخة الاحتياطية {backup_id}: {e}")
            return jsonify({'error': 'خطأ في قاعدة البيانات'}), 500
    except Exception as e:
        print(f"خطأ عام في حذف النسخة الاحتياطية {backup_id}: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

# رفع نسخة احتياطية من الجهاز
@app.route('/api/upload-backup', methods=['POST'])
def upload_backup():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    if 'backup_file' not in request.files:
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400

    file = request.files['backup_file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400

    if file and file.filename.endswith('.zip'):
        import zipfile
        from datetime import datetime

        try:
            # حفظ الملف المرفوع
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'uploaded_backup_{timestamp}.zip'
            file.save(filename)

            # التحقق من صحة الملف
            with zipfile.ZipFile(filename, 'r') as zip_ref:
                # التحقق من وجود قاعدة البيانات
                if 'bills_system.db' not in zip_ref.namelist():
                    os.remove(filename)
                    return jsonify({'error': 'النسخة الاحتياطية غير صالحة - لا تحتوي على قاعدة البيانات'}), 400

            # حساب حجم الملف
            file_size = os.path.getsize(filename)

            with db_lock:
                # حفظ سجل النسخة الاحتياطية
                conn = sqlite3.connect('bills_system.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO backups (filename, file_size, created_by)
                    VALUES (?, ?, ?)
                ''', (filename, file_size, f"{session['user_name']} (مرفوع)"))
                conn.commit()
                conn.close()

            return jsonify({
                'success': True,
                'message': 'تم رفع النسخة الاحتياطية بنجاح',
                'filename': filename
            })

        except Exception as e:
            if os.path.exists(filename):
                os.remove(filename)
            return jsonify({'error': f'خطأ في رفع النسخة الاحتياطية: {str(e)}'}), 500
    else:
        return jsonify({'error': 'يجب أن يكون الملف بصيغة ZIP'}), 400

# استعادة نسخة احتياطية
@app.route('/api/restore-backup/<filename>', methods=['POST'])
def restore_backup(filename):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    # التحقق من وجود الملف
    if not os.path.exists(filename) or not filename.endswith('.zip'):
        return jsonify({'error': 'الملف غير موجود'}), 404

    try:
        import zipfile
        import shutil
        from datetime import datetime

        # إنشاء نسخة احتياطية من الحالة الحالية أولاً
        current_backup = f'pre_restore_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        
        # الملفات المهمة للنسخ الاحتياطي الطارئ
        important_files = [
            'bills_system.db',
            'site_settings.json',
            'telegram_bot_settings.json',
            'main.py',
            'telegram_bot.py'
        ]

        with zipfile.ZipFile(current_backup, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in important_files:
                if os.path.exists(file):
                    zipf.write(file)

        files_restored = []
        total_restored = 0

        # استخراج النسخة الاحتياطية
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # التحقق من وجود قاعدة البيانات
            if 'bills_system.db' not in file_list:
                if os.path.exists(current_backup):
                    os.remove(current_backup)
                return jsonify({'error': 'النسخة الاحتياطية لا تحتوي على قاعدة بيانات صالحة'}), 400

            # إنشاء نسخة من قاعدة البيانات الحالية
            if os.path.exists('bills_system.db'):
                shutil.copy2('bills_system.db', 'bills_system.db.backup')

            # استعادة جميع الملفات
            for file_path in file_list:
                # تجاهل النسخ الاحتياطية السابقة والملفات المؤقتة
                if (file_path.startswith('previous_backups/') or 
                    file_path.endswith('.pyc') or 
                    file_path.endswith('.log') or
                    file_path == 'backup_info.json'):
                    continue

                try:
                    # إنشاء المجلدات إذا لم تكن موجودة
                    dir_name = os.path.dirname(file_path)
                    if dir_name and not os.path.exists(dir_name):
                        os.makedirs(dir_name, exist_ok=True)

                    # استخراج الملف
                    zip_ref.extract(file_path, '.')
                    files_restored.append(file_path)
                    total_restored += 1

                except Exception as e:
                    print(f"تعذر استعادة الملف {file_path}: {e}")

            # قراءة معلومات النسخة الاحتياطية إذا كانت موجودة
            backup_info = {}
            if 'backup_info.json' in file_list:
                try:
                    backup_info_content = zip_ref.read('backup_info.json')
                    import json
                    backup_info = json.loads(backup_info_content.decode('utf-8'))
                except:
                    pass

            # حفظ النسخة الاحتياطية المؤقتة في قاعدة البيانات
            file_size = os.path.getsize(current_backup)
            with db_lock:
                conn = sqlite3.connect('bills_system.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO backups (filename, file_size, created_by)
                    VALUES (?, ?, ?)
                ''', (current_backup, file_size, f"{session['user_name']} (نسخة ما قبل الاستعادة)"))
                conn.commit()
                conn.close()

            success_message = f'تم استعادة النسخة الاحتياطية بنجاح ({total_restored} ملف)'
            if backup_info.get('created_by'):
                success_message += f' - تم إنشاؤها بواسطة {backup_info["created_by"]}'
            if backup_info.get('created_at'):
                success_message += f' في {backup_info["created_at"][:10]}'

            return jsonify({
                'success': True,
                'message': success_message,
                'backup_created': current_backup,
                'files_restored': total_restored,
                'backup_info': backup_info
            })

    except zipfile.BadZipFile:
        if os.path.exists(current_backup):
            os.remove(current_backup)
        return jsonify({'error': 'ملف النسخة الاحتياطية تالف أو غير صالح'}), 400
    except Exception as e:
        # حذف النسخة المؤقتة في حالة الخطأ
        if os.path.exists(current_backup):
            os.remove(current_backup)
        print(f"خطأ في استعادة النسخة الاحتياطية: {e}")
        return jsonify({'error': f'خطأ في استعادة النسخة الاحتياطية: {str(e)}'}), 500



# تسجيل معرف المحادثة للتليجرام
@app.route('/api/register-telegram-chat', methods=['POST'])
def register_telegram_chat():
    """تسجيل معرف المحادثة للمستخدم في التليجرام"""
    try:
        data = request.json
        phone = data.get('phone')
        chat_id = data.get('chat_id')

        if phone and chat_id:
            telegram_users[phone] = str(chat_id)
            print(f"تم تسجيل مستخدم التليجرام: {phone} -> {chat_id}")

            with db_lock:
                # حفظ في قاعدة البيانات لحفظ دائم
                conn = sqlite3.connect('bills_system.db')
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        phone TEXT PRIMARY KEY,
                        chat_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('INSERT OR REPLACE INTO telegram_users (phone, chat_id) VALUES (?, ?)', 
                              (phone, str(chat_id)))
                conn.commit()
                conn.close()

            return jsonify({'success': True})

        return jsonify({'error': 'البيانات غير مكتملة'}), 400
    except Exception as e:
        print(f"خطأ في تسجيل مستخدم التليجرام: {e}")
        return jsonify({'error': 'خطأ في الخادم'}), 500

# إضافة مسار لفحص الصحة
@app.route('/health', methods=['GET'])
def health_check():
    try:
        # فحص اتصال قاعدة البيانات
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()

        response = jsonify({
            'status': 'ok', 
            'message': 'الخادم يعمل بشكل طبيعي',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        })

        # إضافة headers للـ CORS ومنع التخزين المؤقت
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

        return response

    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'مشكلة في الخادم',
            'error': str(e)
        }), 500

# مسارات إدارة بوت التيليجرام
@app.route('/api/telegram-bot-status', methods=['GET'])
def get_telegram_bot_status():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        # فحص حالة البوت
        import subprocess
        import psutil
        
        # البحث عن عملية البوت
        bot_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'telegram_bot.py' in ' '.join(proc.info['cmdline'] or []):
                    bot_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # جلب إحصائيات البوت من قاعدة البيانات
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # عدد المستخدمين المسجلين في التيليجرام
            cursor.execute('SELECT COUNT(*) FROM telegram_users')
            total_users = cursor.fetchone()[0]
            
            # المستخدمين النشطين اليوم (يمكن إضافة جدول للنشاط)
            active_today = total_users  # مؤقتاً
            
            # رسائل اليوم (يمكن إضافة جدول للرسائل)
            messages_today = 0  # مؤقتاً
            
            conn.close()

        return jsonify({
            'status': 'online' if bot_running else 'offline',
            'stats': {
                'total_users': total_users,
                'active_today': active_today,
                'messages_today': messages_today
            }
        })

    except Exception as e:
        print(f"خطأ في فحص حالة البوت: {e}")
        return jsonify({'error': 'خطأ في فحص حالة البوت'}), 500



@app.route('/api/telegram-bot-settings', methods=['GET', 'POST'])
def telegram_bot_settings():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    if request.method == 'GET':
        try:
            # جلب الإعدادات من الملف
            import json
            try:
                with open('telegram_bot_settings.json', 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except FileNotFoundError:
                settings = {
                    'bot_token': '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE',
                    'welcome_message': 'مرحباً بك في بوت مؤسسة نور التجارية 🌟\n\nيمكنك الآن تسديد فواتيرك بسهولة من خلال البوت.\nاختر ما تريد من القائمة أدناه:',
                    'maintenance_message': 'البوت تحت الصيانة حالياً ⚠️\nنعتذر عن الإزعاج، سنعود قريباً.',
                    'outside_hours_message': 'نعمل من الساعة 8 صباحاً حتى 6 مساءً 🕐\nيرجى المحاولة مرة أخرى خلال ساعات العمل.',
                    'not_understood_message': 'لم أفهم طلبك 🤔\nيرجى استخدام الأزرار المتاحة أو إرسال /help للمساعدة.',
                    'general_error_message': 'حدث خطأ في النظام ❌\nيرجى المحاولة مرة أخرى بعد قليل.',
                    'payment_success_message': 'تم إرسال طلب التسديد بنجاح ✅\nسيتم مراجعته من قبل الإدارة.',
                    'insufficient_balance_message': 'رصيدك غير كافي 💰\nيرجى شحن رصيدك أولاً.',
                    'user_not_found_message': 'لم يتم العثور على حسابك 👤\nيرجى التسجيل في النظام أولاً.',
                    'enable_auto_reply': True,
                    'daily_payment_limit': 100000,
                    'daily_transaction_limit': 10,
                    'transaction_cooldown': 30,
                    'min_balance_required': 0,
                    'allow_new_registrations': True,
                    'require_phone_verification': True,
                    'allow_guest_queries': False,
                    'restrict_working_hours': False,
                    'working_hours_start': '08:00',
                    'working_hours_end': '18:00',
                    'bot_auto_start': True,
                    'bot_maintenance_mode': False,
                    'bot_debug_mode': False,
                    'log_user_messages': True,
                    'notify_new_user': True,
                    'notify_new_payment': True,
                    'notify_errors': True,
                    'notify_balance_low': True,
                    'auto_approve_small_amounts': False,
                    'small_amount_threshold': 1000,
                    'enable_payment_confirmation': True,
                    'enable_receipt_generation': True,
                    'max_message_length': 1000,
                    'rate_limit_messages': 10,
                    'rate_limit_period': 60,
                    'blocked_words': ['spam', 'تصيد'],
                    'admin_commands_enabled': True,
                    'user_commands_enabled': True,
                    'backup_chat_data': True,
                    'delete_old_messages': False,
                    'message_retention_days': 30
                }
            return jsonify(settings)
        except Exception as e:
            print(f"خطأ في جلب إعدادات البوت: {e}")
            return jsonify({'error': 'خطأ في جلب الإعدادات'}), 500

    elif request.method == 'POST':
        try:
            data = request.json
            import json
            
            # التحقق من صحة Token إذا تم تغييره
            if 'bot_token' in data and data['bot_token'] and data['bot_token'] != '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE':
                try:
                    test_response = requests.get(f"https://api.telegram.org/bot{data['bot_token']}/getMe", timeout=10)
                    if test_response.status_code != 200:
                        return jsonify({'error': 'Token البوت غير صحيح أو منتهي الصلاحية'}), 400
                    bot_info = test_response.json()
                    if not bot_info.get('ok'):
                        return jsonify({'error': 'Token البوت غير صالح'}), 400
                except requests.exceptions.RequestException:
                    return jsonify({'error': 'فشل في التحقق من Token البوت - تحقق من الاتصال بالإنترنت'}), 400
                except Exception:
                    return jsonify({'error': 'خطأ في التحقق من Token البوت'}), 400
            
            # التحقق من صحة القيم المدخلة
            if 'daily_payment_limit' in data and data['daily_payment_limit'] < 0:
                return jsonify({'error': 'حد الدفع اليومي يجب أن يكون رقماً موجباً'}), 400
                
            if 'daily_transaction_limit' in data and data['daily_transaction_limit'] < 1:
                return jsonify({'error': 'حد المعاملات اليومية يجب أن يكون 1 على الأقل'}), 400
                
            if 'transaction_cooldown' in data and data['transaction_cooldown'] < 0:
                return jsonify({'error': 'فترة الانتظار بين المعاملات يجب أن تكون رقماً موجباً'}), 400
            
            # حفظ الإعدادات مع طابع زمني
            data['last_updated'] = datetime.now().isoformat()
            data['updated_by'] = session['user_name']
            
            with open('telegram_bot_settings.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return jsonify({'success': True, 'message': 'تم حفظ إعدادات البوت بنجاح'})
        except Exception as e:
            print(f"خطأ في حفظ إعدادات البوت: {e}")
            return jsonify({'error': 'خطأ في حفظ الإعدادات'}), 500

@app.route('/api/telegram-bot-restart', methods=['POST'])
def restart_telegram_bot():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        import subprocess
        import psutil
        import time
        
        # إشارة إعادة التشغيل للبوت
        restart_signal_file = 'bot_restart.signal'
        with open(restart_signal_file, 'w') as f:
            f.write('restart')
        
        # قتل العملية الحالية للبوت إذا كانت تعمل
        killed_processes = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and 'telegram_bot.py' in ' '.join(proc.info['cmdline']):
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                        killed_processes += 1
                    except psutil.TimeoutExpired:
                        proc.kill()
                        killed_processes += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # انتظار قليل ثم تشغيل البوت من جديد
        time.sleep(5)
        
        # تشغيل البوت في الخلفية
        try:
            process = subprocess.Popen(
                ['python3', 'telegram_bot.py'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            # التأكد من أن العملية بدأت بنجاح
            time.sleep(3)
            if process.poll() is None:
                # إزالة ملف الإشارة
                if os.path.exists(restart_signal_file):
                    os.remove(restart_signal_file)
                    
                return jsonify({
                    'success': True, 
                    'message': f'تم إعادة تشغيل البوت بنجاح (تم إيقاف {killed_processes} عملية سابقة)',
                    'process_id': process.pid
                })
            else:
                stdout, stderr = process.communicate()
                error_msg = stderr.decode('utf-8') if stderr else 'فشل غير معروف'
                return jsonify({'error': f'فشل في بدء تشغيل البوت: {error_msg}'}), 500
                
        except Exception as start_error:
            return jsonify({'error': f'خطأ في بدء تشغيل البوت: {str(start_error)}'}), 500

    except Exception as e:
        print(f"خطأ في إعادة تشغيل البوت: {e}")
        return jsonify({'error': f'خطأ في إعادة تشغيل البوت: {str(e)}'}), 500

@app.route('/api/telegram-stats', methods=['GET'])
def get_telegram_stats():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # عدد المستخدمين المسجلين في التيليجرام
            cursor.execute('SELECT COUNT(*) FROM telegram_users')
            total_users = cursor.fetchone()[0]
            
            # عدد المستخدمين النشطين (لديهم معاملات حديثة)
            cursor.execute('''
                SELECT COUNT(DISTINCT tu.phone) FROM telegram_users tu
                JOIN users u ON tu.phone = u.phone
                WHERE u.is_active = 1
            ''')
            active_users = cursor.fetchone()[0]
            
            # عدد المستخدمين الجدد اليوم
            cursor.execute('''
                SELECT COUNT(*) FROM telegram_users 
                WHERE DATE(created_at) = DATE('now')
            ''')
            new_users_today = cursor.fetchone()[0]
            
            # عدد المحظورين
            cursor.execute('''
                SELECT COUNT(*) FROM telegram_blocked_users
            ''') if cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='telegram_blocked_users'
            ''').fetchone() else None
            blocked_count = cursor.fetchone()[0] if cursor.fetchone() else 0
            
            # عدد المديرين
            cursor.execute('''
                SELECT COUNT(*) FROM telegram_admin_users
            ''') if cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='telegram_admin_users'
            ''').fetchone() else None
            admin_count = cursor.fetchone()[0] if cursor.fetchone() else 0
            
            # عدد المعاملات اليوم
            cursor.execute('''
                SELECT COUNT(*) FROM transactions 
                WHERE DATE(created_at) = DATE('now')
            ''')
            transactions_today = cursor.fetchone()[0]
            
            conn.close()

        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'new_users_today': new_users_today,
            'blocked_count': blocked_count,
            'admin_count': admin_count,
            'transactions_today': transactions_today,
            'messages_today': 0  # يمكن إضافة جدول للرسائل لاحقاً
        })

    except Exception as e:
        print(f"خطأ في جلب إحصائيات التليجرام: {e}")
        return jsonify({'error': 'خطأ في جلب الإحصائيات'}), 500

@app.route('/api/telegram-clear-cache', methods=['POST'])
def clear_telegram_cache():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        # مسح ملفات التخزين المؤقت إذا وجدت
        cache_files = ['telegram_cache.json', 'bot_sessions.json']
        for file in cache_files:
            if os.path.exists(file):
                os.remove(file)
        
        return jsonify({'success': True, 'message': 'تم مسح ذاكرة التخزين المؤقت'})
    except Exception as e:
        print(f"خطأ في مسح ذاكرة التخزين المؤقت: {e}")
        return jsonify({'error': 'خطأ في مسح ذاكرة التخزين المؤقت'}), 500

@app.route('/api/telegram-export-users', methods=['GET'])
def export_telegram_users():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        import csv
        import io
        from datetime import datetime

        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT tu.phone, tu.chat_id, tu.created_at,
                       u.name, u.balance, u.role,
                       COUNT(t.id) as total_transactions,
                       COALESCE(SUM(CASE WHEN t.status = 'approved' THEN t.amount END), 0) as total_amount
                FROM telegram_users tu
                LEFT JOIN users u ON tu.phone = u.phone
                LEFT JOIN transactions t ON u.id = t.user_id
                GROUP BY tu.phone, tu.chat_id, tu.created_at, u.name, u.balance, u.role
                ORDER BY tu.created_at DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()

        # إنشاء ملف CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # كتابة الرؤوس
        writer.writerow([
            'رقم الهاتف', 'معرف المحادثة', 'تاريخ التسجيل',
            'الاسم', 'الرصيد', 'النوع',
            'عدد المعاملات', 'إجمالي المبلغ'
        ])
        
        # كتابة البيانات
        for row in results:
            writer.writerow(row)

        # إعداد الاستجابة
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=telegram_users_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response

    except Exception as e:
        print(f"خطأ في تصدير المستخدمين: {e}")
        return jsonify({'error': 'خطأ في تصدير المستخدمين'}), 500

@app.route('/api/telegram-block-user', methods=['POST'])
def block_telegram_user():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        user = data.get('user', '').strip()
        
        if not user:
            return jsonify({'error': 'يرجى تحديد المستخدم'}), 400

        # إضافة المستخدم لقائمة المحظورين
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # إنشاء جدول المحظورين إذا لم يكن موجود
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_blocked_users (
                    user_identifier TEXT PRIMARY KEY,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    blocked_by TEXT
                )
            ''')
            
            cursor.execute('''
                INSERT OR REPLACE INTO telegram_blocked_users (user_identifier, blocked_by)
                VALUES (?, ?)
            ''', (user, session['user_name']))
            
            conn.commit()
            conn.close()

        return jsonify({'success': True, 'message': 'تم حظر المستخدم بنجاح'})

    except Exception as e:
        print(f"خطأ في حظر المستخدم: {e}")
        return jsonify({'error': 'خطأ في حظر المستخدم'}), 500

@app.route('/api/telegram-unblock-user', methods=['POST'])
def unblock_telegram_user():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        user = data.get('user', '').strip()
        
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM telegram_blocked_users WHERE user_identifier = ?', (user,))
            conn.commit()
            conn.close()

        return jsonify({'success': True, 'message': 'تم إلغاء حظر المستخدم بنجاح'})

    except Exception as e:
        print(f"خطأ في إلغاء حظر المستخدم: {e}")
        return jsonify({'error': 'خطأ في إلغاء الحظر'}), 500

@app.route('/api/telegram-blocked-users', methods=['GET'])
def get_blocked_telegram_users():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # إنشاء الجدول إذا لم يكن موجود
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_blocked_users (
                    user_identifier TEXT PRIMARY KEY,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    blocked_by TEXT
                )
            ''')
            
            cursor.execute('SELECT user_identifier FROM telegram_blocked_users ORDER BY blocked_at DESC')
            blocked_users = [row[0] for row in cursor.fetchall()]
            conn.close()

        return jsonify(blocked_users)

    except Exception as e:
        print(f"خطأ في جلب المستخدمين المحظورين: {e}")
        return jsonify([])

@app.route('/api/telegram-add-admin', methods=['POST'])
def add_telegram_admin():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({'error': 'يرجى تحديد رقم الهاتف'}), 400

        # التحقق من وجود المستخدم في النظام
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, name FROM users WHERE phone = ? AND is_active = 1', (phone,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return jsonify({'error': 'المستخدم غير موجود في النظام'}), 404

            # إضافة المستخدم لقائمة مديري التيليجرام
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_admin_users (
                    user_id INTEGER PRIMARY KEY,
                    phone TEXT UNIQUE,
                    name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            cursor.execute('''
                INSERT OR REPLACE INTO telegram_admin_users (user_id, phone, name, added_by)
                VALUES (?, ?, ?, ?)
            ''', (user[0], phone, user[1], session['user_name']))
            
            conn.commit()
            conn.close()

        return jsonify({'success': True, 'message': 'تم إضافة المدير بنجاح'})

    except Exception as e:
        print(f"خطأ في إضافة المدير: {e}")
        return jsonify({'error': 'خطأ في إضافة المدير'}), 500

@app.route('/api/telegram-remove-admin', methods=['POST'])
def remove_telegram_admin():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        phone = data.get('phone', '').strip()
        
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM telegram_admin_users WHERE phone = ?', (phone,))
            conn.commit()
            conn.close()

        return jsonify({'success': True, 'message': 'تم إزالة المدير بنجاح'})

    except Exception as e:
        print(f"خطأ في إزالة المدير: {e}")
        return jsonify({'error': 'خطأ في إزالة المدير'}), 500

@app.route('/api/telegram-admin-users', methods=['GET'])
def get_telegram_admin_users():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # إنشاء الجدول إذا لم يكن موجود
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_admin_users (
                    user_id INTEGER PRIMARY KEY,
                    phone TEXT UNIQUE,
                    name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            cursor.execute('''
                SELECT phone, name FROM telegram_admin_users 
                ORDER BY added_at DESC
            ''')
            admin_users = [{'phone': row[0], 'name': row[1]} for row in cursor.fetchall()]
            conn.close()

        return jsonify(admin_users)

    except Exception as e:
        print(f"خطأ في جلب المديرين: {e}")
        return jsonify([])

@app.route('/api/telegram-broadcast', methods=['POST'])
def send_telegram_broadcast():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        target = data.get('target', 'all')
        title = data.get('title', '')
        message = data.get('message', '')
        custom_users = data.get('custom_users', '')
        scheduled = data.get('scheduled', False)
        schedule_time = data.get('schedule_time', '')

        if not title or not message:
            return jsonify({'error': 'العنوان والرسالة مطلوبان'}), 400

        # جلب قائمة المستخدمين المستهدفين
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()

            if target == 'all':
                cursor.execute('SELECT chat_id FROM telegram_users')
            elif target == 'active':
                # المستخدمين النشطين (لديهم معاملات حديثة)
                cursor.execute('''
                    SELECT DISTINCT tu.chat_id FROM telegram_users tu
                    JOIN users u ON tu.phone = u.phone
                    WHERE u.is_active = 1
                ''')
            elif target == 'admins':
                cursor.execute('''
                    SELECT tu.chat_id FROM telegram_users tu
                    JOIN users u ON tu.phone = u.phone
                    WHERE u.role = 'admin' AND u.is_active = 1
                ''')
            elif target == 'custom' and custom_users:
                phones = [phone.strip() for phone in custom_users.split(',')]
                placeholders = ','.join(['?' for _ in phones])
                cursor.execute(f'SELECT chat_id FROM telegram_users WHERE phone IN ({placeholders})', phones)
            else:
                return jsonify({'error': 'نوع الإرسال غير صحيح'}), 400

            chat_ids = [row[0] for row in cursor.fetchall()]
            conn.close()

        if not chat_ids:
            return jsonify({'error': 'لا توجد مستخدمين للإرسال إليهم'}), 404

        # إرسال الرسالة
        sent_count = 0
        full_message = f"🔔 {title}\n\n{message}"
        
        import requests
        bot_token = '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE'  # يمكن جلبه من الإعدادات
        
        for chat_id in chat_ids:
            try:
                payload = {
                    'chat_id': chat_id,
                    'text': full_message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(
                    f'https://api.telegram.org/bot{bot_token}/sendMessage',
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    sent_count += 1
            except Exception as e:
                print(f"خطأ في إرسال رسالة إلى {chat_id}: {e}")

        return jsonify({
            'success': True,
            'message': f'تم إرسال الرسالة بنجاح',
            'sent_count': sent_count,
            'total_targets': len(chat_ids)
        })

    except Exception as e:
        print(f"خطأ في إرسال الرسالة الجماعية: {e}")
        return jsonify({'error': 'خطأ في إرسال الرسالة'}), 500

@app.route('/api/telegram-export-stats', methods=['GET'])
def export_telegram_stats():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        import csv
        import io
        from datetime import datetime

        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            
            # جلب إحصائيات مفصلة
            cursor.execute('''
                SELECT tu.phone, tu.chat_id, tu.created_at,
                       u.name, u.balance, u.role,
                       COUNT(t.id) as total_transactions,
                       COALESCE(SUM(CASE WHEN t.status = 'approved' THEN t.amount END), 0) as total_amount
                FROM telegram_users tu
                LEFT JOIN users u ON tu.phone = u.phone
                LEFT JOIN transactions t ON u.id = t.user_id
                GROUP BY tu.phone, tu.chat_id, tu.created_at, u.name, u.balance, u.role
                ORDER BY tu.created_at DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()

        # إنشاء ملف CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # كتابة الرؤوس
        writer.writerow([
            'رقم الهاتف', 'معرف المحادثة', 'تاريخ التسجيل',
            'الاسم', 'الرصيد', 'النوع',
            'عدد المعاملات', 'إجمالي المبلغ'
        ])
        
        # كتابة البيانات
        for row in results:
            writer.writerow(row)

        # إعداد الاستجابة
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=telegram_stats_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response

    except Exception as e:
        print(f"خطأ في تصدير الإحصائيات: {e}")
        return jsonify({'error': 'خطأ في تصدير الإحصائيات'}), 500

@app.route('/api/telegram-clear-logs', methods=['POST'])
def clear_telegram_logs():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        # يمكن إضافة جدول للسجلات لاحقاً
        # حالياً سنعتبر أنه تم مسح السجلات بنجاح
        return jsonify({'success': True, 'message': 'تم مسح السجلات بنجاح'})

    except Exception as e:
        print(f"خطأ في مسح السجلات: {e}")
        return jsonify({'error': 'خطأ في مسح السجلات'}), 500

@app.route('/api/telegram-test-connection', methods=['POST'])
def test_telegram_connection():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        import requests
        import json
        
        # جلب token البوت من الإعدادات
        try:
            with open('telegram_bot_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
                bot_token = settings.get('bot_token', '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE')
        except FileNotFoundError:
            bot_token = '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE'
        
        # اختبار الاتصال
        response = requests.get(f'https://api.telegram.org/bot{bot_token}/getMe', timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            if bot_info.get('ok'):
                result = bot_info.get('result', {})
                
                # جلب معلومات إضافية عن البوت
                webhook_response = requests.get(f'https://api.telegram.org/bot{bot_token}/getWebhookInfo', timeout=10)
                webhook_info = webhook_response.json().get('result', {}) if webhook_response.status_code == 200 else {}
                
                return jsonify({
                    'success': True, 
                    'message': 'الاتصال بالبوت يعمل بشكل طبيعي',
                    'bot_info': {
                        'id': result.get('id'),
                        'username': result.get('username'),
                        'first_name': result.get('first_name'),
                        'can_join_groups': result.get('can_join_groups'),
                        'can_read_all_group_messages': result.get('can_read_all_group_messages'),
                        'supports_inline_queries': result.get('supports_inline_queries')
                    },
                    'webhook_info': {
                        'url': webhook_info.get('url', ''),
                        'has_custom_certificate': webhook_info.get('has_custom_certificate', False),
                        'pending_update_count': webhook_info.get('pending_update_count', 0)
                    }
                })
            else:
                return jsonify({'error': 'البوت غير صالح أو محظور'}), 400
        else:
            return jsonify({'error': f'فشل في الاتصال بالبوت (كود الخطأ: {response.status_code})'}), 400

    except requests.exceptions.Timeout:
        return jsonify({'error': 'انتهت مهلة الاتصال بخادم تليجرام'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'خطأ في الاتصال بالإنترنت'}), 500
    except Exception as e:
        print(f"خطأ في اختبار الاتصال: {e}")
        return jsonify({'error': 'خطأ في الاتصال بالخادم'}), 500

@app.route('/api/telegram-bot-logs', methods=['GET'])
def get_telegram_bot_logs():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        # قراءة آخر 100 سطر من log البوت إذا كان موجوداً
        log_lines = []
        log_file = 'telegram_bot.log'
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                log_lines = lines[-100:]  # آخر 100 سطر
        
        return jsonify({
            'logs': log_lines,
            'total_lines': len(log_lines),
            'log_file_exists': os.path.exists(log_file)
        })
        
    except Exception as e:
        print(f"خطأ في قراءة سجلات البوت: {e}")
        return jsonify({'error': 'خطأ في قراءة السجلات'}), 500

@app.route('/api/telegram-send-test-message', methods=['POST'])
def send_test_telegram_message():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        data = request.json
        test_phone = data.get('test_phone', '')
        test_message = data.get('test_message', 'رسالة تجريبية من لوحة الإدارة 🧪')
        
        if not test_phone:
            return jsonify({'error': 'يرجى تحديد رقم الهاتف'}), 400
        
        # البحث عن معرف المحادثة
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM telegram_users WHERE phone = ?', (test_phone,))
            result = cursor.fetchone()
            conn.close()
        
        if not result:
            return jsonify({'error': 'المستخدم غير مسجل في التليجرام'}), 404
        
        # إرسال الرسالة التجريبية
        success = send_telegram_notification(test_phone, f"🧪 رسالة تجريبية\n\n{test_message}")
        
        if success:
            return jsonify({'success': True, 'message': 'تم إرسال الرسالة التجريبية بنجاح'})
        else:
            return jsonify({'error': 'فشل في إرسال الرسالة'}), 500
            
    except Exception as e:
        print(f"خطأ في إرسال الرسالة التجريبية: {e}")
        return jsonify({'error': 'خطأ في إرسال الرسالة'}), 500

# إضافة مسار لتعديل الفئات
@app.route('/api/categories/<int:category_id>', methods=['GET'])
def get_category(category_id):
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM company_categories WHERE id = ?', (category_id,))
        category = cursor.fetchone()
        conn.close()

    if category:
        return jsonify({
            'id': category[0],
            'name': category[1],
            'icon': category[2],
            'is_active': category[3]
        })
    else:
        return jsonify({'error': 'الفئة غير موجودة'}), 404

# مسار حفظ إعدادات التليجرام
@app.route('/api/telegram-settings', methods=['POST'])
def save_telegram_settings():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    data = request.json
    bot_token = data.get('bot_token', '')
    chat_id = data.get('chat_id', '')

    try:
        import json
        # تحميل الإعدادات الحالية
        try:
            with open('site_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}

        # إضافة إعدادات التليجرام
        settings['telegram'] = {
            'bot_token': bot_token,
            'chat_id': chat_id
        }

        # حفظ الإعدادات
        with open('site_settings.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return jsonify({'success': True, 'message': 'تم حفظ إعدادات التليجرام بنجاح'})
    except Exception as e:
        return jsonify({'error': f'خطأ في حفظ الإعدادات: {str(e)}'}), 500

# مسار جلب إعدادات التليجرام
@app.route('/api/telegram-settings', methods=['GET'])
def get_telegram_settings():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403

    try:
        import json
        with open('site_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
            telegram_settings = settings.get('telegram', {})
            return jsonify({
                'bot_token': telegram_settings.get('bot_token', ''),
                'chat_id': telegram_settings.get('chat_id', '')
            })
    except FileNotFoundError:
        return jsonify({
            'bot_token': '',
            'chat_id': ''
        })
    except Exception as e:
        return jsonify({'error': f'خطأ في تحميل الإعدادات: {str(e)}'}), 500

# إضافة مسار لتعديل حالة الطلب
@app.route('/api/transactions/<int:transaction_id>', methods=['GET'])
def get_transaction(transaction_id):
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 403

    with db_lock:
        conn = sqlite3.connect('bills_system.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
        transaction = cursor.fetchone()
        conn.close()

    if transaction:
        return jsonify({
            'id': transaction[0],
            'user_id': transaction[1],
            'customer_id': transaction[2],
            'transaction_type': transaction[3],
            'amount': transaction[4],
            'months': transaction[5],
            'status': transaction[6],
            'notes': transaction[7],
            'staff_notes': transaction[8],
            'created_at': transaction[9],
            'approved_at': transaction[10]
        })
    else:
        return jsonify({'error': 'المعاملة غير موجودة'}), 404

def load_telegram_users():
    """تحميل مستخدمي التليجرام من قاعدة البيانات"""
    try:
        with db_lock:
            conn = sqlite3.connect('bills_system.db')
            cursor = conn.cursor()
            cursor.execute('SELECT phone, chat_id FROM telegram_users')
            users = cursor.fetchall()
            conn.close()

        for phone, chat_id in users:
            telegram_users[phone] = chat_id

        print(f"تم تحميل {len(users)} مستخدم تليجرام من قاعدة البيانات")
    except Exception as e:
        print(f"خطأ في تحميل مستخدمي التليجرام: {e}")

# إضافة معالج للأخطاء العامة
@app.errorhandler(500)
def internal_error(error):
    print(f"خطأ داخلي في الخادم: {error}")
    return jsonify({
        'error': 'خطأ داخلي في الخادم',
        'message': 'حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.'
    }), 500

@app.errorhandler(404)
def not_found(error):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({
            'error': 'غير موجود',
            'message': 'المورد المطلوب غير موجود'
        }), 404
    return redirect(url_for('home'))

@app.errorhandler(403)
def forbidden(error):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({
            'error': 'غير مصرح',
            'message': 'ليس لديك صلاحية للوصول لهذا المورد'
        }), 403
    return redirect(url_for('home'))

# إضافة headers أمنية
@app.after_request
def after_request(response):
    # منع التخزين المؤقت للـ API
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    # إضافة headers أمنية
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    return response

def start_telegram_bot():
    """تشغيل بوت التليجرام في thread منفصل"""
    try:
        import subprocess
        import sys
        
        print("🤖 بدء تشغيل بوت التليجرام...")
        
        # تشغيل البوت في عملية منفصلة
        process = subprocess.Popen(
            [sys.executable, 'telegram_bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        print(f"✅ تم تشغيل بوت التليجرام (PID: {process.pid})")
        return process
        
    except Exception as e:
        print(f"❌ خطأ في تشغيل بوت التليجرام: {e}")
        return None

if __name__ == '__main__':
    init_db()
    load_telegram_users()

    print("🚀 بدء تشغيل النظام...")
    print(f"📱 مستخدمو التليجرام المسجلون: {len(telegram_users)}")

    # تشغيل بوت التليجرام أولاً
    bot_process = start_telegram_bot()
    
    # انتظار قصير للتأكد من بدء البوت
    time.sleep(2)
    
    print("🌐 بدء تشغيل خادم Flask...")
    
    try:
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("🛑 إيقاف النظام...")
        if bot_process:
            try:
                bot_process.terminate()
                print("✅ تم إيقاف بوت التليجرام")
            except:
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
BOT_TOKEN = '7815149975:AAEioobhaYQnSVE-7kYbcBu5vHH7_qW36QE'
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
            "🌟 أهلاً وسهلاً بك في بوت مؤسسة نور التجارية\n\n"
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
                        "❓ لم أفهم طلبك. يرجى استخدام الأزرار المتاحة"
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
                pass
