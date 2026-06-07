/**
 * Tale 视觉小说风格引导系统
 * ==============================
 * 全屏 Galgame/VN 风格：
 * 场景背景 + 角色立绘 + 底部对话框 + 打字机效果
 * 点击 / Space / Enter 推进对话
 */
(function () {
    'use strict';

    // ============================================
    // 引导消息库
    // ============================================
    var MESSAGES = {
        welcome: ['guide.welcome.0', 'guide.welcome.1', 'guide.welcome.2'],
        waiting_api: ['guide.waiting_api.0', 'guide.waiting_api.1'],
        all_done: ['guide.all_done.0', 'guide.all_done.1'],
        idle_tips: ['guide.idle_tips.0', 'guide.idle_tips.1', 'guide.idle_tips.2', 'guide.idle_tips.3', 'guide.idle_tips.4', 'guide.idle_tips.5', 'guide.idle_tips.6'],
        night_tips: ['guide.night_tips.0', 'guide.night_tips.1', 'guide.night_tips.2'],
        offline_tip: ['guide.offline_tip.0', 'guide.offline_tip.1'],
        summon: ['guide.summon.0', 'guide.summon.1', 'guide.summon.2', 'guide.summon.3'],
        running: ['guide.running.0', 'guide.running.1', 'guide.running.2']
    };

    // ============================================
    // 配置检查
    // ============================================
    var CHECK_CACHE = null;

    function checkSystem() {
        return fetch('/api/status')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                CHECK_CACHE = data;
                return data;
            })
            .catch(function () {
                CHECK_CACHE = { running: false, offline_reason: 'unknown' };
                return CHECK_CACHE;
            });
    }

    // ============================================
    // 视觉小说引导管理器
    // ============================================
    var Guide = {
        overlay: null,
        textEl: null,
        textContent: null,
        cursor: null,
        indicator: null,
        nameTag: null,
        actionsContainer: null,
        trigger: null,
        btnSkip: null,
        btnAuto: null,
        btnClose: null,
        inputArea: null,
        textInput: null,
        inputBtn: null,
        _pendingResolve: null,

        _initialized: false,
        _onboardingActive: false,
        _autoHideTimer: null,
        _idleInterval: null,
        _typingTimer: null,
        _fullText: '',
        _typingIndex: 0,
        _typingSpeed: 45,    // ms/字
        _autoMode: false,
        _autoTimer: null,
        _onCompleteCallback: null,  // 当前对话完成后的回调

        // ---- 初始化 ----
        init: function () {
            if (this._initialized) return;
            this._initialized = true;

            this.overlay = document.getElementById('guideOverlay');
            this.textEl = document.getElementById('guideText');
            this.textContent = document.getElementById('vnTextContent');
            this.cursor = document.getElementById('vnCursor');
            this.indicator = document.getElementById('vnIndicator');
            this.nameTag = document.getElementById('vnNameTag');
            this.actionsContainer = document.getElementById('guideActions');
            this.trigger = document.getElementById('guideTrigger');
            this.btnSkip = document.getElementById('vnBtnSkip');
            this.btnAuto = document.getElementById('vnBtnAuto');
            this.btnClose = document.getElementById('vnBtnClose');
            this.inputArea = document.getElementById('vnInputArea');
            this.textInput = document.getElementById('vnTextInput');
            this.inputBtn = document.getElementById('vnInputBtn');

            if (!this.overlay) return;

            var self = this;

            // 点击对话框推进
            var textbox = this.overlay.querySelector('.vn-textbox');
            if (textbox) {
                textbox.addEventListener('click', function (e) {
                    // 如果正在显示按钮选择，不响应点击
                    if (self.actionsContainer.children.length > 0) return;
                    self._onTextBoxClick();
                });
            }

            // 键盘控制
            document.addEventListener('keydown', function (e) {
                if (!self.overlay.classList.contains('active')) return;
                if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault();
                    if (self.actionsContainer.children.length > 0) return;
                    self._onTextBoxClick();
                }
            });

            // 文本输入确认按钮
            if (this.inputBtn) {
                this.inputBtn.addEventListener('click', function () {
                    self._submitTextInput();
                });
            }
            // 文本输入框 Enter 键
            if (this.textInput) {
                this.textInput.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        self._submitTextInput();
                    }
                });
            }

            // SKIP 按钮
            if (this.btnSkip) {
                this.btnSkip.addEventListener('click', function () {
                    if (self._onboardingActive) {
                        self.skipOnboarding();
                    } else {
                        self.hideDialog();
                    }
                });
            }

            // AUTO 按钮
            if (this.btnAuto) {
                this.btnAuto.addEventListener('click', function () {
                    self._toggleAuto();
                });
            }

            // 关闭按钮
            if (this.btnClose) {
                this.btnClose.addEventListener('click', function () {
                    if (self._onboardingActive) {
                        self.skipOnboarding();
                    } else {
                        self.hideDialog();
                    }
                });
            }

            // 召唤触发器
            if (this.trigger) {
                this.trigger.addEventListener('click', function () {
                    self.onSummon();
                });
            }

            // 顶部通知铃铛 → 召唤 Tali 帮助菜单
            var notifyBtn = document.getElementById('topbarNotifyBtn');
            if (notifyBtn) {
                notifyBtn.addEventListener('click', function () {
                    self.showHelpMenu();
                });
            }

            // 延迟启动
            setTimeout(function () { self.boot(); }, 800);
        },

        // ---- 对话框点击逻辑 ----
        _onTextBoxClick: function () {
            // 如果还在打字中 → 立刻显示完整文本
            if (this._typingTimer) {
                this._completeTyping();
                return;
            }
            // 打字已完成 → 推进到下一步（触发回调）
            if (this._onCompleteCallback) {
                var cb = this._onCompleteCallback;
                this._onCompleteCallback = null;
                cb();
            }
        },

        // ---- 打字机效果 ----
        _startTyping: function (text) {
            var self = this;
            this._fullText = text || '';
            this._typingIndex = 0;
            if (this.textContent) this.textContent.textContent = '';
            if (this.cursor) this.cursor.classList.remove('done');
            if (this.indicator) this.indicator.classList.add('hidden');
            if (this.actionsContainer) this.actionsContainer.innerHTML = '';

            this._clearTypingTimer();

            if (!this._fullText) {
                this._onTypingDone();
                return;
            }

            this._typingTimer = setInterval(function () {
                self._typingIndex++;
                if (self._typingIndex >= self._fullText.length) {
                    self._onTypingDone();
                }
                if (self.textContent) {
                    self.textContent.textContent = self._fullText.substring(0, self._typingIndex);
                }
            }, this._typingSpeed);
        },

        _completeTyping: function () {
            this._clearTypingTimer();
            if (this.textContent) this.textContent.textContent = this._fullText;
            this._onTypingDone();
        },

        _onTypingDone: function () {
            this._clearTypingTimer();
            if (this.cursor) this.cursor.classList.add('done');
            if (this.indicator) this.indicator.classList.remove('hidden');

            if (this._autoMode && this._onCompleteCallback) {
                var self = this;
                var cb = this._onCompleteCallback;
                this._onCompleteCallback = null;
                this._autoTimer = setTimeout(function () {
                    cb();
                }, 2500);
            }
        },

        _clearTypingTimer: function () {
            if (this._typingTimer) {
                clearInterval(this._typingTimer);
                this._typingTimer = null;
            }
        },

        // ---- AUTO 模式 ----
        _toggleAuto: function () {
            this._autoMode = !this._autoMode;
            if (this.btnAuto) {
                if (this._autoMode) {
                    this.btnAuto.classList.add('active');
                } else {
                    this.btnAuto.classList.remove('active');
                    if (this._autoTimer) {
                        clearTimeout(this._autoTimer);
                        this._autoTimer = null;
                    }
                }
            }
            // 如果当前打字已完成且 auto 开启，触发推进
            if (this._autoMode && !this._typingTimer && this._onCompleteCallback) {
                var self = this;
                var cb = this._onCompleteCallback;
                this._onCompleteCallback = null;
                this._autoTimer = setTimeout(function () { cb(); }, 2500);
            }
        },

        _disableAuto: function () {
            this._autoMode = false;
            if (this.btnAuto) this.btnAuto.classList.remove('active');
            if (this._autoTimer) {
                clearTimeout(this._autoTimer);
                this._autoTimer = null;
            }
        },

        // ---- 显示视觉小说对话 ----
        showVNDialog: function (text, options) {
            var self = this;
            options = options || {};

            if (!this.overlay) return;

            this._disableAuto();

            // 设置角色名
            if (this.nameTag) {
                this.nameTag.textContent = options.speaker || 'Tali';
            }

            // 显示覆盖层
            this.overlay.classList.add('active');
            if (this.trigger) this.trigger.classList.remove('visible');

            // 打字机播放文本
            this._startTyping(text || '');

            // 完成后执行回调
            this._onCompleteCallback = function () {
                // 显示按钮
                if (options.buttons && options.buttons.length) {
                    self._showButtons(options.buttons);
                } else if (options.onComplete) {
                    options.onComplete();
                } else {
                    // 没有按钮也没有回调 → 自动隐藏
                    if (!self._autoMode) {
                        self._autoHideTimer = setTimeout(function () {
                            self.hideDialog();
                        }, 8000);
                    }
                }
            };
        },

        // ---- 显示按钮（选择支或操作按钮） ----
        _showButtons: function (buttons) {
            var self = this;
            if (!this.actionsContainer) return;

            this.actionsContainer.innerHTML = '';

            buttons.forEach(function (btn) {
                var el = document.createElement('button');
                el.className = 'guide-btn' + (btn.primary ? '' : ' secondary');
                el.textContent = btn.text || '';
                el.addEventListener('click', function (e) {
                    e.stopPropagation();
                    self.actionsContainer.innerHTML = '';
                    self._onCompleteCallback = null;  // 清除后续回调
                    if (btn.action) btn.action.call(self);
                });
                self.actionsContainer.appendChild(el);
            });
        },

        // ---- 隐藏对话覆盖层 ----
        hideDialog: function () {
            this._hideTextInput();
            if (this.overlay) this.overlay.classList.remove('active');
            this._clearTypingTimer();
            this._disableAuto();
            this._onCompleteCallback = null;
            if (this._pendingResolve) {
                this._pendingResolve(null);
                this._pendingResolve = null;
            }
            if (this.actionsContainer) this.actionsContainer.innerHTML = '';

            if (this._autoHideTimer) {
                clearTimeout(this._autoHideTimer);
                this._autoHideTimer = null;
            }

            // 显示召唤触发器
            if (this.trigger && !this._onboardingActive) {
                this.trigger.classList.add('visible');
            }
        },

        // ---- 兼容旧接口：showDialog ----
        showDialog: function (text, buttons) {
            this.showVNDialog(text, {
                buttons: buttons || [],
                _force: true
            });
        },

        // ---- 辅助：纯文本对话（无按钮） ----
        say: function (text) {
            var self = this;
            return new Promise(function (resolve) {
                self.showVNDialog(text, {
                    onComplete: function () {
                        resolve();
                    }
                });
            });
        },

        // ---- 辅助：提问（选项按钮） ----
        askChoice: function (question, choices) {
            var self = this;
            return new Promise(function (resolve) {
                var buttons = choices.map(function (c) {
                    return {
                        text: c.text,
                        primary: c.primary !== undefined ? c.primary : true,
                        action: function () {
                            if (typeof c.action === 'function') {
                                c.action.call(self);
                            }
                            resolve(c.value !== undefined ? c.value : c.text);
                        }
                    };
                });
                self.showVNDialog(question, {
                    buttons: buttons
                });
            });
        },

        // ---- 辅助：提问（文本输入） ----
        askText: function (question, placeholder) {
            var self = this;
            return new Promise(function (resolve) {
                self._pendingResolve = resolve;
                self.showVNDialog(question);
                // 在打字完成后显示输入框
                var checkTyping = setInterval(function () {
                    if (!self._typingTimer && self._pendingResolve === resolve) {
                        clearInterval(checkTyping);
                        self._showTextInput(placeholder || '');
                    }
                }, 100);
            });
        },

        // ---- 显示文本输入框 ----
        _showTextInput: function (placeholder) {
            // 清除自动隐藏定时器和回调，防止用户输入时对话框消失
            this._onCompleteCallback = null;
            if (this._autoHideTimer) {
                clearTimeout(this._autoHideTimer);
                this._autoHideTimer = null;
            }
            if (this.indicator) this.indicator.classList.add('hidden');
            if (this.actionsContainer) this.actionsContainer.innerHTML = '';
            if (this.inputArea) {
                this.inputArea.style.display = 'flex';
                if (this.textInput) {
                    this.textInput.placeholder = placeholder;
                    this.textInput.value = '';
                    setTimeout(function (self) {
                        self.focus();
                    }, 150, this.textInput);
                }
            }
        },

        // ---- 隐藏文本输入框 ----
        _hideTextInput: function () {
            if (this.inputArea) this.inputArea.style.display = 'none';
            if (this.textInput) this.textInput.value = '';
        },

        // ---- 提交文本输入 ----
        _submitTextInput: function () {
            var value = this.textInput ? this.textInput.value.trim() : '';
            if (!value) return; // 空输入不处理
            this._hideTextInput();
            if (this._pendingResolve) {
                var resolve = this._pendingResolve;
                this._pendingResolve = null;
                resolve(value);
            }
        },

        // ---- 深合并辅助 ----
        _deepMerge: function (target, source) {
            var output = {};
            for (var key in target) {
                if (target.hasOwnProperty(key)) {
                    output[key] = target[key];
                }
            }
            for (var key in source) {
                if (source.hasOwnProperty(key)) {
                    if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key]) &&
                        typeof output[key] === 'object' && output[key] !== null && !Array.isArray(output[key])) {
                        output[key] = this._deepMerge(output[key], source[key]);
                    } else {
                        output[key] = source[key];
                    }
                }
            }
            return output;
        },

        // ---- 保存配置到服务器 ----
        saveConfig: function (name, data) {
            var self = this;
            // 先 GET 现有配置，再深度合并新字段 POST 回去
            return fetch('/api/config/' + name)
                .then(function (r) { return r.json(); })
                .then(function (existing) {
                    var merged = self._deepMerge(existing || {}, data);
                    return fetch('/api/config/' + name, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(merged)
                    });
                })
                .then(function (r) { return r.json(); })
                .then(function (result) {
                    if (!result.ok) throw new Error('Save failed');
                    return result;
                })
                .catch(function (err) {
                    console.error('[Tali] 配置保存失败:', name, err);
                    // 不中断流程，让用户继续
                });
        },

        // ============================================
        // 对话式引导配置（不离开 VN 覆盖层）
        // ============================================
        startConversationalConfig: async function () {
            var self = this;
            this._onboardingActive = true;

            try {
                // ── 第 1 步：选择服务商 ──
                var provider = await this.askChoice(
                    this._t('guide.step1_question'),
                    [
                        { text: this._t('guide.step1_deepseek'), value: 'deepseek' },
                        { text: this._t('guide.step1_openai'), value: 'openai' },
                        { text: this._t('guide.step1_custom'), value: 'custom' }
                    ]
                );

                var providerName, baseUrl;
                if (provider === 'deepseek') {
                    providerName = 'DeepSeek';
                    baseUrl = 'https://api.deepseek.com/v1';
                    await this.say(this._t('guide.deepseek_reply'));
                } else if (provider === 'openai') {
                    providerName = 'OpenAI';
                    baseUrl = 'https://api.openai.com/v1';
                    await this.say(this._t('guide.openai_reply'));
                } else {
                    providerName = 'Custom';
                    baseUrl = '';
                    await this.say(this._t('guide.custom_reply'));
                }

                // ── 第 2 步：API Key ──
                var apiKey = await this.askText(
                    this._t('guide.step2_question'),
                    this._t('guide.step2_placeholder')
                );

                // ── 第 3 步：模型名称 ──
                var defaultModel = provider === 'deepseek' ? 'deepseek-chat' : (provider === 'openai' ? 'gpt-4o' : '');
                var modelPlaceholder = defaultModel || this._t('guide.step3_placeholder');
                var model = await this.askText(
                    this._t('guide.step3_question'),
                    modelPlaceholder
                );
                if (!model && defaultModel) model = defaultModel;
                if (!model) model = '';

                // 保存服务商信息到 services.yaml
                var servicesData = {};
                servicesData[providerName] = {
                    type: 'llm',
                    format: 'openai',
                    api_key: apiKey || '',
                    base_url: baseUrl,
                    model: model
                };
                await this.saveConfig('services', servicesData);

                // 保存路由到 routing.yaml
                await this.saveConfig('routing', {
                    main_llm: { provider: providerName },
                    plan_llm: { provider: providerName },
                    tool_llm: { provider: providerName },
                    generic_llm: { provider: providerName },
                    vlm: { provider: providerName }
                });

                var modelMsg = model ? this._t('guide.model_set', {model: model}) : this._t('guide.model_not_set');
                await this.say(this._t('guide.apikey_saved') + modelMsg);

                // ── 第 4 步：角色名 ──
                var charName = await this.askText(
                    this._t('guide.step4_question'),
                    this._t('guide.step4_placeholder')
                );
                if (!charName) charName = this._t('guide.char_unnamed');
                await this.say(this._t('guide.char_named', {name: charName}));
                await this.saveConfig('character', { character: { ChineseName: charName } });

                // ── 第 5 步：性别 ──
                var gender = await this.askChoice(
                    this._t('guide.step5_question', {name: charName}),
                    [
                        { text: this._t('guide.gender_secret'), value: '保密' },
                        { text: this._t('guide.gender_female'), value: '女' },
                        { text: this._t('guide.gender_male'), value: '男' }
                    ]
                );
                await this.say(this._t('guide.step5_ack'));
                await this.saveConfig('character', { character: { ChineseName: charName, gender: gender } });

                // 重载配置让系统尝试启动
                await fetch('/api/system/reload', { method: 'POST' }).catch(function () {});

                // ── 第 6 步：唤醒设置 ──
                var wantWake = await this.askChoice(
                    this._t('guide.step6_question'),
                    [
                        { text: this._t('guide.step6_yes'), value: 'yes' },
                        { text: this._t('guide.step6_skip'), value: 'skip' }
                    ]
                );

                if (wantWake === 'yes') {
                    var enableKeyword = await this.askChoice(
                        this._t('guide.step6_keyword_question'),
                        [
                            { text: this._t('guide.step6_enable'), value: 'yes' },
                            { text: this._t('guide.step6_disable'), value: 'no' }
                        ]
                    );
                    var keywords = [];
                    if (enableKeyword === 'yes') {
                        var kwInput = await this.askText(
                            this._t('guide.step6_keyword_input'),
                            this._t('guide.step6_keyword_placeholder')
                        );
                        if (kwInput) {
                            keywords = kwInput.split(/[,，\s]+/).filter(function(k) { return k; });
                        }
                    }

                    var enableQuote = await this.askChoice(
                        this._t('guide.step6_quote_question'),
                        [
                            { text: this._t('guide.step6_enable'), value: 'yes' },
                            { text: this._t('guide.step6_disable'), value: 'no' }
                        ]
                    );

                    await this.saveConfig('behavior', {
                        wake: {
                            enable_keyword_wake: enableKeyword === 'yes',
                            waking_keywords: keywords,
                            enable_quote_wake: enableQuote === 'yes'
                        }
                    });

                    await this.say(this._t('guide.step6_saved'));
                }

                // ── 第 7 步：完成 ──
                await this.askChoice(
                    this._t('guide.done_title', {name: charName}),
                    [
                        { text: this._t('guide.done_use'), value: 'done' },
                        { text: this._t('guide.done_config'), value: 'config', action: function () {
                            window.location.href = '/config';
                        }}
                    ]
                );

                localStorage.setItem('tale-onboarded', '1');
                this._onboardingActive = false;
            } catch (e) {
                // 用户 SKIP 或其他中断
                console.warn('[Tali] 对话式引导中断:', e);
            } finally {
                this._hideTextInput();
                // 确保总是标记完成（即使在流程中 SKIP）
                if (!localStorage.getItem('tale-onboarded')) {
                    localStorage.setItem('tale-onboarded', '1');
                }
                this._onboardingActive = false;
            }
        },

        // ============================================
        // 启动引导
        // ============================================
        boot: function () {
            var self = this;
            checkSystem().then(function (status) {
                var onboarded = localStorage.getItem('tale-onboarded');

                // 首次访问先自我介绍（sessionStorage 控制，同标签页仅一次）
                if (!sessionStorage.getItem('tale-intro-shown')) {
                    sessionStorage.setItem('tale-intro-shown', '1');
                    self.showVNDialog(self._pick(MESSAGES.welcome), {
                        buttons: [
                            { text: self._t('guide.btn_gotit'), action: function () {
                                self.hideDialog();
                                // 自我介绍完：未配置则直接进引导，不弹第二个对话框
                                if (!onboarded && !status.running) {
                                    self.startOnboarding();
                                } else {
                                    if (self.trigger) self.trigger.classList.add('visible');
                                    self._startIdleLoop();
                                }
                            }}
                        ]
                    });
                    return;
                }

                // 后续访问
                if (!onboarded) {
                    if (!status.running) {
                        self.showVNDialog(self._pick(MESSAGES.waiting_api), {
                            buttons: [
                                { text: self._t('guide.btn_start'), primary: true, action: function () {
                                    self.startOnboarding();
                                }},
                                { text: self._t('guide.btn_later'), action: function () {
                                    self._skipSetup();
                                }}
                            ]
                        });
                    } else {
                        self.showVNDialog(self._pick(MESSAGES.running), {
                            buttons: [
                                { text: self._t('guide.btn_gotit'), action: function () { self.hideDialog(); }}
                            ]
                        });
                        self._startIdleLoop();
                    }
                } else {
                    if (self.trigger) self.trigger.classList.add('visible');
                    self._startIdleLoop();
                }
            });
        },

        // ============================================
        // 召唤
        // ============================================
        onSummon: function () {
            if (this._onboardingActive) return;

            var self = this;
            checkSystem().then(function (status) {
                if (!status.running) {
                    self.showVNDialog(self._pick(MESSAGES.offline_tip), {
                        buttons: [
                            { text: self._t('guide.btn_goconfig'), primary: true, action: function () {
                                window.location.href = '/config';
                            }},
                            { text: self._t('guide.btn_close'), action: function () { self.hideDialog(); }}
                        ]
                    });
                } else {
                    self.showVNDialog(self._pick(MESSAGES.summon));
                }
            });
        },

        // ---- 帮助菜单（通知铃铛入口） ----
        showHelpMenu: function () {
            if (this._onboardingActive) return;
            if (this.overlay && this.overlay.classList.contains('active')) return;

            var self = this;
            this.say(self._pick(MESSAGES.summon)).then(function () {
                return self.askChoice(self._t('guide.help_question'), [
                    { text: self._t('guide.help_config'), value: 'config' },
                    { text: self._t('guide.help_chat'), value: 'chat' },
                    { text: self._t('guide.help_no_reply'), value: 'no_reply' },
                    { text: self._t('guide.help_platforms'), value: 'platforms' },
                    { text: self._t('guide.help_status'), value: 'status' },
                    { text: self._t('guide.help_character'), value: 'character' },
                    { text: self._t('guide.help_wake'), value: 'wake' }
                ]);
            }).then(function (choice) {
                switch (choice) {
                    case 'config':
                        window.location.href = '/config';
                        break;
                    case 'chat':
                        window.location.href = '/chat';
                        break;
                    case 'no_reply':
                        checkSystem().then(function (status) {
                            var msg = status.running
                                ? self._t('guide.no_reply_running')
                                : self._t('guide.no_reply_offline');
                            self.showVNDialog(msg, {
                                buttons: [
                                    { text: self._t('guide.btn_goconfig'), primary: true, action: function () {
                                        window.location.href = '/config?focus=services';
                                    }},
                                    { text: self._t('guide.btn_close'), action: function () { self.hideDialog(); }}
                                ]
                            });
                        });
                        break;
                    case 'platforms':
                        window.location.href = '/config?focus=platforms';
                        break;
                    case 'status':
                        checkSystem().then(function (status) {
                            var msg = status.running
                                ? self._t('guide.status_running')
                                : self._t('guide.status_offline');
                            self.say(msg);
                        });
                        break;
                    case 'character':
                        window.location.href = '/config?focus=character';
                        break;
                    case 'wake':
                        window.location.href = '/config?focus=behavior';
                        break;
                }
            });
        },

        // ============================================
        // 闲时提示循环
        // ============================================
        _startIdleLoop: function () {
            var self = this;
            this._idleInterval = setInterval(function () {
                if (self._onboardingActive) return;
                if (self.overlay && self.overlay.classList.contains('active')) return;
                if (Math.random() < 0.25) {
                    var hour = new Date().getHours();
                    // 晚上 23:00 ~ 早上 6:00 用夜间关怀
                    var pool = (hour >= 23 || hour < 6) ? MESSAGES.night_tips : MESSAGES.idle_tips;
                    self.showVNDialog(self._pick(pool));
                }
            }, 90000);
        },

        // ---- 跳过设置（不标记完成） ----
        _skipSetup: function () {
            this.hideDialog();
            this._startIdleLoop();
        },

        // ============================================
        // 引导流程（多步向导）
        // ============================================
        startOnboarding: function () {
            this.startConversationalConfig();
        },

        skipOnboarding: function () {
            localStorage.setItem('tale-onboarded', '1');
            this._onboardingActive = false;
            this._hideTextInput();
            if (this._pendingResolve) {
                this._pendingResolve(null);
                this._pendingResolve = null;
            }
            this._clearTypingTimer();
            this._disableAuto();
            if (this.overlay) this.overlay.classList.remove('active');
            this._startIdleLoop();
        },

        // ---- 工具 ----
        _pick: function (arr) {
            var key = arr[Math.floor(Math.random() * arr.length)];
            return this._t(key);
        },
        _t: function(key, params) {
            return (typeof window.t === 'function') ? window.t(key, params) : key;
        }
    };

    // ============================================
    // 配置页焦点支持
    // ============================================
    function handleConfigFocus() {
        var params = new URLSearchParams(window.location.search);
        var focus = params.get('focus');
        if (focus && window.location.pathname === '/config') {
            setTimeout(function () {
                // 使用 hash 导航展开对应 section（新版卡片布局无 tab）
                window.location.hash = 'config-section-' + focus;
                var tips = {
                    'services': window.t('guide.step_tip_services'),
                    'character': window.t('guide.step_tip_character'),
                    'platforms': window.t('guide.step_tip_platforms'),
                    'behavior': window.t('guide.step_tip_behavior'),
                };
                var tip = tips[focus];
                if (tip) {
                    Guide.showVNDialog(tip, {
                        buttons: [
                            { text: window.t('guide.btn_gotit') || '知道了', primary: true, action: function () { Guide.hideDialog(); }}
                        ]
                    });
                }
            }, 500);
        }
    }

    // ============================================
    // 初始化
    // ============================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { Guide.init(); handleConfigFocus(); });
    } else {
        Guide.init();
        handleConfigFocus();
    }

    window.Guide = Guide;
})();
