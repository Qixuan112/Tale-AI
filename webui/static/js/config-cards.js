/**
 * Tale WebUI - 卡片式配置编辑器
 * 为每个配置域提供可视化的卡片编辑界面
 *
 * 用法：
 *   const editor = new ConfigCards(container, configName, initialData);
 *   editor.render();
 *   const data = editor.collectData();
 */

(function () {
    'use strict';

    // ============ 配置卡片 Schema ============

    const SCHEMA = {

        character: {
            cards: [
                {
                    id: 'raw-persona',
                    label: '人格',
                    titleKey: 'card.char.rawPersona',
                    titleDefault: '自由编辑',
                    subtitleKey: 'card.char.rawPersonaDesc',
                    subtitleDefault: '用你自己的话描述角色人格，随意写',
                    color: '#f59e0b',
                    fields: [
                        { key: 'raw_persona', labelKey: 'field.char.rawPersona', labelDefault: '人格描述', type: 'textarea', placeholder: '用自然语言描述你的角色...\n\n比如：\n我是初念（Aurora），17岁，一个温柔又有点小腹黑的女孩子。\n我喜欢听雨声、看星星、写日记。\n我说话简短，一般不超过3-5个分条...' },
                    ]
                },
                {
                    id: 'basic-info',
                    label: '基本信息',
                    titleKey: 'card.char.basicInfo',
                    titleDefault: '基本信息',
                    subtitleKey: 'card.char.basicInfoDesc',
                    subtitleDefault: '角色的身份标识',
                    color: '#6366f1',
                    fields: [
                        { key: 'character.ChineseName', labelKey: 'field.char.ChineseName', labelDefault: '中文名', type: 'text', placeholder: '角色的中文名字' },
                        { key: 'character.EnglishName', labelKey: 'field.char.EnglishName', labelDefault: '英文名', type: 'text', placeholder: '角色的英文名字' },
                        { key: 'character.NickNames', labelKey: 'field.char.NickNames', labelDefault: '昵称', type: 'array', placeholder: '添加昵称' },
                        { key: 'character.gender', labelKey: 'field.char.gender', labelDefault: '性别', type: 'text', placeholder: '如：女、男、其他' },
                        { key: 'character.age', labelKey: 'field.char.age', labelDefault: '年龄', type: 'text', placeholder: '如：18岁、未知' },
                        { key: 'character.birthday', labelKey: 'field.char.birthday', labelDefault: '生日', type: 'text', placeholder: '如：3月14日' },
                    ]
                },
                {
                    id: 'language',
                    label: '语言',
                    titleKey: 'card.char.language',
                    titleDefault: '语言偏好',
                    subtitleKey: 'card.char.languageDesc',
                    subtitleDefault: '角色的语言习惯',
                    color: '#8b5cf6',
                    fields: [
                        { key: 'character.language.primary', labelKey: 'field.char.langPrimary', labelDefault: '主要语言', type: 'text', placeholder: 'Chinese / English / Japanese' },
                        { key: 'character.language.style', labelKey: 'field.char.langStyle', labelDefault: '语言风格', type: 'text', placeholder: 'casual / formal / cute' },
                    ]
                },
                {
                    id: 'personality',
                    label: '性格',
                    titleKey: 'card.char.personality',
                    titleDefault: '外貌与性格',
                    subtitleKey: 'card.char.personalityDesc',
                    subtitleDefault: '角色的形象与内在特征',
                    color: '#ec4899',
                    fields: [
                        { key: 'character.appearance', labelKey: 'field.char.appearance', labelDefault: '外貌', type: 'textarea', placeholder: '描述角色的外貌特征...' },
                        { key: 'character.views', labelKey: 'field.char.views', labelDefault: '世界观', type: 'textarea', placeholder: '角色对世界的看法...' },
                        { key: 'character.values', labelKey: 'field.char.values', labelDefault: '价值观', type: 'array', placeholder: '添加价值观条目' },
                        { key: 'character.hobbies', labelKey: 'field.char.hobbies', labelDefault: '爱好', type: 'array', placeholder: '添加爱好' },
                        { key: 'character.expressions', labelKey: 'field.char.expressions', labelDefault: '表情/语气', type: 'text', placeholder: '常用表达方式' },
                    ]
                },
                {
                    id: 'dialogue-style',
                    label: '对话',
                    titleKey: 'card.char.dialogue',
                    titleDefault: '对话风格',
                    subtitleKey: 'card.char.dialogueDesc',
                    subtitleDefault: '角色的语言表达方式',
                    color: '#f59e0b',
                    fields: [
                        { key: 'character.dialogue_style_imitation', labelKey: 'field.char.styleImitation', labelDefault: '风格示例', type: 'array', placeholder: '添加对话风格示例' },
                    ]
                },
            ]
        },

        behavior: {
            cards: [
                {
                    id: 'bot-behavior',
                    label: '行为',
                    titleKey: 'card.behavior.bot',
                    titleDefault: '机器人行为',
                    subtitleKey: 'card.behavior.botDesc',
                    subtitleDefault: '消息处理与响应参数',
                    color: '#10b981',
                    fields: [
                        { key: 'bot.max_memory_length', labelKey: 'field.behavior.memoryLen', labelDefault: '记忆长度', type: 'number', placeholder: '记住的消息条数', descKey: 'field.behavior.memoryLenDesc', descDefault: '角色能记住的最大消息数' },
                        { key: 'bot.max_message_interval', labelKey: 'field.behavior.msgInterval', labelDefault: '消息间隔', type: 'number', placeholder: '秒', descKey: 'field.behavior.msgIntervalDesc', descDefault: '回复消息的间隔时间（秒）' },
                        { key: 'bot.max_buffer_messages', labelKey: 'field.behavior.bufferMsg', labelDefault: '缓冲消息数', type: 'number', placeholder: '缓冲池大小', descKey: 'field.behavior.bufferMsgDesc', descDefault: '最大缓冲消息数' },
                        { key: 'bot.typing_speed', labelKey: 'field.behavior.typingSpeed', labelDefault: '打字速度', type: 'range', min: 10, max: 200, step: 10, rangeDefault: 50, rangeUnit: 'ms/字', descKey: 'field.behavior.typingSpeedDesc', descDefault: '模拟真人打字速度，越低越快' },
                        { key: 'bot.typing_min_delay', labelKey: 'field.behavior.typingMinDelay', labelDefault: '最短延迟', type: 'range', min: 0.1, max: 3, step: 0.1, rangeDefault: 0.5, rangeUnit: '秒', descKey: 'field.behavior.typingMinDelayDesc', descDefault: '即使消息很短也要等待的最少时间' },
                        { key: 'context.max_context', labelKey: 'field.behavior.maxContext', labelDefault: '上下文长度', type: 'number', placeholder: '保留的对话条数', descKey: 'field.behavior.maxContextDesc', descDefault: 'ChatLLM 保留的最近对话条数' },
                        { key: 'context.chat_context_enabled', labelKey: 'field.behavior.chatContextEnabled', labelDefault: '启用聊天上下文', type: 'boolean' },
                        { key: 'context.chat_context_window', labelKey: 'field.behavior.chatContextWindow', labelDefault: '聊天上下文窗口', type: 'range', min: 0, max: 50, step: 1, rangeDefault: 10, rangeUnit: '条', descKey: 'field.behavior.chatContextWindowDesc', descDefault: '响应时附带上方最近几条聊天记录' },
                    ]
                },
                {
                    id: 'selfie',
                    label: '头像',
                    titleKey: 'card.behavior.selfie',
                    titleDefault: '个性化',
                    subtitleKey: 'card.behavior.selfieDesc',
                    subtitleDefault: '头像与外观设置',
                    color: '#f472b6',
                    fields: [
                        { key: 'selfie.path', labelKey: 'field.behavior.selfiePath', labelDefault: '头像路径', type: 'text', placeholder: '自定义头像文件路径，留空使用默认' },
                    ]
                },
                {
                    id: 'wake-settings',
                    label: '唤醒',
                    titleKey: 'card.behavior.wake',
                    titleDefault: '唤醒设置',
                    subtitleKey: 'card.behavior.wakeDesc',
                    subtitleDefault: '群聊中触发机器人响应的方式',
                    color: '#f97316',
                    fields: [
                        {
                            key: 'wake.enable_keyword_wake',
                            labelKey: 'field.wake.enableKeyword',
                            labelDefault: '关键词唤醒',
                            type: 'boolean',
                            descKey: 'field.wake.enableKeywordDesc',
                            descDefault: '开启后，群聊消息包含指定关键词时自动响应',
                            showFields: ['wake.waking_keywords'],
                        },
                        {
                            key: 'wake.waking_keywords',
                            labelKey: 'field.wake.keywords',
                            labelDefault: '唤醒关键词',
                            type: 'array',
                            placeholder: '添加关键词，如：初念',
                            parentToggle: 'wake.enable_keyword_wake',
                        },
                        {
                            key: 'wake.enable_quote_wake',
                            labelKey: 'field.wake.enableQuote',
                            labelDefault: '引用唤醒',
                            type: 'boolean',
                            descKey: 'field.wake.enableQuoteDesc',
                            descDefault: '开启后，有人引用（回复）机器人发过的消息时自动响应',
                        },
                    ]
                },
            ]
        },

        platforms: {
            // 动态：每个适配器渲染为一张卡片
            dynamic: true,
            dynamicItemSchema: {
                idKey: null,  // 使用对象的顶层 key 作为 ID
                label: '适配器',
                color: '#06b6d4',
                titleKey: null,  // 使用 key 名作为标题
                fields: [
                    { key: 'enabled', labelKey: 'field.platform.enabled', labelDefault: '启用', type: 'boolean' },
                    { key: 'adapter_type', labelKey: 'field.platform.adapterType', labelDefault: '适配器类型', type: 'select', options: ['qq', 'wechat_pc', 'websocket'] },
                    { key: 'ws_url', labelKey: 'field.platform.wsUrl', labelDefault: 'WebSocket URL', type: 'text', placeholder: 'ws://127.0.0.1:3002' },
                    { key: 'http_url', labelKey: 'field.platform.httpUrl', labelDefault: 'HTTP URL', type: 'text', placeholder: 'http://127.0.0.1:3001' },
                    { key: 'access_token', labelKey: 'field.platform.accessToken', labelDefault: 'Access Token', type: 'password', placeholder: '认证令牌' },
                    { key: 'auto_reconnect', labelKey: 'field.platform.autoReconnect', labelDefault: '自动重连', type: 'boolean' },
                    { key: 'reconnect_interval', labelKey: 'field.platform.reconnectInterval', labelDefault: '重连间隔', type: 'number', placeholder: '秒' },
                ],
                statusField: 'enabled',  // 用于显示启用/停用状态
            },
            // 添加按钮文本
            addButtonKey: 'card.platform.add',
            addButtonDefault: '添加适配器',
        },

        services: {
            // 动态：每个 AI 服务提供商渲染为一张卡片
            dynamic: true,
            dynamicItemSchema: {
                idKey: null,
                label: '服务',
                color: '#3b82f6',
                titleKey: null,
                fields: [
                    { key: 'type', labelKey: 'field.service.type', labelDefault: '服务类型', type: 'select', options: ['llm', 'tts', 'image'] },
                    { key: 'format', labelKey: 'field.service.format', labelDefault: 'API 格式', type: 'select', options: ['openai', 'anthropic'] },
                    { key: 'api_key', labelKey: 'field.service.apiKey', labelDefault: 'API Key', type: 'password', placeholder: 'your-api-key' },
                    { key: 'base_url', labelKey: 'field.service.baseUrl', labelDefault: 'Base URL', type: 'text', placeholder: 'https://api.example.com/v1' },
                    { key: 'model', labelKey: 'field.service.model', labelDefault: '模型名称', type: 'text', placeholder: 'model-name' },
                ],
                statusField: 'api_key',  // 根据 api_key 是否填写显示状态
            },
            addButtonKey: 'card.service.add',
            addButtonDefault: '添加 AI 服务',
        },

        routing: {
            cards: [
                {
                    id: 'routing',
                    label: '路由',
                    titleKey: 'card.routing.title',
                    titleDefault: '模型路由',
                    subtitleKey: 'card.routing.desc',
                    subtitleDefault: '为不同 LLM 选择提供商与模型',
                    color: '#f59e0b',
                    fields: [
                        { key: 'main_llm.provider', labelKey: 'field.routing.mainLLM', labelDefault: '主对话模型', type: 'select', placeholder: '提供商名称' },
                        { key: 'main_llm.model', labelKey: 'field.routing.mainLLMModel', labelDefault: '模型', type: 'routing-model', providerField: 'main_llm.provider' },
                        { key: 'plan_llm.provider', labelKey: 'field.routing.planLLM', labelDefault: '计划模型', type: 'select', placeholder: '提供商名称' },
                        { key: 'plan_llm.model', labelKey: 'field.routing.planLLMModel', labelDefault: '模型', type: 'routing-model', providerField: 'plan_llm.provider' },
                        { key: 'tool_llm.provider', labelKey: 'field.routing.toolLLM', labelDefault: '工具调用模型', type: 'select', placeholder: '提供商名称' },
                        { key: 'tool_llm.model', labelKey: 'field.routing.toolLLMModel', labelDefault: '模型', type: 'routing-model', providerField: 'tool_llm.provider' },
                        { key: 'generic_llm.provider', labelKey: 'field.routing.genericLLM', labelDefault: '通用LLM', type: 'select', placeholder: '通用场景（XML修复/插件调用等），可复用主对话模型' },
                        { key: 'generic_llm.model', labelKey: 'field.routing.genericLLMModel', labelDefault: '模型', type: 'routing-model', providerField: 'generic_llm.provider' },
                        { key: 'vlm.provider', labelKey: 'field.routing.vlm', labelDefault: '多模态模型', type: 'select', placeholder: '支持图片识别的 VLM 模型' },
                        { key: 'vlm.model', labelKey: 'field.routing.vlmModel', labelDefault: '模型', type: 'routing-model', providerField: 'vlm.provider' },
                    ]
                },
            ]
        },

        // 插件管理已迁移至独立的 /plugins 页面
        plugins: {
            dynamic: false,
        },
    };

    // ============ Card 渲染器 ============

    class ConfigCards {
        /**
         * @param {HTMLElement} container - 卡片容器元素
         * @param {string} configName - 配置名称 (character/behavior/platforms/services/routing/plugins)
         * @param {object} data - 当前配置数据
         */
        constructor(container, configName, data, contextData) {
            this.container = container;
            this.configName = configName;
            this.data = data || {};
            this.contextData = contextData || {};
            this.schema = SCHEMA[configName] || { cards: [] };
            this.collapsedCards = {};  // 跟踪折叠状态
        }

        // ---------- 工具方法 ----------

        _t(key, fallback) {
            if (window.t) {
                var r = window.t(key);
                if (r !== key) return r;
            }
            return fallback;
        }

        _getValue(fullKey) {
            var parts = fullKey.split('.');
            var obj = this.data;
            for (var i = 0; i < parts.length; i++) {
                if (obj == null || typeof obj !== 'object') return undefined;
                obj = obj[parts[i]];
            }
            return obj;
        }

        _setValue(fullKey, value) {
            var parts = fullKey.split('.');
            var obj = this.data;
            for (var i = 0; i < parts.length - 1; i++) {
                if (!obj[parts[i]] || typeof obj[parts[i]] !== 'object') {
                    obj[parts[i]] = {};
                }
                obj = obj[parts[i]];
            }
            obj[parts[parts.length - 1]] = value;
        }

        _escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // ---------- 状态徽章 ----------

        _getStatusBadge(fieldDef, value) {
            if (fieldDef.type === 'boolean') {
                return value
                    ? '<span class="card-badge ok">' + this._t('card.status.enabled', '已启用') + '</span>'
                    : '<span class="card-badge warn">' + this._t('card.status.disabled', '已停用') + '</span>';
            }
            if (fieldDef.type === 'password' || (fieldDef.key && (fieldDef.key.toLowerCase().indexOf('key') !== -1 || fieldDef.key.toLowerCase().indexOf('token') !== -1))) {
                return value
                    ? '<span class="card-badge ok">' + this._t('card.status.set', '已设置') + '</span>'
                    : '<span class="card-badge error">' + this._t('card.status.unset', '未设置') + '</span>';
            }
            return '';
        }

        // ---------- 渲染单个字段 ----------

        _getProviderOptions() {
            // 路由卡片：使用 services 的 key 作为选项
            if (this.configName === 'routing') {
                var servicesData = this.contextData && this.contextData.services;
                if (servicesData && typeof servicesData === 'object') {
                    return Object.keys(servicesData).filter(function(k) { return k !== '_cardId'; });
                }
            }
            var providers = [];
            if (this.data && typeof this.data === 'object') {
                for (var key in this.data) {
                    if (this.data.hasOwnProperty(key) && key !== '_cardId') {
                        providers.push(key);
                    }
                }
            }
            return providers;
        }

        _renderField(fieldDef) {
            var val = this._getValue(fieldDef.key);
            var label = this._t(fieldDef.labelKey, fieldDef.labelDefault);
            var desc = '';
            if (fieldDef.descKey) {
                desc = '<span class="field-desc">' + this._t(fieldDef.descKey, fieldDef.descDefault) + '</span>';
            }
            var isSecret = fieldDef.type === 'password';
            var inputKey = fieldDef._dataKey || fieldDef.key;
            var parentAttr = fieldDef.parentToggle ? ' data-parent-toggle="' + fieldDef.parentToggle + '"' : '';

            if (fieldDef.type === 'boolean') {
                var checked = val ? ' checked' : '';
                return '<div class="card-field"' + parentAttr + '>'
                    + '<div class="toggle-row">'
                    + '<span class="toggle-label">' + label + '</span>'
                    + '<label class="toggle-switch">'
                    + '<input type="checkbox" data-key="' + inputKey + '" data-type="boolean"' + checked + '>'
                    + '<span class="toggle-slider"></span>'
                    + '</label>'
                    + '</div>'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'textarea') {
                var rows = fieldDef.key === 'raw_persona' ? 14 : 3;
                return '<div class="card-field"' + parentAttr + '>'
                    + '<span class="field-label">' + label + '</span>'
                    + '<textarea data-key="' + inputKey + '" rows="' + rows + '" placeholder="' + (fieldDef.placeholder || '') + '">' + this._escapeHtml(val || '') + '</textarea>'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'array') {
                return this._renderArrayField(fieldDef, label, desc, inputKey);
            }

            if (fieldDef.type === 'number') {
                return '<div class="card-field inline"' + parentAttr + '>'
                    + '<span class="field-label">' + label + '</span>'
                    + '<input type="number" data-key="' + inputKey + '" data-type="number" value="' + (val != null ? val : '') + '" placeholder="' + (fieldDef.placeholder || '') + '">'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'range') {
                var min = fieldDef.min || 0;
                var max = fieldDef.max || 100;
                var step = fieldDef.step || 1;
                var unit = fieldDef.rangeUnit || '';
                var currentVal = val != null && val !== '' ? val : (fieldDef.rangeDefault != null ? fieldDef.rangeDefault : min);
                return '<div class="card-field"' + parentAttr + '>'
                    + '<div class="range-label-row">'
                    + '<span class="field-label">' + label + '</span>'
                    + '<span class="range-value" data-range-display="' + inputKey + '">' + currentVal + (unit ? ' ' + unit : '') + '</span>'
                    + '</div>'
                    + '<div class="range-slider-row">'
                    + '<input type="range" data-key="' + inputKey + '" data-type="range" value="' + currentVal + '" min="' + min + '" max="' + max + '" step="' + step + '">'
                    + '</div>'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'select') {
                var options = fieldDef.options || this._getProviderOptions();
                var optHtml = '<option value="">' + (this._t('common.select', '请选择...') || '请选择...') + '</option>';
                for (var oi = 0; oi < options.length; oi++) {
                    var selected = (val === options[oi]) ? ' selected' : '';
                    optHtml += '<option value="' + this._escapeHtml(options[oi]) + '"' + selected + '>' + this._escapeHtml(options[oi]) + '</option>';
                }
                return '<div class="card-field"' + parentAttr + '>'
                    + '<span class="field-label">' + label + '</span>'
                    + '<select data-key="' + inputKey + '">' + optHtml + '</select>'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'routing-model') {
                var providerField = fieldDef.providerField || '';
                var inputId = 'routing-model-' + inputKey.replace(/\./g, '-');
                return '<div class="card-field"' + parentAttr + '>'
                    + '<span class="field-label">' + label + '</span>'
                    + '<div class="routing-model-row" style="display:flex;gap:6px;">'
                    + '<input type="text" id="' + inputId + '" data-key="' + inputKey + '" value="' + this._escapeHtml(val || '') + '" placeholder="' + (fieldDef.placeholder || '选择模型或手动输入') + '" style="flex:1;">'
                    + '<button type="button" class="btn-fetch-routing-model" data-provider-field="' + providerField + '" data-target-input="' + inputId + '" style="font-size:0.78rem;padding:4px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;white-space:nowrap;">' + (window.t('field.service.fetchModels') || '获取模型列表') + '</button>'
                    + '</div>'
                    + desc
                    + '</div>';
            }

            // text / password / url
            var inputType = isSecret ? 'password' : (fieldDef.type || 'text');
            var html = '<div class="card-field"' + parentAttr + '>'
                + '<span class="field-label">' + label + (isSecret ? this._getStatusBadge(fieldDef, val) : '') + '</span>'
                + '<input type="' + inputType + '" data-key="' + inputKey + '" value="' + this._escapeHtml(val || '') + '" placeholder="' + (fieldDef.placeholder || '') + '">'
                + desc
                + '</div>';
            // 模型字段追加"获取模型"按钮
            if (inputKey.endsWith('model')) {
                var providerName = this.currentCardProvider || '';
                html += '<div class="card-field"><button class="btn-fetch-models" onclick="window.fetchModels(\'' + this._escapeHtml(providerName) + '\')" style="font-size:0.78rem;padding:4px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;">' + (window.t('field.service.fetchModels') || '获取模型列表') + '</button></div>';
            }
            return html;
        }

        _renderArrayField(fieldDef, label, desc, inputKey) {
            var val = this._getValue(fieldDef.key) || [];
            if (!Array.isArray(val)) val = [];
            var dataKey = inputKey || fieldDef.key;
            var listId = 'ae-' + dataKey.replace(/\./g, '-');
            var itemsHtml = val.map(function (v) {
                return '<div class="card-ae-row">'
                    + '<input type="text" data-ae-key="' + dataKey + '" value="' + this._escapeHtml(typeof v === 'string' ? v : '') + '" placeholder="' + (fieldDef.placeholder || '') + '">'
                    + '<button type="button" class="card-ae-remove" title="' + this._t('card.remove', '移除') + '">&times;</button>'
                    + '</div>';
            }.bind(this)).join('');

            var parentAttr = fieldDef.parentToggle ? ' data-parent-toggle="' + fieldDef.parentToggle + '"' : '';
            return '<div class="card-field"' + parentAttr + '>'
                + '<span class="field-label">' + label + '</span>'
                + '<div class="card-array-editor" data-key="' + dataKey + '" id="' + listId + '">'
                + itemsHtml
                + '<button type="button" class="card-ae-add">+ ' + this._t('card.addItem', '添加') + '</button>'
                + '</div>'
                + desc
                + '</div>';
        }

        // ---------- 渲染一张卡片 ----------

        _renderCard(cardDef, cardData) {
            var cardId = cardDef.id || cardData._cardId || '';
            var collapsed = this.collapsedCards[cardId] || false;
            var color = cardDef.color || 'var(--accent)';
            var label = cardDef.label || cardDef.titleDefault || '';
            var title = cardDef.titleKey ? this._t(cardDef.titleKey, cardDef.titleDefault) : (cardDef.titleDefault || cardId);
            var subtitle = cardDef.subtitleKey ? this._t(cardDef.subtitleKey, cardDef.subtitleDefault) : (cardDef.subtitleDefault || '');

            // 摘要：显示关键字段的值
            var summaryParts = [];
            var fields = cardDef.fields || [];
            for (var i = 0; i < fields.length; i++) {
                var f = fields[i];
                if (f.type === 'array') continue;
                var v = cardData ? this._getValueInData(cardData, f.key) : this._getValue(f.key);
                if (v != null && v !== '' && v !== false) {
                    var lbl = this._t(f.labelKey, f.labelDefault);
                    var displayVal = f.type === 'password' ? '****' : String(v).substring(0, 20);
                    summaryParts.push(lbl + ': ' + displayVal);
                }
            }
            var summary = summaryParts.length ? summaryParts.slice(0, 3).join('  ·  ') : this._t('card.noData', '暂无数据');
            var previousData = this.data;
            if (cardData) this.data = cardData;

            var html = '<div class="config-card' + (collapsed ? ' collapsed' : '') + '" data-card-id="' + cardId + '" style="--card-accent:' + color + ';--card-accent-bg:' + color + '18;">';
            html += '<div class="card-header" data-action="toggle" data-card="' + cardId + '">';
            html += '<span class="card-icon" style="background:' + color + '18;color:' + color + ';">' + label + '</span>';
            html += '<div class="card-title-group">';
            html += '<div class="card-title">' + title + '</div>';
            if (subtitle) html += '<div class="card-subtitle">' + subtitle + '</div>';
            html += '</div>';

            // 状态徽章
            if (cardDef.statusField) {
                var statusVal = cardData ? this._getValueInData(cardData, cardDef.statusField) : this._getValue(cardDef.statusField);
                var statusFieldDef = { type: cardDef.statusField === 'enabled' ? 'boolean' : 'password', key: cardDef.statusField };
                html += this._getStatusBadge(statusFieldDef, statusVal);
            }

            html += '<span class="card-collapse-icon">▼</span>';
            html += '</div>';

            // 折叠摘要
            html += '<div class="card-summary">' + summary + '</div>';

            // 字段区
            html += '<div class="card-body">';
            for (var j = 0; j < fields.length; j++) {
                var renderFieldDef = fields[j];
                if (cardDef._isDynamic) {
                    renderFieldDef = Object.assign({}, fields[j], { _dataKey: cardId + '.' + fields[j].key });
                }
                html += this._renderField(renderFieldDef);
            }
            html += '</div>';
            this.data = previousData;

            // 动态卡片：操作按钮
            if (cardDef._isDynamic) {
                html += '<div class="card-actions-row">';
                html += '<button type="button" class="card-action-btn danger" data-action="remove-card" data-card="' + cardId + '">' + this._t('card.removeCard', '删除') + '</button>';
                html += '</div>';
            }

            html += '</div>';
            return html;
        }

        _getValueInData(dataObj, fullKey) {
            var parts = fullKey.split('.');
            var obj = dataObj;
            for (var i = 0; i < parts.length; i++) {
                if (obj == null || typeof obj !== 'object') return undefined;
                obj = obj[parts[i]];
            }
            return obj;
        }

        // ---------- 动态条目处理 ----------

        _getDynamicEntries() {
            var entries = [];
            for (var key in this.data) {
                if (!this.data.hasOwnProperty(key)) continue;
                var val = this.data[key];
                if (val && typeof val === 'object' && !Array.isArray(val)) {
                    entries.push({ key: key, data: val });
                }
            }
            return entries;
        }

        // ---------- 主渲染 ----------

        render() {
            this.container.innerHTML = '';

            if (this.schema.dynamic) {
                var entries = this._getDynamicEntries();
                var html = '<div class="card-grid" id="cardGrid">';

                if (entries.length === 0) {
                    html += '<div class="card-empty-state">'
                        + '<div class="empty-text">' + this._t('card.empty', '暂无配置项，点击下方按钮添加') + '</div>'
                        + '</div>';
                } else {
                    for (var i = 0; i < entries.length; i++) {
                        var cardDef = Object.assign({}, this.schema.dynamicItemSchema, {
                            id: entries[i].key,
                            titleDefault: entries[i].key,
                            _isDynamic: true,
                        });
                        this.currentCardProvider = entries[i].key;
                        html += this._renderCard(cardDef, entries[i].data);
                    }
                    this.currentCardProvider = null;
                }

                // 添加按钮
                html += '<button type="button" class="add-card-btn" data-action="add-card">'
                    + '<span class="plus-icon">+</span> '
                    + '<span>' + this._t(this.schema.addButtonKey, this.schema.addButtonDefault) + '</span>'
                    + '</button>';

                html += '</div>';
                this.container.innerHTML = html;
            } else {
                var cards = this.schema.cards || [];
                var html2 = '<div class="card-grid" id="cardGrid">';

                if (cards.length === 0) {
                    html2 += '<div class="card-empty-state">'
                        + '<div class="empty-text">' + this._t('card.empty', '暂无配置项') + '</div>'
                        + '</div>';
                } else {
                    for (var j = 0; j < cards.length; j++) {
                        html2 += this._renderCard(cards[j], null);
                    }
                }

                html2 += '</div>';
                this.container.innerHTML = html2;
            }

            this._bindEvents();

            // 初始化 parentToggle 可见性
            var self = this;
            var allCheckboxes = this.container.querySelectorAll('input[type="checkbox"][data-key]');
            allCheckboxes.forEach(function(cb) {
                var fieldDef = self._findFieldDef(null, cb.dataset.key);
                if (fieldDef && fieldDef.showFields) {
                    fieldDef.showFields.forEach(function(childKey) {
                        var childField = self.container.querySelector('.card-field[data-parent-toggle="' + childKey + '"]');
                        if (childField && !cb.checked) {
                            childField.style.display = 'none';
                        }
                    });
                }
            });
        }

        // ---------- 事件处理 ----------

        _bindEvents() {
            var self = this;
            if (this._eventsBound) return;
            this._eventsBound = true;

            this.container.addEventListener('click', function (e) {
                var target = e.target;

                // 折叠/展开
                var headerEl = target.closest('[data-action="toggle"]');
                if (headerEl) {
                    var cardId = headerEl.dataset.card;
                    var card = headerEl.closest('.config-card');
                    if (card) {
                        card.classList.toggle('collapsed');
                        self.collapsedCards[cardId] = card.classList.contains('collapsed');
                    }
                    return;
                }

                // 移除动态卡片
                var removeBtn = target.closest('[data-action="remove-card"]');
                if (removeBtn) {
                    var removeCardId = removeBtn.dataset.card;
                    var confirmMsg = self._t('card.confirmRemove', '确定要删除「') + removeCardId + self._t('card.confirmRemoveEnd', '」吗？');
                    self._showConfirm(confirmMsg).then(function (confirmed) {
                        if (confirmed) {
                            self._removeCard(removeCardId);
                            self.render();
                        }
                    });
                    return;
                }

                // 添加卡片
                var addBtn = target.closest('[data-action="add-card"]');
                if (addBtn) {
                    self._addCard();
                    return;
                }

                // 数组编辑器：添加
                if (target.classList.contains('card-ae-add')) {
                    var editor = target.closest('.card-array-editor');
                    var key = editor.dataset.key;
                    var row = document.createElement('div');
                    row.className = 'card-ae-row';
                    row.innerHTML = '<input type="text" data-ae-key="' + key + '" value=""> '
                        + '<button type="button" class="card-ae-remove" title="' + self._t('card.remove', '移除') + '">&times;</button>';
                    editor.insertBefore(row, target);
                    return;
                }

                // 数组编辑器：移除
                if (target.classList.contains('card-ae-remove')) {
                    var rowEl = target.closest('.card-ae-row');
                    if (rowEl) rowEl.remove();
                    return;
                }

                // 路由卡片：获取模型列表
                if (target.classList.contains('btn-fetch-routing-model')) {
                    var providerField = target.dataset.providerField;
                    var targetInputId = target.dataset.targetInput;
                    var providerSelect = self.container.querySelector('select[data-key="' + providerField + '"]');
                    var providerName = providerSelect ? providerSelect.value : '';
                    var modelInput = document.getElementById(targetInputId);

                    if (!providerName) {
                        self._showToast(self._t('card.routing.selectProviderFirst', '请先选择服务商'));
                        return;
                    }

                    window.fetchRoutingModels(providerName, function(selectedModel) {
                        if (modelInput && selectedModel) {
                            modelInput.value = selectedModel;
                            modelInput.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    });
                    return;
                }
            });

            // range 滑动条实时更新数值显示
            this.container.addEventListener('input', function (e) {
                if (e.target.type === 'range' && e.target.dataset.key) {
                    var display = self.container.querySelector('[data-range-display="' + e.target.dataset.key + '"]');
                    if (display) {
                        var unit = display.textContent.replace(/^[\d.]+/, '').trim();
                        display.textContent = e.target.value + (unit ? ' ' + unit : '');
                    }
                }
            });

            // Toggle 开关控制子字段显示/隐藏
            this.container.addEventListener('change', function(e) {
                if (e.target.type === 'checkbox' && e.target.dataset.key) {
                    var key = e.target.dataset.key;
                    var fieldDef = self._findFieldDef(null, key);
                    if (fieldDef && fieldDef.showFields) {
                        fieldDef.showFields.forEach(function(childKey) {
                            var childField = self.container.querySelector('.card-field[data-parent-toggle="' + childKey + '"]');
                            if (childField) {
                                childField.style.display = e.target.checked ? '' : 'none';
                            }
                        });
                    }
                }
            });
        }

        _removeCard(cardId) {
            delete this.data[cardId];
            var cardEl = this.container.querySelector('[data-card-id="' + cardId + '"]');
            if (cardEl) cardEl.remove();

            // 如果没卡片了，刷新以显示空状态
            var remaining = this.container.querySelectorAll('.config-card');
            if (remaining.length === 0) {
                this.render();
            }
        }

        _showModal(title, placeholder) {
            var self = this;
            return new Promise(function(resolve) {
                var overlay = document.createElement('div');
                overlay.className = 'modal-overlay';

                overlay.innerHTML = ''
                    + '<div class="modal-dialog">'
                    + '<div class="modal-dialog-header">' + self._escapeHtml(title) + '</div>'
                    + '<div class="modal-dialog-body">'
                    + '<input type="text" class="modal-input" placeholder="' + self._escapeHtml(placeholder || '') + '" autofocus>'
                    + '<div class="modal-error"></div>'
                    + '</div>'
                    + '<div class="modal-dialog-footer">'
                    + '<button class="modal-btn modal-cancel">' + (window.t ? window.t('common.cancel') : '取消') + '</button>'
                    + '<button class="modal-btn primary modal-confirm">' + (window.t ? window.t('common.confirm') : '确认添加') + '</button>'
                    + '</div>'
                    + '</div>';

                document.body.appendChild(overlay);

                var input = overlay.querySelector('.modal-input');
                var errorEl = overlay.querySelector('.modal-error');
                var confirmBtn = overlay.querySelector('.modal-confirm');
                var cancelBtn = overlay.querySelector('.modal-cancel');

                function close(val) {
                    overlay.addEventListener('animationend', function() {
                        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                    });
                    overlay.style.opacity = '0';
                    overlay.style.transition = 'opacity 0.15s';
                    if (overlay.parentNode && val === null) {
                        // 取消时立即移除
                        overlay.parentNode.removeChild(overlay);
                    }
                    setTimeout(function() {
                        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                    }, 200);
                    resolve(val);
                }

                confirmBtn.addEventListener('click', function() {
                    var val = input.value.trim();
                    if (!val) {
                        errorEl.textContent = self._t('card.nameRequired', '请输入名称');
                        errorEl.style.display = 'block';
                        input.focus();
                        return;
                    }
                    close(val);
                });

                cancelBtn.addEventListener('click', function() {
                    close(null);
                });

                overlay.addEventListener('click', function(e) {
                    if (e.target === overlay) close(null);
                });

                input.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') confirmBtn.click();
                    if (e.key === 'Escape') close(null);
                });

                setTimeout(function() { input.focus(); }, 150);
            });
        }

        // ---- 自定义确认对话框（替代浏览器原生 confirm） ----
        _showConfirm(message) {
            var self = this;
            return new Promise(function(resolve) {
                var overlay = document.createElement('div');
                overlay.className = 'modal-overlay';
                overlay.innerHTML = '<div class="modal-dialog" style="max-width:400px;">'
                    + '<div class="modal-dialog-header">' + (window.t('common.confirm', '确认') || '确认') + '</div>'
                    + '<div class="modal-dialog-body" style="padding:18px 20px;font-size:14px;line-height:1.5;">' + self._escapeHtml(message) + '</div>'
                    + '<div class="modal-dialog-footer">'
                    + '<button class="modal-btn modal-cancel" id="confirmCancel">' + (window.t('common.cancel', '取消') || '取消') + '</button>'
                    + '<button class="modal-btn primary" id="confirmOk" style="background:#ef4444;">' + (window.t('common.delete', '确认删除') || '确认删除') + '</button>'
                    + '</div>'
                    + '</div>';
                document.body.appendChild(overlay);

                function close(result) {
                    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                    resolve(result);
                }
                overlay.querySelector('#confirmOk').addEventListener('click', function() { close(true); });
                overlay.querySelector('#confirmCancel').addEventListener('click', function() { close(false); });
                overlay.addEventListener('click', function(e) { if (e.target === overlay) close(false); });
            });
        }

        _addCard() {
            var self = this;
            this._showModal(
                this._t('card.newTitle', '添加新项目'),
                this._t('card.newPlaceholder', '请输入名称')
            ).then(function(name) {
                if (!name) return;

                if (self.data[name]) {
                    self._showToast(self._t('card.nameExists', '该名称已存在'));
                    return;
                }

                var defaultData = {};
                var fields = self.schema.dynamicItemSchema.fields || [];
                for (var i = 0; i < fields.length; i++) {
                    var f = fields[i];
                    var parts = f.key.split('.');
                    var lastKey = parts[parts.length - 1];
                    if (f.type === 'boolean') {
                        defaultData[lastKey] = false;
                    } else if (f.type === 'number') {
                        defaultData[lastKey] = 0;
                    } else {
                        defaultData[lastKey] = '';
                    }
                }

                self.data[name] = defaultData;
                self.render();
            });
        }

        _showToast(msg) {
            var toast = document.createElement('div');
            toast.className = 'modal-toast';
            toast.textContent = msg;
            document.body.appendChild(toast);
            requestAnimationFrame(function() {
                toast.classList.add('visible');
            });
            setTimeout(function() {
                toast.classList.remove('visible');
                setTimeout(function() {
                    if (toast.parentNode) toast.parentNode.removeChild(toast);
                }, 300);
            }, 2000);
        }

        _findFieldDef(cardId, key) {
            var cards = this.schema.cards || [];
            for (var i = 0; i < cards.length; i++) {
                var card = cards[i];
                if (cardId && card.id !== cardId) continue;
                var fields = card.fields || [];
                for (var j = 0; j < fields.length; j++) {
                    if (fields[j].key === key) return fields[j];
                }
            }
            return null;
        }

        // ---------- 数据收集 ----------

        collectData() {
            var result = {};

            // 收集普通字段
            var inputs = this.container.querySelectorAll('input[data-key]:not([data-ae-key]), textarea[data-key], select[data-key]');
            for (var i = 0; i < inputs.length; i++) {
                var el = inputs[i];
                var fullKey = el.dataset.key;
                var keyType = el.dataset.type;
                var value;

                if (el.type === 'checkbox') {
                    value = el.checked;
                } else if (keyType === 'number') {
                    value = el.value === '' ? 0 : Number(el.value);
                    if (isNaN(value)) value = 0;
                } else if (keyType === 'range') {
                    value = parseFloat(el.value) || 0;
                } else {
                    value = el.value;
                }

                this._setValueInObject(result, fullKey, value);
            }

            // 收集数组字段
            var seenArrays = {};
            var aeInputs = this.container.querySelectorAll('input[data-ae-key]');
            for (var j = 0; j < aeInputs.length; j++) {
                var aeKey = aeInputs[j].dataset.aeKey;
                if (!seenArrays[aeKey]) {
                    seenArrays[aeKey] = [];
                }
                var v = aeInputs[j].value.trim();
                if (v) seenArrays[aeKey].push(v);
            }

            for (var arrKey in seenArrays) {
                if (seenArrays.hasOwnProperty(arrKey)) {
                    this._setValueInObject(result, arrKey, seenArrays[arrKey]);
                }
            }

            return result;
        }

        _setValueInObject(obj, fullKey, value) {
            var parts = fullKey.split('.');
            var target = obj;
            for (var i = 0; i < parts.length - 1; i++) {
                if (!target[parts[i]] || typeof target[parts[i]] !== 'object') {
                    target[parts[i]] = {};
                }
                target = target[parts[i]];
            }
            target[parts[parts.length - 1]] = value;
        }

        // ---------- 搜索 ----------

        search(query) {
            var q = query.toLowerCase().trim();
            var cards = this.container.querySelectorAll('.config-card, .add-card-btn');

            cards.forEach(function (card) {
                if (card.classList.contains('add-card-btn')) {
                    // 搜索时隐藏添加按钮
                    card.classList.toggle('search-hidden', q !== '');
                    return;
                }
                if (!q) {
                    card.classList.remove('search-hidden');
                    return;
                }
                var text = card.textContent.toLowerCase();
                if (text.indexOf(q) !== -1) {
                    card.classList.remove('search-hidden');
                    // 搜索到匹配项时自动展开卡片
                    card.classList.remove('collapsed');
                } else {
                    card.classList.add('search-hidden');
                }
            });
        }
        getCardCount() {
            if (this.schema.dynamic) {
                var count = 0;
                for (var k in this.data) {
                    if (this.data.hasOwnProperty(k) && this.data[k] && typeof this.data[k] === 'object' && !Array.isArray(this.data[k])) {
                        count++;
                    }
                }
                return count;
            }
            return (this.schema.cards || []).length;
        }

        getVisibleCardCount() {
            var cards = this.container.querySelectorAll('.config-card:not(.search-hidden)');
            return cards.length;
        }
    }

    // ============ 导出 ============

    window.ConfigCards = ConfigCards;
    window.CONFIG_CARD_SCHEMA = SCHEMA;

})();

// ===== 路由卡片模型获取函数（支持回调） =====

window.fetchRoutingModels = function (providerName, onSelect) {
    if (!providerName) return;

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    overlay.innerHTML = '<div class="modal-dialog" style="max-width:520px;">'
        + '<div class="modal-dialog-header">' + (window.t('field.service.fetchModels') || '选择模型') + ' - ' + providerName + '</div>'
        + '<div class="modal-dialog-body" style="min-height:100px;">'
        + '<input type="text" id="routingModelSearch-' + providerName + '" placeholder="' + (window.t('common.search', '搜索模型...')) + '" style="width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:14px;background:var(--bg);color:var(--text);margin-bottom:8px;">'
        + '<div id="routingModelList-' + providerName + '" style="max-height:320px;overflow-y:auto;"></div>'
        + '</div>'
        + '<div class="modal-dialog-footer">'
        + '<button class="modal-btn" id="routingModalCloseBtn">' + (window.t('common.cancel', '关闭')) + '</button>'
        + '</div>'
        + '</div>';

    document.body.appendChild(overlay);

    var listEl = overlay.querySelector('#routingModelList-' + providerName);
    listEl.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-secondary);">' + (window.t('common.loading', '加载中...')) + '</div>';

    function closeModal() {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    overlay.querySelector('#routingModalCloseBtn').addEventListener('click', closeModal);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });

    fetch('/api/services/' + encodeURIComponent(providerName) + '/models')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) {
                listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;">' + (data.error || (window.t('common.failed', '获取失败'))) + '</div>';
                return;
            }
            var models = data.models || [];
            if (!models.length) {
                listEl.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-secondary);">' + (window.t('common.empty', '无可用模型')) + '</div>';
                return;
            }
            var html = '';
            models.forEach(function (m) {
                var mid = (m.id || '').replace(/'/g, "\\'");
                html += '<div class="model-item" data-model-id="' + (m.id || '') + '" style="padding:8px 12px;cursor:pointer;font-size:14px;border-bottom:1px solid var(--border);border-radius:4px;">'
                    + '<span>' + (m.id || '') + '</span>'
                    + (m.owned_by ? ' <span style="color:var(--text-secondary);font-size:12px;">' + m.owned_by + '</span>' : '')
                    + '</div>';
            });
            listEl.innerHTML = html;

            // 绑定点击事件
            listEl.querySelectorAll('.model-item').forEach(function(item) {
                item.addEventListener('click', function() {
                    var modelId = this.dataset.modelId;
                    closeModal();
                    if (typeof onSelect === 'function') {
                        onSelect(modelId);
                    }
                });
            });
        })
        .catch(function () {
            listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;">' + (window.t('common.networkError', '网络错误')) + '</div>';
        });

    // 搜索过滤
    overlay.querySelector('#routingModelSearch-' + providerName).addEventListener('input', function () {
        var q = this.value.toLowerCase();
        var items = listEl.querySelectorAll('.model-item');
        for (var i = 0; i < items.length; i++) {
            items[i].style.display = items[i].textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
        }
    });
};

// ===== 全局模型获取函数 =====

window.fetchModels = function (providerName) {
    if (!providerName) return;

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    overlay.innerHTML = '<div class="modal-dialog" style="max-width:520px;">'
        + '<div class="modal-dialog-header">' + (window.t('field.service.fetchModels') || '选择模型') + ' - ' + providerName + '</div>'
        + '<div class="modal-dialog-body" style="min-height:100px;">'
        + '<input type="text" id="modelSearchModal-' + providerName + '" placeholder="' + (window.t('common.search', '搜索模型...')) + '" style="width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:14px;background:var(--bg);color:var(--text);margin-bottom:8px;">'
        + '<div id="modelListModal-' + providerName + '" style="max-height:320px;overflow-y:auto;"></div>'
        + '</div>'
        + '<div class="modal-dialog-footer">'
        + '<button class="modal-btn" id="modalCloseBtn">' + (window.t('common.cancel', '关闭')) + '</button>'
        + '</div>'
        + '</div>';

    document.body.appendChild(overlay);

    var listEl = overlay.querySelector('#modelListModal-' + providerName);
    listEl.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-secondary);">' + (window.t('common.loading', '加载中...')) + '</div>';

    function closeModal() {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    overlay.querySelector('#modalCloseBtn').addEventListener('click', closeModal);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });

    fetch('/api/services/' + encodeURIComponent(providerName) + '/models')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) {
                listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;">' + (data.error || (window.t('common.failed', '获取失败'))) + '</div>';
                return;
            }
            var models = data.models || [];
            if (!models.length) {
                listEl.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-secondary);">' + (window.t('common.empty', '无可用模型')) + '</div>';
                return;
            }
            var html = '';
            models.forEach(function (m) {
                var mid = (m.id || '').replace(/'/g, "\\'");
                html += '<div class="model-item" onclick="window.selectModel(\'' + providerName.replace(/'/g, "\\'") + '\',\'' + mid + '\')" style="padding:8px 12px;cursor:pointer;font-size:14px;border-bottom:1px solid var(--border);border-radius:4px;" data-model-id="' + (m.id || '') + '">'
                    + '<span>' + (m.id || '') + '</span>'
                    + (m.owned_by ? ' <span style="color:var(--text-secondary);font-size:12px;">' + m.owned_by + '</span>' : '')
                    + '</div>';
            });
            listEl.innerHTML = html;
        })
        .catch(function () {
            listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444;">' + (window.t('common.networkError', '网络错误')) + '</div>';
        });

    // 搜索过滤
    overlay.querySelector('#modelSearchModal-' + providerName).addEventListener('input', function () {
        var q = this.value.toLowerCase();
        var items = listEl.querySelectorAll('.model-item');
        for (var i = 0; i < items.length; i++) {
            items[i].style.display = items[i].textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
        }
    });
};

window.selectModel = function (providerName, modelId) {
    // 关闭所有模态框
    var overlays = document.querySelectorAll('.modal-overlay');
    for (var i = 0; i < overlays.length; i++) {
        if (overlays[i].parentNode) overlays[i].parentNode.removeChild(overlays[i]);
    }

    var cards = document.querySelectorAll('.config-card');
    for (var j = 0; j < cards.length; j++) {
        var titleEl = cards[j].querySelector('.card-title');
        if (titleEl && titleEl.textContent.trim().toLowerCase() === providerName.toLowerCase()) {
            var input = cards[j].querySelector('input[data-key$="model"]');
            if (input) {
                input.value = modelId;
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
            break;
        }
    }
};
