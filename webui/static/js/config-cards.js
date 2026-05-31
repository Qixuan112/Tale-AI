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
                        { key: 'bot.min_message_delay', labelKey: 'field.behavior.minDelay', labelDefault: '最小延迟', type: 'number', placeholder: '秒', descKey: 'field.behavior.minDelayDesc', descDefault: '发送消息的最短延迟（秒）' },
                        { key: 'bot.max_message_delay', labelKey: 'field.behavior.maxDelay', labelDefault: '最大延迟', type: 'number', placeholder: '秒', descKey: 'field.behavior.maxDelayDesc', descDefault: '发送消息的最长延迟（秒）' },
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
                    { key: 'adapter_type', labelKey: 'field.platform.adapterType', labelDefault: '适配器类型', type: 'text', placeholder: 'qq / wechat_pc / websocket' },
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
                    { key: 'type', labelKey: 'field.service.type', labelDefault: '服务类型', type: 'text', placeholder: 'llm / tts / image' },
                    { key: 'format', labelKey: 'field.service.format', labelDefault: 'API 格式', type: 'text', placeholder: 'openai / anthropic' },
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
                    subtitleDefault: '为不同 LLM 选择提供商',
                    color: '#f59e0b',
                    fields: [
                        { key: 'main_llm.provider', labelKey: 'field.routing.mainLLM', labelDefault: '主对话模型', type: 'text', placeholder: '提供商名称' },
                        { key: 'plan_llm.provider', labelKey: 'field.routing.planLLM', labelDefault: '计划模型', type: 'text', placeholder: '提供商名称' },
                        { key: 'tool_llm.provider', labelKey: 'field.routing.toolLLM', labelDefault: '工具调用模型', type: 'text', placeholder: '提供商名称' },
                    ]
                },
            ]
        },

        plugins: {
            // 动态：每个插件渲染为一张卡片
            dynamic: true,
            dynamicItemSchema: {
                idKey: null,
                label: '插件',
                color: '#84cc16',
                titleKey: null,
                fields: [
                    { key: 'enabled', labelKey: 'field.plugin.enabled', labelDefault: '启用', type: 'boolean' },
                    // config 子字段动态生成（如果是对象）
                ],
                statusField: 'enabled',
            },
            addButtonKey: 'card.plugin.add',
            addButtonDefault: '添加插件',
            // 插件可以有嵌套 config 对象
            nestedConfigKey: 'config',
        },
    };

    // ============ Card 渲染器 ============

    class ConfigCards {
        /**
         * @param {HTMLElement} container - 卡片容器元素
         * @param {string} configName - 配置名称 (character/behavior/platforms/services/routing/plugins)
         * @param {object} data - 当前配置数据
         */
        constructor(container, configName, data) {
            this.container = container;
            this.configName = configName;
            this.data = data || {};
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

        _renderField(fieldDef) {
            var val = this._getValue(fieldDef.key);
            var label = this._t(fieldDef.labelKey, fieldDef.labelDefault);
            var desc = '';
            if (fieldDef.descKey) {
                desc = '<span class="field-desc">' + this._t(fieldDef.descKey, fieldDef.descDefault) + '</span>';
            }
            var isSecret = fieldDef.type === 'password';
            var inputKey = fieldDef._dataKey || fieldDef.key;

            if (fieldDef.type === 'boolean') {
                var checked = val ? ' checked' : '';
                return '<div class="card-field">'
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
                return '<div class="card-field">'
                    + '<span class="field-label">' + label + '</span>'
                    + '<textarea data-key="' + inputKey + '" rows="3" placeholder="' + (fieldDef.placeholder || '') + '">' + this._escapeHtml(val || '') + '</textarea>'
                    + desc
                    + '</div>';
            }

            if (fieldDef.type === 'array') {
                return this._renderArrayField(fieldDef, label, desc, inputKey);
            }

            if (fieldDef.type === 'number') {
                return '<div class="card-field inline">'
                    + '<span class="field-label">' + label + '</span>'
                    + '<input type="number" data-key="' + inputKey + '" data-type="number" value="' + (val != null ? val : '') + '" placeholder="' + (fieldDef.placeholder || '') + '">'
                    + desc
                    + '</div>';
            }

            // text / password / url / select
            var inputType = isSecret ? 'password' : (fieldDef.type || 'text');
            return '<div class="card-field">'
                + '<span class="field-label">' + label + (isSecret ? this._getStatusBadge(fieldDef, val) : '') + '</span>'
                + '<input type="' + inputType + '" data-key="' + inputKey + '" value="' + this._escapeHtml(val || '') + '" placeholder="' + (fieldDef.placeholder || '') + '">'
                + desc
                + '</div>';
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

            return '<div class="card-field">'
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
                        html += this._renderCard(cardDef, entries[i].data);
                    }
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
        }

        // ---------- 事件处理 ----------

        _bindEvents() {
            var self = this;

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
                    if (confirm(confirmMsg)) {
                        self._removeCard(removeCardId);
                    }
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
