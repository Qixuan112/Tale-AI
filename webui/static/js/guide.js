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
        _savedAnswers: {},   // 引导步骤已保存的答案
        _stepOrder: [],      // 步骤完成顺序
        _allowEmpty: false,  // 当前输入框是否允许空提交
        _v010: null,         // V0.1.0 流程状态对象
        _blipAudio: null,    // 说话音效 Audio 对象
        _blipMuted: false,   // 说话音效是否静音

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
            this.btnBack = document.getElementById('vnBtnBack');
            this.btnPrev = document.getElementById('vnBtnPrev');
            this.btnNext = document.getElementById('vnBtnNext');
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

            // 后退按钮
            if (this.btnBack) {
                this.btnBack.addEventListener('click', function () {
                    self._onBack();
                });
            }
            // 上一步 / 下一步 导航按钮
            if (this.btnPrev) {
                this.btnPrev.addEventListener('click', function () {
                    if (this.classList.contains('disabled')) return;
                    self._onBack();
                });
            }
            if (this.btnNext) {
                this.btnNext.addEventListener('click', function (e) {
                    if (this.classList.contains('disabled')) return;
                    e.stopPropagation();
                    self._onTextBoxClick();
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

        // ---- 说话音效（Undertale 风格 blip） ----
        playBlip: function () {
            if (this._blipMuted) return;
            if (localStorage.getItem('tale-sound') === 'off') return;
            try {
                if (!this._blipAudio) {
                    this._blipAudio = new Audio('/static/audio/blip.wav');
                    this._blipAudio.volume = 0.25;
                }
                this._blipAudio.currentTime = 0;
                var p = this._blipAudio.play();
                if (p && p.catch) p.catch(function () {});
            } catch (e) {}
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

            this._typingTimer = setTimeout(function () { self._typeTick(); }, this._typingSpeed);
        },

        // ---- 打字机单步（可变延迟：标点后停顿） ----
        _typeTick: function () {
            var self = this;
            this._typingTimer = null;
            if (this._typingIndex >= this._fullText.length) {
                this._onTypingDone();
                return;
            }
            var ch = this._fullText.charAt(this._typingIndex);
            this._typingIndex++;
            if (ch && !/\s/.test(ch)) this.playBlip();
            if (this.textContent) {
                this.textContent.textContent = this._fullText.substring(0, this._typingIndex);
            }
            if (this._typingIndex >= this._fullText.length) {
                this._onTypingDone();
                return;
            }
            // 标点停顿：长标点（句末）多停，短标点（句中）少停
            var delay = this._typingSpeed;
            // 连续点号（... 省略号序列）触发长停顿：当前或下一个是 . 才算
            var inDots = ch === '.' && (
                this._fullText.charAt(this._typingIndex) === '.' ||
                this._fullText.charAt(this._typingIndex - 2) === '.'
            );
            if (/[。！？!?\n…]/.test(ch) || inDots) {
                delay = this._typingSpeed * 8;   // 长停顿
            } else if (/[，、,；;：:]/.test(ch)) {
                delay = this._typingSpeed * 4;   // 短停顿
            }
            this._typingTimer = setTimeout(function () { self._typeTick(); }, delay);
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
                clearTimeout(this._typingTimer);
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

            // 打字中：下一步可用（用户可点击补全+推进）；待选项/输入出现时再禁用
            this._updateNavButtons({ nextDisabled: false });

            // 完成后执行回调
            this._onCompleteCallback = function () {
                // 显示按钮
                if (options.buttons && options.buttons.length) {
                    self._showButtons(options.buttons);
                } else if (options.onComplete) {
                    self._updateNavButtons({ nextDisabled: false });
                    options.onComplete();
                } else {
                    // 没有按钮也没有回调 → 立即关闭对话框
                    self.hideDialog();
                }
            };
        },

        // ---- 显示按钮（选择支或操作按钮） ----
        _showButtons: function (buttons) {
            var self = this;
            if (!this.actionsContainer) return;

            this.actionsContainer.innerHTML = '';
            // 选项出现：禁用下一步（用户必须先选一个选项）
            this._updateNavButtons({ nextDisabled: true });

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
            // 隐藏导航按钮
            this._updateNavButtons();

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
        askChoice: function (question, choices, opts) {
            opts = opts || {};
            var self = this;
            return new Promise(function (resolve) {
                var buttons = choices.map(function (c) {
                    return {
                        text: c.text,
                        primary: c.primary !== undefined ? c.primary : true,
                        action: function () {
                            var val = c.value !== undefined ? c.value : c.text;
                            // 保存步骤答案
                            if (opts.stepId) {
                                self._savedAnswers[opts.stepId] = val;
                                self._stepOrder.push(opts.stepId);
                            }
                            self.actionsContainer.innerHTML = '';
                            self._onCompleteCallback = null;
                            if (typeof c.action === 'function') {
                                c.action.call(self);
                            }
                            resolve(val);
                        }
                    };
                });
                self.showVNDialog(question, {
                    buttons: buttons
                });
            });
        },

        // ---- 辅助：提问（文本输入） ----
        askText: function (question, placeholder, opts) {
            opts = opts || {};
            var self = this;
            return new Promise(function (resolve) {
                // 包装 resolve 以保存步骤答案
                var savedResolve = function (val) {
                    if (opts.stepId) {
                        self._savedAnswers[opts.stepId] = val;
                        self._stepOrder.push(opts.stepId);
                    }
                    resolve(val);
                };
                self._pendingResolve = savedResolve;
                self._allowEmpty = !!opts.allowEmpty;
                self.showVNDialog(question);
                // 在打字完成后显示输入框
                var checkTyping = setInterval(function () {
                    if (!self._typingTimer && self._pendingResolve === savedResolve) {
                        clearInterval(checkTyping);
                        self._showTextInput(placeholder || '', opts.inputType || 'text');
                    }
                }, 100);
            });
        },

        // ---- 显示文本输入框 ----
        _showTextInput: function (placeholder, inputType) {
            // 清除自动隐藏定时器和回调，防止用户输入时对话框消失
            this._onCompleteCallback = null;
            if (this._autoHideTimer) {
                clearTimeout(this._autoHideTimer);
                this._autoHideTimer = null;
            }
            if (this.indicator) this.indicator.classList.add('hidden');
            if (this.actionsContainer) this.actionsContainer.innerHTML = '';
            // 输入框出现：禁用下一步（用户必须先输入并提交）
            this._updateNavButtons({ nextDisabled: true });
            if (this.inputArea) {
                this.inputArea.style.display = 'flex';
                if (this.textInput) {
                    this.textInput.type = inputType || 'text';
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
            if (!value && !this._allowEmpty) return;
            this._hideTextInput();
            if (this._pendingResolve) {
                var resolve = this._pendingResolve;
                this._pendingResolve = null;
                resolve(value);
            }
        },

        // ---- 返回上一步 ----
        _onBack: function () {
            if (this._stepOrder.length === 0) return;
            var self = this;
            var lastStep = this._stepOrder.pop();
            delete this._savedAnswers[lastStep];
            this._hideTextInput();
            if (this._pendingResolve) {
                this._pendingResolve('__back__');
                this._pendingResolve = null;
            }
            // 显示后退按钮（可能在第一步被隐藏了）
            if (this.btnBack) this.btnBack.style.display = 'inline-block';
            // 启动新协程（旧协程被中断）
            setTimeout(function () { self.startConversationalConfig(); }, 50);
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

        // ---- 导航按钮显示/禁用控制 ----
        // nextDisabled: true 时禁用下一步（选项/输入框出现时，用户必须先选/输入）
        _updateNavButtons: function (opts) {
            opts = opts || {};
            if (!this._onboardingActive) {
                if (this.btnPrev) this.btnPrev.style.display = 'none';
                if (this.btnNext) this.btnNext.style.display = 'none';
                return;
            }
            // 上一步：第一步（_stepOrder 空）时隐藏
            var atFirst = this._stepOrder.length === 0;
            if (this.btnPrev) {
                this.btnPrev.style.display = atFirst ? 'none' : 'inline-block';
                this.btnPrev.classList.toggle('disabled', !!opts.prevDisabled);
            }
            if (this.btnNext) {
                this.btnNext.style.display = 'inline-block';
                this.btnNext.classList.toggle('disabled', !!opts.nextDisabled);
            }
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
        // ---- 立绘情绪切换（V0.1.0） ----
        setEmotion: function (emotion) {
            var img = document.getElementById('guideCharacterImg');
            if (!img) return;
            var valid = ['neutral', 'happy', 'thinking', 'compliant', 'troubled',
                         'surprised', 'impressed', 'proud', 'sad'];
            if (valid.indexOf(emotion) === -1) emotion = 'neutral';
            img.style.opacity = '0';
            var self = this;
            setTimeout(function () {
                img.src = '/static/img/tali/tali_' + emotion + '.jpeg';
                img.style.opacity = '1';
            }, 150);
        },

        // ---- 拉取模型列表（V0.1.0） ----
        fetchModels: function (baseUrl, apiKey) {
            return fetch('/api/guide/fetch_models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
            })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (!res.ok) throw new Error(res.error || 'unknown');
                    return res.models || [];
                });
        },

        // ---- 语言选择器（V0.1.0 步骤1） ----
        showLangSelector: function (onPick) {
            var self = this;
            var sel = document.getElementById('vnLangSelector');
            var preview = document.getElementById('vnLangPreview');
            if (!sel) return;
            sel.style.display = 'flex';
            // 语言选择器出现：禁用下一步（用户必须先选语言）
            this._updateNavButtons({ nextDisabled: true });
            var btns = sel.querySelectorAll('.vn-lang-btn');
            var handler = function (e) {
                e.stopPropagation();
                var lang = e.currentTarget.getAttribute('data-lang');
                sel.style.display = 'none';
                btns.forEach(function (b) {
                    b.classList.remove('active');
                    b.removeEventListener('click', handler);
                    b.removeEventListener('mouseenter', hover);
                });
                if (preview) preview.textContent = '';
                if (onPick) onPick(lang);
            };
            var hover = function (e) {
                var lang = e.currentTarget.getAttribute('data-lang');
                e.currentTarget.classList.add('active');
                if (preview) preview.textContent = self._t('guide.v010.lang_preview_' + lang);
            };
            var leave = function (e) {
                e.currentTarget.classList.remove('active');
            };
            btns.forEach(function (b) {
                b.addEventListener('click', handler);
                b.addEventListener('mouseenter', hover);
                b.addEventListener('mouseleave', leave);
            });
            // 默认预览中文
            if (preview) preview.textContent = self._t('guide.v010.lang_preview_zh');
        },

        hideLangSelector: function () {
            var sel = document.getElementById('vnLangSelector');
            if (sel) sel.style.display = 'none';
        },

        // ---- V0.1.0 预设服务商表 ----
        PROVIDER_PRESETS: {
            deepseek:   { name: 'DeepSeek',    base_url: 'https://api.deepseek.com/v1' },
            silicon:    { name: 'SiliconFlow', base_url: 'https://api.siliconflow.cn/v1' },
            bytedance:  { name: 'ByteDance',   base_url: 'https://ark.cn-beijing.volces.com/api/v3' },
            custom:     { name: 'Custom',      base_url: '' }
        },

        // ============================================
        // 对话式引导配置 V0.1.0（不离开 VN 覆盖层）
        // ============================================
        startConversationalConfig: async function () {
            var self = this;
            this._onboardingActive = true;
            if (this.btnBack) this.btnBack.style.display = 'inline-block';

            if (!this._v010) {
                this._v010 = {
                    lang: null, userName: '', provider: null, providerName: '', apiKey: '', baseUrl: '',
                    models: [], assign: { main: '', plan: '', tool: '' },
                    second: { enabled: false, providerName: '', apiKey: '', baseUrl: '', models: [], assign: { main: '', plan: '', tool: '' } },
                    adapters: { qq: false, wxpc: false }, persona: ''
                };
            }
            var st = this._v010;

            try {
                // ── 第 1 步：语言选择 ──
                this.setEmotion('happy');
                if (!st.lang) {
                    if (this.btnBack && this._stepOrder.length === 0) this.btnBack.style.display = 'none';
                    await this.showVNDialogAsync(this._t('guide.v010.lang_title'));
                    var lang = await new Promise(function (resolve) { self.showLangSelector(resolve); });
                    st.lang = lang;
                    if (typeof window.i18n !== 'undefined' && window.i18n.setLang) window.i18n.setLang(lang);
                    this.hideLangSelector();
                    await this.say(this._t('guide.v010.lang_locked', { lang: lang }));
                    // zh/ja 采集用户名，en 可选
                    var name = '';
                    if (lang === 'zh' || lang === 'ja' || lang === 'en') {
                        name = await this.askText(this._t('guide.v010.name_question'), this._t('guide.v010.name_hint'), { stepId: 'v010_name', allowEmpty: true });
                        if (name === '__back__') return;
                    }
                    st.userName = name || (lang === 'en' ? 'operator' : '操作者');
                    if (name) await this.say(this._t('guide.v010.name_ack', { name: name }));
                }
                if (this.btnBack) this.btnBack.style.display = 'inline-block';

                // ── 第 2 步：分支判断 ──
                this.setEmotion('thinking');
                var branch = this._savedAnswers['v010_branch'];
                if (!branch) {
                    branch = await this.askChoice(
                        this._t('guide.v010.branch_question'),
                        [
                            { text: this._t('guide.v010.btn_yes'), value: 'yes' },
                            { text: this._t('guide.v010.btn_no'), value: 'no' }
                        ],
                        { stepId: 'v010_branch' }
                    );
                    if (branch === '__back__') return;
                }
                if (branch === 'no') {
                    this.setEmotion('sad');
                    await this.say(this._t('guide.v010.skip_goodbye'));
                    this._finishOnboarding();
                    return;
                }

                // ── 第 3 步：API Key ──
                this.setEmotion('troubled');
                await this._stepApiKey(st, false);

                // ── 第 4 步：模型分配 ──
                this.setEmotion('surprised');
                await this._stepModels(st, false);

                // 第二个服务端
                var wantSecond = this._savedAnswers['v010_second'];
                if (!wantSecond) {
                    wantSecond = await this.askChoice(
                        this._t('guide.v010.ask_second_server'),
                        [
                            { text: this._t('guide.v010.btn_second_yes'), value: 'yes' },
                            { text: this._t('guide.v010.btn_second_no'), value: 'no' }
                        ],
                        { stepId: 'v010_second' }
                    );
                    if (wantSecond === '__back__') return;
                }
                if (wantSecond === 'yes') {
                    st.second.enabled = true;
                    this.setEmotion('troubled');
                    await this._stepApiKey(st, true);
                    this.setEmotion('surprised');
                    await this._stepModels(st, true);
                    await this.say(this._t('guide.v010.second_server_done'));
                }

                // ── 第 5 步：适配器 ──
                this.setEmotion('compliant');
                await this._stepAdapters(st);

                // ── 第 6 步：人格 ──
                this.setEmotion('impressed');
                await this._stepPersona(st);

                // 重载配置让系统尝试启动
                await fetch('/api/system/reload', { method: 'POST' }).catch(function () {});

                // ── 第 7 步：收尾 ──
                this.setEmotion('proud');
                await this.say(this._t('guide.v010.finished'));
                this._finishOnboarding();
            } catch (e) {
                console.warn('[Tali] V0.1.0 引导中断:', e);
            } finally {
                this._hideTextInput();
                this.hideLangSelector();
                if (!localStorage.getItem('tale-onboarded')) {
                    localStorage.setItem('tale-onboarded', '1');
                }
                this._onboardingActive = false;
            }
        },

        // showVNDialog 的 Promise 包装（等待打字+用户点击推进）
        showVNDialogAsync: function (text) {
            var self = this;
            return new Promise(function (resolve) {
                self.showVNDialog(text, { onComplete: function () { resolve(); } });
            });
        },

        _finishOnboarding: function () {
            localStorage.setItem('tale-onboarded', '1');
            this._onboardingActive = false;
            this.hideDialog();
        },

        // ── 步骤3：API Key（isSecond=true 时采集第二服务端） ──
        _stepApiKey: async function (st, isSecond) {
            var self = this;
            var prefix = isSecond ? 'v010_2_' : 'v010_';
            var target = isSecond ? st.second : st;

            var providerKey = this._savedAnswers[prefix + 'provider'];
            if (!providerKey) {
                providerKey = await this.askChoice(
                    this._t('guide.v010.key_intro', { name: st.userName }),
                    [
                        { text: this._t('guide.v010.provider_deepseek'), value: 'deepseek' },
                        { text: this._t('guide.v010.provider_silicon'), value: 'silicon' },
                        { text: this._t('guide.v010.provider_bytedance'), value: 'bytedance' },
                        { text: this._t('guide.v010.provider_custom'), value: 'custom' }
                    ],
                    { stepId: prefix + 'provider' }
                );
                if (providerKey === '__back__') return;
            }
            var preset = this.PROVIDER_PRESETS[providerKey] || this.PROVIDER_PRESETS.custom;
            target.provider = providerKey;
            target.providerName = preset.name;

            var baseUrl = target.baseUrl;
            if (!baseUrl) {
                if (preset.base_url) {
                    target.baseUrl = preset.base_url;
                    await this.say(this._t('guide.v010.url_autofilled'));
                } else {
                    var urlInput = await this.askText(
                        this._t('guide.v010.url_question'),
                        this._t('guide.v010.url_placeholder'),
                        { stepId: prefix + 'url' }
                    );
                    if (urlInput === '__back__') return;
                    target.baseUrl = urlInput;
                }
            }

            var apiKey = target.apiKey;
            if (!apiKey) {
                apiKey = await this.askText(
                    this._t('guide.v010.key_hint'),
                    this._t('guide.v010.key_placeholder'),
                    { stepId: prefix + 'key', inputType: 'password' }
                );
                if (apiKey === '__back__') return;
                target.apiKey = apiKey;
            }

            // 保存到 services.yaml
            var svc = {};
            svc[target.providerName] = {
                type: 'llm',
                format: 'openai',
                api_key: target.apiKey,
                base_url: target.baseUrl,
                model: target.assign && target.assign.main ? target.assign.main : ''
            };
            await this.saveConfig('services', svc);
        },

        // ── 步骤4：模型分配（isSecond=true 时处理第二服务端） ──
        _stepModels: async function (st, isSecond) {
            var self = this;
            var prefix = isSecond ? 'v010_2_' : 'v010_';
            var target = isSecond ? st.second : st;
            var assign = target.assign;

            if (!target.models || !target.models.length) {
                try {
                    target.models = await this.fetchModels(target.baseUrl, target.apiKey);
                } catch (e) {
                    await this.say(this._t('guide.v010.models_fetch_failed', { error: e.message || e }));
                    target.models = [];
                }
            }

            if (!target.models.length) {
                // 无模型，允许手填
                var manual = await this.askText(
                    this._t('guide.v010.models_empty'),
                    this._t('guide.v010.key_placeholder'),
                    { stepId: prefix + 'manual_model', allowEmpty: true }
                );
                if (manual === '__back__') return;
                if (manual) {
                    target.models = [manual];
                } else {
                    await this.say(this._t('guide.v010.btn_skip_models'));
                    return;
                }
            }

            await this.say(this._t('guide.v010.models_fetched') + '\n' + target.models.join('、'));

            var mode = this._savedAnswers[prefix + 'assign_mode'];
            if (!mode) {
                var choices = [];
                if (target.models.length >= 1) choices.push({ text: this._t('guide.v010.btn_auto_assign'), value: 'auto' });
                choices.push({ text: this._t('guide.v010.btn_manual_assign'), value: 'manual' });
                choices.push({ text: this._t('guide.v010.btn_skip_models'), value: 'skip' });
                mode = await this.askChoice(this._t('guide.v010.assign_main'), choices, { stepId: prefix + 'assign_mode' });
                if (mode === '__back__') return;
            }

            if (mode === 'skip') {
                await this.say(this._t('guide.v010.btn_skip_models'));
                return;
            }

            if (mode === 'auto') {
                assign.main = assign.plan = assign.tool = target.models[0];
            } else {
                // 手动：三次选择
                var mkChoices = function () {
                    return target.models.map(function (m) { return { text: m, value: m }; });
                };
                if (!assign.main) {
                    assign.main = await this.askChoice(this._t('guide.v010.assign_main'), mkChoices(), { stepId: prefix + 'm_main' });
                    if (assign.main === '__back__') return;
                }
                if (!assign.plan) {
                    assign.plan = await this.askChoice(this._t('guide.v010.assign_plan'), mkChoices(), { stepId: prefix + 'm_plan' });
                    if (assign.plan === '__back__') return;
                }
                if (!assign.tool) {
                    assign.tool = await this.askChoice(this._t('guide.v010.assign_tool'), mkChoices(), { stepId: prefix + 'm_tool' });
                    if (assign.tool === '__back__') return;
                }
            }

            await this.say(this._t('guide.v010.assign_done'));

            // 更新 services.yaml 的 model 字段 + routing.yaml
            var svc = {};
            svc[target.providerName] = { model: assign.main };
            await this.saveConfig('services', svc);

            if (!isSecond) {
                await this.saveConfig('routing', {
                    main_llm: { provider: target.providerName, model: assign.main },
                    plan_llm: { provider: target.providerName, model: assign.plan },
                    tool_llm: { provider: target.providerName, model: assign.tool }
                });
            }
        },

        // ── 步骤5：适配器 ──
        _stepAdapters: async function (st) {
            var self = this;
            await this.say(this._t('guide.v010.adapter_intro'));
            await this.say(this._t('guide.v010.onebot_notice'));

            var qqChoice = this._savedAnswers['v010_qq'];
            if (qqChoice === undefined) {
                qqChoice = await this.askChoice(
                    this._t('guide.v010.btn_qq'),
                    [
                        { text: this._t('guide.v010.btn_qq'), value: 'yes' },
                        { text: this._t('guide.v010.btn_skip_chat'), value: 'no' }
                    ],
                    { stepId: 'v010_qq' }
                );
                if (qqChoice === '__back__') return;
            }
            st.adapters.qq = (qqChoice === 'yes');

            var wxChoice = this._savedAnswers['v010_wxpc'];
            if (wxChoice === undefined) {
                wxChoice = await this.askChoice(
                    this._t('guide.v010.btn_wxpc'),
                    [
                        { text: this._t('guide.v010.btn_wxpc'), value: 'yes' },
                        { text: this._t('guide.v010.btn_skip_chat'), value: 'no' }
                    ],
                    { stepId: 'v010_wxpc' }
                );
                if (wxChoice === '__back__') return;
            }
            st.adapters.wxpc = (wxChoice === 'yes');

            var platformsData = {};
            if (st.adapters.qq) {
                var wsUrl = this._savedAnswers['v010_qq_ws'];
                if (wsUrl === undefined) {
                    wsUrl = await this.askText(
                        this._t('guide.v010.qq_ws_question'),
                        this._t('guide.v010.qq_ws_placeholder'),
                        { stepId: 'v010_qq_ws', allowEmpty: true }
                    );
                    if (wsUrl === '__back__') return;
                }
                platformsData['QQ Adapter'] = {
                    adapter_type: 'qq',
                    enabled: true,
                    ws_url: wsUrl || '',
                    http_url: '',
                    auto_reconnect: true
                };
            }
            if (st.adapters.wxpc) {
                platformsData['WeChat PC'] = {
                    adapter_type: 'wechat_pc',
                    enabled: true,
                    poll_interval: 2.0,
                    language: st.lang === 'ja' ? 'cn_t' : 'cn',
                    permission_mode: 'allow_list'
                };
            }
            if (Object.keys(platformsData).length) {
                await this.saveConfig('platforms', platformsData);
            }
            await this.say(this._t('guide.v010.adapter_saved'));
        },

        // ── 步骤6：人格 ──
        _stepPersona: async function (st) {
            var self = this;
            await this.say(this._t('guide.v010.persona_missing'));
            var persona = st.persona;
            if (!persona) {
                persona = await this.askText(
                    this._t('guide.v010.persona_hint'),
                    this._t('guide.v010.persona_placeholder'),
                    { stepId: 'v010_persona' }
                );
                if (persona === '__back__') return;
                st.persona = persona;
            }
            await this.saveConfig('character', { raw_persona: persona });
            await this.say(this._t('guide.v010.persona_saved'));
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
            this._savedAnswers = {};
            this._stepOrder = [];
            if (this.btnBack) this.btnBack.style.display = 'none';
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
