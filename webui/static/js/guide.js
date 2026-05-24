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
        welcome: [
            '嗨嗨～我是 Tali！Tale-AI 的看板娘兼日常小管家～让我带你完成初始设置吧！',
            '欢迎来到 Tale！我是 Tali～先配好服务商，就能一起搞数字生活啦！',
            '初次见面！我是 Tali～系统还需要一点配置才能跑起来，跟我来吧～',
        ],
        waiting_api: [
            '唔，还没有 API Key 呢～要先去配置一下 LLM 服务商哦！',
            '系统现在还不能运行……先去填一下 API Key 吧，我在这儿等你～',
        ],
        all_done: [
            '搞定啦！所有配置都完成咯～去跟 TA 聊聊天吧！',
            '完美！系统已经准备好啦～点左侧"对话"就能开始，一起搞数字生活呀～',
        ],
        idle_tips: [
            '今天日程搞定没？',
            '有什么不懂的随时点我哦，我就在右下角～',
            '点击配置中心可以修改所有设置，随时调整都行！',
            '对话页面可以直接跟 AI 聊天哦，去试试嘛～',
            '你去过仪表盘了吗？那里能看到系统运行状态呢！',
            '唔，你又在忙……记得休息一下眼睛哦。',
            '喝杯水吧，我帮你盯着系统～',
        ],
        night_tips: [
            '唔，都这么晚了……明天再弄嘛，快去睡觉！',
            '熬夜对身体不好哦！我记着呢，快去休息～',
            '你又在熬夜……有什么明天再搞啦，我帮你看着。',
        ],
        offline_tip: [
            '系统当前离线，可能是缺 API Key 哦～要我帮你看看吗？',
            '唔，系统好像没在跑……要不要我帮你检查一下配置？',
        ],
        summon: [
            '来啦来啦～有什么需要帮忙的吗？',
            '嗯？在找什么功能吗？我帮你指路！',
            '嘿嘿，我就知道你会点我～说吧说吧～',
            '一起搞数字生活呀～',
        ],
        running: [
            '系统已经在运行啦！一切正常～一起搞数字生活呀～',
            '运行正常！今天也要一起加油哦～',
            '状态良好～有什么我可以帮你的吗？',
        ]
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
                    '首先来配置 AI 服务商吧！你想用哪个大模型？',
                    [
                        { text: 'DeepSeek', value: 'deepseek' },
                        { text: 'OpenAI', value: 'openai' },
                        { text: '自定义', value: 'custom' }
                    ]
                );

                var providerName, baseUrl;
                if (provider === 'deepseek') {
                    providerName = 'DeepSeek';
                    baseUrl = 'https://api.deepseek.com/v1';
                    await this.say('DeepSeek 性价比超高，不错的选择！我帮你把地址都记好啦～');
                } else if (provider === 'openai') {
                    providerName = 'OpenAI';
                    baseUrl = 'https://api.openai.com/v1';
                    await this.say('OpenAI 生态丰富，GPT-4 能力很强哦！我帮你把地址填好了～');
                } else {
                    providerName = 'Custom';
                    baseUrl = '';
                    await this.say('自定义服务商也没问题，只要兼容 OpenAI 接口格式就行！');
                }

                // ── 第 2 步：API Key ──
                var apiKey = await this.askText(
                    '接下来需要 API Key～去官网申请一个然后粘贴给我吧！我会好好保管的～',
                    'sk-...'
                );

                // ── 第 3 步：模型名称 ──
                var defaultModel = provider === 'deepseek' ? 'deepseek-chat' : (provider === 'openai' ? 'gpt-4o' : '');
                var modelPlaceholder = defaultModel || '模型名称';
                var model = await this.askText(
                    '使用的模型名称是什么？不填的话就用默认的啦～',
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
                    main_llm: { provider: providerName }
                });

                var modelMsg = model ? '「' + model + '」，记住了！服务商这边全部搞定啦～' : '服务商这边搞定啦～回头记得去配置页补上模型名称哦！';
                await this.say('收到！API Key 已保存～' + modelMsg);

                // ── 第 4 步：角色名 ──
                var charName = await this.askText(
                    '来给你的 AI 角色起个响亮的名字吧！你想叫 TA 什么？',
                    '比如：小灵、星辰、晓梦...'
                );
                if (!charName) charName = '未命名';
                await this.say('「' + charName + '」——好名字！我喜欢～我帮你填上～');
                await this.saveConfig('character', { character: { ChineseName: charName } });

                // ── 第 5 步：性别 ──
                var gender = await this.askChoice(
                    charName + '的性别是什么呢？',
                    [
                        { text: '保密', value: '保密' },
                        { text: '女', value: '女' },
                        { text: '男', value: '男' }
                    ]
                );
                await this.say('了解啦～');
                await this.saveConfig('character', { character: { ChineseName: charName, gender: gender } });

                // 重载配置让系统尝试启动
                await fetch('/api/system/reload', { method: 'POST' }).catch(function () {});

                // ── 第 6 步：完成 ──
                await this.askChoice(
                    '搞定啦！核心配置都填好了～系统正在尝试启动，你可以去仪表盘看看状态，或者去对话页面跟「' + charName + '」聊聊天！想手动调整更多细节的话，随时去配置中心哦～',
                    [
                        { text: '开始使用！', value: 'done' },
                        { text: '去配置页看看', value: 'config', action: function () {
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

                if (!onboarded) {
                    // 首次启动 → 自动显示看板娘引导
                    if (!status.running) {
                        self.showVNDialog(self._pick(MESSAGES.welcome), {
                            buttons: [
                                { text: '开始引导', primary: true, action: function () {
                                    self.startOnboarding();
                                }},
                                { text: '稍后再说', action: function () {
                                    self._skipSetup();
                                }}
                            ]
                        });
                    } else {
                        self.showVNDialog(self._pick(MESSAGES.running), {
                            buttons: [
                                { text: '知道了', action: function () { self.hideDialog(); }}
                            ]
                        });
                        self._startIdleLoop();
                    }
                } else {
                    // 后续访问 → 不弹对话框，只显示触发器 + 闲时提示
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
                            { text: '去配置', primary: true, action: function () {
                                window.location.href = '/config';
                            }},
                            { text: '关闭', action: function () { self.hideDialog(); }}
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
                return self.askChoice('有什么我可以帮你的吗？选一个话题吧～', [
                    { text: '系统配置问题', value: 'config' },
                    { text: '如何开始对话', value: 'chat' },
                    { text: 'AI 不回复怎么办', value: 'no_reply' },
                    { text: '平台适配器设置', value: 'platforms' },
                    { text: '查看运行状态', value: 'status' },
                    { text: '修改角色人设', value: 'character' }
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
                                ? '系统正在运行中～如果 AI 还是没回复，可能是没 @ 到它，或者被权限过滤了哦。去配置中心检查一下权限设置吧！'
                                : '唔，系统还没启动呢……可能是缺 API Key 或模型没配好。要不要去配置页面看看？';
                            self.showVNDialog(msg, {
                                buttons: [
                                    { text: '去配置', primary: true, action: function () {
                                        window.location.href = '/config?focus=services';
                                    }},
                                    { text: '关闭', action: function () { self.hideDialog(); }}
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
                                ? '系统一切正常！正在运行中～有什么问题随时问我哦。'
                                : '系统当前离线……可能是还没配置好 API Key 或者服务没启动。去配置页面检查一下吧！';
                            self.say(msg);
                        });
                        break;
                    case 'character':
                        window.location.href = '/config?focus=character';
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

        renderStep: function (step) {
            var self = this;
            if (!this.overlay) return;

            var steps = [
                {
                    title: '第一步：配置 AI 服务商',
                    desc: 'Tale 需要连接 AI 模型才能工作哦。填上 API Key 和模型名称就行～',
                    tip: '推荐 DeepSeek、OpenAI 或任何兼容 OpenAI 接口的服务',
                    action: function () { window.location.href = '/config?focus=services'; }
                },
                {
                    title: '第二步：设定角色人设',
                    desc: '给你的 AI 起名字、设性格、写爱好，让 TA 更有灵魂！人设越丰富，角色表现越棒～',
                    tip: '可以先简单填几个，以后随时都能改',
                    action: function () { window.location.href = '/config?focus=character'; }
                },
                {
                    title: '第三步：选择聊天平台',
                    desc: 'Tale 可以接入 QQ、Telegram、B站等平台。只在网页上聊的话这步跳过就好！',
                    tip: '适配器可以在"适配器管理"页面配置',
                    action: function () { window.location.href = '/config?focus=platforms'; }
                },
                {
                    title: '全部完成！',
                    desc: 'Tale 已经准备就绪啦！去跟你的 AI 小伙伴打个招呼吧～一起搞数字生活呀～',
                    tip: '以后点右下角的问号按钮就能随时召唤我啦',
                    action: function () {
                        localStorage.setItem('tale-onboarded', '1');
                        self._onboardingActive = false;
                        self.hideDialog();
                    }
                }
            ];

            var s = steps[step] || steps[steps.length - 1];
            var isLast = step >= steps.length - 1;

            // 清理旧步骤面板
            var oldPanel = this.overlay.querySelector('.vn-step-panel');
            if (oldPanel) oldPanel.remove();

            // 显示覆盖层
            this.overlay.classList.add('active');
            if (this.trigger) this.trigger.classList.remove('visible');

            // 创建步骤面板
            var stepContent = document.createElement('div');
            stepContent.className = 'vn-step-panel';

            // 步骤进度
            var stepsHtml = '';
            for (var i = 0; i < steps.length; i++) {
                var cls = i < step ? 'done' : (i === step ? 'active' : '');
                var num = i < step ? '✓' : (i + 1);
                var label = steps[i].title.replace(/第.步：/, '');
                stepsHtml += '<li class="' + cls + '"><span class="guide-step-num">' + num + '</span>' + label + '</li>';
            }

            // 导航按钮
            var navHtml = '';
            if (step > 0) {
                navHtml += '<button class="guide-btn secondary" id="guideStepPrev">上一步</button>';
            }
            if (isLast) {
                navHtml += '<button class="guide-btn" id="guideStepFinish">开始使用！</button>';
            } else {
                navHtml += '<button class="guide-btn" id="guideStepNext">下一步</button>';
            }
            navHtml += '<button class="guide-btn secondary" id="guideStepSkip">跳过引导</button>';

            stepContent.innerHTML =
                '<h2>' + s.title + '</h2>' +
                '<p class="guide-step-desc">' + s.desc + '</p>' +
                '<ul class="vn-step-list">' + stepsHtml + '</ul>' +
                (s.tip ? '<div class="vn-step-tip">' + s.tip + '</div>' : '') +
                '<div class="guide-actions">' + navHtml + '</div>';

            this.overlay.appendChild(stepContent);

            // 同时更新底部对话框显示简短提示
            this.nameTag.textContent = 'Tali';
            this._startTyping('来，跟着我一步一步搞定吧～');
            if (this.indicator) this.indicator.classList.add('hidden');
            if (this.actionsContainer) this.actionsContainer.innerHTML = '';

            // 绑定按钮事件
            var selfRef = this;
            setTimeout(function () {
                var prevBtn = document.getElementById('guideStepPrev');
                var nextBtn = document.getElementById('guideStepNext');
                var finishBtn = document.getElementById('guideStepFinish');
                var skipBtn = document.getElementById('guideStepSkip');

                if (prevBtn) prevBtn.addEventListener('click', function () {
                    selfRef.renderStep(step - 1);
                });
                if (nextBtn) nextBtn.addEventListener('click', function () {
                    selfRef.renderStep(step + 1);
                });
                if (finishBtn) finishBtn.addEventListener('click', function () {
                    s.action();
                });
                if (skipBtn) skipBtn.addEventListener('click', function () {
                    selfRef.skipOnboarding();
                });
            }, 0);
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
            // 清理步骤面板
            var panel = this.overlay ? this.overlay.querySelector('.vn-step-panel') : null;
            if (panel) panel.remove();
            this._startIdleLoop();
        },

        // ---- 工具 ----
        _pick: function (arr) {
            return arr[Math.floor(Math.random() * arr.length)];
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
                var tab = document.querySelector('[data-tab="' + focus + '"]');
                if (tab) tab.click();
                var tips = {
                    'services': '在这里填入你的 API Key 和模型名称就好～',
                    'character': '这是角色设定页面，名字、性格、爱好都可以随意改！',
                    'platforms': '这里配置 QQ、Telegram 等平台，目前可以先跳过哦～',
                };
                Guide.showVNDialog(tips[focus] || '在这个页面修改配置吧～');
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
