/* ═══════════════════════════════════════════
   UTHAO — Global JavaScript
   ═══════════════════════════════════════════ */

(function () {
    'use strict';

    /* ── Sidebar toggle (mobile) ── */
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const burger = document.getElementById('burgerBtn');

    function openSidebar() {
        sidebar?.classList.add('open');
        overlay?.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        sidebar?.classList.remove('open');
        overlay?.classList.remove('open');
        document.body.style.overflow = '';
    }

    burger?.addEventListener('click', openSidebar);
    overlay?.addEventListener('click', closeSidebar);

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSidebar();
    });

    // Close sidebar when nav item clicked on mobile
    document.querySelectorAll('.nav-item:not(.disabled)').forEach((item) => {
        item.addEventListener('click', () => {
            if (window.innerWidth <= 900) closeSidebar();
        });
    });

    /* ── Toast system ── */
    window.uthaoToast = function (message, type = 'info', duration = 3500) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }

        const icons = {
            info: 'fa-circle-info',
            success: 'fa-check-circle',
            error: 'fa-circle-xmark'
        };
        const colors = {
            info: 'var(--orange)',
            success: 'var(--green)',
            error: '#ef4444'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
      <i class="fas ${icons[type] || icons.info}" style="color:${colors[type]};font-size:15px;flex-shrink:0"></i>
      <span>${message}</span>
    `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    };

    /* ── Flash messages from Flask ── */
    document.querySelectorAll('.flask-flash').forEach((el) => {
        const msg = el.dataset.message;
        const type = el.dataset.type || 'info';
        if (msg) setTimeout(() => window.uthaoToast(msg, type), 200);
    });

    /* ── User dropdown ── */
    const topbarUser = document.getElementById('topbarUser');
    const userDropdown = document.getElementById('userDropdown');

    if (topbarUser && userDropdown) {
        topbarUser.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('open');
        });

        document.addEventListener('click', () => {
            userDropdown?.classList.remove('open');
        });
    }

    /* ── Search: emit custom event so pages can hook in ── */
    const searchInput = document.getElementById('globalSearch');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            document.dispatchEvent(new CustomEvent('uthao:search', {
                detail: e.target.value
            }));
        });
    }

})();


let notifDropdownOpen = false;
let eventSource = null;

// Toggle dropdown
function toggleNotifDropdown() {
    const dropdown = document.getElementById('notifDropdown');
    notifDropdownOpen = !notifDropdownOpen;
    dropdown.style.display = notifDropdownOpen ? 'flex' : 'none';
    
    if (notifDropdownOpen) {
        loadNotifications();
        // Start SSE connection
        if (!eventSource) {
            startNotifStream();
        }
    }
}

// Load notifications via AJAX
async function loadNotifications() {
    try {
        const response = await fetch('/user/api/notifications?limit=10');
        const data = await response.json();
        
        const list = document.getElementById('notifList');
        
        if (data.notifications.length === 0) {
            list.innerHTML = `
                <div class="notif-empty">
                    <i class="fas fa-bell-slash"></i>
                    <p>No new notifications</p>
                </div>
            `;
        } else {
            list.innerHTML = data.notifications.map(n => `
                <a href="${n.link || '/user/notifications'}" class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markReadAndGo(${n.id}, '${n.link || '/user/notifications'}')">
                    <div class="notif-item-icon" style="background: ${n.color}20; color: ${n.color};">
                        <i class="fas ${n.icon}"></i>
                    </div>
                    <div class="notif-item-content">
                        <div class="notif-item-title">${n.title}</div>
                        <div class="notif-item-message">${n.message}</div>
                        <div class="notif-item-time">${n.time_ago}</div>
                    </div>
                </a>
            `).join('');
        }
        
        // Update badge
        updateNotifBadge(data.unread_count);
        
    } catch (err) {
        console.error('Failed to load notifications:', err);
    }
}

// Update notification badge
function updateNotifBadge(count) {
    const dot = document.getElementById('notifDot');
    if (count > 0) {
        dot.style.display = 'block';
        dot.classList.add('active');
    } else {
        dot.style.display = 'none';
        dot.classList.remove('active');
    }
}

// Mark as read and navigate
async function markReadAndGo(id, link) {
    try {
        await fetch(`/user/api/notifications/${id}/read`, {
            method: 'POST',
            headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''}
        });
        window.location.href = link;
    } catch (err) {
        console.error('Failed to mark as read:', err);
    }
}

// Mark all read from dropdown
async function markAllReadFromDropdown() {
    try {
        await fetch('/user/api/notifications/mark-all-read', {
            method: 'POST',
            headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''}
        });
        loadNotifications();
        updateNotifBadge(0);
    } catch (err) {
        console.error('Failed to mark all as read:', err);
    }
}

// Server-Sent Events for real-time notifications
function startNotifStream() {
    if (!window.EventSource) {
        console.log('SSE not supported');
        return;
    }
    
    eventSource = new EventSource('/user/notifications/stream');
    
    eventSource.onmessage = (event) => {
        if (event.data.startsWith(':heartbeat')) return;
        
        try {
            const data = JSON.parse(event.data);
            // Show toast notification
            if (window.showToast) {
                showToast(data.title + ': ' + data.message, 'info');
            }
            // Reload dropdown if open
            if (notifDropdownOpen) {
                loadNotifications();
            }
            // Update badge
            fetch('/user/api/notifications/unread-count')
                .then(r => r.json())
                .then(d => updateNotifBadge(d.count));
                
        } catch (e) {
            console.error('Invalid SSE data:', e);
        }
    };
    
    eventSource.onerror = () => {
        console.log('SSE error, reconnecting...');
        eventSource.close();
        setTimeout(startNotifStream, 5000);
    };
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const container = document.querySelector('.notification-dropdown-container');
    if (container && !container.contains(e.target) && notifDropdownOpen) {
        document.getElementById('notifDropdown').style.display = 'none';
        notifDropdownOpen = false;
    }
});

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    // Load unread count
    fetch('/user/api/notifications/unread-count')
        .then(r => r.json())
        .then(d => updateNotifBadge(d.count));
    
    // Start SSE
    startNotifStream();
});


