/**
 * Tale WebUI - 主入口
 * 功能：侧边栏导航高亮、状态刷新、主题切换
 */

(function () {
    'use strict';

    // ===== 侧边栏导航高亮 =====
    function highlightNav() {
        const path = window.location.pathname;
        const page = path.replace(/^\//, '') || 'dashboard';
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });
    }

    // ===== 系统状态刷新 =====
    async function refreshStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            const dot = document.getElementById('sysStatusDot');
            const text = document.getElementById('sysStatusText');
            const topDot = document.getElementById('topbarStatusDot');
            const topText = document.getElementById('topbarStatusText');
            const online = data.running !== false;
            const reasonKey = data.offline_reason ? ('offline.' + data.offline_reason) : null;
            const reasonText = reasonKey ? (window.t ? window.t(reasonKey) : reasonKey) : '';
            if (dot) {
                dot.classList.toggle('offline', !online);
                if (reasonText) dot.title = reasonText;
            }
            if (text) {
                const baseText = online ? (window.t ? window.t('status.active') : 'Active') : (window.t ? window.t('status.stopped') : 'Stopped');
                text.textContent = baseText;
            }
            if (topDot) {
                topDot.classList.toggle('offline', !online);
                if (reasonText) topDot.title = reasonText;
            }
            if (topText) {
                const baseText = online ? (window.t ? window.t('topbar.systemStatus') : 'System Status') : (window.t ? window.t('topbar.systemOffline') : 'System Offline');
                topText.textContent = reasonText ? baseText + ' · ' + reasonText : baseText;
            }

            // 显示系统告警
            var alertContainer = document.getElementById('topbarAlertMsg');
            if (alertContainer) {
                if (data.alerts && data.alerts.length > 0) {
                    var firstAlert = data.alerts[0];
                    var msg = firstAlert.message;
                    if (window.t && firstAlert.key) {
                        var tKey = 'alert.' + firstAlert.key;
                        var tVal = window.t(tKey);
                        if (tVal !== tKey) msg = tVal;
                    }
                    alertContainer.textContent = msg;
                    alertContainer.style.display = '';
                } else {
                    alertContainer.style.display = 'none';
                }
            }
        } catch (e) {
            // 静默失败
        }
    }

    // ===== 快捷导航：Ctrl+Tab 键在对话页触发卡片模式 =====
    document.addEventListener('keydown', (e) => {
        const tag = document.activeElement?.tagName;
        if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(tag)) return;

        if (e.key === 'Tab' && e.ctrlKey) {
            const isChatPage = document.querySelector('.chat-layout');
            if (isChatPage && typeof toggleCardView === 'function') {
                e.preventDefault();
                toggleCardView();
            }
        }
    });

    // ===== 主题切换 =====
    function initTheme() {
        const saved = localStorage.getItem('tale-theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isDark = saved ? saved === 'dark' : prefersDark;
        setTheme(isDark ? 'dark' : 'light');
    }

    function setTheme(theme) {
        const isDark = theme === 'dark';
        document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
        localStorage.setItem('tale-theme', isDark ? 'dark' : 'light');

        const label = document.getElementById('themeLabel');
        if (label) label.textContent = window.t ? window.t(isDark ? 'theme.light' : 'theme.dark') : (isDark ? 'Light Mode' : 'Dark Mode');
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        setTheme(current === 'light' ? 'dark' : 'light');
    }

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);

    // ===== 语言切换 =====
    const langSwitchBtn = document.getElementById('langSwitchBtn');
    if (langSwitchBtn) langSwitchBtn.addEventListener('click', () => {
        if (window.i18n) window.i18n.toggleLang();
    });

    // 监听语言变化事件，刷新状态文本
    window.addEventListener('i18n:change', () => {
        refreshStatus();
    });

    // ===== 初始化 =====
    initTheme();
    highlightNav();
    refreshStatus();
    setInterval(refreshStatus, 10000);

    // ===== 全局 fetch 拦截：自动附加 CSRF Token =====
    const origFetch = window.fetch;
    window.fetch = function (url, opts) {
        opts = opts || {};
        if (opts.method && opts.method !== 'GET' && opts.method !== 'HEAD') {
            opts.headers = opts.headers || {};
            if (opts.headers instanceof Headers) {
                if (!opts.headers.has('X-CSRF-Token')) {
                    opts.headers.set('X-CSRF-Token', window.csrfToken);
                }
            } else if (Array.isArray(opts.headers)) {
                const has = opts.headers.some(h => h[0].toLowerCase() === 'x-csrf-token');
                if (!has) opts.headers.push(['X-CSRF-Token', window.csrfToken]);
            } else {
                opts.headers['X-CSRF-Token'] = window.csrfToken;
            }
        }
        return origFetch.call(this, url, opts);
    };

    // 全局工具函数
    window.formatTime = function (dateStr) {
        const d = new Date(dateStr);
        const lang = window.__i18nLang || navigator.language || 'zh-CN';
        try {
            return d.toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' });
        } catch (_) {
            return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }
    };

    window.escapeHtml = function (str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    };

    // 用于 HTML 属性上下文（data-*="..."），必须额外转义双引号和单引号，
    // escapeHtml 只转义 < > &，不足以防止属性注入型 XSS。
    window.escapeAttr = function (str) {
        const s = str == null ? '' : String(str);
        return s.replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
    };
})();
