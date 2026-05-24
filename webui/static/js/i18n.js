/**
 * Tale WebUI - 轻量级前端国际化 (i18n)
 * 支持：data-i18n 属性翻译、placeholder翻译、JS动态文本 t() 函数
 */

(function () {
    'use strict';

    const DEFAULT_LANG = 'zh';
    const STORAGE_KEY = 'tale-lang';

    const dict = {
        zh: {
            // base.html 侧边栏
            'nav.dashboard': '仪表盘',
            'nav.conversations': '对话',
            'nav.schedule': '日程',
            'nav.settings': '设置',
            'nav.adapters': '适配器',
            'nav.tools': '工具',
            'nav.logs': '日志',
            'theme.toggle': '切换主题',
            'theme.dark': '深色模式',
            'theme.light': '浅色模式',
            'status.active': '运行中',
            'status.stopped': '已停止',
            'topbar.search': '搜索',
            'topbar.notifications': '通知',
            'topbar.tasks': '任务',
            'topbar.systemStatus': '系统状态',
            'topbar.systemOffline': '系统离线',
            'offline.missing_api_key': '未配置 API Key',
            'offline.unknown': '未知原因',
            'lang.switch': 'English',
            'common.cancel': '取消',
            'common.next': '下一步',
            'common.confirm': '确认添加',

            // dashboard.html
            'dash.title': '仪表盘',
            'dash.runningStatus': '运行状态',
            'dash.memoryUsage': '内存占用',
            'dash.adapterCount': '适配器数量',
            'dash.sessionCount': '会话数量',
            'dash.active': '运行中',
            'dash.stopped': '已停止',
            'dash.systemActivity': '系统活动概览',
            'dash.dailySchedule': '今日日程',
            'dash.adapterStatus': '适配器状态',
            'dash.openConversation': '打开对话',
            'dash.generatePlan': '生成今日计划',
            'dash.clearLogs': '清空日志',
            'dash.systemReboot': '重启系统',
            'dash.reloadConfig': '重载配置',
            'dash.loading': '加载中...',
            'dash.noAdapters': '无适配器',
            'dash.noEvents': '今日无日程',
            'dash.failedLoad': '加载失败',
            'dash.confirmGenPlan': '生成今日计划？',
            'dash.planGenerated': '计划已生成',
            'dash.planFailed': '生成失败',
            'dash.confirmClearLogs': '清空所有日志？',
            'dash.logsCleared': '日志已清空',
            'dash.confirmReboot': '重启系统？',
            'dash.confirmReload': '重载系统配置？',
            'dash.rebooting': '正在重启',
            'dash.reloaded': '配置已重载',
            'dash.generating': '生成中...',
            'dash.requestFailed': '请求失败',
            'dash.general': '通用',

            // chat.html
            'chat.title': '对话管理',
            'chat.newChat': '新建对话',
            'chat.expand': '展开',
            'chat.clear': '清空',
            'chat.placeholder': '输入消息，按 Enter 发送，Shift+Enter 换行...',
            'chat.loading': '加载中...',
            'chat.noConversations': '暂无对话',
            'chat.noMessages': '无消息',
            'chat.messages': '条',
            'chat.defaultSession': '默认会话',
            'chat.startChat': '发送第一条消息开始对话',
            'chat.loadingFailed': '加载失败',
            'chat.loadMessagesFailed': '加载消息失败',
            'chat.sendFailed': '发送失败',
            'chat.networkError': '网络错误',
            'chat.errorPrefix': '[错误]',
            'chat.networkErrorPrefix': '[网络错误]',
            'chat.confirmClear': '确定要清空当前对话历史吗？',
            'chat.clearFailed': '清空失败',
            'chat.createFailed': '创建对话失败',
            'chat.delete': '删除',
            'chat.confirmDelete': '确定要永久删除会话',
            'chat.deleteFailed': '删除失败',

            // card-view.js
            'card.noMessage': '无消息',
            'card.previewLabel': '最后消息预览：',
            'card.messageCount': '条消息',
            'card.hint': '键盘左右方向键 / 鼠标滚轮 切换会话，回车进入会话',

            // plan.html
            'plan.title': '日程规划',
            'plan.subtitle': '管理每日日程与长期目标',
            'plan.selectDate': '选择日期',
            'plan.load': '加载',
            'plan.generatePlan': '生成计划',
            'plan.generatePlaceholder': '制定今天的学习计划...',
            'plan.generate': '生成',
            'plan.addEvent': '添加行程',
            'plan.eventTitle': '标题',
            'plan.eventDesc': '描述',
            'plan.eventType': '类型',
            'plan.add': '添加',
            'plan.loading': '加载中...',
            'plan.noSchedule': '暂无日程',
            'plan.generating': '生成中...',
            'plan.generated': '已生成',
            'plan.genFailed': '生成失败',
            'plan.fillRequired': '请填写标题和开始时间',
            'plan.added': '已添加',
            'plan.addFailed': '添加失败',
            'plan.confirmDelete': '确定删除此行程？',
            'plan.deleteFailed': '删除失败',
            'plan.delete': '删除',
            'plan.pending': '待办',
            'plan.inProgress': '进行中',
            'plan.completed': '已完成',
            'plan.cancelled': '已取消',
            'plan.now': '现在',
            'plan.other': '其他',

            // config.html
            'config.title': '配置中心',
            'config.subtitle': '编辑角色人设、行为参数、平台与服务配置',
            'config.loading': '加载中...',
            'config.loadFailed': '加载失败',
            'config.noConfig': '无配置',
            'config.save': '保存配置',
            'config.saved': '[OK] 已保存',
            'config.saveFailed': '[X] 保存失败',
            'config.networkError': '[X] 网络错误',
            'config.formMode': '表单模式',
            'config.sourceMode': '源码模式',
            'config.import': '导入',
            'config.export': '导出',
            'config.presetPlaceholder': '预设列表',
            'config.presetSave': '另存为预设',
            'config.presetDelete': '删除预设',

            // config.html FIELD_META keys (used as t() keys)
            '中文名': '中文名',
            '英文名': '英文名',
            '昵称': '昵称',
            '性别': '性别',
            '年龄': '年龄',
            '生日': '生日',
            '语言': '语言',
            '外貌': '外貌',
            '世界观': '世界观',
            '价值观': '价值观',
            '爱好': '爱好',
            '表情/语气': '表情/语气',
            '对话风格': '对话风格',
            '记忆长度': '记忆长度',
            '消息间隔': '消息间隔',
            '缓冲消息数': '缓冲消息数',
            '最小延迟': '最小延迟',
            '最大延迟': '最大延迟',
            '上下文长度': '上下文长度',
            '记忆启用': '记忆启用',
            '性格强度': '性格强度',
            '头像路径': '头像路径',
            '基本信息': '基本信息',
            '性格设定': '性格设定',
            '行为参数': '行为参数',
            '上下文设置': '上下文设置',
            '其他': '其他',
            '添加': '添加',

            // login.html
            'login.title': '认证令牌',
            'login.placeholder': '输入 6 位令牌',
            'login.submit': '登 录',
            'login.emptyToken': '请输入认证令牌',
            'login.authFailed': '认证失败',
            'login.networkError': '网络错误',

            // adapter.html
            'adapter.title': '适配器管理',
            'adapter.subtitle': '查看和控制各平台适配器',
            'adapter.loading': '加载中...',
            'adapter.noAdapters': '未找到适配器',
            'adapter.running': '运行中',
            'adapter.stopped': '已停止',
            'adapter.start': '启动',
            'adapter.stop': '停止',
            'adapter.version': '版本',
            'adapter.author': '作者',
            'adapter.unknown': '未知',
            'adapter.loadFailed': '加载失败',
            'adapter.toggleFailed': '操作失败',
            'adapter.toggleSuccess': '操作成功',
            'adapter.requestFailed': '请求失败',
            'adapter.addAdapter': '+ 添加适配器',
            'adapter.selectAdapter': '请选择要添加的适配器类型',
            'adapter.configTitle': '配置',
            'adapter.noConfigNeeded': '此适配器无需额外配置',
            'adapter.pressEnter': '输入后按回车添加',
            'adapter.addSuccess': '添加成功',
            'adapter.addFailed': '添加失败',
            'adapter.instanceName': '实例名称',
            'adapter.inputInstanceName': '请输入实例名称（用于区分同一类型的多个适配器）',
            'adapter.config': '配置',
            'adapter.editConfig': '编辑配置',
            'adapter.saveConfig': '保存配置',
            'adapter.saveSuccess': '保存成功',
            'adapter.saveFailed': '保存失败',
            'adapter.delete': '删除',
            'adapter.confirmDelete': '确定要删除适配器「{name}」吗？删除后不可恢复！',
            'adapter.deleteSuccess': '删除成功',
            'adapter.deleteFailed': '删除失败',

            // tools.html
            'tools.title': '工具测试',
            'tools.subtitle': '测试可用工具的调用与返回结果',
            'tools.loading': '加载中...',
            'tools.noTools': '未找到工具',
            'tools.execute': '执行',
            'tools.loadFailed': '加载失败',

            // logs.html
            'logs.title': '日志中心',
            'logs.subtitle': '实时日志流与历史查询',
            'logs.allLevels': '全部级别',
            'logs.allModules': '全部模块',
            'logs.refresh': '刷新',
            'logs.export': '导出',
            'logs.realtime': '实时推送',
            'logs.waiting': '等待日志...',
            'logs.noLogs': '无日志',
            'logs.loadFailed': '加载失败',
            'logs.DEBUG': '调试',
            'logs.INFO': '信息',
            'logs.WARNING': '警告',
            'logs.ERROR': '错误',
        },
        en: {
            // base.html sidebar
            'nav.dashboard': 'Dashboard',
            'nav.conversations': 'Conversations',
            'nav.schedule': 'Schedule',
            'nav.settings': 'Settings',
            'nav.adapters': 'Adapters',
            'nav.tools': 'Tools',
            'nav.logs': 'Logs',
            'theme.toggle': 'Toggle Theme',
            'theme.dark': 'Dark Mode',
            'theme.light': 'Light Mode',
            'status.active': 'Active',
            'status.stopped': 'Stopped',
            'topbar.search': 'Search',
            'topbar.notifications': 'Notifications',
            'topbar.tasks': 'Tasks',
            'topbar.systemStatus': 'System Status',
            'topbar.systemOffline': 'System Offline',
            'offline.missing_api_key': 'API Key not configured',
            'offline.unknown': 'Unknown reason',
            'lang.switch': '中文',
            'common.cancel': 'Cancel',
            'common.next': 'Next',
            'common.confirm': 'Confirm',

            // dashboard.html
            'dash.title': 'Dashboard',
            'dash.runningStatus': 'Running Status',
            'dash.memoryUsage': 'Memory Usage',
            'dash.adapterCount': 'Adapter Count',
            'dash.sessionCount': 'Session Count',
            'dash.active': 'Active',
            'dash.stopped': 'Stopped',
            'dash.systemActivity': 'System Activity Overview',
            'dash.dailySchedule': 'Daily Schedule',
            'dash.adapterStatus': 'Adapter Status',
            'dash.openConversation': 'Open Conversation',
            'dash.generatePlan': 'Generate Daily Plan',
            'dash.clearLogs': 'Clear Logs',
            'dash.systemReboot': 'System Reboot',
            'dash.reloadConfig': 'Reload Config',
            'dash.loading': 'Loading...',
            'dash.noAdapters': 'No adapters',
            'dash.noEvents': 'No events today',
            'dash.failedLoad': 'Failed to load',
            'dash.confirmGenPlan': 'Generate today\'s plan?',
            'dash.planGenerated': 'Plan generated',
            'dash.planFailed': 'Failed to generate',
            'dash.confirmClearLogs': 'Clear all logs?',
            'dash.logsCleared': 'Logs cleared',
            'dash.confirmReboot': 'Reboot system?',
            'dash.confirmReload': 'Reload configuration?',
            'dash.rebooting': 'Rebooting',
            'dash.reloaded': 'Config reloaded',
            'dash.generating': 'Generating...',
            'dash.requestFailed': 'Request failed',
            'dash.general': 'General',

            // chat.html
            'chat.title': 'Conversations',
            'chat.newChat': 'New Chat',
            'chat.expand': 'Expand',
            'chat.clear': 'Clear',
            'chat.placeholder': 'Type a message, Enter to send, Shift+Enter for newline...',
            'chat.loading': 'Loading...',
            'chat.noConversations': 'No conversations',
            'chat.noMessages': 'No messages',
            'chat.messages': 'msgs',
            'chat.defaultSession': 'Default Session',
            'chat.startChat': 'Send your first message to start',
            'chat.loadingFailed': 'Loading failed',
            'chat.loadMessagesFailed': 'Failed to load messages',
            'chat.sendFailed': 'Failed to send',
            'chat.networkError': 'Network error',
            'chat.errorPrefix': '[Error]',
            'chat.networkErrorPrefix': '[Network Error]',
            'chat.confirmClear': 'Clear current conversation history?',
            'chat.clearFailed': 'Failed to clear',
            'chat.createFailed': 'Failed to create conversation',
            'chat.delete': 'Delete',
            'chat.confirmDelete': 'Permanently delete conversation',
            'chat.deleteFailed': 'Failed to delete conversation',

            // card-view.js
            'card.noMessage': 'No message',
            'card.previewLabel': 'Last message preview:',
            'card.messageCount': 'messages',
            'card.hint': 'Arrow keys / mouse wheel to switch, Enter to open',

            // plan.html
            'plan.title': 'Schedule',
            'plan.subtitle': 'Manage daily schedules and long-term goals',
            'plan.selectDate': 'Select Date',
            'plan.load': 'Load',
            'plan.generatePlan': 'Generate Plan',
            'plan.generatePlaceholder': 'Make a study plan for today...',
            'plan.generate': 'Generate',
            'plan.addEvent': 'Add Event',
            'plan.eventTitle': 'Title',
            'plan.eventDesc': 'Description',
            'plan.eventType': 'Type',
            'plan.add': 'Add',
            'plan.loading': 'Loading...',
            'plan.noSchedule': 'No events',
            'plan.generating': 'Generating...',
            'plan.generated': 'Generated',
            'plan.genFailed': 'Failed to generate',
            'plan.fillRequired': 'Please fill in title and start time',
            'plan.added': 'Added',
            'plan.addFailed': 'Failed to add',
            'plan.confirmDelete': 'Delete this event?',
            'plan.deleteFailed': 'Failed to delete',
            'plan.delete': 'Delete',
            'plan.pending': 'Pending',
            'plan.inProgress': 'In Progress',
            'plan.completed': 'Completed',
            'plan.cancelled': 'Cancelled',
            'plan.now': 'Now',
            'plan.other': 'Other',

            // config.html
            'config.title': 'Configuration',
            'config.subtitle': 'Edit character, behavior, platform and service settings',
            'config.loading': 'Loading...',
            'config.loadFailed': 'Failed to load',
            'config.noConfig': 'No configuration',
            'config.save': 'Save Config',
            'config.saved': '[OK] Saved',
            'config.saveFailed': '[X] Save failed',
            'config.networkError': '[X] Network error',
            'config.formMode': 'Form Mode',
            'config.sourceMode': 'Source Mode',
            'config.import': 'Import',
            'config.export': 'Export',
            'config.presetPlaceholder': 'Presets',
            'config.presetSave': 'Save as Preset',
            'config.presetDelete': 'Delete Preset',

            // config.html FIELD_META keys (used as t() keys)
            '中文名': 'Chinese Name',
            '英文名': 'English Name',
            '昵称': 'Nickname',
            '性别': 'Gender',
            '年龄': 'Age',
            '生日': 'Birthday',
            '语言': 'Language',
            '外貌': 'Appearance',
            '世界观': 'Worldview',
            '价值观': 'Values',
            '爱好': 'Hobbies',
            '表情/语气': 'Expressions/Tone',
            '对话风格': 'Dialogue Style',
            '记忆长度': 'Memory Length',
            '消息间隔': 'Message Interval',
            '缓冲消息数': 'Buffer Messages',
            '最小延迟': 'Min Delay',
            '最大延迟': 'Max Delay',
            '上下文长度': 'Context Length',
            '记忆启用': 'Memory Enabled',
            '性格强度': 'Personality Strength',
            '头像路径': 'Avatar Path',
            '基本信息': 'Basic Info',
            '性格设定': 'Personality',
            '行为参数': 'Behavior',
            '上下文设置': 'Context Settings',
            '其他': 'Other',
            '添加': 'Add',

            // login.html
            'login.title': 'Auth Token',
            'login.placeholder': 'Enter 6-digit token',
            'login.submit': 'Login',
            'login.emptyToken': 'Please enter auth token',
            'login.authFailed': 'Authentication failed',
            'login.networkError': 'Network error',

            // adapter.html
            'adapter.title': 'Adapter Management',
            'adapter.subtitle': 'View and control platform adapters',
            'adapter.loading': 'Loading...',
            'adapter.noAdapters': 'No adapters found',
            'adapter.running': 'Running',
            'adapter.stopped': 'Stopped',
            'adapter.start': 'Start',
            'adapter.stop': 'Stop',
            'adapter.version': 'Version',
            'adapter.author': 'Author',
            'adapter.unknown': 'unknown',
            'adapter.loadFailed': 'Failed to load',
            'adapter.toggleFailed': 'Operation failed',
            'adapter.toggleSuccess': 'Operation successful',
            'adapter.requestFailed': 'Request failed',
            'adapter.addAdapter': '+ Add Adapter',
            'adapter.selectAdapter': 'Please select an adapter type',
            'adapter.configTitle': 'Configuration',
            'adapter.noConfigNeeded': 'No additional configuration needed',
            'adapter.pressEnter': 'Press Enter to add',
            'adapter.addSuccess': 'Added successfully',
            'adapter.addFailed': 'Failed to add',
            'adapter.instanceName': 'Instance Name',
            'adapter.inputInstanceName': 'Enter an instance name (to distinguish multiple adapters of the same type)',
            'adapter.config': 'Config',
            'adapter.editConfig': 'Edit Config',
            'adapter.saveConfig': 'Save Config',
            'adapter.saveSuccess': 'Saved successfully',
            'adapter.saveFailed': 'Failed to save',
            'adapter.delete': 'Delete',
            'adapter.confirmDelete': 'Are you sure to delete adapter "{name}"? This cannot be undone!',
            'adapter.deleteSuccess': 'Deleted successfully',
            'adapter.deleteFailed': 'Failed to delete',

            // tools.html
            'tools.title': 'Tool Testing',
            'tools.subtitle': 'Test available tools and their results',
            'tools.loading': 'Loading...',
            'tools.noTools': 'No tools found',
            'tools.execute': 'Execute',
            'tools.loadFailed': 'Failed to load',

            // logs.html
            'logs.title': 'Log Center',
            'logs.subtitle': 'Real-time log stream and history',
            'logs.allLevels': 'All Levels',
            'logs.allModules': 'All Modules',
            'logs.refresh': 'Refresh',
            'logs.export': 'Export',
            'logs.realtime': 'Real-time',
            'logs.waiting': 'Waiting for logs...',
            'logs.noLogs': 'No logs',
            'logs.loadFailed': 'Failed to load',
            'logs.DEBUG': 'DEBUG',
            'logs.INFO': 'INFO',
            'logs.WARNING': 'WARNING',
            'logs.ERROR': 'ERROR',
        }
    };

    let currentLang = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;

    function getText(key) {
        return (dict[currentLang] && dict[currentLang][key]) || (dict[DEFAULT_LANG] && dict[DEFAULT_LANG][key]) || key;
    }

    function setLang(lang) {
        if (!dict[lang]) return;
        currentLang = lang;
        localStorage.setItem(STORAGE_KEY, lang);
        apply();
        document.documentElement.setAttribute('lang', lang === 'zh' ? 'zh-CN' : 'en');
        // 触发自定义事件，供其他模块响应
        window.dispatchEvent(new CustomEvent('i18n:change', { detail: { lang } }));
    }

    function toggleLang() {
        setLang(currentLang === 'zh' ? 'en' : 'zh');
    }

    function apply() {
        // 翻译 data-i18n 元素
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const text = getText(key);
            if (text) el.textContent = text;
        });

        // 翻译 data-i18n-placeholder 元素
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const text = getText(key);
            if (text) el.setAttribute('placeholder', text);
        });

        // 翻译 data-i18n-title 元素
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const text = getText(key);
            if (text) el.setAttribute('title', text);
        });

        // 更新语言切换按钮文本
        const langBtn = document.getElementById('langSwitchBtn');
        if (langBtn) {
            const langBtnSpan = langBtn.querySelector('span');
            if (langBtnSpan) {
                langBtnSpan.textContent = getText('lang.switch');
            }
        }
    }

    function init() {
        document.documentElement.setAttribute('lang', currentLang === 'zh' ? 'zh-CN' : 'en');
        // 等待 DOM 就绪后执行一次翻译
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', apply);
        } else {
            apply();
        }
    }

    // 暴露全局接口
    window.t = getText;
    window.i18n = { setLang, toggleLang, apply, getLang: () => currentLang };

    init();
})();
