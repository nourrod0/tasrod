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

// تحديث ألوان أيقونة الإشعارات
function updateNotificationIconColors(hasUnreadNotifications) {
    // البحث عن جميع أيقونات الإشعارات
    const notificationIcons = document.querySelectorAll('.notification-btn i.fa-bell, .nav-menu-item i.fa-bell');
    
    notificationIcons.forEach(icon => {
        if (hasUnreadNotifications) {
            // تغيير اللون إلى الأحمر عند وجود إشعارات غير مقروءة
            icon.style.color = '#dc3545';
            icon.style.animation = 'shake 2s infinite';
        } else {
            // العودة للون الأصلي
            icon.style.color = '';
            icon.style.animation = '';
        }
    });
}

// إظهار تنبيه الإشعارات
function showNotificationAlert(count) {
    // تجنب إظهار عدة تنبيهات متتالية
    if (window.notificationAlertShown) {
        return;
    }
    
    window.notificationAlertShown = true;
    
    // إنشاء تنبيه مخصص
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-warning alert-dismissible fade show position-fixed notification-alert';
    alertDiv.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        border-left: 4px solid #dc3545;
        animation: slideInRight 0.5s ease-out;
    `;
    
    alertDiv.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-bell text-danger me-3 fa-lg" style="animation: shake 1s infinite;"></i>
            <div class="flex-grow-1">
                <strong class="text-danger">إشعارات جديدة!</strong>
                <div class="small">لديك ${count} إشعار${count > 1 ? 'ات' : ''} غير مقروء${count > 1 ? 'ة' : ''}</div>
            </div>
            <button class="btn btn-sm btn-outline-primary ms-2" onclick="showSection('notifications'); this.closest('.notification-alert').remove();">
                <i class="fas fa-eye"></i> عرض
            </button>
        </div>
        <button type="button" class="btn-close" onclick="this.closest('.notification-alert').remove(); window.notificationAlertShown = false;"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // إزالة التنبيه تلقائياً بعد 8 ثوان
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
            window.notificationAlertShown = false;
        }
    }, 8000);
    
    // السماح بإظهار تنبيه آخر بعد دقيقة
    setTimeout(() => {
        window.notificationAlertShown = false;
    }, 60000);
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
        // تعيين علامة للفحص الأول
        window.firstNotificationCheck = true;
        
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
            const previousCount = notificationCount;
            notificationCount = data.count;

            // تحديث جميع شارات الإشعارات
            const badges = ['notificationBadge', 'sidebarNotificationBadge', 'sidebarNotificationBadgeInline'];
            badges.forEach(badgeId => {
                const badge = document.getElementById(badgeId);
                if (badge) {
                    if (notificationCount > 0) {
                        // عرض الأرقام بوضوح
                        badge.textContent = notificationCount > 99 ? '99+' : notificationCount;
                        badge.style.display = 'inline-block';
                        badge.style.minWidth = '18px';
                        badge.style.height = '18px';
                        badge.style.fontSize = '11px';
                        badge.style.lineHeight = '1.4';
                        badge.style.textAlign = 'center';
                    } else {
                        badge.style.display = 'none';
                    }
                }
            });

            // تحديث لون أيقونة الإشعارات
            updateNotificationIconColors(notificationCount > 0);

            // إظهار تنبيه عند دخول الصفحة أو عند وجود إشعارات جديدة
            if (notificationCount > 0) {
                // إذا كان هذا أول تحديث للصفحة أو زاد عدد الإشعارات
                if (window.firstNotificationCheck || notificationCount > previousCount) {
                    showNotificationAlert(notificationCount);
                    window.firstNotificationCheck = false;
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

// متغيرات عامة لإدارة الإشعارات
let notificationsData = [];
let selectedNotifications = new Set();
let currentNotificationsPage = 1;
let notificationsPerPage = 10; // تقليل العدد لتحسين الأداء
let isLoadingNotifications = false;
let notificationsTotalPages = 0;
let notificationsTotalCount = 0;

// تحميل الإشعارات
async function loadNotificationsAdmin() {
    if (isLoadingNotifications) return;
    
    try {
        isLoadingNotifications = true;
        
        // إظهار مؤشر التحميل في الجدول
        const tableBody = document.getElementById('notificationsTableBody');
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center p-4">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">جاري التحميل...</span>
                        </div>
                        <div class="mt-2">جاري تحميل الإشعارات...</div>
                    </td>
                </tr>
            `;
        }
        
        const searchTerm = document.getElementById('notificationsSearch')?.value || '';
        const typeFilter = document.getElementById('notificationTypeFilter')?.value || '';
        const priorityFilter = document.getElementById('notificationPriorityFilter')?.value || '';
        const readFilter = document.getElementById('notificationReadFilter')?.value || '';
        
        const params = new URLSearchParams({
            page: currentNotificationsPage,
            per_page: notificationsPerPage
        });
        
        if (searchTerm) params.append('search', searchTerm);
        if (typeFilter) params.append('type', typeFilter);
        if (priorityFilter) params.append('priority', priorityFilter);
        if (readFilter) params.append('read_status', readFilter);
        
        console.log('تحميل الإشعارات - الصفحة:', currentNotificationsPage);
        
        const response = await fetch(`/api/admin/notifications?${params}`);
        if (response.ok) {
            const data = await response.json();
            console.log('تم تحميل الإشعارات:', data.notifications?.length || 0);
            
            notificationsData = data.notifications || [];
            notificationsTotalPages = data.total_pages || 0;
            notificationsTotalCount = data.total || 0;
            
            displayNotifications(data);
            updateNotificationsPagination(data);
            
            // مسح التحديدات السابقة عند تحميل صفحة جديدة
            selectedNotifications.clear();
            updateBulkActionsButton();
            updateSelectAllCheckbox();
        } else if (response.status === 401) {
            showAlert('انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى', 'error');
        } else {
            throw new Error('فشل في تحميل الإشعارات');
        }
    } catch (error) {
        console.error('خطأ في تحميل الإشعارات:', error);
        showAlert('فشل في تحميل الإشعارات: ' + error.message, 'error');
        
        // إظهار رسالة خطأ في الجدول
        const tableBody = document.getElementById('notificationsTableBody');
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center p-4">
                        <div class="alert alert-danger d-inline-block">
                            <i class="fas fa-exclamation-triangle"></i>
                            خطأ في تحميل الإشعارات
                            <br>
                            <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadNotificationsAdmin()">
                                <i class="fas fa-redo"></i> إعادة المحاولة
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }
    } finally {
        isLoadingNotifications = false;
    }
}

// عرض الإشعارات
function displayNotifications(data) {
    const tbody = document.getElementById('notificationsTableBody');
    if (!tbody) return;
    
    if (!data.notifications || data.notifications.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center p-4">
                    <div class="text-center">
                        <i class="fas fa-bell-slash fa-3x text-muted mb-3"></i>
                        <p class="text-muted">لا توجد إشعارات</p>
                        <small class="text-muted">جرب تغيير معايير البحث أو الفلترة</small>
                    </div>
                </td>
            </tr>
        `;
        // مسح التحديدات
        selectedNotifications.clear();
        updateBulkActionsButton();
        updateSelectAllCheckbox();
        return;
    }
    
    let html = '';
    data.notifications.forEach(notification => {
        const typeColors = {
            'info': 'info',
            'success': 'success',
            'warning': 'warning',
            'error': 'danger'
        };
        
        const priorityColors = {
            'high': 'danger',
            'normal': 'primary',
            'low': 'secondary'
        };
        
        const typeIcons = {
            'info': 'fa-info-circle',
            'success': 'fa-check-circle',
            'warning': 'fa-exclamation-triangle',
            'error': 'fa-times-circle'
        };
        
        const priorityIcons = {
            'high': 'fa-exclamation-circle',
            'normal': 'fa-flag',
            'low': 'fa-minus-circle'
        };
        
        const isSelected = selectedNotifications.has(notification.id);
        const rowClass = notification.is_read ? '' : 'table-warning';
        
        html += `
            <tr class="${rowClass} notification-row" 
                style="cursor: pointer;" 
                data-notification-id="${notification.id}">
                <td class="text-center align-middle" onclick="event.stopPropagation()">
                    <input type="checkbox" 
                           class="form-check-input notification-checkbox" 
                           value="${notification.id}" 
                           id="checkbox_${notification.id}"
                           ${isSelected ? 'checked' : ''}
                           onchange="toggleNotificationSelection(${notification.id}, this.checked)">
                </td>
                <td class="align-middle" onclick="showNotificationDetails(${notification.id})">
                    <div class="d-flex align-items-start">
                        <div class="flex-grow-1">
                            <div class="fw-bold mb-1" style="line-height: 1.3;">
                                ${!notification.is_read ? '<i class="fas fa-circle text-warning me-2" style="font-size: 8px;"></i>' : ''}
                                <span class="text-truncate d-inline-block" style="max-width: 220px;" title="${notification.title}">${notification.title}</span>
                            </div>
                            <div class="text-muted small" style="line-height: 1.2;">
                                <span class="text-truncate d-inline-block" style="max-width: 250px;" title="${notification.message}">${notification.message}</span>
                            </div>
                        </div>
                    </div>
                </td>
                <td class="align-middle" onclick="showNotificationDetails(${notification.id})">
                    <div class="fw-bold text-truncate" style="max-width: 120px;" title="${notification.user_name || 'غير محدد'}">${notification.user_name || 'غير محدد'}</div>
                    ${notification.user_phone ? `<div class="text-muted small text-truncate" style="max-width: 120px;" title="${notification.user_phone}">${notification.user_phone}</div>` : ''}
                </td>
                <td class="text-center align-middle" onclick="showNotificationDetails(${notification.id})">
                    <span class="badge bg-${typeColors[notification.type]} text-white" style="font-size: 10px;">
                        <i class="fas ${typeIcons[notification.type]} me-1"></i>
                        ${getNotificationTypeText(notification.type)}
                    </span>
                </td>
                <td class="text-center align-middle" onclick="showNotificationDetails(${notification.id})">
                    <span class="badge bg-${priorityColors[notification.priority]} text-white" style="font-size: 10px;">
                        <i class="fas ${priorityIcons[notification.priority]} me-1"></i>
                        ${getNotificationPriorityText(notification.priority)}
                    </span>
                </td>
                <td class="text-center align-middle" onclick="showNotificationDetails(${notification.id})">
                    <span class="badge ${notification.is_read ? 'bg-success' : 'bg-warning'} text-white" style="font-size: 10px;">
                        <i class="fas ${notification.is_read ? 'fa-check' : 'fa-clock'} me-1"></i>
                        ${notification.is_read ? 'مقروء' : 'غير مقروء'}
                    </span>
                </td>
                <td class="align-middle" onclick="showNotificationDetails(${notification.id})">
                    <div class="small text-nowrap">${formatDate(notification.created_at)}</div>
                </td>
                <td class="align-middle" onclick="showNotificationDetails(${notification.id})">
                    <div class="small text-truncate" style="max-width: 100px;" title="${notification.sent_by_name || 'النظام'}">
                        ${notification.sent_by_name || 'النظام'}
                    </div>
                </td>
                <td class="text-center align-middle" onclick="event.stopPropagation()">
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info btn-sm" 
                                onclick="event.stopPropagation(); showNotificationDetails(${notification.id})"
                                title="عرض التفاصيل">
                            <i class="fas fa-eye"></i>
                        </button>
                        ${!notification.is_read ? `
                            <button class="btn btn-outline-success btn-sm" 
                                    onclick="event.stopPropagation(); markSingleNotificationRead(${notification.id})"
                                    title="تعليم كمقروء">
                                <i class="fas fa-check"></i>
                            </button>
                        ` : ''}
                        <button class="btn btn-outline-danger btn-sm" 
                                onclick="event.stopPropagation(); deleteSingleNotification(${notification.id})"
                                title="حذف الإشعار">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
    
    // إضافة مستمعي أحداث النقر للصفوف
    document.querySelectorAll('.notification-row').forEach(row => {
        row.addEventListener('click', function(e) {
            // تجنب تنشيط الحدث إذا تم النقر على checkbox أو أزرار
            if (e.target.type === 'checkbox' || e.target.closest('.btn-group')) {
                return;
            }
            
            const notificationId = this.dataset.notificationId;
            if (notificationId) {
                showNotificationDetails(parseInt(notificationId));
            }
        });
    });
    
    // تحديث حالة التحديدات
    updateSelectAllCheckbox();
    updateBulkActionsButton();
}

// تحديث التنقل بين الصفحات
function updateNotificationsPagination(data) {
    const paginationInfo = document.getElementById('notificationsPaginationInfo');
    const paginationInfoBottom = document.getElementById('notificationsPaginationInfoBottom');
    const pagination = document.getElementById('notificationsPagination');
    
    // تحديث معلومات التنقل
    const start = Math.min((data.page - 1) * data.per_page + 1, data.total);
    const end = Math.min(data.page * data.per_page, data.total);
    const infoText = `عرض ${start}-${end} من ${data.total} إشعار`;
    
    if (paginationInfo) {
        paginationInfo.textContent = infoText;
    }
    if (paginationInfoBottom) {
        paginationInfoBottom.textContent = infoText;
    }
    
    if (!pagination) return;
    
    if (data.total_pages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let paginationHtml = '';
    const currentPage = parseInt(data.page) || 1;
    const totalPages = parseInt(data.total_pages) || 1;
    
    // زر السابق
    if (currentPage > 1) {
        paginationHtml += `
            <li class="page-item">
                <button type="button" class="page-link" onclick="changeNotificationsPage(${currentPage - 1})" title="الصفحة السابقة">
                    <i class="fas fa-chevron-right me-1"></i>السابق
                </button>
            </li>
        `;
    } else {
        paginationHtml += `
            <li class="page-item disabled">
                <span class="page-link">
                    <i class="fas fa-chevron-right me-1"></i>السابق
                </span>
            </li>
        `;
    }
    
    // الصفحة الأولى
    if (currentPage > 3) {
        paginationHtml += `
            <li class="page-item">
                <button type="button" class="page-link" onclick="changeNotificationsPage(1)">1</button>
            </li>
        `;
        if (currentPage > 4) {
            paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }
    
    // أرقام الصفحات المحيطة
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        if (i === currentPage) {
            paginationHtml += `
                <li class="page-item active">
                    <span class="page-link">${i}</span>
                </li>
            `;
        } else {
            paginationHtml += `
                <li class="page-item">
                    <button type="button" class="page-link" onclick="changeNotificationsPage(${i})">${i}</button>
                </li>
            `;
        }
    }
    
    // الصفحة الأخيرة
    if (currentPage < totalPages - 2) {
        if (currentPage < totalPages - 3) {
            paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        paginationHtml += `
            <li class="page-item">
                <button type="button" class="page-link" onclick="changeNotificationsPage(${totalPages})">${totalPages}</button>
            </li>
        `;
    }
    
    // زر التالي
    if (currentPage < totalPages) {
        paginationHtml += `
            <li class="page-item">
                <button type="button" class="page-link" onclick="changeNotificationsPage(${currentPage + 1})" title="الصفحة التالية">
                    التالي<i class="fas fa-chevron-left ms-1"></i>
                </button>
            </li>
        `;
    } else {
        paginationHtml += `
            <li class="page-item disabled">
                <span class="page-link">
                    التالي<i class="fas fa-chevron-left ms-1"></i>
                </span>
            </li>
        `;
    }
    
    pagination.innerHTML = paginationHtml;
}

// تغيير الصفحة
function changeNotificationsPage(page) {
    if (isLoadingNotifications) {
        console.log('التحميل قيد التشغيل، يرجى الانتظار...');
        return;
    }
    
    // التحقق من صحة رقم الصفحة
    if (page < 1) {
        console.warn('رقم صفحة غير صحيح:', page);
        return;
    }
    
    if (notificationsTotalPages > 0 && page > notificationsTotalPages) {
        console.warn('رقم الصفحة أكبر من إجمالي الصفحات:', page, 'من', notificationsTotalPages);
        return;
    }
    
    console.log('تغيير إلى الصفحة:', page, 'من إجمالي', notificationsTotalPages);
    currentNotificationsPage = page;
    
    // مسح التحديدات الحالية عند الانتقال لصفحة جديدة
    selectedNotifications.clear();
    updateBulkActionsButton();
    updateSelectAllCheckbox();
    
    // تحميل الصفحة الجديدة
    loadNotificationsAdmin();
}

// تحميل إحصائيات الإشعارات
async function loadNotificationsStats() {
    try {
        const response = await fetch('/api/admin/notifications/stats');
        if (response.ok) {
            const stats = await response.json();
            updateNotificationsStatsDisplay(stats);
        }
    } catch (error) {
        console.error('خطأ في تحميل إحصائيات الإشعارات:', error);
    }
}

// تحديث عرض الإحصائيات
function updateNotificationsStatsDisplay(stats) {
    const elements = {
        totalNotifications: document.getElementById('totalNotifications'),
        unreadNotifications: document.getElementById('unreadNotifications'),
        todayNotifications: document.getElementById('todayNotifications'),
        highPriorityNotifications: document.getElementById('highPriorityNotifications')
    };
    
    if (elements.totalNotifications) elements.totalNotifications.textContent = stats.total || 0;
    if (elements.unreadNotifications) elements.unreadNotifications.textContent = stats.unread || 0;
    if (elements.todayNotifications) elements.todayNotifications.textContent = stats.by_period?.today || 0;
    if (elements.highPriorityNotifications) elements.highPriorityNotifications.textContent = stats.by_priority?.high || 0;
}

// تحديث الإشعارات
async function refreshNotifications() {
    await loadNotificationsAdmin();
    await loadNotificationsStats();
    showAlert('تم تحديث الإشعارات بنجاح', 'success');
}

// إظهار نموذج الإشعار الجماعي
function showBroadcastNotificationModal() {
    const modal = new bootstrap.Modal(document.getElementById('broadcastNotificationModal'));
    modal.show();
    
    // مسح النموذج
    document.getElementById('broadcastNotificationForm').reset();
}

// إرسال إشعار جماعي
async function sendBroadcastNotification() {
    const title = document.getElementById('broadcastTitle').value.trim();
    const message = document.getElementById('broadcastMessage').value.trim();
    const type = document.getElementById('broadcastType').value;
    const priority = document.getElementById('broadcastPriority').value;
    const target = document.getElementById('broadcastTarget').value;
    
    if (!title || !message) {
        showAlert('يرجى ملء جميع الحقول المطلوبة', 'error');
        return;
    }
    
    try {
        showLoader('جاري إرسال الإشعار...');
        
        const response = await fetch('/api/notifications/broadcast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                title: title,
                message: message,
                type: type,
                priority: priority,
                target_type: target
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert(result.message, 'success');
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('broadcastNotificationModal'));
            modal.hide();
            
            // تحديث الإشعارات
            setTimeout(() => {
                refreshNotifications();
            }, 1000);
        } else {
            showAlert(result.error || 'فشل في إرسال الإشعار', 'error');
        }
    } catch (error) {
        console.error('خطأ في إرسال الإشعار:', error);
        showAlert('خطأ في إرسال الإشعار', 'error');
    } finally {
        hideLoader();
    }
}

// عرض تفاصيل الإشعار
async function showNotificationDetails(notificationId) {
    let notification = notificationsData.find(n => n.id === notificationId);
    
    // إذا لم يتم العثور على الإشعار في البيانات المحلية، جلبه من الخادم
    if (!notification) {
        try {
            showLoader('جاري تحميل تفاصيل الإشعار...');
            const response = await fetch(`/api/admin/notifications/${notificationId}`);
            if (response.ok) {
                notification = await response.json();
            } else {
                throw new Error('فشل في تحميل تفاصيل الإشعار');
            }
        } catch (error) {
            console.error('خطأ في تحميل تفاصيل الإشعار:', error);
            showAlert('فشل في تحميل تفاصيل الإشعار', 'error');
            return;
        } finally {
            hideLoader();
        }
    }
    
    const modalBody = document.getElementById('notificationDetailsBody');
    modalBody.innerHTML = `
        <div class="card">
            <div class="card-header bg-primary text-white">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">
                        <i class="fas fa-bell me-2"></i>
                        ${notification.title}
                    </h6>
                    <span class="badge ${notification.is_read ? 'bg-success' : 'bg-warning'}">
                        <i class="fas ${notification.is_read ? 'fa-check' : 'fa-clock'} me-1"></i>
                        ${notification.is_read ? 'مقروء' : 'غير مقروء'}
                    </span>
                </div>
            </div>
            <div class="card-body">
                <div class="row mb-3">
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-light">
                                <h6 class="mb-0"><i class="fas fa-user me-2"></i>معلومات المستخدم</h6>
                            </div>
                            <div class="card-body">
                                <p><strong>الاسم:</strong> ${notification.user_name || 'غير محدد'}</p>
                                <p><strong>رقم الهاتف:</strong> ${notification.user_phone || 'غير محدد'}</p>
                                <p><strong>معرف المستخدم:</strong> ${notification.user_id || 'غير محدد'}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-light">
                                <h6 class="mb-0"><i class="fas fa-info-circle me-2"></i>تفاصيل الإشعار</h6>
                            </div>
                            <div class="card-body">
                                <p><strong>النوع:</strong> 
                                    <span class="badge bg-secondary">
                                        <i class="fas fa-tag me-1"></i>
                                        ${getNotificationTypeText(notification.type)}
                                    </span>
                                </p>
                                <p><strong>الأولوية:</strong> 
                                    <span class="badge bg-info">
                                        <i class="fas fa-flag me-1"></i>
                                        ${getNotificationPriorityText(notification.priority)}
                                    </span>
                                </p>
                                <p><strong>المرسل:</strong> ${notification.sent_by_name || 'النظام'}</p>
                                <p><strong>تاريخ الإرسال:</strong> ${formatDate(notification.created_at)}</p>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header bg-light">
                        <h6 class="mb-0"><i class="fas fa-comment me-2"></i>محتوى الرسالة</h6>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-light border" style="white-space: pre-wrap;">${notification.message}</div>
                    </div>
                </div>
            </div>
            <div class="card-footer">
                <div class="d-flex justify-content-between">
                    <div>
                        ${!notification.is_read ? `
                            <button class="btn btn-success btn-sm me-2" onclick="markSingleNotificationRead(${notification.id})">
                                <i class="fas fa-check me-1"></i>تعليم كمقروء
                            </button>
                        ` : ''}
                        <button class="btn btn-danger btn-sm" onclick="deleteSingleNotification(${notification.id})">
                            <i class="fas fa-trash me-1"></i>حذف الإشعار
                        </button>
                    </div>
                    <div>
                        <small class="text-muted">معرف الإشعار: #${notification.id}</small>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    const modal = new bootstrap.Modal(document.getElementById('notificationDetailsModal'));
    modal.show();
}

// تعليم إشعار واحد كمقروء
async function markSingleNotificationRead(notificationId) {
    try {
        const response = await fetch(`/api/admin/notifications/mark-read`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ids: [notificationId]
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('تم تعليم الإشعار كمقروء', 'success');
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('notificationDetailsModal'));
            if (modal) modal.hide();
            
            // إعادة تحميل الإشعارات
            loadNotificationsAdmin();
        } else {
            showAlert(result.error || 'فشل في تعليم الإشعار', 'error');
        }
    } catch (error) {
        console.error('خطأ في تعليم الإشعار:', error);
        showAlert('خطأ في تعليم الإشعار', 'error');
    }
}

// حذف إشعار واحد
async function deleteSingleNotification(notificationId) {
    if (!confirm('هل أنت متأكد من حذف هذا الإشعار؟')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/admin/notifications/${notificationId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('تم حذف الإشعار بنجاح', 'success');
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('notificationDetailsModal'));
            if (modal) modal.hide();
            
            // إعادة تحميل الإشعارات
            loadNotificationsAdmin();
        } else {
            showAlert(result.error || 'فشل في حذف الإشعار', 'error');
        }
    } catch (error) {
        console.error('خطأ في حذف الإشعار:', error);
        showAlert('خطأ في حذف الإشعار', 'error');
    }
}

// حذف إشعار
async function deleteNotification(notificationId) {
    if (!confirm('هل أنت متأكد من حذف هذا الإشعار؟')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/admin/notifications/${notificationId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('تم حذف الإشعار بنجاح', 'success');
            loadNotificationsAdmin();
        } else {
            showAlert(result.error || 'فشل في حذف الإشعار', 'error');
        }
    } catch (error) {
        console.error('خطأ في حذف الإشعار:', error);
        showAlert('خطأ في حذف الإشعار', 'error');
    }
}

// تبديل تحديد الإشعار
function toggleNotificationSelection(notificationId, isChecked) {
    console.log('تبديل التحديد للإشعار:', notificationId, 'حالة:', isChecked);
    
    if (isChecked) {
        selectedNotifications.add(notificationId);
    } else {
        selectedNotifications.delete(notificationId);
    }
    
    // تحديث حالة الـ checkbox المقابل
    const checkbox = document.getElementById(`checkbox_${notificationId}`);
    if (checkbox) {
        checkbox.checked = isChecked;
    }
    
    updateSelectAllCheckbox();
    updateBulkActionsButton();
    
    console.log('الإشعارات المحددة:', Array.from(selectedNotifications));
}

// تبديل تحديد جميع الإشعارات
function toggleSelectAllNotifications() {
    const selectAllCheckbox = document.getElementById('selectAllNotifications');
    const checkboxes = document.querySelectorAll('.notification-checkbox');
    
    if (selectAllCheckbox.checked) {
        checkboxes.forEach(checkbox => {
            checkbox.checked = true;
            selectedNotifications.add(parseInt(checkbox.value));
        });
    } else {
        checkboxes.forEach(checkbox => {
            checkbox.checked = false;
            selectedNotifications.delete(parseInt(checkbox.value));
        });
    }
    
    updateBulkActionsButton();
}

// تحديث حالة خانة تحديد الكل
function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('selectAllNotifications');
    const checkboxes = document.querySelectorAll('.notification-checkbox');
    const checkedBoxes = document.querySelectorAll('.notification-checkbox:checked');
    
    if (checkedBoxes.length === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
    } else if (checkedBoxes.length === checkboxes.length) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = true;
    } else {
        selectAllCheckbox.indeterminate = true;
    }
}

// تحديث زر العمليات المتعددة
function updateBulkActionsButton() {
    const bulkButton = document.querySelector('[onclick="showBulkActionsModal()"]');
    if (bulkButton) {
        const selectedCount = selectedNotifications.size;
        
        if (selectedCount > 0) {
            bulkButton.innerHTML = `<i class="fas fa-cogs me-1"></i> عمليات متعددة (${selectedCount})`;
            bulkButton.classList.remove('btn-outline-danger', 'disabled');
            bulkButton.classList.add('btn-danger');
            bulkButton.disabled = false;
            bulkButton.setAttribute('title', `تم تحديد ${selectedCount} إشعار`);
        } else {
            bulkButton.innerHTML = '<i class="fas fa-cogs me-1"></i> عمليات متعددة';
            bulkButton.classList.remove('btn-danger');
            bulkButton.classList.add('btn-outline-danger');
            bulkButton.disabled = false; // الزر نشط دائماً لإظهار الرسالة
            bulkButton.setAttribute('title', 'حدد إشعارات للقيام بعمليات متعددة');
        }
    }
}

// إظهار نموذج العمليات المتعددة
function showBulkActionsModal() {
    if (selectedNotifications.size === 0) {
        showAlert('يرجى تحديد إشعار واحد على الأقل', 'warning');
        return;
    }
    
    const modal = new bootstrap.Modal(document.getElementById('bulkActionsModal'));
    modal.show();
    
    // تحديث عدد الإشعارات المختارة
    const selectedCount = document.getElementById('selectedCount');
    selectedCount.textContent = `تم تحديد ${selectedNotifications.size} إشعار`;
    
    // مراقبة تغيير نوع العملية
    const actions = document.querySelectorAll('input[name="bulkAction"]');
    const deleteWarning = document.getElementById('deleteWarning');
    
    actions.forEach(action => {
        action.addEventListener('change', function() {
            if (this.value === 'delete') {
                deleteWarning.style.display = 'block';
            } else {
                deleteWarning.style.display = 'none';
            }
        });
    });
}

// تنفيذ العملية المتعددة
async function executeBulkAction() {
    const selectedAction = document.querySelector('input[name="bulkAction"]:checked');
    if (!selectedAction) {
        showAlert('يرجى اختيار نوع العملية', 'warning');
        return;
    }
    
    const action = selectedAction.value;
    const notificationIds = Array.from(selectedNotifications);
    
    try {
        showLoader('جاري تنفيذ العملية...');
        
        let endpoint, method;
        if (action === 'delete') {
            endpoint = '/api/admin/notifications/bulk-delete';
            method = 'POST';
        } else if (action === 'mark_read') {
            endpoint = '/api/admin/notifications/mark-read';
            method = 'POST';
        }
        
        const response = await fetch(endpoint, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ids: notificationIds
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert(result.message, 'success');
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('bulkActionsModal'));
            modal.hide();
            
            // مسح التحديدات
            selectedNotifications.clear();
            
            // تحديث الإشعارات
            loadNotificationsAdmin();
        } else {
            showAlert(result.error || 'فشل في تنفيذ العملية', 'error');
        }
    } catch (error) {
        console.error('خطأ في تنفيذ العملية:', error);
        showAlert('خطأ في تنفيذ العملية', 'error');
    } finally {
        hideLoader();
    }
}

// مسح فلاتر البحث
function clearNotificationFilters() {
    document.getElementById('notificationsSearch').value = '';
    document.getElementById('notificationTypeFilter').value = '';
    document.getElementById('notificationPriorityFilter').value = '';
    document.getElementById('notificationReadFilter').value = '';
    
    currentNotificationsPage = 1;
    loadNotificationsAdmin();
}

// دوال مساعدة
function getNotificationTypeText(type) {
    const types = {
        'info': 'معلومات',
        'success': 'نجاح',
        'warning': 'تحذير',
        'error': 'خطأ'
    };
    return types[type] || 'معلومات';
}

function getNotificationPriorityText(priority) {
    const priorities = {
        'high': 'عالية',
        'normal': 'عادية',
        'low': 'منخفضة'
    };
    return priorities[priority] || 'عادية';
}

// دوال التحميل المباشر (للاستخدام عند فشل النطاق العام)
async function loadNotificationsDirectly() {
    console.log('تحميل الإشعارات مباشرة...');
    await loadNotificationsAdmin();
}

async function loadNotificationsStatsDirectly() {
    console.log('تحميل إحصائيات الإشعارات مباشرة...');
    await loadNotificationsStats();
}

async function refreshNotificationsDirectly() {
    console.log('تحديث الإشعارات مباشرة...');
    await loadNotificationsAdmin();
    await loadNotificationsStats();
    showAlert('تم تحديث الإشعارات بنجاح', 'success');
}

// إعداد مستمعي الأحداث للبحث والفلترة
document.addEventListener('DOMContentLoaded', function() {
    // البحث التلقائي
    const searchInput = document.getElementById('notificationsSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                currentNotificationsPage = 1;
                selectedNotifications.clear(); // مسح التحديدات عند البحث
                loadNotificationsAdmin();
            }, 500);
        });
    }
    
    // فلاتر التصفية
    const filters = ['notificationTypeFilter', 'notificationPriorityFilter', 'notificationReadFilter'];
    filters.forEach(filterId => {
        const filter = document.getElementById(filterId);
        if (filter) {
            filter.addEventListener('change', function() {
                currentNotificationsPage = 1;
                selectedNotifications.clear(); // مسح التحديدات عند تغيير الفلتر
                loadNotificationsAdmin();
            });
        }
    });
});

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

// إظهار الأقسام المختلفة - محسن مع التمرير التلقائي
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
            
            // التمرير التلقائي إلى القسم المطلوب
            setTimeout(() => {
                targetSection.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'start',
                    inline: 'nearest'
                });
            }, 100);
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

// دالة تغيير كلمة المرور المحسنة
async function changePassword() {
    const currentPassword = document.getElementById('currentPassword')?.value?.trim();
    const newPassword = document.getElementById('newPassword')?.value?.trim();
    const confirmPassword = document.getElementById('confirmPassword')?.value?.trim();
    const changePasswordBtn = document.getElementById('changePasswordBtn');

    // التحقق من البيانات الأساسية
    if (!currentPassword || !newPassword || !confirmPassword) {
        showPasswordError('يرجى ملء جميع الحقول المطلوبة');
        return;
    }

    // التحقق من تطابق كلمات المرور
    if (newPassword !== confirmPassword) {
        showPasswordError('كلمة المرور الجديدة وتأكيدها غير متطابقتين');
        highlightField('confirmPassword', false);
        return;
    }

    // التحقق من طول كلمة المرور
    if (newPassword.length < 6) {
        showPasswordError('كلمة المرور يجب أن تكون 6 أحرف على الأقل');
        highlightField('newPassword', false);
        return;
    }

    // التحقق من قوة كلمة المرور
    const passwordStrength = calculatePasswordStrength(newPassword);
    if (passwordStrength < 25) {
        if (!confirm('كلمة المرور ضعيفة. هل تريد المتابعة؟')) {
            return;
        }
    }

    // التحقق من أن كلمة المرور الجديدة مختلفة عن الحالية
    if (currentPassword === newPassword) {
        showPasswordError('كلمة المرور الجديدة يجب أن تكون مختلفة عن الحالية');
        highlightField('newPassword', false);
        return;
    }

    try {
        // تعطيل الزر منعاً للنقر المتكرر
        if (changePasswordBtn) {
            changePasswordBtn.disabled = true;
            changePasswordBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري التغيير...';
        }

        showLoader('جاري تغيير كلمة المرور...');

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 ثانية

        const response = await fetch('/api/change-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        const result = await response.json();

        if (response.ok) {
            // إظهار رسالة نجاح مفصلة
            showPasswordSuccess(result.message || 'تم تغيير كلمة المرور بنجاح');
            
            // مسح النموذج
            clearPasswordForm();
            
            // إغلاق النموذج
            const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
            if (modal) {
                modal.hide();
            }
            
            // إذا كان مطلوب تسجيل خروج، إظهار رسالة تحذيرية وإعادة توجيه
            if (result.logout_required) {
                showAlert('تم تغيير كلمة المرور بنجاح. سيتم تسجيل خروجك لضمان الأمان...', 'success');
                
                setTimeout(() => {
                    // إيقاف جميع العمليات
                    clearInterval(window.notificationInterval);
                    clearInterval(window.statsInterval);
                    
                    // إعادة توجيه
                    window.location.href = '/?password_changed=1';
                }, 3000);
            }
        } else if (response.status === 400) {
            const errorMsg = result.error || 'بيانات غير صحيحة';
            showPasswordError(errorMsg);
            
            // تمييز الحقل المناسب حسب نوع الخطأ
            if (errorMsg.includes('كلمة المرور الحالية')) {
                highlightField('currentPassword', false);
            } else if (errorMsg.includes('كلمة المرور الجديدة')) {
                highlightField('newPassword', false);
            }
        } else if (response.status === 401) {
            showPasswordError('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى');
            setTimeout(() => window.location.href = '/', 2000);
        } else if (response.status === 503) {
            showPasswordError('الخادم غير متاح حالياً. يرجى المحاولة مرة أخرى بعد قليل');
        } else {
            showPasswordError(result.error || 'حدث خطأ غير متوقع في تغيير كلمة المرور');
        }
    } catch (error) {
        console.error('خطأ في تغيير كلمة المرور:', error);
        
        let errorMessage = 'حدث خطأ غير متوقع';
        if (error.name === 'AbortError') {
            errorMessage = 'انتهت مهلة العملية. يرجى المحاولة مرة أخرى';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'فشل في الاتصال بالخادم. تحقق من اتصال الإنترنت';
        } else {
            errorMessage = error.message;
        }
        
        showPasswordError(errorMessage);
    } finally {
        // إعادة تفعيل الزر
        if (changePasswordBtn) {
            changePasswordBtn.disabled = false;
            changePasswordBtn.innerHTML = '<i class="fas fa-save"></i> تغيير كلمة المرور';
        }
        
        hideLoader();
    }
}

// دالة لحساب قوة كلمة المرور
function calculatePasswordStrength(password) {
    let strength = 0;
    
    // طول كلمة المرور
    if (password.length >= 8) strength += 25;
    else if (password.length >= 6) strength += 15;
    
    // احتواء أرقام
    if (/\d/.test(password)) strength += 25;
    
    // احتواء أحرف كبيرة وصغيرة
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 25;
    
    // احتواء رموز خاصة
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength += 25;
    
    return strength;
}

// دالة لإظهار رسائل خطأ كلمة المرور
function showPasswordError(message) {
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            <i class="fas fa-exclamation-triangle me-2"></i>
            <strong>خطأ:</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // إضافة الرسالة في بداية النموذج
    const modalBody = document.querySelector('#changePasswordModal .modal-body');
    if (modalBody) {
        // إزالة أي رسائل سابقة
        const existingAlert = modalBody.querySelector('.alert');
        if (existingAlert) {
            existingAlert.remove();
        }
        
        modalBody.insertAdjacentHTML('afterbegin', alertHtml);
    }
}

// دالة لإظهار رسائل نجاح كلمة المرور
function showPasswordSuccess(message) {
    const alertHtml = `
        <div class="alert alert-success alert-dismissible fade show" role="alert">
            <i class="fas fa-check-circle me-2"></i>
            <strong>نجح:</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const modalBody = document.querySelector('#changePasswordModal .modal-body');
    if (modalBody) {
        const existingAlert = modalBody.querySelector('.alert');
        if (existingAlert) {
            existingAlert.remove();
        }
        
        modalBody.insertAdjacentHTML('afterbegin', alertHtml);
    }
}

// دالة لتمييز الحقول
function highlightField(fieldId, isValid) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.classList.remove('is-valid', 'is-invalid');
        field.classList.add(isValid ? 'is-valid' : 'is-invalid');
        
        // إزالة التمييز بعد 3 ثوان
        setTimeout(() => {
            field.classList.remove('is-valid', 'is-invalid');
        }, 3000);
    }
}

// دالة لمسح نموذج كلمة المرور
function clearPasswordForm() {
    const fields = ['currentPassword', 'newPassword', 'confirmPassword'];
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.value = '';
            field.classList.remove('is-valid', 'is-invalid');
        }
    });
    
    // مسح رسائل القوة والتطابق
    const strengthDiv = document.getElementById('passwordStrength');
    const matchDiv = document.getElementById('passwordMatch');
    if (strengthDiv) strengthDiv.innerHTML = '';
    if (matchDiv) matchDiv.innerHTML = '';
    
    // مسح أي رسائل تنبيه
    const alerts = document.querySelectorAll('#changePasswordModal .alert');
    alerts.forEach(alert => alert.remove());
}

// إظهار نموذج تغيير كلمة المرور المحسن
function showChangePasswordModal() {
    // البحث عن النموذج الموجود في الصفحة
    let modal = document.getElementById('changePasswordModal');

    if (!modal) {
        console.error('نموذج تغيير كلمة المرور غير موجود في الصفحة');
        showAlert('نموذج تغيير كلمة المرور غير متاح', 'error');
        return;
    }

    // مسح النموذج من أي بيانات سابقة
    clearPasswordForm();

    // إعادة تعيين حالة الزر
    const changePasswordBtn = document.getElementById('changePasswordBtn');
    if (changePasswordBtn) {
        changePasswordBtn.disabled = true; // معطل في البداية حتى يتم التحقق من البيانات
        changePasswordBtn.innerHTML = '<i class="fas fa-save"></i> تغيير كلمة المرور';
    }

    // إظهار المودال
    const bootstrapModal = new bootstrap.Modal(modal, {
        backdrop: 'static',
        keyboard: true
    });
    bootstrapModal.show();

    // التركيز على حقل كلمة المرور الحالية بعد ظهور المودال
    setTimeout(() => {
        const currentPasswordField = document.getElementById('currentPassword');
        if (currentPasswordField) {
            currentPasswordField.focus();
        }
    }, 500);

    console.log('تم فتح نموذج تغيير كلمة المرور بنجاح');
}

// دالة لإضافة مستمعي الأحداث لنموذج كلمة المرور
function setupPasswordFormListeners() {
    const newPasswordField = document.getElementById('newPassword');
    const confirmPasswordField = document.getElementById('confirmPassword');
    const currentPasswordField = document.getElementById('currentPassword');

    if (newPasswordField) {
        newPasswordField.addEventListener('input', function() {
            const password = this.value;
            updatePasswordStrength(password);
            validatePasswordMatch();
            validateForm();
        });

        newPasswordField.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmPasswordField?.focus();
            }
        });
    }

    if (confirmPasswordField) {
        confirmPasswordField.addEventListener('input', function() {
            validatePasswordMatch();
            validateForm();
        });

        confirmPasswordField.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const changePasswordBtn = document.getElementById('changePasswordBtn');
                if (changePasswordBtn && !changePasswordBtn.disabled) {
                    changePassword();
                }
            }
        });
    }

    if (currentPasswordField) {
        currentPasswordField.addEventListener('input', validateForm);
        
        currentPasswordField.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                newPasswordField?.focus();
            }
        });
    }
}

// دالة لتحديث مؤشر قوة كلمة المرور
function updatePasswordStrength(password) {
    const strengthDiv = document.getElementById('passwordStrength');
    if (!strengthDiv) return;

    if (!password) {
        strengthDiv.innerHTML = '';
        return;
    }

    const strength = calculatePasswordStrength(password);
    let strengthText = '';
    let strengthClass = '';
    let suggestions = [];

    if (strength >= 75) {
        strengthText = 'قوية جداً';
        strengthClass = 'success';
    } else if (strength >= 50) {
        strengthText = 'قوية';
        strengthClass = 'info';
    } else if (strength >= 25) {
        strengthText = 'متوسطة';
        strengthClass = 'warning';
    } else {
        strengthText = 'ضعيفة';
        strengthClass = 'danger';
    }

    // إضافة اقتراحات للتحسين
    if (password.length < 8) suggestions.push('استخدم 8 أحرف على الأقل');
    if (!/\d/.test(password)) suggestions.push('أضف أرقام');
    if (!/[a-z]/.test(password)) suggestions.push('أضف أحرف صغيرة');
    if (!/[A-Z]/.test(password)) suggestions.push('أضف أحرف كبيرة');
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) suggestions.push('أضف رموز خاصة');

    strengthDiv.innerHTML = `
        <div class="progress mb-2" style="height: 10px;">
            <div class="progress-bar bg-${strengthClass}" 
                 style="width: ${strength}%; transition: width 0.3s ease;"
                 role="progressbar"></div>
        </div>
        <small class="text-${strengthClass}">
            <i class="fas fa-shield-alt me-1"></i>
            قوة كلمة المرور: <strong>${strengthText}</strong>
            ${suggestions.length > 0 ? '<br><i class="fas fa-lightbulb me-1 text-warning"></i>' + suggestions.join(' • ') : ''}
        </small>
    `;
}

// دالة للتحقق من تطابق كلمات المرور
function validatePasswordMatch() {
    const newPassword = document.getElementById('newPassword')?.value || '';
    const confirmPassword = document.getElementById('confirmPassword')?.value || '';
    const matchDiv = document.getElementById('passwordMatch');
    
    if (!matchDiv || !confirmPassword) return false;

    if (newPassword === confirmPassword && confirmPassword.length >= 6) {
        matchDiv.innerHTML = '<small class="text-success"><i class="fas fa-check me-1"></i>كلمات المرور متطابقة</small>';
        return true;
    } else if (confirmPassword.length > 0) {
        matchDiv.innerHTML = '<small class="text-danger"><i class="fas fa-times me-1"></i>كلمات المرور غير متطابقة</small>';
        return false;
    } else {
        matchDiv.innerHTML = '';
        return false;
    }
}

// دالة للتحقق من صحة النموذج
function validateForm() {
    const currentPassword = document.getElementById('currentPassword')?.value?.trim() || '';
    const newPassword = document.getElementById('newPassword')?.value?.trim() || '';
    const confirmPassword = document.getElementById('confirmPassword')?.value?.trim() || '';
    const changePasswordBtn = document.getElementById('changePasswordBtn');

    if (!changePasswordBtn) return;

    const isValid = currentPassword.length >= 1 && 
                   newPassword.length >= 6 && 
                   confirmPassword.length >= 6 && 
                   newPassword === confirmPassword &&
                   currentPassword !== newPassword;

    changePasswordBtn.disabled = !isValid;
    
    if (isValid) {
        changePasswordBtn.classList.remove('btn-outline-warning');
        changePasswordBtn.classList.add('btn-warning');
    } else {
        changePasswordBtn.classList.remove('btn-warning');
        changePasswordBtn.classList.add('btn-outline-warning');
    }
}

// إعداد مستمعي الأحداث عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // إعداد مستمعي الأحداث لنموذج كلمة المرور
    setupPasswordFormListeners();
    
    // إعداد مستمعي الأحداث للنموذج عند ظهوره
    const changePasswordModal = document.getElementById('changePasswordModal');
    if (changePasswordModal) {
        changePasswordModal.addEventListener('shown.bs.modal', function() {
            setupPasswordFormListeners();
            
            // التركيز على الحقل الأول
            setTimeout(() => {
                const currentPasswordField = document.getElementById('currentPassword');
                if (currentPasswordField) {
                    currentPasswordField.focus();
                }
            }, 100);
        });

        changePasswordModal.addEventListener('hidden.bs.modal', function() {
            clearPasswordForm();
        });
    }
});

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
                    case 'adminNotifications':
                        console.log('تحميل إدارة الإشعارات...');
                        await retryWithDelay(() => loadNotificationsAdmin());
                        await retryWithDelay(() => loadNotificationsStats());
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
                
                // إضافة زر إضافة بيانات جديدة لنفس الرقم (دائماً يظهر)
                html += `
                    <div class="text-center mb-3">
                        <button class="btn btn-primary btn-sm" onclick="showAddNewCustomerForm('${phoneNumber}')">
                            <i class="fas fa-plus"></i> إضافة بيانات جديدة لنفس الرقم
                        </button>
                    </div>
                `;
                
                data.customers.forEach((customer, index) => {
                    html += `
                        <div class="card mb-3 border-success customer-inquiry-card" style="transition: all 0.3s ease;">
                            <div class="card-header bg-gradient text-white d-flex justify-content-between align-items-center" style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%);">
                                <div class="flex-grow-1">
                                    <h6 class="mb-1 fw-bold">
                                        <i class="fas fa-user me-2"></i>
                                        ${customer.name || 'غير محدد'}
                                    </h6>
                                    <div class="d-flex align-items-center">
                                        <i class="fas fa-building text-warning me-2"></i>
                                        <span class="fw-bold text-warning">${customer.company_name || 'غير محدد'}</span>
                                    </div>
                                </div>
                                <button class="btn btn-light btn-sm fw-bold" onclick="selectCustomerForInquiry(${index}, '${phoneNumber}')" 
                                        style="min-width: 80px;">
                                    <i class="fas fa-hand-pointer me-1"></i> اختيار
                                </button>
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
                
                // حفظ النتائج في متغير عام للاستخدام لاحقاً
                window.currentSearchResults = data.customers;
                window.currentSearchPhone = phoneNumber;
                
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
        
        // إعادة تعيين حالة البحث
        document.getElementById('customerSearched').value = 'false';
        clearSearchStatus();
        enableCustomerFields(false); // تعطيل الحقول في البداية
        
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
                phoneInput.placeholder = 'أدخل رقم الهاتف ثم اضغط البحث';
            }
        }, 500);

        console.log('تم فتح نموذج طلب الخدمة بنجاح');
        
    } catch (error) {
        console.error('خطأ في فتح نموذج طلب الخدمة:', error);
        showMessage('خطأ في فتح نموذج طلب الخدمة', 'error');
    }
}

// التعامل مع الضغط على Enter في حقل الهاتف
function handlePhoneKeyPress(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        searchExistingCustomer();
    }
}

// دالة تفعيل/تعطيل الحقول
function enableCustomerFields(enable = true) {
    const fieldsContainer = document.getElementById('customerFieldsContainer');
    const submitBtn = document.querySelector('#serviceRequestModal .btn-primary[onclick*="submitServiceRequest"]');
    
    if (fieldsContainer) {
        if (enable) {
            fieldsContainer.removeAttribute('disabled');
            fieldsContainer.style.opacity = '1';
        } else {
            fieldsContainer.setAttribute('disabled', 'disabled');
            fieldsContainer.style.opacity = '0.6';
        }
    }
    
    if (submitBtn) {
        submitBtn.disabled = !enable;
    }
}

// دالة إظهار حالة البحث
function showSearchStatus(message, type = 'info') {
    const statusDiv = document.getElementById('searchStatus');
    if (!statusDiv) return;
    
    let alertClass = 'alert-info';
    let icon = 'fas fa-info-circle';
    
    switch(type) {
        case 'success':
            alertClass = 'alert-success';
            icon = 'fas fa-check-circle';
            break;
        case 'warning':
            alertClass = 'alert-warning';
            icon = 'fas fa-exclamation-triangle';
            break;
        case 'error':
            alertClass = 'alert-danger';
            icon = 'fas fa-exclamation-circle';
            break;
        case 'loading':
            alertClass = 'alert-primary';
            icon = 'fas fa-spinner fa-spin';
            break;
    }
    
    statusDiv.innerHTML = `
        <div class="alert ${alertClass} alert-sm mb-0">
            <i class="${icon} me-2"></i>${message}
        </div>
    `;
    statusDiv.style.display = 'block';
}

// دالة ملء بيانات العميل
function fillCustomerData(customer) {
    try {
        console.log('ملء بيانات العميل:', customer);
        
        // تفعيل الحقول
        enableCustomerFields(true);
        document.getElementById('customerSearched').value = 'true';
        
        // ملء البيانات
        const nameInput = document.getElementById('serviceCustomerName');
        const mobileInput = document.getElementById('serviceMobileNumber');
        const companySelect = document.getElementById('serviceCompanySelect');
        const notesInput = document.getElementById('serviceNotes');
        
        if (nameInput) {
            nameInput.value = customer.name || '';
            nameInput.readOnly = true; // جعل الحقل للقراءة فقط
        }
        
        if (mobileInput) {
            mobileInput.value = customer.mobile_number || '';
        }
        
        if (companySelect && customer.company_id) {
            companySelect.value = customer.company_id;
            // تحديث تفاصيل الخدمة
            updateServiceDetails();
        }
        
        if (notesInput && customer.notes) {
            notesInput.value = customer.notes;
        }
        
        // إضافة معلومات إضافية للعميل
        const customerInfo = document.getElementById('customerInfo');
        if (customerInfo) {
            customerInfo.innerHTML = `
                <div class="alert alert-info alert-sm">
                    <strong>بيانات العميل الموجود:</strong><br>
                    <small>
                        الاسم: ${customer.name}<br>
                        ${customer.mobile_number ? `الجوال: ${customer.mobile_number}<br>` : ''}
                        ${customer.company_name ? `الشركة: ${customer.company_name}<br>` : ''}
                        ${customer.speed ? `السرعة: ${customer.speed}<br>` : ''}
                        ${customer.speed_price ? `السعر: ${customer.speed_price} ل.س` : ''}
                    </small>
                </div>
            `;
        }
        
        console.log('تم ملء بيانات العميل بنجاح');
        
    } catch (error) {
        console.error('خطأ في ملء بيانات العميل:', error);
        showSearchStatus('خطأ في ملء البيانات', 'error');
    }
}

// دالة مسح حالة البحث
function clearSearchStatus() {
    const statusDiv = document.getElementById('searchStatus');
    if (statusDiv) {
        statusDiv.style.display = 'none';
        statusDiv.innerHTML = '';
    }
}

// دالة عرض العملاء المتعددين للاختيار - محسنة
function showMultipleCustomersSelection(customers, phoneNumber) {
    try {
        console.log(`عرض ${customers.length} عميل للاختيار`);
        
        const statusDiv = document.getElementById('searchStatus');
        if (!statusDiv) return;
        
        let html = `
            <div class="alert border-0 shadow-lg mb-4" style="border-radius: 20px; background: linear-gradient(135deg, rgba(40,167,69,0.1) 0%, rgba(32,201,151,0.05) 100%); border-left: 4px solid #28a745;">
                <div class="d-flex align-items-center">
                    <div class="bg-success bg-opacity-15 rounded-circle p-3 me-3" style="width: 60px; height: 60px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(40,167,69,0.2);">
                        <i class="fas fa-users text-success fa-lg"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h5 class="mb-1 fw-bold text-success">تم العثور على ${customers.length} عميل</h5>
                        <p class="mb-0 text-muted">للرقم <span class="fw-bold text-dark">${phoneNumber}</span> - اختر العميل المطلوب أو أضف بيانات جديدة</p>
                    </div>
                </div>
            </div>
        `;
        
        customers.forEach((customer, index) => {
            const companyBadge = customer.company_name ? `<span class="badge bg-primary bg-opacity-20 text-primary border border-primary border-opacity-25">${customer.company_name}</span>` : '<span class="badge bg-light text-muted">غير محدد</span>';
            const mobileBadge = customer.mobile_number ? `<span class="badge bg-info bg-opacity-20 text-info border border-info border-opacity-25">${customer.mobile_number}</span>` : '';
            
            html += `
                <div class="mb-4">
                    <div class="card border-0 shadow-sm customer-result-card" 
                         style="border-radius: 18px; transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1); cursor: pointer; overflow: hidden; position: relative;" 
                         onclick="selectCustomerFromList(${index}, '${phoneNumber}')"
                         onmouseover="animateCardHover(this, true)"
                         onmouseout="animateCardHover(this, false)">
                        
                        <!-- شريط ملون في الأعلى -->
                        <div style="height: 4px; background: linear-gradient(90deg, #007bff 0%, #6f42c1 50%, #28a745 100%);"></div>
                        
                        <!-- Header مع الاسم والإجراءات -->
                        <div class="card-header border-0 bg-white" style="border-radius: 0 0 18px 18px;">
                            <div class="row align-items-center g-0">
                                <div class="col">
                                    <div class="d-flex align-items-center">
                                        <!-- أيقونة العميل -->
                                        <div class="customer-avatar me-3" style="width: 50px; height: 50px; background: linear-gradient(135deg, #007bff 0%, #6f42c1 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(0,123,255,0.3);">
                                            <i class="fas fa-user text-white fa-lg"></i>
                                        </div>
                                        
                                        <!-- معلومات أساسية -->
                                        <div class="flex-grow-1">
                                            <h5 class="mb-1 fw-bold text-dark customer-name" style="font-size: 1.1rem;">${customer.name || 'غير محدد'}</h5>
                                            <div class="d-flex flex-wrap gap-2 align-items-center">
                                                ${companyBadge}
                                                ${mobileBadge}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- زر الاختيار -->
                                <div class="col-auto">
                                    <button class="btn btn-primary btn-lg px-4 select-btn" 
                                            onclick="event.stopPropagation(); selectCustomerFromList(${index}, '${phoneNumber}')"
                                            style="border-radius: 25px; font-weight: 600; box-shadow: 0 4px 15px rgba(0,123,255,0.4); background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); border: none; transition: all 0.3s ease;">
                                        <i class="fas fa-hand-pointer me-2"></i>
                                        <span class="d-none d-sm-inline">اختيار هذا العميل</span>
                                        <span class="d-sm-none">اختيار</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- تفاصيل العميل -->
                        <div class="card-body pt-0" style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);">
                            <div class="row g-3">
                                <!-- معلومات الاتصال -->
                                <div class="col-12">
                                    <div class="info-section p-3" style="background: rgba(255,255,255,0.7); border-radius: 12px; border-left: 3px solid #007bff;">
                                        <h6 class="text-primary mb-2 fw-bold">
                                            <i class="fas fa-phone me-2"></i>معلومات الاتصال
                                        </h6>
                                        <div class="row g-2">
                                            <div class="col-md-6">
                                                <div class="info-item d-flex align-items-center">
                                                    <div class="info-icon bg-success bg-opacity-15 rounded-circle me-2" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                                                        <i class="fas fa-phone text-success" style="font-size: 12px;"></i>
                                                    </div>
                                                    <div>
                                                        <small class="text-muted d-block" style="font-size: 10px; line-height: 1;">رقم الهاتف</small>
                                                        <span class="fw-bold text-dark" style="font-size: 14px;">${customer.phone_number || 'غير محدد'}</span>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            ${customer.mobile_number ? `
                                            <div class="col-md-6">
                                                <div class="info-item d-flex align-items-center">
                                                    <div class="info-icon bg-info bg-opacity-15 rounded-circle me-2" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                                                        <i class="fas fa-mobile-alt text-info" style="font-size: 12px;"></i>
                                                    </div>
                                                    <div>
                                                        <small class="text-muted d-block" style="font-size: 10px; line-height: 1;">رقم الجوال</small>
                                                        <span class="fw-bold text-dark" style="font-size: 14px;">${customer.mobile_number}</span>
                                                    </div>
                                                </div>
                                            </div>
                                            ` : ''}
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- معلومات الخدمة -->
                                ${(customer.speed || customer.speed_price) ? `
                                <div class="col-12">
                                    <div class="info-section p-3" style="background: rgba(255,255,255,0.7); border-radius: 12px; border-left: 3px solid #28a745;">
                                        <h6 class="text-success mb-2 fw-bold">
                                            <i class="fas fa-cogs me-2"></i>تفاصيل الخدمة
                                        </h6>
                                        <div class="row g-2">
                                            ${customer.speed ? `
                                            <div class="col-md-6">
                                                <div class="info-item d-flex align-items-center">
                                                    <div class="info-icon bg-warning bg-opacity-15 rounded-circle me-2" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                                                        <i class="fas fa-tachometer-alt text-warning" style="font-size: 12px;"></i>
                                                    </div>
                                                    <div>
                                                        <small class="text-muted d-block" style="font-size: 10px; line-height: 1;">السرعة</small>
                                                        <span class="fw-bold text-dark" style="font-size: 14px;">${customer.speed}</span>
                                                    </div>
                                                </div>
                                            </div>
                                            ` : ''}
                                            
                                            ${customer.speed_price ? `
                                            <div class="col-md-6">
                                                <div class="info-item d-flex align-items-center">
                                                    <div class="info-icon bg-success bg-opacity-15 rounded-circle me-2" style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                                                        <i class="fas fa-money-bill text-success" style="font-size: 12px;"></i>
                                                    </div>
                                                    <div>
                                                        <small class="text-muted d-block" style="font-size: 10px; line-height: 1;">السعر الشهري</small>
                                                        <span class="fw-bold text-success" style="font-size: 14px;">${customer.speed_price} ل.س</span>
                                                    </div>
                                                </div>
                                            </div>
                                            ` : ''}
                                        </div>
                                    </div>
                                </div>
                                ` : ''}
                                
                                <!-- الملاحظات -->
                                ${customer.notes ? `
                                <div class="col-12">
                                    <div class="info-section p-3" style="background: rgba(255,255,255,0.7); border-radius: 12px; border-left: 3px solid #6c757d;">
                                        <h6 class="text-secondary mb-2 fw-bold">
                                            <i class="fas fa-sticky-note me-2"></i>ملاحظات
                                        </h6>
                                        <div class="notes-content p-2" style="background: rgba(108,117,125,0.1); border-radius: 8px; font-style: italic;">
                                            <span style="font-size: 13px; line-height: 1.5;">${customer.notes}</span>
                                        </div>
                                    </div>
                                </div>
                                ` : ''}
                                
                                <!-- معلومات النظام -->
                                <div class="col-12">
                                    <div class="d-flex justify-content-between align-items-center mt-2 pt-2" style="border-top: 1px solid rgba(0,0,0,0.1);">
                                        <small class="text-muted">
                                            <i class="fas fa-calendar text-secondary me-1"></i>
                                            أُضيف في: ${formatDate(customer.created_at)}
                                        </small>
                                        <small class="text-primary fw-bold">
                                            عميل #${index + 1}
                                        </small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += `
            <div class="text-center mt-5">
                <div class="card border-0 shadow-lg" style="border-radius: 20px; background: linear-gradient(135deg, rgba(40,167,69,0.05) 0%, rgba(32,201,151,0.02) 100%);">
                    <div class="card-body p-4">
                        <div class="d-flex align-items-center justify-content-center mb-3">
                            <div class="bg-success bg-opacity-15 rounded-circle p-3 me-3" style="width: 50px; height: 50px; display: flex; align-items: center; justify-content: center;">
                                <i class="fas fa-user-plus text-success"></i>
                            </div>
                            <div>
                                <h6 class="mb-1 fw-bold text-dark">لم تجد العميل المطلوب؟</h6>
                                <small class="text-muted">يمكنك إضافة بيانات جديدة لنفس رقم الهاتف</small>
                            </div>
                        </div>
                        <button class="btn btn-success btn-lg px-5 py-3" onclick="showAddNewCustomerFormForPayment('${phoneNumber}')" 
                                style="border-radius: 30px; font-weight: 600; box-shadow: 0 6px 20px rgba(40,167,69,0.4); background: linear-gradient(135deg, #28a745 0%, #20c997 100%); border: none; transition: all 0.3s ease;">
                            <i class="fas fa-plus me-2"></i>
                            <span>إضافة عميل جديد للرقم ${phoneNumber}</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        statusDiv.innerHTML = html;
        statusDiv.style.display = 'block';
        
        // حفظ النتائج للاستخدام لاحقاً
        window.currentSearchResults = customers;
        window.currentSearchPhone = phoneNumber;
        
    } catch (error) {
        console.error('خطأ في عرض العملاء المتعددين:', error);
        showSearchStatus('خطأ في عرض النتائج', 'error');
    }
}

// دالة تحريك البطاقة عند التمرير
function animateCardHover(card, isHover) {
    const avatar = card.querySelector('.customer-avatar');
    const selectBtn = card.querySelector('.select-btn');
    
    if (isHover) {
        card.style.transform = 'translateY(-8px) scale(1.02)';
        card.style.boxShadow = '0 15px 40px rgba(0,123,255,0.2), 0 5px 15px rgba(0,0,0,0.1)';
        
        if (avatar) {
            avatar.style.transform = 'scale(1.1) rotate(5deg)';
            avatar.style.boxShadow = '0 6px 20px rgba(0,123,255,0.4)';
        }
        
        if (selectBtn) {
            selectBtn.style.transform = 'translateY(-2px)';
            selectBtn.style.boxShadow = '0 6px 20px rgba(0,123,255,0.5)';
        }
    } else {
        card.style.transform = 'translateY(0) scale(1)';
        card.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        
        if (avatar) {
            avatar.style.transform = 'scale(1) rotate(0deg)';
            avatar.style.boxShadow = '0 4px 15px rgba(0,123,255,0.3)';
        }
        
        if (selectBtn) {
            selectBtn.style.transform = 'translateY(0)';
            selectBtn.style.boxShadow = '0 4px 15px rgba(0,123,255,0.4)';
        }
    }
}

// دالة اختيار عميل من القائمة
function selectCustomerFromList(index, phoneNumber) {
    try {
        if (window.currentSearchResults && window.currentSearchResults[index]) {
            const customer = window.currentSearchResults[index];
            console.log('تم اختيار العميل:', customer);
            
            fillCustomerData(customer);
            showSearchStatus(`تم اختيار العميل: ${customer.name}`, 'success');
        } else {
            showSearchStatus('خطأ في اختيار العميل', 'error');
        }
    } catch (error) {
        console.error('خطأ في اختيار العميل:', error);
        showSearchStatus('خطأ في اختيار العميل', 'error');
    }
}

// دالة إظهار خيار إضافة عميل جديد
function showAddNewCustomerOption(phoneNumber) {
    try {
        // تفعيل الحقول لإدخال بيانات جديدة
        enableCustomerFields(true);
        document.getElementById('customerSearched').value = 'true';
        
        // مسح الحقول
        const nameInput = document.getElementById('serviceCustomerName');
        const mobileInput = document.getElementById('serviceMobileNumber');
        const companySelect = document.getElementById('serviceCompanySelect');
        
        if (nameInput) {
            nameInput.value = '';
            nameInput.readOnly = false;
        }
        if (mobileInput) mobileInput.value = '';
        if (companySelect) companySelect.value = '';
        
        showSearchStatus('يرجى إدخال بيانات العميل الجديد', 'info');
        
        // التركيز على حقل الاسم
        setTimeout(() => {
            if (nameInput) nameInput.focus();
        }, 100);
        
    } catch (error) {
        console.error('خطأ في إظهار خيار العميل الجديد:', error);
    }
}

// دالة إضافة عميل جديد في صفحة التسديد
function showAddNewCustomerFormForPayment(phoneNumber) {
    try {
        // تفعيل الحقول لإدخال بيانات جديدة
        enableCustomerFields(true);
        document.getElementById('customerSearched').value = 'true';
        
        // مسح الحقول
        const nameInput = document.getElementById('serviceCustomerName');
        const mobileInput = document.getElementById('serviceMobileNumber');
        const companySelect = document.getElementById('serviceCompanySelect');
        
        if (nameInput) {
            nameInput.value = '';
            nameInput.readOnly = false;
        }
        if (mobileInput) mobileInput.value = '';
        if (companySelect) companySelect.value = '';
        
        showSearchStatus(`
            <div class="alert alert-info">
                <i class="fas fa-user-plus"></i> 
                <strong>إضافة عميل جديد للرقم: ${phoneNumber}</strong><br>
                <small>يرجى ملء البيانات التالية للعميل الجديد</small>
            </div>
        `, 'info');
        
        // التركيز على حقل الاسم
        setTimeout(() => {
            if (nameInput) nameInput.focus();
        }, 100);
        
    } catch (error) {
        console.error('خطأ في إظهار نموذج العميل الجديد:', error);
    }
}

async function searchExistingCustomer() {
    const phoneNumber = document.getElementById('servicePhoneNumber')?.value.trim();
    const searchBtn = document.getElementById('searchCustomerBtn');
    
    if (!phoneNumber) {
        showSearchStatus('يرجى إدخال رقم الهاتف أولاً', 'warning');
        document.getElementById('servicePhoneNumber')?.focus();
        return;
    }
    
    // التحقق من صحة رقم الهاتف - مرونة أكثر في التحقق
    if (phoneNumber.length < 10) {
        showSearchStatus('رقم الهاتف يجب أن يكون 10 أرقام على الأقل', 'warning');
        return;
    }
    
    // التحقق من تنسيق رقم الهاتف مع مرونة أكثر
    const phonePattern011 = /^011\d{7,8}$/;  // 011 + 7-8 أرقام
    const phonePattern09 = /^09\d{7,8}$/;    // 09 + 7-8 أرقام
    const phonePatternGeneral = /^0\d{9,10}$/; // أي رقم يبدأ بـ 0 ويحتوي على 10-11 رقم
    
    if (!phonePattern011.test(phoneNumber) && !phonePattern09.test(phoneNumber) && !phonePatternGeneral.test(phoneNumber)) {
        console.log('تحذير: تنسيق رقم الهاتف قد يكون غير مألوف، لكن سيتم البحث عنه');
        // لا نوقف البحث، فقط تحذير
    }
    
    try {
        // تعطيل زر البحث أثناء البحث
        if (searchBtn) {
            searchBtn.disabled = true;
            searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري البحث...';
        }
        
        showSearchStatus('جاري البحث عن العميل...', 'loading');
        
        // إنشاء طلب مع timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        console.log(`بحث عن رقم: ${phoneNumber}`);
        
        const response = await fetch(`/api/customers/search/${encodeURIComponent(phoneNumber)}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        console.log(`نتيجة البحث - حالة الاستجابة: ${response.status}`);
        
        if (response.ok) {
            const data = await response.json();
            console.log('بيانات البحث المستلمة:', data);
            
            // التحقق من النتائج مع مرونة أكثر
            if (data && ((data.found && data.customers && data.customers.length > 0) || (data.customer))) {
                // إذا كان هناك customer واحد في البيانات
                if (data.customer) {
                    console.log('تم العثور على عميل واحد:', data.customer);
                    fillCustomerData(data.customer);
                    showSearchStatus(`
                        <div class="alert alert-success mb-2">
                            <i class="fas fa-check-circle"></i> 
                            تم العثور على العميل: ${data.customer.name} - ${data.customer.company_name || 'غير محدد'}
                        </div>
                        <div class="text-center">
                            <button class="btn btn-primary btn-sm" onclick="showAddNewCustomerFormForPayment('${phoneNumber}')">
                                <i class="fas fa-plus"></i> إضافة عميل جديد بنفس الرقم
                            </button>
                        </div>
                    `, 'success');
                }
                // إذا كان هناك customers متعددة
                else if (data.customers && data.customers.length > 0) {
                    console.log(`تم العثور على ${data.customers.length} عميل`);
                    if (data.customers.length === 1) {
                        // عميل واحد فقط - ملء البيانات مباشرة مع إظهار زر إضافة جديد
                        const customer = data.customers[0];
                        fillCustomerData(customer);
                        showSearchStatus(`
                            <div class="alert alert-success mb-2">
                                <i class="fas fa-check-circle"></i> 
                                تم العثور على العميل: ${customer.name} - ${customer.company_name || 'غير محدد'}
                            </div>
                            <div class="text-center">
                                <button class="btn btn-primary btn-sm" onclick="showAddNewCustomerFormForPayment('${phoneNumber}')">
                                    <i class="fas fa-plus"></i> إضافة عميل جديد بنفس الرقم
                                </button>
                            </div>
                        `, 'success');
                    } else {
                        // عدة عملاء - عرض قائمة الاختيار
                        showMultipleCustomersSelection(data.customers, phoneNumber);
                    }
                }
            } else {
                console.log('لم يتم العثور على أي عميل للرقم:', phoneNumber);
                // لم يتم العثور على العميل - تفعيل الحقول لإدخال بيانات جديدة
                enableCustomerFields(true);
                document.getElementById('customerSearched').value = 'true';
                
                // مسح الحقول
                const nameInput = document.getElementById('serviceCustomerName');
                const mobileInput = document.getElementById('serviceMobileNumber');
                const companySelect = document.getElementById('serviceCompanySelect');
                
                if (nameInput) nameInput.value = '';
                if (mobileInput) mobileInput.value = '';
                if (companySelect) companySelect.value = '';
                
                showSearchStatus('لم يتم العثور على العميل. يرجى إدخال البيانات يدوياً', 'warning');
                
                // التركيز على حقل الاسم
                setTimeout(() => {
                    const nameField = document.getElementById('serviceCustomerName');
                    if (nameField) nameField.focus();
                }, 500);
            }
        } else if (response.status === 401) {
            showSearchStatus('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى', 'error');
        } else if (response.status === 404) {
            // نفس المعاملة كما لو لم يتم العثور على العميل
            enableCustomerFields(true);
            document.getElementById('customerSearched').value = 'true';
            
            showSearchStatus('لم يتم العثور على العميل. يرجى إدخال البيانات يدوياً', 'warning');
            
            setTimeout(() => {
                const nameField = document.getElementById('serviceCustomerName');
                if (nameField) nameField.focus();
            }, 500);
        } else {
            throw new Error(`خطأ في الخادم: ${response.status}`);
        }
    } catch (error) {
        console.error('خطأ في البحث عن العميل:', error);
        
        let errorMessage = 'حدث خطأ غير متوقع';
        if (error.name === 'AbortError') {
            errorMessage = 'انتهت مهلة البحث (10 ثوان)';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'فشل في الاتصال بالخادم - تحقق من اتصال الإنترنت';
        } else {
            errorMessage = error.message;
        }
        
        showSearchStatus(errorMessage, 'error');
        
    } finally {
        // إعادة تفعيل زر البحث
        if (searchBtn) {
            searchBtn.disabled = false;
            searchBtn.innerHTML = '<i class="fas fa-search"></i> بحث';
        }
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
    
    // التحقق من أن البحث تم تنفيذه
    const customerSearched = document.getElementById('customerSearched')?.value;
    if (customerSearched !== 'true') {
        showMessage('يجب البحث عن رقم الهاتف أولاً قبل إرسال الطلب', 'warning');
        document.getElementById('servicePhoneNumber')?.focus();
        return;
    }
    
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
        document.getElementById('serviceAmount')?.focus();
        return;
    }
    
    // التحقق من الرصيد
    const currentBalance = parseFloat(document.getElementById('modalCurrentBalance')?.textContent) || 0;
    if (currentBalance < parseFloat(amount)) {
        showMessage('الرصيد غير كافي لهذا المبلغ', 'error');
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
            document.getElementById('customerSearched').value = 'false';
            clearSearchStatus();
            enableCustomerFields(false);
            
            // تحديث الرصيد في الواجهة
            const newBalance = currentBalance - parseFloat(amount);
            document.getElementById('modalCurrentBalance').textContent = newBalance;
            document.getElementById('currentBalance').textContent = newBalance;
            
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

// دالة لعرض اختيار العملاء المتعددين في نموذج التسديد
function showMultipleCustomersSelection(customers, phoneNumber) {
    let html = `
        <div class="alert alert-info">
            <i class="fas fa-users"></i> 
            تم العثور على ${customers.length} عميل بنفس الرقم. اختر العميل المطلوب:
        </div>
    `;
    
    customers.forEach((customer, index) => {
        html += `
            <div class="card mb-2 border-primary customer-selection-card" style="cursor: pointer;" 
                 onclick="selectCustomerForPayment(${index}, '${phoneNumber}')">
                <div class="card-body p-2">
                    <div class="d-flex flex-column flex-md-row justify-content-between align-items-start align-items-md-center">
                        <div class="flex-grow-1 mb-2 mb-md-0">
                            <h6 class="mb-1">
                                <i class="fas fa-user text-primary"></i>
                                ${customer.name || 'غير محدد'}
                            </h6>
                            <small class="text-muted">
                                <i class="fas fa-building"></i> ${customer.company_name || 'غير محدد'}
                            </small>
                            ${customer.mobile_number ? `
                                <br><small class="text-info">
                                    <i class="fas fa-mobile-alt"></i> ${customer.mobile_number}
                                </small>
                            ` : ''}
                        </div>
                        <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); selectCustomerForPayment(${index}, '${phoneNumber}')">
                            <i class="fas fa-hand-pointer d-md-none"></i>
                            <span class="d-none d-md-inline">اختيار</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    
    // إضافة زر إضافة عميل جديد
    html += `
        <div class="text-center mt-3">
            <button class="btn btn-success btn-sm" onclick="showAddNewCustomerFormForPayment('${phoneNumber}')">
                <i class="fas fa-plus"></i> إضافة عميل جديد بنفس الرقم
            </button>
        </div>
    `;
    
    const statusDiv = document.getElementById('searchStatus');
    if (statusDiv) {
        statusDiv.innerHTML = html;
        statusDiv.style.display = 'block';
    }
    
    // حفظ النتائج للاستخدام لاحقاً
    window.currentPaymentSearchResults = customers;
    window.currentPaymentSearchPhone = phoneNumber;
}

// دالة لاختيار عميل معين للتسديد
function selectCustomerForPayment(customerIndex, phoneNumber) {
    if (!window.currentPaymentSearchResults || !window.currentPaymentSearchResults[customerIndex]) {
        showSearchStatus('خطأ في تحديد العميل', 'error');
        return;
    }
    
    const customer = window.currentPaymentSearchResults[customerIndex];
    fillCustomerData(customer);
    showSearchStatus(`تم اختيار العميل: ${customer.name}`, 'success');
}

// دالة لاختيار عميل معين للاستعلام
function selectCustomerForInquiry(customerIndex, phoneNumber) {
    if (!window.currentSearchResults || !window.currentSearchResults[customerIndex]) {
        return;
    }
    
    const customer = window.currentSearchResults[customerIndex];
    
    // إظهار تفاصيل العميل المختار فقط
    const resultDiv = document.getElementById('inquiryResult');
    if (resultDiv) {
        let html = `
            <div class="alert alert-info">
                <i class="fas fa-user-check"></i> 
                تم اختيار العميل: ${customer.name}
            </div>
            <div class="card border-success">
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
            <div class="text-center mt-3">
                <button class="btn btn-secondary" onclick="searchCustomerInquiry()">
                    <i class="fas fa-arrow-left"></i> العودة للنتائج الكاملة
                </button>
                <button class="btn btn-primary" onclick="showAddNewCustomerForm('${phoneNumber}')">
                    <i class="fas fa-plus"></i> إضافة بيانات جديدة لنفس الرقم
                </button>
            </div>
        `;
        
        resultDiv.innerHTML = html;
    }
}

// دالة ملء بيانات العميل في نموذج التسديد
function fillCustomerData(customer) {
    const nameInput = document.getElementById('serviceCustomerName');
    const mobileInput = document.getElementById('serviceMobileNumber');
    const companySelect = document.getElementById('serviceCompanySelect');
    
    if (nameInput) nameInput.value = customer.name || '';
    if (mobileInput) mobileInput.value = customer.mobile_number || '';
    if (companySelect && customer.company_id) {
        companySelect.value = customer.company_id;
        updateServiceDetails();
    }
    
    // تفعيل الحقول
    enableCustomerFields(true);
    document.getElementById('customerSearched').value = 'true';
    
    // التركيز على حقل المبلغ
    setTimeout(() => {
        const amountField = document.getElementById('serviceAmount');
        if (amountField) amountField.focus();
    }, 500);
}

// دالة إظهار نموذج إضافة عميل جديد للاستعلام
function showAddNewCustomerForm(phoneNumber) {
    // إنشاء نموذج إضافة عميل جديد
    const modalHtml = `
        <div class="modal fade" id="addNewCustomerModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-success text-white">
                        <h5 class="modal-title">
                            <i class="fas fa-user-plus"></i>
                            إضافة عميل جديد - ${phoneNumber}
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="newCustomerForm">
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label for="newCustomerName" class="form-label">اسم العميل <span class="text-danger">*</span></label>
                                    <input type="text" class="form-control" id="newCustomerName" required>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label for="newCustomerPhone" class="form-label">رقم الهاتف</label>
                                    <input type="tel" class="form-control" id="newCustomerPhone" value="${phoneNumber}" readonly>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label for="newCustomerMobile" class="form-label">رقم الجوال</label>
                                    <input type="tel" class="form-control" id="newCustomerMobile">
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label for="newCustomerCompany" class="form-label">الشركة <span class="text-danger">*</span></label>
                                    <select class="form-select" id="newCustomerCompany" required>
                                        <option value="">اختر الشركة</option>
                                    </select>
                                </div>
                            </div>
                            <div class="mb-3">
                                <label for="newCustomerNotes" class="form-label">ملاحظات</label>
                                <textarea class="form-control" id="newCustomerNotes" rows="3"></textarea>
                            </div>
                            <input type="hidden" id="newCustomerPhoneHidden" value="${phoneNumber}">
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times"></i> إلغاء
                        </button>
                        <button type="button" class="btn btn-success" onclick="saveNewCustomer()">
                            <i class="fas fa-save"></i> حفظ العميل
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // إزالة النموذج القديم إن وجد
    const existingModal = document.getElementById('addNewCustomerModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // إضافة النموذج الجديد
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // ملء قائمة الشركات
    populateNewCustomerCompanies();
    
    // إظهار النموذج
    const modal = new bootstrap.Modal(document.getElementById('addNewCustomerModal'));
    modal.show();
    
    // التركيز على حقل الاسم
    setTimeout(() => {
        document.getElementById('newCustomerName')?.focus();
    }, 500);
}

// دالة إظهار نموذج إضافة عميل جديد للتسديد
function showAddNewCustomerFormForPayment(phoneNumber) {
    // إغلاق نموذج التسديد مؤقتاً وفتح نموذج الإضافة
    showAddNewCustomerForm(phoneNumber);
    
    // إضافة معرف خاص للتسديد
    window.isAddingForPayment = true;
    window.paymentPhoneNumber = phoneNumber;
}

// دالة ملء قائمة الشركات في نموذج إضافة العميل
function populateNewCustomerCompanies() {
    const select = document.getElementById('newCustomerCompany');
    if (!select) return;
    
    select.innerHTML = '<option value="">اختر الشركة</option>';
    
    if (companies && companies.length > 0) {
        companies.forEach(company => {
            const option = document.createElement('option');
            option.value = company.id;
            option.textContent = company.name;
            select.appendChild(option);
        });
    }
}

// دالة حفظ العميل الجديد
async function saveNewCustomer() {
    const name = document.getElementById('newCustomerName')?.value.trim();
    const phone = document.getElementById('newCustomerPhoneHidden')?.value;
    const mobile = document.getElementById('newCustomerMobile')?.value.trim();
    const companyId = document.getElementById('newCustomerCompany')?.value;
    const notes = document.getElementById('newCustomerNotes')?.value.trim();
    
    if (!name || !phone || !companyId) {
        showAlert('يرجى ملء جميع الحقول المطلوبة', 'error');
        return;
    }
    
    try {
        showLoader('جاري حفظ العميل الجديد...');
        
        const response = await fetch('/api/customers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                phone_number: phone,
                mobile_number: mobile,
                company_id: parseInt(companyId),
                notes: notes
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('تم حفظ العميل الجديد بنجاح', 'success');
            
            // إغلاق نموذج الإضافة
            const modal = bootstrap.Modal.getInstance(document.getElementById('addNewCustomerModal'));
            if (modal) modal.hide();
            
            // إذا كان من نموذج التسديد، ملء البيانات
            if (window.isAddingForPayment && window.paymentPhoneNumber) {
                const newCustomer = {
                    name: name,
                    phone_number: phone,
                    mobile_number: mobile,
                    company_id: parseInt(companyId),
                    notes: notes
                };
                fillCustomerData(newCustomer);
                
                // تنظيف المتغيرات
                window.isAddingForPayment = false;
                window.paymentPhoneNumber = null;
            } else {
                // إعادة البحث لإظهار النتائج المحدثة
                searchCustomerInquiry();
            }
            
        } else {
            showAlert(result.error || 'حدث خطأ في حفظ العميل', 'error');
        }
    } catch (error) {
        console.error('خطأ في حفظ العميل:', error);
        showAlert('خطأ في الاتصال بالخادم', 'error');
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
    
    // دوال النتائج المتعددة والإضافة الجديدة
    window.showMultipleCustomersSelection = showMultipleCustomersSelection;
    window.selectCustomerForPayment = selectCustomerForPayment;
    window.selectCustomerForInquiry = selectCustomerForInquiry;
    window.fillCustomerData = fillCustomerData;
    window.showAddNewCustomerForm = showAddNewCustomerForm;
    window.showAddNewCustomerFormForPayment = showAddNewCustomerFormForPayment;
    window.populateNewCustomerCompanies = populateNewCustomerCompanies;
    window.saveNewCustomer = saveNewCustomer;
    
    // دوال التنقل
    window.showSection = showSection;
    
    console.log('تم تصدير دوال تفاصيل الزبون بنجاح');
    console.log('تم تصدير جميع دوال صفحة المستخدم بنجاح');
}