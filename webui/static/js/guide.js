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
            if (this._onboardingActive && !options._force) return;

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

        // ============================================
        // 启动引导
        // ============================================
        boot: function () {
            var self = this;
            checkSystem().then(function (status) {
                var onboarded = localStorage.getItem('tale-onboarded');
                var needsSetup = !status.running;

                if (needsSetup && !onboarded) {
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
                } else if (!status.running) {
                    var reason = status.offline_reason === 'missing_api_key'
                        ? self._pick(MESSAGES.waiting_api)
                        : self._pick(MESSAGES.offline_tip);
                    self.showVNDialog(reason, {
                        buttons: [
                            { text: '去配置', primary: true, action: function () {
                                window.location.href = '/config';
                            }},
                            { text: '关闭', action: function () { self.hideDialog(); }}
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
            this._onboardingActive = true;
            this._currentStep = 0;
            this.hideDialog();
            this.renderStep(0);
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
