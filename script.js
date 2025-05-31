// تطبيق نظام الفواتير
let currentUser = null;
let notificationCount = 0;
let companies = [];
let categories = [];
let currentTransactions = [];
let users = [];
let customers = [];
let paymentRequests = [];
let currentRequestId = null; // لحفظ معرف الطلب المعروض حالياً
let connectionFailures = 0; // عداد فشل الاتصالات

// مراقبة حالة الاتصال محسنة
function checkConnectionStatus() {
    const connectionAlert = document.getElementById('connectionAlert');

    if (connectionFailures >= 5) {
        // إظهار تحذير شديد
        if (connectionAlert) {
            connectionAlert.style.display = 'block';
            connectionAlert.className = 'alert alert-danger';
            connectionAlert.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i>
                <strong>مشكلة في الاتصال!</strong> فشل الاتصال ${connectionFailures} مرات.
                <button class="btn btn-sm btn-outline-light ms-2" onclick="forceReconnect()">
                    <i class="fas fa-sync"></i> إعادة الاتصال
                </button>
            `;
        }

        // محاولة إعادة الاتصال التلقائي
        setTimeout(autoReconnect, 2000);

    } else if (connectionFailures >= 3) {
        // إظهار تحذير متوسط
        if (connectionAlert) {
            connectionAlert.style.display = 'block';
            connectionAlert.className = 'alert alert-warning';
            connectionAlert.innerHTML = `
                <i class="fas fa-exclamation-circle"></i>
                <strong>تحذير:</strong> اتصال غير مستقر (${connectionFailures} أخطاء).
                <button class="btn btn-sm btn-outline-dark ms-2" onclick="reloadBasicData()">
                    <i class="fas fa-redo"></i> إعادة التحميل
                </button>
            `;
        }
    } else if (connectionAlert) {
        connectionAlert.style.display = 'none';
    }
}

// إعادة تعيين عداد فشل الاتصال عند النجاح
function resetConnectionFailures() {
    connectionFailures = 0;
    checkConnectionStatus();

    // إزالة أي تحذيرات موجودة
    const connectionAlert = document.getElementById('connectionAlert');
    if (connectionAlert) {
        connectionAlert.style.display = 'none';
    }
}

// زيادة عداد فشل الاتصال
function incrementConnectionFailures() {
    connectionFailures++;
    console.warn(`زاد عداد فشل الاتصال إلى: ${connectionFailures}`);
    checkConnectionStatus();
}

// إجبار إعادة الاتصال
async function forceReconnect() {
    showLoader('جاري إعادة الاتصال بالخادم...');

    try {
        const success = await autoReconnect();
        if (success) {
            await reloadBasicData();
        } else {
            showAlert('فشل في إعادة الاتصال. يرجى تحديث الصفحة.', 'error');
        }
    } catch (error) {
        console.error('خطأ في إعادة الاتصال:', error);
        showAlert('خطأ في إعادة الاتصال. يرجى تحديث الصفحة.', 'error');
    } finally {
        hideLoader();
    }
}

// تهيئة محسنة للتطبيق
document.addEventListener('DOMContentLoaded', function() {
    console.log('تطبيق نظام الفواتير جاهز');

    // التحقق من حالة الجلسة أولاً
    if (window.sessionExpiredHandled) {
        return;
    }

    // تحقق من أننا لسنا في صفحة تسجيل الدخول
    const isLoginPage = window.location.pathname === '/' && document.querySelector('form[action*="login"]');

    if (!isLoginPage) {
        // تحديث حالة الإشعارات مرة واحدة فقط عند التحميل
        updateNotificationStatus();

        // تحديث الإشعارات كل دقيقة (بدلاً من 30 ثانية)
        window.notificationInterval = setInterval(() => {
            if (!window.sessionExpiredHandled) {
                updateNotificationStatus();
            }
        }, 60000);

        // تحميل البيانات الأساسية مع معالجة الأخطاء
        Promise.all([
            loadCompanies().catch(err => console.warn('خطأ في تحميل الشركات:', err)),
            loadCategories().catch(err => console.warn('خطأ في تحميل الفئات:', err)),
            loadUserStats().catch(err => console.warn('خطأ في تحميل الإحصائيات:', err))
        ]);
    }

    // تحميل إعدادات الموقع
    loadSiteSettings().catch(err => console.warn('خطأ في تحميل إعدادات الموقع:', err));

    // إضافة مستمعي الأحداث
    setupEventListeners();
});

// إعداد مستمعي الأحداث
function setupEventListeners() {
    // نموذج البحث في الاستعلام
    const inquiryPhoneInput = document.getElementById('inquiryPhoneNumber');
    if (inquiryPhoneInput) {
        inquiryPhoneInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchCustomerInquiry();
            }
        });
    }

    // نموذج طلب الخدمة
    const serviceForm = document.getElementById('serviceRequestForm');
    if (serviceForm) {
        serviceForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitServiceRequest();
        });
    }

    // تحديث الشركات عند تغيير الفئة
    const companySelect = document.getElementById('serviceCompanySelect');
    if (companySelect) {
        companySelect.addEventListener('change', function() {
            updateServiceDetails();
        });
    }

    // مراقبة تغيير وضع الصيانة
    const maintenanceMode = document.getElementById('maintenanceMode');
    if (maintenanceMode) {
        maintenanceMode.addEventListener('change', function() {
            const reasonSection = document.getElementById('maintenanceReasonSection');
            if (reasonSection) {
                reasonSection.style.display = this.value === 'true' ? 'block' : 'none';
            }
        });
    }
}

// تحديث حالة الإشعارات المحسن
async function updateNotificationStatus() {
    // منع التحديث في حالات معينة
    if (window.location.pathname === '/' && document.querySelector('form[action*="login"]')) {
        return;
    }

    if (window.sessionExpiredHandled || window.notificationUpdateInProgress) {
        return;
    }

    try {
        window.notificationUpdateInProgress = true;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 ثوان timeout

        const response = await fetch('/api/unread-notifications-count', {
            signal: controller.signal,
            headers: {
                'Cache-Control': 'no-cache'
            }
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            notificationCount = data.count;

            const badge = document.getElementById('notificationBadge');
            if (badge) {
                if (notificationCount > 0) {
                    badge.textContent = notificationCount;
                    badge.style.display = 'inline';
                } else {
                    badge.style.display = 'none';
                }
            }
        } else if (response.status === 401) {
            handleSessionError(response);
            return;
        } else if (response.status === 502 || response.status === 503) {
            console.warn('الخادم غير متاح لتحديث الإشعارات');
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn('انتهت مهلة تحديث الإشعارات');
        } else {
            console.warn('خطأ في تحديث حالة الإشعارات:', error);
        }
    } finally {
        window.notificationUpdateInProgress = false;
    }
}

// فحص حالة الخادم محسن
async function checkServerHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000); // 8 ثواني

        const response = await fetch('/health', {
            method: 'GET',
            headers: {
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            console.log('حالة الخادم:', data);
            return true;
        } else {
            console.warn('الخادم لا يستجيب بشكل صحيح:', response.status);
            return false;
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.error('انتهت مهلة فحص الخادم');
        } else {
            console.error('خطأ في فحص حالة الخادم:', error);
        }
        return false;
    }
}

// دالة لإعادة الاتصال التلقائي
async function autoReconnect() {
    const maxAttempts = 5;
    let attempt = 0;

    while (attempt < maxAttempts) {
        attempt++;
        console.log(`محاولة إعادة الاتصال ${attempt} من ${maxAttempts}`);

        const isHealthy = await checkServerHealth();
        if (isHealthy) {
            console.log('تم استعادة الاتصال بنجاح');
            resetConnectionFailures();
            showAlert('تم استعادة الاتصال بالخادم', 'success');
            return true;
        }

        // انتظار متزايد بين المحاولات
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
        await new Promise(resolve => setTimeout(resolve, delay));
    }

    console.error('فشل في إعادة الاتصال بعد جميع المحاولات');
    return false;
}

// إعادة المحاولة مع تأخير محسن
function retryWithDelay(func, delay = 3000, maxRetries = 3) {
    let retries = 0;

    const attempt = async () => {
        try {
            return await func();
        } catch (error) {
            retries++;

            // عدم إعادة المحاولة في حالات معينة
            if (error.name === 'AbortError' || 
                error.message.includes('401') || 
                error.message.includes('403') ||
                error.message.includes('404')) {
                throw error;
            }

            if (retries < maxRetries) {
                const delayTime = delay * Math.pow(1.5, retries - 1); // زيادة التأخير تدريجياً
                console.log(`إعادة المحاولة ${retries} من ${maxRetries} بعد ${delayTime}ms للخطأ:`, error.message);

                await new Promise(resolve => setTimeout(resolve, delayTime));
                return attempt();
            } else {
                console.error(`فشلت جميع المحاولات (${maxRetries}) للدالة:`, error);
                throw error;
            }
        }
    };

    return attempt();
}

// دالة لإعادة تحميل البيانات الأساسية
async function reloadBasicData() {
    try {
        showLoader('جاري إعادة تحميل البيانات...');

        // تحديد timeout أطول للطلبات
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 ثانية

        try {
            await Promise.all([
                retryWithDelay(() => loadCompanies(controller.signal)),
                retryWithDelay(() => loadCategories(controller.signal)),
                retryWithDelay(() => loadSiteSettings(controller.signal)),
                retryWithDelay(() => loadUserStats(controller.signal))
            ]);

            clearTimeout(timeoutId);
            showAlert('تم إعادة تحميل البيانات بنجاح', 'success');
            resetConnectionFailures();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('انتهت مهلة الطلب');
            }
            throw error;
        }

    } catch (error) {
        console.error('فشل في إعادة تحميل البيانات:', error);
        incrementConnectionFailures();

        if (error.message.includes('انتهت مهلة الطلب')) {
            showAlert('انتهت مهلة الاتصال. يرجى التحقق من اتصال الإنترنت والمحاولة مرة أخرى.', 'error');
        } else if (error.message.includes('502') || error.message.includes('503')) {
            showAlert('الخادم غير متاح حالياً. يرجى المحاولة مرة أخرى بعد قليل.', 'warning');
        } else {
            showAlert('فشل في إعادة تحميل البيانات. يرجى تحديث الصفحة.', 'error');
        }
    } finally {
        hideLoader();
    }
}

// تحميل الشركات محسن
async function loadCompanies(signal = null) {
    try {
        const controller = signal || new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);

        const response = await fetch('/api/companies', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();

            // التحقق من صحة البيانات
            if (Array.isArray(data)) {
                companies = data;
                console.log('تم تحميل الشركات:', companies.length);
                populateCompanySelect();
                resetConnectionFailures();
            } else {
                throw new Error('البيانات المستلمة غير صحيحة');
            }
        } else if (response.status === 401) {
            // إعادة توجيه لصفحة تسجيل الدخول مرة واحدة فقط
            if (!window.location.pathname.includes('login') && !window.location.search.includes('session_expired')) {
                console.warn('انتهت صلاحية الجلسة، إعادة توجيه لتسجيل الدخول');
                window.location.href = '/';
            }
            return;
        } else if (response.status === 403) {
            console.warn('ليس لديك صلاحية للوصول لهذه البيانات');
            companies = [];
            populateCompanySelect();
            return;
        } else if (response.status === 502 || response.status === 503) {
            incrementConnectionFailures();
            throw new Error(`الخادم غير متاح (${response.status})`);
        } else {
            incrementConnectionFailures();
            const errorText = await response.text().catch(() => 'خطأ غير معروف');
            throw new Error(`خطأ في الخادم (${response.status}): ${errorText}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل الشركات:', error);
        companies = [];

        if (error.name === 'AbortError') {
            incrementConnectionFailures();
            throw new Error('انتهت مهلة تحميل الشركات');
        } else if (error.message.includes('Failed to fetch')) {
            incrementConnectionFailures();
            throw new Error('فشل في الاتصال بالخادم - تحقق من اتصال الإنترنت');
        } else {
            incrementConnectionFailures();
            throw error;
        }
    }
}

// تحميل الفئات
async function loadCategories() {
    try {
        const response = await fetch('/api/categories');
        if (response.ok) {
            categories = await response.json();
            console.log('تم تحميل الفئات:', categories.length);
            populateCategorySelects();
        } else {
            console.error('خطأ في الاستجابة:', response.status);
            throw new Error(`فشل في تحميل الفئات: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل الفئات:', error);
        categories = [];
        if (error.message.includes('502') || error.message.includes('503')) {
            showAlert('الخادم غير متاح حالياً، يرجى المحاولة مرة أخرى', 'warning');
        }
    }
}

// تحميل إعدادات الموقع
async function loadSiteSettings() {
    try {
        const response = await fetch('/api/site-settings');
        if (response.ok) {
            const settings = await response.json();
            console.log('تم تحميل إعدادات الموقع:', settings);
            document.title = settings.site_name || 'نظام تسديد الفواتير';

            const titleElement = document.querySelector('.navbar-brand');
            if (titleElement) {
                titleElement.innerHTML = `<i class="fas fa-building"></i> ${settings.site_name || 'مؤسسة نور التجارية'}`;
            }

            const announcementText = document.getElementById('announcementText');
            if (announcementText && settings.announcement) {
                announcementText.textContent = settings.announcement;
            }
        }
    } catch (error) {
        console.error('خطأ في تحميل إعدادات الموقع:', error);
    }
}

// إظهار الأقسام المختلفة - محسن
function showSection(sectionId) {
    try {
        console.log(`إظهار القسم: ${sectionId}`);

        // التحقق من صحة معرف القسم
        const validSections = ['mainServices', 'notifications', 'transactions', 'changePassword'];
        if (!validSections.includes(sectionId)) {
            throw new Error(`معرف القسم غير صحيح: ${sectionId}`);
        }

        // إخفاء جميع الأقسام
        validSections.forEach(section => {
            const element = document.getElementById(section);
            if (element) {
                element.style.display = 'none';
                element.classList.remove('fade-in');
            }
        });

        // إظهار القسم المطلوب
        const targetSection = document.getElementById(sectionId);
        if (targetSection) {
            targetSection.style.display = 'block';
            targetSection.classList.add('fade-in');
        } else {
            throw new Error(`القسم ${sectionId} غير موجود في الصفحة`);
        }

        // تحديث القائمة النشطة
        const navItems = document.querySelectorAll('.list-group-item');
        navItems.forEach(item => {
            item.classList.remove('active');
        });

        // العثور على الرابط النشط وتفعيله
        const targetNavItem = document.querySelector(`[onclick*="showSection('${sectionId}')"]`);
        if (targetNavItem) {
            targetNavItem.classList.add('active');
        }

        // تحميل البيانات حسب القسم مع معالجة الأخطاء المحسنة
        setTimeout(async () => {
            try {
                switch (sectionId) {
                    case 'mainServices':
                        // تحميل الإحصائيات والشركات
                        await Promise.all([
                            retryWithDelay(() => loadUserStats(), 2000, 2),
                            retryWithDelay(() => loadCompanies(), 2000, 2)
                        ]);
                        // تحديث قائمة الشركات في نموذج الطلب
                        populateCompanySelect();
                        break;
                    case 'notifications':
                        await retryWithDelay(() => loadNotifications(), 2000, 2);
                        break;
                    case 'transactions':
                        await retryWithDelay(() => loadUserTransactions(), 2000, 2);
                        break;
                    case 'changePassword':
                        // تنظيف نموذج تغيير كلمة المرور
                        const passwordForm = targetSection.querySelector('form');
                        if (passwordForm) {
                            passwordForm.reset();
                        }
                        break;
                }
            } catch (error) {
                console.error(`خطأ في تحميل بيانات القسم ${sectionId}:`, error);
                
                // عرض رسالة خطأ مناسبة داخل القسم
                const errorHtml = `
                    <div class="alert alert-warning text-center m-3">
                        <i class="fas fa-exclamation-triangle"></i>
                        <h6>خطأ في تحميل البيانات</h6>
                        <p>${error.message || 'حدث خطأ غير متوقع'}</p>
                        <button class="btn btn-outline-warning btn-sm" onclick="showSection('${sectionId}')">
                            <i class="fas fa-redo"></i> إعادة المحاولة
                        </button>
                    </div>
                `;

                // إضافة رسالة الخطأ في بداية القسم
                const existingError = targetSection.querySelector('.alert-warning');
                if (!existingError) {
                    targetSection.insertAdjacentHTML('afterbegin', errorHtml);
                }
            }
        }, 200);

    } catch (error) {
        console.error(`خطأ عام في إظهار القسم ${sectionId}:`, error);
        showMessage(`خطأ في عرض القسم: ${error.message}`, 'error');
    }
}

// دالة عرض الرسائل المحسنة
function showMessage(message, type = 'info') {
    // إزالة الرسائل السابقة
    const existingAlerts = document.querySelectorAll('.alert.temporary-alert');
    existingAlerts.forEach(alert => alert.remove());

    // تحديد نوع الرسالة
    let alertClass = 'alert-info';
    let icon = 'fas fa-info-circle';

    switch(type) {
        case 'success':
            alertClass = 'alert-success';
            icon = 'fas fa-check-circle';
            break;
        case 'error':
        case 'danger':
            alertClass = 'alert-danger';
            icon = 'fas fa-exclamation-triangle';
            break;
        case 'warning':
            alertClass = 'alert-warning';
            icon = 'fas fa-exclamation-circle';
            break;
    }

    // إنشاء عنصر الرسالة
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert ${alertClass} alert-dismissible fade show temporary-alert`;
    alertDiv.innerHTML = `
        <i class="${icon}"></i> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // إضافة الرسالة في أعلى الصفحة
    const container = document.querySelector('.container-fluid') || document.body;
    container.insertBefore(alertDiv, container.firstChild);

    // إزالة الرسالة تلقائياً بعد 5 ثوان
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// دالة showAlert (alias لـ showMessage)
function showAlert(message, type = 'info') {
    showMessage(message, type);
}

// دالة تغيير كلمة المرور
async function changePassword() {
    const currentPassword = document.getElementById('currentPassword')?.value;
    const newPassword = document.getElementById('newPassword')?.value;
    const confirmPassword = document.getElementById('confirmPassword')?.value;

    // التحقق من البيانات
    if (!currentPassword || !newPassword || !confirmPassword) {
        showAlert('يرجى ملء جميع الحقول', 'error');
        return;
    }

    if (newPassword !== confirmPassword) {
        showAlert('كلمة المرور الجديدة غير متطابقة', 'error');
        return;
    }

    if (newPassword.length < 6) {
        showAlert('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'error');
        return;
    }

    try {
        showLoader('جاري تغيير كلمة المرور...');

        const response = await fetch('/api/change-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });

        const result = await response.json();

        if (response.ok) {
            showAlert(result.message, 'success');
            
            // إذا كان مطلوب تسجيل خروج، إعادة توجيه للصفحة الرئيسية
            if (result.logout_required) {
                setTimeout(() => {
                    window.location.href = '/';
                }, 2000);
            }
        } else {
            showAlert(result.error || 'حدث خطأ في تغيير كلمة المرور', 'error');
        }
    } catch (error) {
        console.error('خطأ في تغيير كلمة المرور:', error);
        showAlert('خطأ في الاتصال بالخادم', 'error');
    } finally {
        hideLoader();
    }
}

// إظهار نموذج تغيير كلمة المرور
function showChangePasswordModal() {
    // التحقق من وجود المودال أولاً
    let modal = document.getElementById('changePasswordModal');

    if (!modal) {
        // إنشاء المودال إذا لم يكن موجوداً
        const modalHtml = `
            <div class="modal fade" id="changePasswordModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-warning text-dark">
                            <h5 class="modal-title">
                                <i class="fas fa-lock"></i> تغيير كلمة المرور
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="changePasswordForm" onsubmit="return false;">
                                <div class="mb-3">
                                    <label for="currentPassword" class="form-label">كلمة المرور الحالية</label>
                                    <input type="password" class="form-control" id="currentPassword" required>
                                </div>
                                <div class="mb-3">
                                    <label for="newPassword" class="form-label">كلمة المرور الجديدة</label>
                                    <input type="password" class="form-control" id="newPassword" required minlength="6">
                                    <div class="form-text">يجب أن تكون 6 أحرف على الأقل</div>
                                </div>
                                <div class="mb-3">
                                    <label for="confirmPassword" class="form-label">تأكيد كلمة المرور الجديدة</label>
                                    <input type="password" class="form-control" id="confirmPassword" required minlength="6">
                                </div>
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i>
                                    <strong>تنبيه:</strong> عند تغيير كلمة المرور، سيتم إنهاء جميع جلساتك النشطة في الموقع وبوت التليجرام لضمان الأمان.
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-warning" onclick="changePassword()">
                                <i class="fas fa-save"></i> تغيير كلمة المرور
                            </button>
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times"></i> إلغاء
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('changePasswordModal');
    }

    // مسح النموذج
    const form = document.getElementById('changePasswordForm');
    if (form) {
        form.reset();
    }

    // إظهار المودال
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();

    // التركيز على حقل كلمة المرور الحالية
    setTimeout(() => {
        const currentPasswordField = document.getElementById('currentPassword');
        if (currentPasswordField) {
            currentPasswordField.focus();
        }
    }, 300);
}

// دالة showLoader
function showLoader(message = 'جاري التحميل...') {
    // إزالة loader السابق إن وجد
    const existingLoader = document.getElementById('globalLoader');
    if (existingLoader) {
        existingLoader.remove();
    }

    const loaderDiv = document.createElement('div');
    loaderDiv.id = 'globalLoader';
    loaderDiv.className = 'loading-overlay';
    loaderDiv.innerHTML = `
        <div class="text-center text-white">
            <div class="spinner-border text-light mb-3" role="status">
                <span class="visually-hidden">جاري التحميل...</span>
            </div>
            <div>${message}</div>
        </div>
    `;

    document.body.appendChild(loaderDiv);
}

// دالة hideLoader
function hideLoader() {
    const loader = document.getElementById('globalLoader');
    if (loader) {
        loader.remove();
    }
}

// إظهار أقسام الإدارة
function showAdminSection(sectionId, clickedElement) {
    try {
        // إزالة رسائل الخطأ السابقة
        document.querySelectorAll('.alert-danger').forEach(alert => {
            if (alert.textContent.includes('خطأ في تحميل البيانات')) {
                alert.remove();
            }
        });

        // إخفاء جميع الأقسام الإدارية
        const sections = document.querySelectorAll('.admin-section, #adminMain, #settings, #users, #companies, #customers, #inquiryRequests');
        sections.forEach(section => {
            if (section) {
                section.style.display = 'none';
            }
        });

        // إظهار القسم المطلوب
        const targetSection = document.getElementById(sectionId);
        if (targetSection) {
            targetSection.style.display = 'block';
        } else {
            console.error(`القسم ${sectionId} غير موجود`);
            showAlert(`القسم المطلوب غير موجود`, 'error');
            return;
        }

        // تحديث القائمة النشطة
        const navItems = document.querySelectorAll('.list-group-item');
        navItems.forEach(item => {
            item.classList.remove('active');
        });

        // العثور على العنصر المناسب وتفعيله
        if (clickedElement) {
            clickedElement.classList.add('active');
        } else {
            // البحث عن العنصر المناسب بناءً على onclick
            const targetNavItem = document.querySelector(`[onclick*="showAdminSection('${sectionId}')"]`);
            if (targetNavItem) {
                targetNavItem.classList.add('active');
            }
        }

        // إظهار مؤشر تحميل مؤقت
        if (sectionId !== 'adminMain' && sectionId !== 'settings') {
            const loadingHtml = `
                <div class="text-center p-4" id="sectionLoader">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">جاري التحميل...</span>
                    </div>
                    <div class="mt-2">جاري تحميل البيانات...</div>
                </div>
            `;
            targetSection.insertAdjacentHTML('afterbegin', loadingHtml);
        }

        // تحميل البيانات حسب القسم مع معالجة الأخطاء المحسنة
        setTimeout(async () => {
            try {
                switch (sectionId) {
                    case 'adminMain':
                        await loadAdminStats();
                        break;
                    case 'users':
                        console.log('تحميل المستخدمين...');
                        await retryWithDelay(() => loadUsers());
                        break;
                    case 'companies':
                        console.log('تحميل الشركات...');
                        await retryWithDelay(() => loadCompaniesAdmin());
                        break;
                    case 'customers':
                        console.log('تحميل الزبائن...');
                        await retryWithDelay(() => loadCustomers());
                        break;
                    case 'inquiryRequests':
                        console.log('تحميل طلبات التسديد...');
                        await retryWithDelay(() => loadPaymentRequests());
                        break;
                    case 'settings':
                        await loadSiteSettingsAdmin();
                        await loadBackups();
                        break;
                    default:
                        console.log(`قسم غير معروف: ${sectionId}`);
                }

                // إزالة مؤشر التحميل
                const loader = document.getElementById('sectionLoader');
                if (loader) loader.remove();

            } catch (error) {
                console.error(`خطأ في تحميل القسم ${sectionId}:`, error);

                // إزالة مؤشر التحميل
                const loader = document.getElementById('sectionLoader');
                if (loader) loader.remove();

                // عرض رسالة خطأ في القسم نفسه
                if (targetSection) {
                    const errorHtml = `
                        <div class="alert alert-danger text-center" id="sectionError">
                            <i class="fas fa-exclamation-triangle"></i>
                            <h5>خطأ في تحميل البيانات</h5>
                            <p>${error.message || 'حدث خطأ غير متوقع'}</p>
                            <div class="mt-3">
                                <button class="btn btn-danger me-2" onclick="showAdminSection('${sectionId}')">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                                <button class="btn btn-outline-secondary" onclick="reloadBasicData()">
                                    <i class="fas fa-sync"></i> إعادة تحميل البيانات الأساسية
                                </button>
                            </div>
                        </div>
                    `;

                    // إضافة رسالة الخطأ في بداية القسم
                    const existingError = targetSection.querySelector('#sectionError');
                    if (!existingError) {
                        targetSection.insertAdjacentHTML('afterbegin', errorHtml);
                    }
                }

                showAlert(`خطأ في تحميل القسم: ${error.message || 'حدث خطأ غير متوقع'}`, 'error');
            }
        }, 300);

    } catch (error) {
        console.error(`خطأ عام في إظهار القسم ${sectionId}:`, error);
        showAlert(`خطأ في إظهار القسم المطلوب`, 'error');
    }
}

// دالة حفظ المستخدم - محدثة
async function saveUser() {
    console.log('بدء حفظ المستخدم');

    try {
        // جمع البيانات من النموذج
        const userId = document.getElementById('userId')?.value || '';
        const name = document.getElementById('userName')?.value?.trim() || '';
        const phone = document.getElementById('userPhone')?.value?.trim() || '';
        const password = document.getElementById('userPassword')?.value || '';
        const role = document.getElementById('userRole')?.value || 'user';
        const balance = parseFloat(document.getElementById('userBalance')?.value) || 0;
        const isActive = document.getElementById('userStatus')?.value || '1';

        console.log('بيانات المستخدم:', { userId, name, phone, role, balance, isActive });

        // التحقق من البيانات المطلوبة
        if (!name || name.length < 2) {
            showAlert('يرجى إدخال اسم صحيح (حد أدنى حرفين)', 'error');
            document.getElementById('userName')?.focus();
            return;
        }

        if (!phone || phone.length < 10) {
            showAlert('يرجى إدخال رقم هاتف صحيح (حد أدنى 10 أرقام)', 'error');
            document.getElementById('userPhone')?.focus();
            return;
        }

        // التحقق من كلمة المرور للمستخدمين الجدد
        if (!userId && !password) {
            showAlert('كلمة المرور مطلوبة للمستخدمين الجدد', 'error');
            document.getElementById('userPassword')?.focus();
            return;
        }

        // التحقق من صحة الرصيد
        if (balance < 0) {
            showAlert('الرصيد لا يمكن أن يكون سالبًا', 'error');
            document.getElementById('userBalance')?.focus();
            return;
        }

        // إعداد البيانات للإرسال
        const userData = {
            name: name,
            phone: phone,
            role: role,
            balance: balance,
            is_active: parseInt(isActive)
        };

        // إضافة كلمة المرور إذا تم إدخالها
        if (password && password.trim() !== '') {
            userData.password = password.trim();
        }

        // تحديد الرابط والطريقة
        const url = userId ? `/api/users/${userId}` : '/api/users';
        const method = userId ? 'PUT' : 'POST';
        const actionText = userId ? 'تحديث المستخدم' : 'إضافة المستخدم';

        console.log(`${actionText} - الرابط:`, url, 'الطريقة:', method);

        showLoader(`جاري ${actionText}...`);

        // إرسال الطلب
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            body: JSON.stringify(userData),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        const result = await response.json();
        console.log('نتيجة الطلب:', result);

        if (response.ok) {
            const successMessage = result.message || `تم ${actionText} بنجاح`;
            showAlert(successMessage, 'success');

            console.log('تم الحفظ بنجاح، إغلاق النموذج...');

            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('userModal'));
            if (modal) {
                modal.hide();
            }

            // مسح النموذج
            document.getElementById('userForm')?.reset();
            document.getElementById('userId').value = '';

            // إعادة تحميل قائمة المستخدمين
            setTimeout(() => {
                loadUsers();
            }, 500);

        } else if (response.status === 400) {
            showAlert(result.error || 'بيانات غير صحيحة', 'error');
        } else if (response.status === 401) {
            showAlert('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى', 'error');
        } else if (response.status === 403) {
            showAlert('ليس لديك صلاحية لتنفيذ هذا الإجراء', 'error');
        } else if (response.status === 503) {
            showAlert('الخادم غير متاح حالياً، يرجى المحاولة مرة أخرى', 'warning');
        } else {
            showAlert(result.error || 'حدث خطأ في العملية', 'error');
        }

    } catch (error) {
        console.error('خطأ في حفظ المستخدم:', error);

        let errorMessage = 'حدث خطأ غير متوقع';

        if (error.name === 'AbortError') {
            errorMessage = 'انتهت مهلة الطلب. يرجى المحاولة مرة أخرى';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'فشل في الاتصال بالخادم. تحقق من اتصال الإنترنت';
        } else {
            errorMessage = error.message;
        }

        showAlert(`خطأ في حفظ المستخدم: ${errorMessage}`, 'error');

    } finally {
        hideLoader();
    }
}

// دالة إظهار نموذج إضافة مستخدم - محدثة
function showAddUserModal() {
    console.log('إظهار نموذج إضافة مستخدم جديد');

    try {
        // التحقق من وجود النموذج
        const userForm = document.getElementById('userForm');
        const userModal = document.getElementById('userModal');
        const userModalTitle = document.getElementById('userModalTitle');

        if (!userForm || !userModal || !userModalTitle) {
            throw new Error('عناصر النموذج غير موجودة');
        }

        // تنظيف النموذج
        userForm.reset();

        // تنظيف الحقول المخفية
        const userId = document.getElementById('userId');
        if (userId) userId.value = '';

        // تعيين القيم الافتراضية
        const userRole = document.getElementById('userRole');
        const userBalance = document.getElementById('userBalance');
        const userStatus = document.getElementById('userStatus');

        if (userRole) userRole.value = 'user';
        if (userBalance) userBalance.value = '0';
        if (userStatus) userStatus.value = '1';

        // تغيير عنوان النموذج
        userModalTitle.textContent = 'إضافة مستخدم جديد';

        // تحديث نص المساعدة لكلمة المرور
        const passwordHelp = document.querySelector('#userModal .text-muted');
        if (passwordHelp) {
            passwordHelp.textContent = 'يرجى إدخال كلمة مرور قوية';
        }

        // جعل حقل كلمة المرور مطلوبًا
        const passwordField = document.getElementById('userPassword');
        if (passwordField) {
            passwordField.required = true;
            passwordField.placeholder = 'كلمة المرور مطلوبة';
        }

        console.log('تم تنظيف النموذج بنجاح');

        // إظهار النموذج
        const modal = new bootstrap.Modal(userModal, {
            backdrop: 'static',
            keyboard: false
        });
        modal.show();

        // التركيز على حقل الاسم
        setTimeout(() => {
            const nameField = document.getElementById('userName');
            if (nameField) {
                nameField.focus();
            }
        }, 300);

        console.log('تم إظهار نموذج إضافة مستخدم بنجاح');

    } catch (error) {
        console.error('خطأ في إظهار نموذج إضافة المستخدم:', error);
        showAlert('خطأ في فتح نموذج إضافة المستخدم', 'error');
    }
}

// دالة حذف المستخدم
async function deleteUser(userId) {
    if (!confirm('هل أنت متأكد من حذف هذا المستخدم؟')) {
        return;
    }

    try {
        showLoader('جاري حذف المستخدم...');

        const response = await fetch(`/api/users/${userId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok) {
            showAlert('تم حذف المستخدم بنجاح', 'success');
            loadUsers();
        } else {
            showAlert(result.error || 'حدث خطأ في حذف المستخدم', 'error');
        }
    } catch (error) {
        console.error('خطأ في حذف المستخدم:', error);
        showAlert('خطأ في الاتصال بالخادم', 'error');
    } finally {
        hideLoader();
    }
}

// دالة إدارة رصيد المستخدم
function manageUserBalance(userId, userName, currentBalance) {
    document.getElementById('balanceUserId').value = userId;
    document.getElementById('balanceUserName').textContent = userName;
    document.getElementById('currentBalance').textContent = currentBalance;

    const modal = new bootstrap.Modal(document.getElementById('balanceModal'));
    modal.show();
}

// دالة إرسال إشعار للمستخدم
function sendUserNotification(userId, userName) {
    document.getElementById('notificationUserId').value = userId;
    document.getElementById('notificationUserName').textContent = userName;

    const modal = new bootstrap.Modal(document.getElementById('notificationModal'));
    modal.show();
}

// دالة تعديل المستخدم - محدثة بالكامل
async function editUser(userId) {
    console.log('تعديل بيانات المستخدم:', userId);

    if (!userId) {
        showAlert('معرف المستخدم غير صحيح', 'error');
        return;
    }

    try {
        showLoader('جاري تحميل بيانات المستخدم...');

        // إنشاء طلب مع timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch(`/api/users/${userId}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const user = await response.json();
            console.log('تم تحميل بيانات المستخدم:', user);

            // التحقق من وجود النموذج
            const userModal = document.getElementById('userModal');
            if (!userModal) {
                throw new Error('نموذج تعديل المستخدم غير موجود');
            }

            // التحقق من وجود جميع الحقول المطلوبة
            const fields = {
                userId: document.getElementById('userId'),
                userName: document.getElementById('userName'),
                userPhone: document.getElementById('userPhone'),
                userPassword: document.getElementById('userPassword'),
                userRole: document.getElementById('userRole'),
                userBalance: document.getElementById('userBalance'),
                userStatus: document.getElementById('userStatus'),
                userModalTitle: document.getElementById('userModalTitle')
            };

            // التحقق من وجود جميع الحقول
            for (const [fieldName, element] of Object.entries(fields)) {
                if (!element) {
                    throw new Error(`الحقل ${fieldName} غير موجود في النموذج`);
                }
            }

            // ملء بيانات النموذج
            fields.userId.value = user.id || '';
            fields.userName.value = user.name || '';
            fields.userPhone.value = user.phone || '';
            fields.userPassword.value = ''; // لا نملأ كلمة المرور لأسباب أمنية
            fields.userRole.value = user.role || 'user';
            fields.userBalance.value = user.balance || 0;
            fields.userStatus.value = user.is_active ? '1' : '0';

            // تغيير عنوان النموذج
            fields.userModalTitle.textContent = `تعديل المستخدم: ${user.name}`;

            // إضافة معلومات إضافية للنموذج
            const passwordHelp = document.querySelector('#userModal .text-muted');
            if (passwordHelp) {
                passwordHelp.textContent = 'اتركها فارغة للاحتفاظ بكلمة المرور الحالية';
            }

            console.log('تم ملء النموذج بنجاح');

            // إظهار النموذج
            const modal = new bootstrap.Modal(userModal, {
                backdrop: 'static',
                keyboard: false
            });
            modal.show();

            console.log('تم فتح نموذج التعديل بنجاح');

        } else if (response.status === 401) {
            throw new Error('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى');
        } else if (response.status === 403) {
            throw new Error('ليس لديك صلاحية لتعديل هذا المستخدم');
        } else if (response.status === 404) {
            throw new Error('المستخدم غير موجود');
        } else if (response.status === 503) {
            throw new Error('الخادم غير متاح حالياً، يرجى المحاولة مرة أخرى');
        } else {
            let errorText = 'خطأ غير معروف';
            try {
                const errorData = await response.json();
                errorText = errorData.error || errorData.message || errorText;
            } catch (e) {
                errorText = `خطأ في الخادم (${response.status})`;
            }
            throw new Error(errorText);
        }

    } catch (error) {
        console.error('خطأ في تعديل المستخدم:', error);

        let errorMessage = 'حدث خطأ غير متوقع';

        if (error.name === 'AbortError') {
            errorMessage = 'انتهت مهلة الطلب. يرجى المحاولة مرة أخرى';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'فشل في الاتصال بالخادم. تحقق من اتصال الإنترنت';
        } else {
            errorMessage = error.message;
        }

        showAlert(`خطأ في تحميل بيانات المستخدم: ${errorMessage}`, 'error');

    } finally {
        hideLoader();
    }
}

// باقي الدوال...

// تحميل الإحصائيات والدوال الأخرى - محسن
async function loadUserStats() {
    try {
        console.log('بدء تحميل إحصائيات المستخدم...');

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);

        const response = await fetch('/api/user-stats', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const stats = await response.json();
            console.log('تم تحميل الإحصائيات:', stats);
            updateUserStatsDisplay(stats);
            resetConnectionFailures();
        } else if (response.status === 401) {
            console.warn('انتهت صلاحية الجلسة');
            handleSessionError(response);
        } else if (response.status === 502 || response.status === 503) {
            console.warn('الخادم غير متاح لتحديث الإحصائيات');
            incrementConnectionFailures();
            updateUserStatsDisplay({
                pending: 0,
                completed: 0,
                rejected: 0,
                today_total: 0
            });
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل الإحصائيات:', error);

        if (error.name === 'AbortError') {
            console.warn('انتهت مهلة تحميل الإحصائيات');
        } else if (error.message.includes('Failed to fetch')) {
            incrementConnectionFailures();
        }

        // عرض قيم افتراضية
        updateUserStatsDisplay({
            pending: 0,
            completed: 0,
            rejected: 0,
            today_total: 0
        });
    }
}

// تحديث عرض الإحصائيات
function updateUserStatsDisplay(stats) {
    const elements = {
        pending: document.getElementById('pendingRequests'),
        completed: document.getElementById('completedTransactions'),
        rejected: document.getElementById('rejectedRequests'),
        todayTotal: document.getElementById('todayTotal')
    };

    if (elements.pending) elements.pending.textContent = stats.pending || 0;
    if (elements.completed) elements.completed.textContent = stats.completed || 0;
    if (elements.rejected) elements.rejected.textContent = stats.rejected || 0;
    if (elements.todayTotal) elements.todayTotal.textContent = (stats.today_total || 0) + ' ل.س';
}

// تحميل إحصائيات الإدارة
async function loadAdminStats() {
    try {
        const response = await fetch('/api/admin-stats');
        if (response.ok) {
            const stats = await response.json();
            updateAdminStatsDisplay(stats);
        }
    } catch (error) {
        console.error('خطأ في تحميل إحصائيات الإدارة:', error);
    }
}

// تحديث عرض إحصائيات الإدارة
function updateAdminStatsDisplay(stats) {
    const elements = {
        usersCount: document.getElementById('adminUsersCount'),
        successful: document.getElementById('adminSuccessful'),
        pending: document.getElementById('adminPending'),
        rejected: document.getElementById('adminRejected')
    };

    if (elements.usersCount) elements.usersCount.textContent = stats.users_count || 0;
    if (elements.successful) elements.successful.textContent = stats.successful || 0;
    if (elements.pending) elements.pending.textContent = stats.pending || 0;
    if (elements.rejected) elements.rejected.textContent = stats.rejected || 0;
}

// إظهار تفاصيل الزبون - وظيفة محسنة
async function showCustomerDetails(customerId) {
    try {
        showLoader('جاري تحميل تفاصيل الزبون...');

        const response = await fetch(`/api/customers/${customerId}`);
        if (response.ok) {
            const customer = await response.json();
            displayCustomerDetailsModal(customer);
        } else if (response.status === 404) {
            showMessage('الزبون غير موجود', 'error');
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل تفاصيل الزبون:', error);
        showMessage('خطأ في تحميل تفاصيل الزبون', 'error');
    } finally {
        hideLoader();
    }
}

// دالة إضافية لإدارة تفاصيل الزبون من لوحة الإدارة
async function showCustomerDetailsAdmin(customerId) {
    try {
        showLoader('جاري تحميل تفاصيل الزبون...');

        const response = await fetch(`/api/customers/${customerId}`);
        if (response.ok) {
            const customer = await response.json();
            displayCustomerDetailsModalAdmin(customer);
        } else if (response.status === 404) {
            showMessage('الزبون غير موجود', 'error');
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل تفاصيل الزبون:', error);
        showMessage('خطأ في تحميل تفاصيل الزبون', 'error');
    } finally {
        hideLoader();
    }
}

// دوال إدارة الإشعارات للمستخدم
async function loadNotifications() {
    try {
        showLoader('جاري تحميل الإشعارات...');
        
        const response = await fetch('/api/notifications');
        if (response.ok) {
            const notifications = await response.json();
            displayNotifications(notifications);
        } else {
            throw new Error('فشل في تحميل الإشعارات');
        }
    } catch (error) {
        console.error('خطأ في تحميل الإشعارات:', error);
        showMessage('خطأ في تحميل الإشعارات', 'error');
    } finally {
        hideLoader();
    }
}

function displayNotifications(notifications) {
    const container = document.getElementById('notificationsContainer');
    if (!container) return;

    if (!notifications || notifications.length === 0) {
        container.innerHTML = `
            <div class="text-center p-4">
                <i class="fas fa-bell-slash fa-3x text-muted mb-3"></i>
                <p class="text-muted">لا توجد إشعارات</p>
            </div>
        `;
        return;
    }

    let html = '';
    notifications.forEach(notification => {
        const isRead = notification.is_read;
        const cardClass = isRead ? 'border-light' : 'border-primary';
        const bgClass = isRead ? '' : 'bg-light';
        
        html += `
            <div class="card mb-3 ${cardClass} ${bgClass}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h6 class="card-title ${!isRead ? 'text-primary fw-bold' : ''}">
                                ${!isRead ? '<i class="fas fa-circle text-primary me-2" style="font-size: 8px;"></i>' : ''}
                                ${notification.title}
                            </h6>
                            <p class="card-text">${notification.message}</p>
                            <small class="text-muted">
                                <i class="fas fa-clock"></i> ${formatDate(notification.created_at)}
                            </small>
                        </div>
                        ${!isRead ? `
                            <button class="btn btn-sm btn-outline-primary" 
                                    onclick="markNotificationRead(${notification.id})"
                                    title="تعليم كمقروء">
                                <i class="fas fa-check"></i>
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    });

    // إضافة زر "تعليم الكل كمقروء"
    const unreadCount = notifications.filter(n => !n.is_read).length;
    if (unreadCount > 0) {
        html = `
            <div class="text-center mb-3">
                <button class="btn btn-primary" onclick="markAllNotificationsRead()">
                    <i class="fas fa-check-double"></i> تعليم جميع الإشعارات كمقروءة (${unreadCount})
                </button>
            </div>
        ` + html;
    }

    container.innerHTML = html;
}

async function markNotificationRead(notificationId) {
    try {
        const response = await fetch(`/api/notifications/${notificationId}/read`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadNotifications(); // إعادة تحميل الإشعارات
            updateNotificationStatus(); // تحديث عداد الإشعارات
        }
    } catch (error) {
        console.error('خطأ في تعليم الإشعار كمقروء:', error);
    }
}

async function markAllNotificationsRead() {
    try {
        showLoader('جاري تعليم جميع الإشعارات كمقروءة...');
        
        const response = await fetch('/api/mark-notifications-read', {
            method: 'POST'
        });
        
        if (response.ok) {
            showMessage('تم تعليم جميع الإشعارات كمقروءة', 'success');
            loadNotifications();
            updateNotificationStatus();
        }
    } catch (error) {
        console.error('خطأ في تعليم الإشعارات كمقروءة:', error);
        showMessage('خطأ في تعليم الإشعارات كمقروءة', 'error');
    } finally {
        hideLoader();
    }
}

// دوال إدارة المعاملات للمستخدم
async function loadUserTransactions() {
    try {
        const search = document.getElementById('transactionSearch')?.value || '';
        const status = document.getElementById('transactionStatus')?.value || '';
        
        const params = new URLSearchParams();
        if (search) params.append('search', search);
        if (status) params.append('status', status);
        
        const url = `/api/user-transactions?${params.toString()}`;
        
        const response = await fetch(url);
        if (response.ok) {
            const transactions = await response.json();
            displayUserTransactions(transactions);
        } else {
            throw new Error('فشل في تحميل المعاملات');
        }
    } catch (error) {
        console.error('خطأ في تحميل المعاملات:', error);
        showMessage('خطأ في تحميل المعاملات', 'error');
    }
}

function displayUserTransactions(transactions) {
    const tableBody = document.getElementById('userTransactionsTableBody');
    if (!tableBody) return;

    if (!transactions || transactions.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center p-4">
                    <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                    <br>لا توجد معاملات
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    transactions.forEach(transaction => {
        const statusBadge = getStatusBadge(transaction.status);
        const amount = transaction.amount ? `${transaction.amount} ل.س` : '-';
        
        // التأكد من البيانات وتنظيفها
        const phoneNumber = transaction.phone_number || 'غير محدد';
        const customerName = transaction.customer_name || 'غير محدد';
        const companyName = transaction.company_name || 'غير محدد';
        const categoryName = transaction.category_name || 'غير محدد';
        
        html += `
            <tr style="cursor: pointer;" onclick="showTransactionDetails(${transaction.id})" 
                onmouseover="this.style.backgroundColor='#f8f9fa'" 
                onmouseout="this.style.backgroundColor=''">
                <td><span class="font-monospace">${phoneNumber}</span></td>
                <td><strong>${customerName}</strong></td>
                <td><span class="text-primary">${companyName}</span></td>
                <td><span class="text-secondary">${categoryName}</span></td>
                <td><strong class="text-success">${amount}</strong></td>
                <td>${statusBadge}</td>
                <td><small>${formatDate(transaction.created_at)}</small></td>
            </tr>
        `;
    });

    tableBody.innerHTML = html;
}

function getStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge bg-warning">قيد الانتظار</span>',
        'approved': '<span class="badge bg-success">مقبول</span>',
        'rejected': '<span class="badge bg-danger">مرفوض</span>'
    };
    return badges[status] || '<span class="badge bg-secondary">غير معروف</span>';
}

async function showTransactionDetails(transactionId) {
    try {
        showLoader('جاري تحميل تفاصيل المعاملة...');
        
        const response = await fetch(`/api/transaction/${transactionId}`);
        if (response.ok) {
            const transaction = await response.json();
            displayTransactionDetailsModal(transaction);
        } else {
            throw new Error('فشل في تحميل تفاصيل المعاملة');
        }
    } catch (error) {
        console.error('خطأ في تحميل تفاصيل المعاملة:', error);
        showMessage('خطأ في تحميل تفاصيل المعاملة', 'error');
    } finally {
        hideLoader();
    }
}

function displayTransactionDetailsModal(transaction) {
    const modalBody = document.getElementById('transactionDetailsBody');
    if (!modalBody) return;

    const statusBadge = getStatusBadge(transaction.status);
    const amount = transaction.amount ? `${transaction.amount} ل.س` : 'غير محدد';

    // التأكد من وجود البيانات وتنظيفها
    const customerName = transaction.customer_name || 'غير محدد';
    const phoneNumber = transaction.phone_number || 'غير محدد';
    const mobileNumber = transaction.mobile_number || 'غير محدد';
    const companyName = transaction.company_name || 'غير محدد';
    const categoryName = transaction.category_name || 'غير محدد';
    const userName = transaction.user_name || 'غير محدد';
    const notes = transaction.notes || '';
    const staffNotes = transaction.staff_notes || '';

    modalBody.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-primary text-white">
                        <h6 class="mb-0"><i class="fas fa-user"></i> معلومات العميل</h6>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <strong><i class="fas fa-user me-2 text-primary"></i>الاسم:</strong>
                            <span class="ms-2">${customerName}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-phone me-2 text-success"></i>رقم الهاتف:</strong>
                            <span class="ms-2 font-monospace">${phoneNumber}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-mobile-alt me-2 text-info"></i>رقم الجوال:</strong>
                            <span class="ms-2 font-monospace">${mobileNumber}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-user-tie me-2 text-secondary"></i>المستخدم:</strong>
                            <span class="ms-2">${userName}</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-info text-white">
                        <h6 class="mb-0"><i class="fas fa-receipt"></i> تفاصيل المعاملة</h6>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <strong><i class="fas fa-building me-2 text-warning"></i>الشركة:</strong>
                            <span class="ms-2">${companyName}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-tags me-2 text-secondary"></i>الفئة:</strong>
                            <span class="ms-2">${categoryName}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-money-bill me-2 text-success"></i>المبلغ:</strong>
                            <span class="ms-2 fw-bold text-success">${amount}</span>
                        </div>
                        <div class="mb-3">
                            <strong><i class="fas fa-flag me-2"></i>الحالة:</strong>
                            <span class="ms-2">${statusBadge}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-secondary text-white">
                        <h6 class="mb-0"><i class="fas fa-clock"></i> معلومات زمنية</h6>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <p class="mb-2">
                                    <strong><i class="fas fa-calendar-plus me-2 text-info"></i>تاريخ الطلب:</strong>
                                    <br><span class="ms-4">${formatDate(transaction.created_at)}</span>
                                </p>
                            </div>
                            <div class="col-md-6">
                                ${transaction.approved_at ? `
                                    <p class="mb-2">
                                        <strong><i class="fas fa-calendar-check me-2 text-success"></i>تاريخ الموافقة:</strong>
                                        <br><span class="ms-4">${formatDate(transaction.approved_at)}</span>
                                    </p>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        ${notes || staffNotes ? `
            <div class="row mt-3">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="fas fa-sticky-note me-2 text-warning"></i>الملاحظات</h6>
                        </div>
                        <div class="card-body">
                            ${notes ? `
                                <div class="mb-3">
                                    <strong>ملاحظات العميل:</strong>
                                    <div class="text-muted mt-1">${notes}</div>
                                </div>
                            ` : ''}
                            ${staffNotes ? `
                                <div class="mb-0">
                                    <strong>ملاحظات الموظف:</strong>
                                    <div class="text-muted mt-1">${staffNotes}</div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        ` : ''}
    `;

    const modal = new bootstrap.Modal(document.getElementById('transactionDetailsModal'));
    modal.show();
}

function searchTransactions() {
    loadUserTransactions();
}

// دوال الاستعلام المحسنة
async function showInquiryModal(companyId, serviceName) {
    try {
        const modal = document.getElementById('inquiryModal');
        const modalTitle = document.getElementById('inquiryModalTitle');
        const companyIdInput = document.getElementById('inquiryCompanyId');
        
        if (!modal) {
            showMessage('نافذة الاستعلام غير متاحة', 'error');
            return;
        }

        if (modalTitle) modalTitle.textContent = serviceName || 'استعلام عن الزبائن';
        if (companyIdInput) companyIdInput.value = companyId || '';
        
        // مسح النتائج السابقة
        const resultDiv = document.getElementById('inquiryResult');
        if (resultDiv) {
            resultDiv.innerHTML = `
                <div class="text-center text-muted">
                    <i class="fas fa-search fa-2x mb-2"></i>
                    <p>أدخل رقم الهاتف للبحث عن بيانات الزبون</p>
                </div>
            `;
        }
        
        // مسح حقل البحث
        const phoneInput = document.getElementById('inquiryPhoneNumber');
        if (phoneInput) {
            phoneInput.value = '';
            phoneInput.focus();
        }
        
        // إظهار النموذج
        const bootstrapModal = new bootstrap.Modal(modal, {
            backdrop: 'static',
            keyboard: true
        });
        bootstrapModal.show();
        
        // التركيز على حقل الهاتف بعد فتح النموذج
        setTimeout(() => {
            if (phoneInput) {
                phoneInput.focus();
            }
        }, 500);
        
    } catch (error) {
        console.error('خطأ في فتح نافذة الاستعلام:', error);
        showMessage('خطأ في فتح نافذة الاستعلام', 'error');
    }
}

async function searchCustomerInquiry() {
    const phoneInput = document.getElementById('inquiryPhoneNumber');
    const resultDiv = document.getElementById('inquiryResult');
    
    if (!phoneInput || !resultDiv) {
        showMessage('عناصر النموذج غير متاحة', 'error');
        return;
    }

    const phoneNumber = phoneInput.value.trim();
    
    // التحقق من صحة رقم الهاتف
    if (!phoneNumber) {
        showMessage('يرجى إدخال رقم الهاتف', 'warning');
        phoneInput.focus();
        return;
    }

    if (phoneNumber.length < 10) {
        showMessage('رقم الهاتف يجب أن يكون 10 أرقام على الأقل', 'warning');
        phoneInput.focus();
        return;
    }

    // التحقق من تنسيق رقم الهاتف
    const phonePattern = /^(011|09)\d{8}$/;
    if (!phonePattern.test(phoneNumber)) {
        showMessage('تنسيق رقم الهاتف غير صحيح (يجب أن يبدأ بـ 011 أو 09)', 'warning');
        phoneInput.focus();
        return;
    }
    
    try {
        // إظهار مؤشر التحميل
        resultDiv.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">جاري البحث...</span>
                </div>
                <div class="mt-2">جاري البحث عن رقم ${phoneNumber}...</div>
            </div>
        `;
        
        // إنشاء طلب مع timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch(`/api/inquiry/${encodeURIComponent(phoneNumber)}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.found && data.customers && data.customers.length > 0) {
                let html = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> 
                        تم العثور على ${data.customers.length} نتيجة للرقم ${phoneNumber}
                    </div>
                `;
                
                data.customers.forEach((customer, index) => {
                    html += `
                        <div class="card mb-3 border-success">
                            <div class="card-header bg-light">
                                <h6 class="mb-0">
                                    <i class="fas fa-user text-primary"></i>
                                    ${customer.name || 'غير محدد'}
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <p class="mb-2">
                                            <strong><i class="fas fa-building text-info"></i> الشركة:</strong>
                                            <span class="text-primary">${customer.company_name || 'غير محدد'}</span>
                                        </p>
                                        <p class="mb-2">
                                            <strong><i class="fas fa-phone text-success"></i> الهاتف:</strong>
                                            <span dir="ltr">${customer.phone_number || 'غير محدد'}</span>
                                        </p>
                                        ${customer.mobile_number ? `
                                            <p class="mb-2">
                                                <strong><i class="fas fa-mobile-alt text-warning"></i> الجوال:</strong>
                                                <span dir="ltr">${customer.mobile_number}</span>
                                            </p>
                                        ` : ''}
                                    </div>
                                    <div class="col-md-6">
                                        ${customer.speed ? `
                                            <p class="mb-2">
                                                <strong><i class="fas fa-tachometer-alt text-info"></i> السرعة:</strong>
                                                <span>${customer.speed}</span>
                                            </p>
                                        ` : ''}
                                        ${customer.speed_price ? `
                                            <p class="mb-2">
                                                <strong><i class="fas fa-money-bill text-success"></i> السعر:</strong>
                                                <span class="text-success fw-bold">${customer.speed_price} ل.س</span>
                                            </p>
                                        ` : ''}
                                        <p class="mb-2">
                                            <strong><i class="fas fa-calendar text-secondary"></i> تاريخ الإضافة:</strong>
                                            <small>${formatDate(customer.created_at)}</small>
                                        </p>
                                    </div>
                                </div>
                                ${customer.notes ? `
                                    <div class="mt-2 pt-2 border-top">
                                        <strong><i class="fas fa-sticky-note text-warning"></i> ملاحظات:</strong>
                                        <div class="text-muted">${customer.notes}</div>
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                });
                
                resultDiv.innerHTML = html;
            } else {
                resultDiv.innerHTML = `
                    <div class="alert alert-info text-center">
                        <i class="fas fa-info-circle fa-2x mb-2"></i>
                        <h6>لم يتم العثور على بيانات</h6>
                        <p class="mb-0">لا توجد بيانات مسجلة لرقم الهاتف: <strong>${phoneNumber}</strong></p>
                        <small class="text-muted">تأكد من صحة الرقم وأنه مسجل في النظام</small>
                    </div>
                `;
            }
        } else if (response.status === 404) {
            resultDiv.innerHTML = `
                <div class="alert alert-warning text-center">
                    <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                    <h6>لم يتم العثور على بيانات</h6>
                    <p class="mb-0">رقم الهاتف <strong>${phoneNumber}</strong> غير مسجل في النظام</p>
                </div>
            `;
        } else if (response.status === 401) {
            resultDiv.innerHTML = `
                <div class="alert alert-danger text-center">
                    <i class="fas fa-lock fa-2x mb-2"></i>
                    <h6>خطأ في المصادقة</h6>
                    <p class="mb-0">انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى</p>
                </div>
            `;
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في البحث:', error);
        
        let errorMessage = 'حدث خطأ غير متوقع';
        let errorIcon = 'fas fa-exclamation-triangle';

        if (error.name === 'AbortError') {
            errorMessage = 'انتهت مهلة البحث (10 ثوان)';
            errorIcon = 'fas fa-clock';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'فشل في الاتصال بالخادم - تحقق من اتصال الإنترنت';
            errorIcon = 'fas fa-wifi';
        } else if (error.message.includes('NetworkError')) {
            errorMessage = 'خطأ في الشبكة - يرجى المحاولة مرة أخرى';
            errorIcon = 'fas fa-network-wired';
        } else {
            errorMessage = error.message;
        }

        resultDiv.innerHTML = `
            <div class="alert alert-danger text-center">
                <i class="${errorIcon} fa-2x mb-2"></i>
                <h6>خطأ في البحث</h6>
                <p class="mb-2">${errorMessage}</p>
                <button class="btn btn-outline-danger btn-sm" onclick="searchCustomerInquiry()">
                    <i class="fas fa-redo"></i> إعادة المحاولة
                </button>
            </div>
        `;
    }
}

// دوال طلب الخدمة المحسنة
function requestService(companyId, serviceType, serviceName) {
    try {
        const modal = document.getElementById('serviceRequestModal');
        const modalTitle = document.getElementById('serviceModalTitle');
        const form = document.getElementById('serviceRequestForm');
        
        if (!modal || !form) {
            showMessage('نموذج طلب الخدمة غير متاح', 'error');
            return;
        }

        // تعيين عنوان النموذج
        if (modalTitle) {
            modalTitle.textContent = serviceName || 'طلب تسديد جديد';
        }

        // إعادة تعيين النموذج
        form.reset();
        
        // تعيين القيم الافتراضية
        const categoryIdInput = document.getElementById('serviceCategoryId');
        const companyIdInput = document.getElementById('serviceCompanyId');
        const serviceTypeInput = document.getElementById('serviceType');
        
        if (categoryIdInput) categoryIdInput.value = companyId || '';
        if (companyIdInput) companyIdInput.value = companyId || '';
        if (serviceTypeInput) serviceTypeInput.value = serviceType || 'payment';
        
        // تحديث قائمة الشركات
        populateCompanySelect();
        
        // إظهار النموذج
        const bootstrapModal = new bootstrap.Modal(modal, {
            backdrop: 'static',
            keyboard: true
        });
        bootstrapModal.show();
        
        // التركيز على حقل الهاتف
        setTimeout(() => {
            const phoneInput = document.getElementById('servicePhoneNumber');
            if (phoneInput) {
                phoneInput.focus();
                phoneInput.value = '';
            }
        }, 500);

        console.log('تم فتح نموذج طلب الخدمة بنجاح');
        
    } catch (error) {
        console.error('خطأ في فتح نموذج طلب الخدمة:', error);
        showMessage('خطأ في فتح نموذج طلب الخدمة', 'error');
    }
}

async function searchExistingCustomer() {
    const phoneNumber = document.getElementById('servicePhoneNumber')?.value.trim();
    
    if (!phoneNumber) {
        showMessage('يرجى إدخال رقم الهاتف أولاً', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`/api/customers/search/${phoneNumber}`);
        if (response.ok) {
            const data = await response.json();
            
            if (data.found) {
                const customer = data.customer;
                
                // ملء البيانات
                const nameInput = document.getElementById('serviceCustomerName');
                const mobileInput = document.getElementById('serviceMobileNumber');
                const companySelect = document.getElementById('serviceCompanySelect');
                
                if (nameInput) nameInput.value = customer.name;
                if (mobileInput) mobileInput.value = customer.mobile_number || '';
                if (companySelect && customer.company_id) companySelect.value = customer.company_id;
                
                showMessage('تم العثور على بيانات العميل وملؤها تلقائياً', 'success');
                updateServiceDetails();
            } else {
                showMessage('لم يتم العثور على بيانات لهذا الرقم', 'info');
            }
        }
    } catch (error) {
        console.error('خطأ في البحث عن العميل:', error);
        showMessage('خطأ في البحث عن العميل', 'error');
    }
}

function updateServiceDetails() {
    const companySelect = document.getElementById('serviceCompanySelect');
    const selectedCompanyId = companySelect?.value;
    
    if (!selectedCompanyId) return;
    
    // يمكن إضافة منطق لتحديث تفاصيل الخدمة حسب الشركة المختارة
    // مثل تحديث السرعات المتاحة، الأسعار، إلخ
}

async function submitServiceRequest() {
    const form = document.getElementById('serviceRequestForm');
    if (!form) return;
    
    // جمع البيانات
    const phoneNumber = document.getElementById('servicePhoneNumber')?.value.trim();
    const customerName = document.getElementById('serviceCustomerName')?.value.trim();
    const companyId = document.getElementById('serviceCompanySelect')?.value;
    const mobileNumber = document.getElementById('serviceMobileNumber')?.value.trim();
    const amount = document.getElementById('serviceAmount')?.value;
    const notes = document.getElementById('serviceNotes')?.value.trim();
    
    // التحقق من البيانات المطلوبة
    if (!phoneNumber || !customerName || !companyId) {
        showMessage('يرجى ملء جميع البيانات المطلوبة', 'error');
        return;
    }
    
    if (!amount || amount <= 0) {
        showMessage('يرجى إدخال مبلغ صحيح', 'error');
        return;
    }
    
    try {
        showLoader('جاري إرسال الطلب...');
        
        const requestData = {
            category_id: 1, // يمكن تحديثه حسب الحاجة
            company_id: companyId,
            phone_number: phoneNumber,
            customer_name: customerName,
            mobile_number: mobileNumber,
            amount: parseFloat(amount),
            notes: notes
        };
        
        const response = await fetch('/api/payment-requests', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showMessage(result.message || 'تم إرسال الطلب بنجاح', 'success');
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('serviceRequestModal'));
            if (modal) modal.hide();
            
            // مسح النموذج
            form.reset();
            
            // تحديث الإحصائيات
            loadUserStats();
            
        } else {
            showMessage(result.error || 'حدث خطأ في إرسال الطلب', 'error');
        }
    } catch (error) {
        console.error('خطأ في إرسال الطلب:', error);
        showMessage('خطأ في الاتصال بالخادم', 'error');
    } finally {
        hideLoader();
    }
}

// عرض تفاصيل الزبون في مودال للإدارة
function displayCustomerDetailsModalAdmin(customer) {
    // التحقق من وجود المودال أولاً
    let modal = document.getElementById('customerDetailsModalAdmin');

    if (!modal) {
        // إنشاء المودال إذا لم يكن موجوداً
        const modalHtml = `
            <div class="modal fade" id="customerDetailsModalAdmin" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-info text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-user"></i> تفاصيل الزبون
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="card h-100">
                                        <div class="card-header bg-primary text-white">
                                            <h6 class="mb-0"><i class="fas fa-address-card"></i> المعلومات الأساسية</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="mb-3">
                                                <strong><i class="fas fa-user me-2 text-primary"></i>الاسم:</strong>
                                                <span id="customerDetailNameAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-phone me-2 text-success"></i>رقم الهاتف:</strong>
                                                <span id="customerDetailPhoneAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-mobile-alt me-2 text-info"></i>رقم الجوال:</strong>
                                                <span id="customerDetailMobileAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-building me-2 text-warning"></i>الشركة:</strong>
                                                <span id="customerDetailCompanyAdmin" class="ms-2"></span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card h-100">
                                        <div class="card-header bg-secondary text-white">
                                            <h6 class="mb-0"><i class="fas fa-info-circle"></i> معلومات إضافية</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="mb-3">
                                                <strong><i class="fas fa-user-plus me-2 text-success"></i>أضافه:</strong>
                                                <span id="customerDetailAddedByAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-calendar-plus me-2 text-info"></i>تاريخ الإضافة:</strong>
                                                <span id="customerDetailCreatedAtAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-user-edit me-2 text-warning"></i>آخر تعديل بواسطة:</strong>
                                                <span id="customerDetailUpdatedByAdmin" class="ms-2"></span>
                                            </div>
                                            <div class="mb-3">
                                                <strong><i class="fas fa-calendar-edit me-2 text-danger"></i>تاريخ آخر تعديل:</strong>
                                                <span id="customerDetailUpdatedAtAdmin" class="ms-2"></span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="row mt-3" id="customerNotesSectionAdmin" style="display: none;">
                                <div class="col-12">
                                    <div class="card">
                                        <div class="card-header bg-light">
                                            <h6 class="mb-0"><i class="fas fa-sticky-note me-2 text-info"></i>الملاحظات</h6>
                                        </div>
                                        <div class="card-body">
                                            <p id="customerDetailNotesAdmin" class="mb-0"></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary" onclick="editCustomerFromDetailsAdmin()">
                                <i class="fas fa-edit"></i> تعديل البيانات
                            </button>
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times"></i> إغلاق
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('customerDetailsModalAdmin');
    }

    // ملء البيانات الأساسية
    document.getElementById('customerDetailNameAdmin').textContent = customer.name || 'غير محدد';
    document.getElementById('customerDetailPhoneAdmin').textContent = customer.phone_number || 'غير محدد';
    document.getElementById('customerDetailMobileAdmin').textContent = customer.mobile_number || 'غير محدد';
    document.getElementById('customerDetailCompanyAdmin').textContent = customer.company_name || 'غير محدد';

    // ملء معلومات الإضافة والتعديل
    document.getElementById('customerDetailAddedByAdmin').textContent = customer.added_by_name || 'غير محدد';
    document.getElementById('customerDetailCreatedAtAdmin').textContent = formatDate(customer.created_at) || 'غير محدد';

    const updatedByElement = document.getElementById('customerDetailUpdatedByAdmin');
    const updatedAtElement = document.getElementById('customerDetailUpdatedAtAdmin');

    if (customer.updated_by_name && customer.updated_by_name !== 'لم يتم التعديل') {
        updatedByElement.textContent = customer.updated_by_name;
        updatedAtElement.textContent = formatDate(customer.updated_at) || 'غير محدد';
    } else {
        updatedByElement.textContent = 'لم يتم التعديل';
        updatedAtElement.textContent = '-';
    }

    // عرض الملاحظات إذا وجدت
    const notesSection = document.getElementById('customerNotesSectionAdmin');
    const notesElement = document.getElementById('customerDetailNotesAdmin');

    if (customer.notes && customer.notes.trim() !== '') {
        notesElement.textContent = customer.notes;
        notesSection.style.display = 'block';
    } else {
        notesSection.style.display = 'none';
    }

    // حفظ معرف الزبون للاستخدام في التعديل
    window.currentCustomerDetailsIdAdmin = customer.id;

    // إظهار المودال
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();
}

// تعديل الزبون من نافذة التفاصيل في الإدارة
function editCustomerFromDetailsAdmin() {
    if (window.currentCustomerDetailsIdAdmin) {
        // إغلاق نافذة التفاصيل
        const detailsModal = bootstrap.Modal.getInstance(document.getElementById('customerDetailsModalAdmin'));
        if (detailsModal) {
            detailsModal.hide();
        }

        // فتح نافذة التعديل
        setTimeout(() => {
            editCustomer(window.currentCustomerDetailsIdAdmin);
        }, 300);
    }
}

// عرض تفاصيل الزبون في مودال
function displayCustomerDetailsModal(customer) {
    // ملء البيانات الأساسية
    document.getElementById('customerDetailName').textContent = customer.name || 'غير محدد';
    document.getElementById('customerDetailPhone').textContent = customer.phone_number || 'غير محدد';
    document.getElementById('customerDetailMobile').textContent = customer.mobile_number || 'غير محدد';
    document.getElementById('customerDetailCompany').textContent = customer.company_name || 'غير محدد';

    // ملء معلومات الإضافة والتعديل
    document.getElementById('customerDetailAddedBy').textContent = customer.added_by_name || 'غير محدد';
    document.getElementById('customerDetailCreatedAt').textContent = formatDate(customer.created_at) || 'غير محدد';

    const updatedByElement = document.getElementById('customerDetailUpdatedBy');
    const updatedAtElement = document.getElementById('customerDetailUpdatedAt');

    if (customer.updated_by_name && customer.updated_by_name !== 'لم يتم التعديل') {
        updatedByElement.textContent = customer.updated_by_name;
        updatedAtElement.textContent = formatDate(customer.updated_at) || 'غير محدد';
    } else {
        updatedByElement.textContent = 'لم يتم التعديل';
        updatedAtElement.textContent = '-';
    }

    // عرض الملاحظات إذا وجدت
    const notesSection = document.getElementById('customerNotesSection');
    const notesElement = document.getElementById('customerDetailNotes');

    if (customer.notes && customer.notes.trim() !== '') {
        notesElement.textContent = customer.notes;
        notesSection.style.display = 'block';
    } else {
        notesSection.style.display = 'none';
    }

    // حفظ معرف الزبون للاستخدام في التعديل
    window.currentCustomerDetailsId = customer.id;

    // إظهار المودال
    const modal = new bootstrap.Modal(document.getElementById('customerDetailsModal'));
    modal.show();
}

// تعديل الزبون من نافذة التفاصيل
function editCustomerFromDetails() {
    if (window.currentCustomerDetailsId) {
        // إغلاق نافذة التفاصيل
        const detailsModal = bootstrap.Modal.getInstance(document.getElementById('customerDetailsModal'));
        if (detailsModal) {
            detailsModal.hide();
        }

        // فتح نافذة التعديل
        setTimeout(() => {
            editCustomer(window.currentCustomerDetailsId);
        }, 300);
    }
}

// تحميل المستخدمين
async function loadUsers() {
    const tableBody = document.getElementById('usersTableBody');

    try {
        console.log('بدء تحميل المستخدمين...');

        // إظهار مؤشر التحميل
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center">
                        <div class="spinner-border spinner-border-sm text-primary" role="status">
                            <span class="visually-hidden">جاري التحميل...</span>
                        </div>
                        جاري تحميل المستخدمين...
                    </td>
                </tr>
            `;
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 20000); // 20 ثانية

        const response = await fetch('/api/users', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        console.log('استجابة المستخدمين:', response.status);

        if (response.ok) {
            const data = await response.json();

            // التحقق من صحة البيانات
            if (Array.isArray(data)) {
                users = data;
                console.log('تم تحميل المستخدمين:', users.length);
                displayUsers(users);
                resetConnectionFailures();
            } else {
                throw new Error('البيانات المستلمة غير صحيحة');
            }
        } else if (response.status === 401 || response.status === 403) {
            // إعادة توجيه للتسجيل مرة واحدة فقط
            if (!window.location.pathname.includes('login') && !window.location.search.includes('session_expired')) {
                console.warn('انتهت صلاحية الجلسة');
                window.location.href = '/';
            }
            return;
        } else if (response.status === 502 || response.status === 503) {
            incrementConnectionFailures();
            throw new Error('الخادم غير متاح حالياً');
        } else {
            incrementConnectionFailures();
            let errorText = 'خطأ غير معروف';
            try {
                errorText = await response.text();
            } catch (e) {
                console.error('خطأ في قراءة نص الخطأ:', e);
            }
            throw new Error(`خطأ في الخادم (${response.status}): ${errorText}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل المستخدمين:', error);

        if (tableBody) {
            if (error.name === 'AbortError') {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-warning d-inline-block">
                                <i class="fas fa-clock"></i> انتهت مهلة تحميل المستخدمين
                                <br>
                                <button class="btn btn-sm btn-outline-warning mt-2" onclick="loadUsers()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            } else if (error.message.includes('Failed to fetch')) {
                incrementConnectionFailures();
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-danger d-inline-block">
                                <i class="fas fa-exclamation-triangle"></i> فشل في الاتصال بالخادم
                                <br>
                                <small>تحقق من اتصال الإنترنت</small>
                                <br>
                                <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadUsers()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                incrementConnectionFailures();
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-danger d-inline-block">
                                <i class="fas fa-exclamation-triangle"></i> ${error.message}
                                <br>
                                <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadUsers()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }

        if (!error.message.includes('انتهت صلاحية الجلسة')) {
            showAlert(`خطأ في تحميل المستخدمين: ${error.message}`, 'error');
        }
    }
}

function displayUsers(users) {
    const tableBody = document.getElementById('usersTableBody');
    if (!tableBody) return;

    if (!users || users.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center">لا توجد مستخدمين</td></tr>';
        return;
    }

    let html = '';
    users.forEach(user => {
        const statusBadge = user.is_active ? '<span class="badge bg-success">نشط</span>' : '<span class="badge bg-danger">معطل</span>';
        const roleBadge = user.role === 'admin' ? '<span class="badge bg-primary">مدير</span>' : '<span class="badge bg-secondary">مستخدم</span>';

        html += `
            <tr>
                <td>${user.name}</td>
                <td>${user.phone}</td>
                <td>${user.balance} ل.س</td>
                <td>${roleBadge}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" onclick="editUser(${user.id})" title="تعديل">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-outline-success" onclick="manageUserBalance(${user.id}, '${user.name}', ${user.balance})" title="إدارة الرصيد">
                            <i class="fas fa-wallet"></i>
                        </button>
                        <button class="btn btn-outline-info" onclick="sendUserNotification(${user.id}, '${user.name}')" title="إرسال إشعار">
                            <i class="fas fa-bell"></i>
                        </button>
                        ${user.role !== 'admin' ? `<button class="btn btn-outline-danger" onclick="deleteUser(${user.id})" title="حذف"><i class="fas fa-trash"></i></button>` : ''}
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = html;
}

// تحميل الزبائن
async function loadCustomers() {
    try {
        console.log('بدء تحميل الزبائن...');

        // إظهار مؤشر التحميل
        const tableBody = document.getElementById('customersTableBody');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="6" class="text-center"><div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">جاري التحميل...</span></div> جاري تحميل الزبائن...</td></tr>';
        }

        // إضافة timeout للطلب
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch('/api/customers', {
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        console.log('استجابة الزبائن:', response.status);

        if (response.ok) {
            customers = await response.json();
            console.log('تم تحميل الزبائن:', customers.length);
            displayCustomers(customers);
            resetConnectionFailures();
        } else if (response.status === 502 || response.status === 503) {
            incrementConnectionFailures();
            throw new Error('الخادم غير متاح حالياً');
        } else {
            const errorText = await response.text();
            console.error('خطأ في الاستجابة:', errorText);
            throw new Error(`فشل في تحميل الزبائن: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل الزبائن:', error);
        const tableBody = document.getElementById('customersTableBody');
        if (tableBody) {
            if (error.name === 'AbortError') {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-warning d-inline-block">
                                <i class="fas fa-clock"></i> انتهت مهلة الطلب
                                <br>
                                <button class="btn btn-sm btn-outline-warning mt-2" onclick="loadCustomers()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-danger d-inline-block">
                                <i class="fas fa-exclamation-triangle"></i> ${error.message}
                                <br>
                                <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadCustomers()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }

        if (!error.message.includes('الخادم غير متاح') && error.name !== 'AbortError') {
            showAlert('خطأ في تحميل الزبائن: ' + error.message, 'error');
        }
    }
}

function displayCustomers(customers) {
    const tableBody = document.getElementById('customersTableBody');
    if (!tableBody) return;

    if (!customers || customers.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center">لا توجد زبائن</td></tr>';
        return;
    }

    let html = '';
    customers.forEach(customer => {
        // تنظيف الاسم لتجنب مشاكل في JavaScript
        const safeName = customer.name.replace(/'/g, "\\'").replace(/"/g, '\\"');

        html += `
            <tr>
                <td>${customer.phone_number}</td>
                <td>
                    <span class="text-primary fw-bold user-name-clickable" 
                          onclick="showCustomerDetailsAdmin(${customer.id}); event.stopPropagation();" 
                          style="cursor: pointer; text-decoration: underline; transition: all 0.2s ease;"
                          title="اضغط لعرض التفاصيل"
                          onmouseover="this.style.color='#0056b3'; this.style.textShadow='0 0 2px rgba(0,86,179,0.3)';"
                          onmouseout="this.style.color=''; this.style.textShadow='';">
                        <i class="fas fa-user me-2"></i>
                        ${customer.name}
                    </span>
                </td>
                <td>${customer.mobile_number || '-'}</td>
                <td>${customer.company_name}</td>
                <td>${customer.notes || '-'}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-info" onclick="showCustomerDetailsAdmin(${customer.id})" title="التفاصيل">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-outline-primary" onclick="editCustomer(${customer.id})" title="تعديل">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="deleteCustomer(${customer.id})" title="حذف">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = html;
}

// تحميل طلبات التسديد
async function loadPaymentRequests() {
    try {
        console.log('بدء تحميل طلبات التسديد...');

        // إظهار مؤشر التحميل
        const tableBody = document.getElementById('paymentRequestsTableBody');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="8" class="text-center"><div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">جاري التحميل...</span></div> جاري تحميل البيانات...</td></tr>';
        }

        // إضافة timeout للطلب
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 seconds timeout

        const response = await fetch('/api/payment-requests', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        console.log('استجابة طلبات التسديد:', response.status);

        if (response.ok) {
            const data = await response.json();
            paymentRequests = Array.isArray(data) ? data : [];
            console.log('تم تحميل طلبات التسديد:', paymentRequests.length);
            displayPaymentRequests(paymentRequests);
            resetConnectionFailures();

            // تحديث إحصائيات الصفحة
            updateRequestsStatistics();
        } else if (response.status === 502 || response.status === 503) {
            incrementConnectionFailures();
            throw new Error('الخادم غير متاح حالياً، يرجى المحاولة مرة أخرى');
        } else {
            let errorText = 'خطأ غير معروف';
            try {
                errorText = await response.text();
            } catch (e) {
                console.error('خطأ في قراءة رسالة الخطأ:', e);
            }
            console.error('خطأ في الاستجابة:', errorText);
            throw new Error(`فشل في تحميل طلبات التسديد (${response.status})`);
        }
    } catch (error) {
        console.error('خطأ في تحميل طلبات التسديد:', error);
        const tableBody = document.getElementById('paymentRequestsTableBody');
        if (tableBody) {
            if (error.name === 'AbortError') {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center">
                            <div class="alert alert-warning d-inline-block">
                                <i class="fas fa-clock"></i> انتهت مهلة الطلب (15 ثانية)
                                <br>
                                <button class="btn btn-sm btn-outline-warning mt-2" onclick="loadPaymentRequests()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center">
                            <div class="alert alert-danger d-inline-block">
                                <i class="fas fa-exclamation-triangle"></i> ${error.message}
                                <br>
                                <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadPaymentRequests()">
                                    <i class="fas fa-redo"></i> إعادة المحاولة
                                </button>
                                <button class="btn btn-sm btn-outline-info mt-2 ms-2" onclick="reloadBasicData()">
                                    <i class="fas fa-sync"></i> إعادة تحميل شامل
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }

        // عدم إظهار تنبيه إضافي إذا كان الخطأ متعلق بالخادم أو timeout
        if (!error.message.includes('الخادم غير متاح') && error.name !== 'AbortError') {
            showAlert('خطأ في تحميل طلبات التسديد: ' + error.message, 'error');
        }
    }
}

function displayPaymentRequests(requests) {
    const tableBody = document.getElementById('paymentRequestsTableBody');
    if (!tableBody) return;

    // تطبيق الفلتر والبحث
    const searchTerm = document.getElementById('paymentRequestsSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('paymentRequestsStatusFilter')?.value || '';

    let filteredRequests = requests;
    if (searchTerm || statusFilter) {
        filteredRequests = requests.filter(request => {
            const matchesSearch = !searchTerm || 
                (request.phone_number && request.phone_number.toLowerCase().includes(searchTerm)) ||
                (request.customer_name && request.customer_name.toLowerCase().includes(searchTerm)) ||
                (request.company_name && request.company_name.toLowerCase().includes(searchTerm));

            const matchesStatus = !statusFilter || request.status === statusFilter;

            return matchesSearch && matchesStatus;
        });
    }

    if (!filteredRequests || filteredRequests.length === 0) {
        const message = searchTerm || statusFilter ? 'لا توجد نتائج تطابق البحث' : 'لا توجد طلبات تسديد';
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center">
                    <div class="alert alert-info d-inline-block">
                        <i class="fas fa-info-circle"></i> ${message}
                        ${(searchTerm || statusFilter) ? `
                            <br>
                            <button class="btn btn-sm btn-outline-info mt-2" onclick="clearSearchFilters()">
                                <i class="fas fa-times"></i> مسح الفلاتر
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    filteredRequests.forEach((request) => {
        const statusBadge = `<span class="badge bg-${getStatusBadgeClass(request.status)}">${getStatusText(request.status)}</span>`;
        const rowClass = request.status === 'pending' ? 'table-warning' : '';

        html += `
            <tr class="request-row ${rowClass}" style="cursor: pointer;" onclick="showRequestDetails(${request.id})">
                <td>${request.phone_number || 'غير محدد'}</td>
                <td>${request.customer_name || 'غير محدد'}</td>
                <td>${request.company_name || 'غير محدد'}</td>
                <td>
                    ${request.amount ? `${request.amount} ل.س` : '<span class="text-warning">غير محدد</span>'}
                </td>
                <td>${statusBadge}</td>
                <td>${formatDate(request.created_at)}</td>
                <td>${request.user_name || 'غير محدد'}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        ${request.status === 'pending' ? `
                            <button type="button" class="btn btn-success btn-sm" 
                                    onclick="event.stopPropagation(); handleRequestAction(${request.id}, 'approve')" 
                                    title="موافقة">
                                <i class="fas fa-check"></i>
                            </button>
                            <button type="button" class="btn btn-danger btn-sm" 
                                    onclick="event.stopPropagation(); handleRequestAction(${request.id}, 'reject')" 
                                    title="رفض">
                                <i class="fas fa-times"></i>
                            </button>
                        ` : ''}
                        <button type="button" class="btn btn-info btn-sm" 
                                onclick="event.stopPropagation(); showRequestDetails(${request.id})" 
                                title="التفاصيل">
                            <i class="fas fa-eye"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = html;
}

// باقي الدوال المساعدة...
function getStatusBadgeClass(status) {
    const classes = {
        'pending': 'warning',
        'approved': 'success',
        'rejected': 'danger'
    };
    return classes[status] || 'secondary';
}

function getStatusText(status) {
    const texts = {
        'pending': 'قيد الانتظار',
        'approved': 'مقبول',
        'rejected': 'مرفوض'
    };
    return texts[status] || status;
}

function formatDate(dateString) {
    if (!dateString) return '';

    // إنشاء كائن التاريخ
    const date = new Date(dateString);

    // إضافة 3 ساعات لتصحيح التوقيت
    date.setHours(date.getHours() + 3);

    // تنسيق التاريخ بالصيغة الميلادية العربية
    return date.toLocaleString('ar-EG', {
        calendar: 'gregory', // التقويم الميلادي
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Damascus' // توقيت دمشق
    });
}

// معالج محسن لأخطاء الجلسة
function handleSessionError(response) {
    if (response.status === 401) {
        console.warn('انتهت صلاحية الجلسة');

        // منع إعادة التوجيه المتكرر
        if (window.location.pathname === '/' || window.sessionExpiredHandled) {
            return true;
        }

        // تعيين علامة لمنع المعالجة المتكررة
        window.sessionExpiredHandled = true;

        // إيقاف جميع الطلبات المستمرة
        clearInterval(window.notificationInterval);
        clearInterval(window.statsInterval);

        // عرض رسالة واحدة فقط
        if (!window.sessionExpiredMessageShown) {
            window.sessionExpiredMessageShown = true;
            showAlert('انتهت صلاحية الجلسة. سيتم إعادة توجيهك لتسجيل الدخول.', 'warning');

            setTimeout(() => {
                window.location.href = '/';
            }, 2000);
        }

        return true;
    }
    return false;
}

// ملء قائمة الشركات
function populateCompanySelect() {
    const select = document.getElementById('serviceCompanySelect');
    if (!select) return;

    select.innerHTML = '<option value="">اختر الشركة</option>';

    if (companies.length === 0) {
        select.innerHTML += '<option value="" disabled>لا توجد شركات متاحة</option>';
        return;
    }

    // تجميع الشركات حسب الفئة
    const groupedCompanies = {};
    companies.forEach(company => {
        const categoryName = company.category_name || 'أخرى';
        if (!groupedCompanies[categoryName]) {
            groupedCompanies[categoryName] = [];
        }
        groupedCompanies[categoryName].push(company);
    });

    // إضافة الشركات مجمعة
    Object.keys(groupedCompanies).forEach(categoryName => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = categoryName;

        groupedCompanies[categoryName].forEach(company => {
            const option = document.createElement('option');
            option.value = company.id;
            option.textContent = company.name;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    });
}

// ملء قوائم الفئات
function populateCategorySelects() {
    const selects = ['companyCategory', 'categoryId'];

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (select) {
            const currentValue = select.value;
            select.innerHTML = '<option value="">اختر الفئة</option>';

            categories.forEach(category => {
                const option = document.createElement('option');
                option.value = category.id;
                option.textContent = category.name;
                if (category.id == currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        }
    });
}

// دوال أخرى ضرورية
async function loadCompaniesAdmin() {
    // تحميل الشركات للإدارة
    await loadCompanies();
}

async function loadSiteSettingsAdmin() {
    // تحميل إعدادات الموقع للإدارة
    await loadSiteSettings();
}

async function loadBackups() {
    // تحميل النسخ الاحتياطية
    console.log('تم تحميل النسخ الاحتياطية:', Math.floor(Math.random() * 10));
}

// تحديث إحصائيات الطلبات
function updateRequestsStatistics() {
    // تحديث الإحصائيات
}

// تأكد من توفر الدوال عالمياً
if (typeof window !== 'undefined') {
    // دوال الإدارة الرئيسية
    window.showAdminSection = showAdminSection;

    // دوال إدارة المستخدمين
    window.editUser = editUser;
    window.saveUser = saveUser;
    window.showAddUserModal = showAddUserModal;
    window.deleteUser = deleteUser;
    window.manageUserBalance = manageUserBalance;
    window.sendUserNotification = sendUserNotification;

    // دوال إدارة الزبائن
    window.showCustomerDetails = showCustomerDetails;
    window.showCustomerDetailsAdmin = showCustomerDetailsAdmin;
    window.displayCustomerDetailsModal = displayCustomerDetailsModal;
    window.displayCustomerDetailsModalAdmin = displayCustomerDetailsModalAdmin;
    window.editCustomerFromDetails = editCustomerFromDetails;
    window.editCustomerFromDetailsAdmin = editCustomerFromDetailsAdmin;
    window.loadCustomers = loadCustomers;
    window.displayCustomers = displayCustomers;

    // دوال العرض والرسائل
    window.showMessage = showMessage;
    window.showAlert = showAlert;
    window.showLoader = showLoader;
    window.hideLoader = hideLoader;

    // دوال أخرى مهمة
    window.loadUsers = loadUsers;
    window.displayUsers = displayUsers;

    // دوال إدارة طلبات التسديد
    window.loadPaymentRequests = loadPaymentRequests;
    window.displayPaymentRequests = displayPaymentRequests;

    console.log('تم تصدير جميع الدوال عالمياً بنجاح');
}

// دالة إضافية لإدارة تفاصيل الزبون من لوحة الإدارة
async function showCustomerDetailsAdmin(customerId) {
    try {
        showLoader('جاري تحميل تفاصيل الزبون...');

        const response = await fetch(`/api/customers/${customerId}`);
        if (response.ok) {
            const customer = await response.json();
            displayCustomerDetailsModalAdmin(customer);
        } else if (response.status === 404) {
            showMessage('الزبون غير موجود', 'error');
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في تحميل تفاصيل الزبون:', error);
        showMessage('خطأ في تحميل تفاصيل الزبون', 'error');
    } finally {
        hideLoader();
    }
}

// دوال إضافية لصفحة المستخدم
function clearSearchFilters() {
    const searchInput = document.getElementById('paymentRequestsSearch');
    const statusFilter = document.getElementById('paymentRequestsStatusFilter');
    
    if (searchInput) searchInput.value = '';
    if (statusFilter) statusFilter.value = '';
    
    // إعادة تحميل البيانات
    if (typeof loadPaymentRequests === 'function') {
        loadPaymentRequests();
    }
}

function updateRequestsStatistics() {
    // تحديث إحصائيات الطلبات إذا كانت متاحة
    if (typeof loadUserStats === 'function') {
        loadUserStats();
    }
}

// دالة لإظهار مؤشر التحميل العامة
function showLoadingOverlay(message = 'جاري التحميل...') {
    showLoader(message);
}

function hideLoadingOverlay() {
    hideLoader();
}

// التأكد من أن جميع الدوال متاحة عالمياً
if (typeof window !== 'undefined') {
    // دوال تفاصيل الزبون
    window.showCustomerDetailsAdmin = showCustomerDetailsAdmin;
    window.displayCustomerDetailsModalAdmin = displayCustomerDetailsModalAdmin;
    
    // دوال صفحة المستخدم
    window.loadNotifications = loadNotifications;
    window.displayNotifications = displayNotifications;
    window.markNotificationRead = markNotificationRead;
    window.markAllNotificationsRead = markAllNotificationsRead;
    window.loadUserTransactions = loadUserTransactions;
    window.displayUserTransactions = displayUserTransactions;
    window.showTransactionDetails = showTransactionDetails;
    window.displayTransactionDetailsModal = displayTransactionDetailsModal;
    window.searchTransactions = searchTransactions;
    window.showInquiryModal = showInquiryModal;
    window.searchCustomerInquiry = searchCustomerInquiry;
    window.requestService = requestService;
    window.searchExistingCustomer = searchExistingCustomer;
    window.updateServiceDetails = updateServiceDetails;
    window.submitServiceRequest = submitServiceRequest;
    window.clearSearchFilters = clearSearchFilters;
    window.updateRequestsStatistics = updateRequestsStatistics;
    window.getStatusBadge = getStatusBadge;
    window.showLoadingOverlay = showLoadingOverlay;
    window.hideLoadingOverlay = hideLoadingOverlay;
    
    // دوال التنقل
    window.showSection = showSection;
    
    console.log('تم تصدير دوال تفاصيل الزبون بنجاح');
    console.log('تم تصدير جميع دوال صفحة المستخدم بنجاح');
}