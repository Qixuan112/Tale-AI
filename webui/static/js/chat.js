/**
 * Tale WebUI - 对话管理
 * 功能：会话列表加载、消息渲染、发送消息、新建/清空对话
 */

(function () {
    'use strict';

    // ===== DOM 引用 =====
    const elConvList = document.getElementById('conversationList');
    const elChatMessages = document.getElementById('chatMessages');
    const elChatHeader = document.getElementById('chatHeader');
    const elMessageInput = document.getElementById('messageInput');
    const elBtnSend = document.getElementById('btnSend');
    const elBtnNewChat = document.getElementById('btnNewChat');
    const elBtnClearChat = document.getElementById('btnClearChat');

    // ===== 状态 =====
    let conversations = [];
    let currentConvId = null;
    let isSending = false;
    var uploadedImages = [];

    // ===== 初始化 =====
    async function init() {
        await loadConversations();
        if (conversations.length > 0) {
            await switchConversation(conversations[0].id);
        }
    }

    // ===== 加载会话列表 =====
    async function loadConversations() {
        try {
            const res = await fetch('/api/chat/conversations');
            conversations = await res.json();
            renderConvList();
        } catch (e) {
            elConvList.innerHTML = '<div class="empty-tip">' + (window.t ? window.t('chat.loadingFailed') : '加载失败') + '</div>';
        }
    }

    function renderConvList() {
        if (!conversations.length) {
            elConvList.innerHTML = '<div class="empty-tip">' + (window.t ? window.t('chat.noConversations') : '暂无对话') + '</div>';
            return;
        }
        elConvList.innerHTML = conversations.map(c => `
            <div class="conv-item ${c.id === currentConvId ? 'active' : ''}" data-id="${c.id}">
                <div class="conv-title">${escapeHtml(c.title)} #${c.id}</div>
                <div class="conv-preview">${escapeHtml(c.last_message || (window.t ? window.t('chat.noMessages') : '无消息'))}</div>
                <div class="conv-meta">
                    <span>${escapeHtml(c.time || '')}</span>
                    <span>${c.count} ${window.t ? window.t('chat.messages') : '条'}</span>
                </div>
                <button class="conv-delete" title="${window.t ? window.t('chat.delete') : '删除'}">&times;</button>
            </div>
        `).join('');

        elConvList.querySelectorAll('.conv-item').forEach(item => {
            const id = parseInt(item.dataset.id);
            item.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete')) return;
                switchConversation(id);
            });
        });

        // 删除按钮事件（独立绑定防止冒泡干扰）
        elConvList.querySelectorAll('.conv-delete').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const item = e.target.closest('.conv-item');
                const id = parseInt(item.dataset.id);
                const conv = conversations.find(c => c.id === id);
                const name = conv ? conv.title + ' #' + conv.id : '#' + id;
                if (!confirm((window.t ? window.t('chat.confirmDelete') : '确定要永久删除会话') + `「${name}」吗？`)) return;
                try {
                    const res = await fetch(`/api/chat/${id}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.ok) {
                        await loadConversations();
                    } else {
                        alert((window.t ? window.t('chat.deleteFailed') : '删除失败') + ': ' + (data.error || ''));
                    }
                } catch (e) {
                    alert((window.t ? window.t('chat.deleteFailed') : '删除失败') + ': ' + e.message);
                }
            });
        });
    }

    // ===== 切换会话 =====
    async function switchConversation(convId) {
        currentConvId = convId;
        renderConvList();

        const conv = conversations.find(c => c.id === convId);
        if (conv) {
            elChatHeader.querySelector('.chat-title').textContent = `${conv.title} #${conv.id}`;
        }

        try {
            const res = await fetch(`/api/chat/history/${convId}`);
            const messages = await res.json();
            renderMessages(messages);
        } catch (e) {
            elChatMessages.innerHTML = '<div class="empty-tip">' + (window.t ? window.t('chat.loadMessagesFailed') : '加载消息失败') + '</div>';
        }
    }

    // ===== XML 消息解析渲染 =====
    /**
     * 检测字符串是否包含 XML 消息标签
     */
    function isXmlContent(str) {
        return /<msg>/.test(str) || /<act>/.test(str) || /<plan>/.test(str) || /<tool>/.test(str);
    }

    /**
     * 将 XML 消息内容渲染为 HTML
     * 支持标签: msg, text, emoji, at_targets, act, plan, tool
     */
    function renderXmlContent(xmlStr) {
        // 用 DOMParser 解析
        const parser = new DOMParser();
        let doc;
        try {
            doc = parser.parseFromString(`<root>${xmlStr}</root>`, 'text/xml');
        } catch (e) {
            return escapeHtml(xmlStr);
        }

        // 检查解析错误
        const parseError = doc.querySelector('parsererror');
        if (parseError) {
            return escapeHtml(xmlStr);
        }

        const root = doc.documentElement;
        let parts = [];

        // 渲染 <msg> 标签
        root.querySelectorAll('msg').forEach(msgEl => {
            const msgDiv = document.createElement('div');
            msgDiv.className = 'msg-block';

            msgEl.childNodes.forEach(child => {
                if (child.nodeType === Node.ELEMENT_NODE) {
                    const tag = child.tagName.toLowerCase();
                    const text = child.textContent || '';

                    if (tag === 'text') {
                        const span = document.createElement('span');
                        span.className = 'msg-text';
                        span.textContent = text;
                        msgDiv.appendChild(span);
                    } else if (tag === 'emoji') {
                        const span = document.createElement('span');
                        span.className = 'msg-emoji';
                        span.textContent = text;
                        msgDiv.appendChild(span);
                    } else if (tag === 'at_targets') {
                        const targets = text.split(',').map(t => t.trim()).filter(Boolean);
                        targets.forEach(t => {
                            const span = document.createElement('span');
                            span.className = 'msg-at';
                            span.textContent = `@${t}`;
                            msgDiv.appendChild(span);
                        });
                    } else {
                        // 未知标签，显示文本
                        const span = document.createElement('span');
                        span.textContent = text;
                        msgDiv.appendChild(span);
                    }
                } else if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
                    // 文本节点直接添加
                    msgDiv.appendChild(document.createTextNode(child.textContent));
                }
            });

            parts.push(msgDiv.outerHTML);
        });

        // 渲染 <act> 标签
        root.querySelectorAll('act').forEach(actEl => {
            const actDiv = document.createElement('div');
            actDiv.className = 'msg-act';
            const label = document.createElement('span');
            label.className = 'msg-badge';
            label.textContent = 'ACTION';
            actDiv.appendChild(label);
            const text = document.createElement('span');
            text.textContent = actEl.textContent || '';
            actDiv.appendChild(text);
            parts.push(actDiv.outerHTML);
        });

        // 渲染 <plan> 标签
        root.querySelectorAll('plan').forEach(planEl => {
            const planDiv = document.createElement('div');
            planDiv.className = 'msg-plan';
            const label = document.createElement('span');
            label.className = 'msg-badge';
            label.textContent = 'PLAN';
            planDiv.appendChild(label);
            const text = document.createElement('span');
            text.textContent = planEl.textContent || '';
            planDiv.appendChild(text);
            parts.push(planDiv.outerHTML);
        });

        // 渲染 <tool> 标签
        root.querySelectorAll('tool').forEach(toolEl => {
            const toolDiv = document.createElement('div');
            toolDiv.className = 'msg-tool';
            const label = document.createElement('span');
            label.className = 'msg-badge';
            label.textContent = 'TOOL';
            toolDiv.appendChild(label);
            const text = document.createElement('span');
            text.textContent = toolEl.textContent || '';
            toolDiv.appendChild(text);
            parts.push(toolDiv.outerHTML);
        });

        if (parts.length > 0) {
            return parts.join('\n');
        }

        // 没有匹配到任何已知标签，回退到转义输出
        return escapeHtml(xmlStr);
    }

    /**
     * 将 XML 按 <msg> 拆分为多个独立片段，每个 <msg> 生成一个片段
     * 非 msg 标签（act/plan/tool）附加到前一个 msg 片段末尾
     */
    function splitXmlByMsg(xmlStr) {
        const parser = new DOMParser();
        let doc;
        try {
            doc = parser.parseFromString(`<root>${xmlStr}</root>`, 'text/xml');
        } catch (e) {
            return [xmlStr];
        }

        const parseError = doc.querySelector('parsererror');
        if (parseError) {
            return [xmlStr];
        }

        const root = doc.documentElement;
        const children = Array.from(root.childNodes);

        // 只统计元素节点中的 msg 数量
        const msgNodes = children.filter(
            n => n.nodeType === Node.ELEMENT_NODE && n.tagName.toLowerCase() === 'msg'
        );

        // 只有一个或没有 msg，不需要拆分
        if (msgNodes.length <= 1) {
            return [xmlStr];
        }

        // 按 msg 分组：每个 msg 及后面跟的非 msg 兄弟节点
        const segments = [];
        let currentParts = [];

        for (const child of children) {
            const isMsg = child.nodeType === Node.ELEMENT_NODE && child.tagName.toLowerCase() === 'msg';
            if (isMsg) {
                if (currentParts.length > 0) {
                    segments.push(currentParts.map(n => n.outerHTML || n.textContent).join(''));
                }
                currentParts = [child];
            } else if (currentParts.length > 0) {
                // 非 msg 节点（act/plan/tool/文本）附加到当前 msg 后面
                currentParts.push(child);
            }
        }
        if (currentParts.length > 0) {
            segments.push(currentParts.map(n => n.outerHTML || n.textContent).join(''));
        }

        return segments;
    }

    /**
     * 渲染消息内容（自动检测 XML/纯文本）
     */
    function renderContent(content) {
        if (isXmlContent(content)) {
            return renderXmlContent(content);
        }
        return escapeHtml(content);
    }

    // ===== 渲染消息 =====
    function renderMessages(messages) {
        if (!messages || messages.length <= 1) {
            elChatMessages.innerHTML = '<div class="empty-tip">' + (window.t ? window.t('chat.startChat') : '发送第一条消息开始对话') + '</div>';
            return;
        }

        const html = messages.flatMap((m) => {
            if (m.role === 'system') return [];
            const isUser = m.role === 'user';
            const avatar = isUser ? 'U' : 'A';
            const timeStr = formatTime(new Date());

            // assistant 的 XML 消息若有多个 <msg>，拆成多个独立气泡
            const contents = (!isUser && isXmlContent(m.content))
                ? splitXmlByMsg(m.content).map(c => renderContent(c))
                : [renderContent(m.content)];

            return contents.map(content => `
                <div class="message ${isUser ? 'user' : 'assistant'}">
                    <div class="avatar">${avatar}</div>
                    <div>
                        <div class="bubble">${content}</div>
                        <div class="time">${timeStr}</div>
                    </div>
                </div>
            `);
        }).join('');

        elChatMessages.innerHTML = html;
        scrollToBottom();
    }

    function scrollToBottom() {
        elChatMessages.scrollTop = elChatMessages.scrollHeight;
    }

    // ===== 发送消息 =====
    async function sendMessage() {
        const text = elMessageInput.value.trim();
        if ((!text && !uploadedImages.length) || isSending) return;

        isSending = true;
        elBtnSend.disabled = true;

        if (text) {
            appendMessage('user', text);
        }
        if (uploadedImages.length) {
            appendMessage('user', '[图片 ' + uploadedImages.length + ' 张]');
        }
        elMessageInput.value = '';
        elMessageInput.focus();

        var thinkingEl = document.createElement('div');
        thinkingEl.className = 'message assistant thinking';
        thinkingEl.innerHTML = '<div class="avatar">A</div><div><div class="bubble"><span class="thinking-dots"><span></span><span></span><span></span></span></div></div>';
        elChatMessages.appendChild(thinkingEl);
        scrollToBottom();

        try {
            var body = { message: text, conv_id: currentConvId, images: uploadedImages.slice() };
            uploadedImages = [];
            renderPreviews();
            const res = await fetch('/api/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await res.json();
            // 移除思考中指示器
            if (thinkingEl && thinkingEl.parentNode) {
                thinkingEl.parentNode.removeChild(thinkingEl);
            }
            if (data.error) {
                appendMessage('system', `${window.t ? window.t('chat.errorPrefix') : '[错误]'} ${data.error}`);
            } else {
                appendMessage('assistant', data.reply);
                // 更新会话列表元数据
                await loadConversations();
            }
        } catch (e) {
            // 移除思考中指示器
            if (thinkingEl && thinkingEl.parentNode) {
                thinkingEl.parentNode.removeChild(thinkingEl);
            }
            appendMessage('system', `${window.t ? window.t('chat.networkErrorPrefix') : '[网络错误]'} ${e.message}`);
        } finally {
            isSending = false;
            elBtnSend.disabled = false;
        }
    }

    function appendMessage(role, content) {
        const empty = elChatMessages.querySelector('.empty-tip');
        if (empty) empty.remove();

        const isUser = role === 'user';
        const avatar = isUser ? 'U' : (role === 'system' ? '!' : 'A');
        const timeStr = formatTime(new Date());

        // assistant 的 XML 若有多个 <msg>，拆成多个独立气泡
        const contents = (!isUser && role !== 'system' && isXmlContent(content))
            ? splitXmlByMsg(content).map(c => renderContent(c))
            : [renderContent(content)];

        const fragment = document.createDocumentFragment();
        contents.forEach(html => {
            const div = document.createElement('div');
            div.className = `message ${role === 'system' ? 'assistant' : role}`;
            div.innerHTML = `
                <div class="avatar">${avatar}</div>
                <div>
                    <div class="bubble">${html}</div>
                    <div class="time">${timeStr}</div>
                </div>
            `;
            fragment.appendChild(div);
        });
        elChatMessages.appendChild(fragment);
        scrollToBottom();
    }

    // ===== 新建对话 =====
    async function newConversation() {
        try {
            const res = await fetch('/api/chat/new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: '新对话' })
            });
            const conv = await res.json();
            await loadConversations();
            await switchConversation(conv.id);
        } catch (e) {
            alert((window.t ? window.t('chat.createFailed') : '创建对话失败') + ': ' + e.message);
        }
    }

    // ===== 清空对话 =====
    async function clearConversation() {
        if (!confirm(window.t ? window.t('chat.confirmClear') : '确定要清空当前对话历史吗？')) return;
        try {
            await fetch('/api/chat/history', { method: 'DELETE' });
            await switchConversation(currentConvId);
            await loadConversations();
        } catch (e) {
            alert((window.t ? window.t('chat.clearFailed') : '清空失败') + ': ' + e.message);
        }
    }

    // ===== 事件绑定 =====
    elBtnSend.addEventListener('click', sendMessage);
    elMessageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    elBtnNewChat.addEventListener('click', newConversation);
    elBtnClearChat.addEventListener('click', clearConversation);

    // ===== 图片上传与粘贴 =====
    var $imageInput = document.getElementById('imageInput');
    var $btnImage = document.getElementById('btnImage');
    var $imagePreview = document.getElementById('imagePreview');

    if ($btnImage && $imageInput) {
        $btnImage.addEventListener('click', function () { $imageInput.click(); });
        $imageInput.addEventListener('change', function (e) {
            uploadFiles(Array.from(e.target.files));
            e.target.value = '';
        });
    }

    document.addEventListener('paste', function (e) {
        if (document.activeElement !== elMessageInput) return;
        var items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        var files = [];
        for (var i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                files.push(items[i].getAsFile());
            }
        }
        if (files.length) {
            e.preventDefault();
            uploadFiles(files);
        }
    });

    function uploadFiles(files) {
        files.forEach(function (file) {
            var formData = new FormData();
            formData.append('file', file);
            fetch('/api/chat/upload', { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.ok) {
                        uploadedImages.push(data.path);
                        renderPreviews();
                    }
                })
                .catch(function (e) { console.error('Image upload failed:', e); });
        });
    }

    function renderPreviews() {
        if (!$imagePreview) return;
        $imagePreview.innerHTML = '';
        uploadedImages.forEach(function (path, idx) {
            var div = document.createElement('div');
            div.style.cssText = 'position:relative;width:48px;height:48px;border-radius:6px;overflow:hidden;border:1px solid var(--border);flex-shrink:0;';
            var img = document.createElement('img');
            img.src = '/' + path;
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
            var btn = document.createElement('span');
            btn.textContent = '×';
            btn.style.cssText = 'position:absolute;top:0;right:0;background:rgba(0,0,0,0.6);color:#fff;font-size:11px;line-height:1;padding:1px 4px;cursor:pointer;border-radius:0 0 0 4px;';
            btn.onclick = function () { uploadedImages.splice(idx, 1); renderPreviews(); };
            div.appendChild(img);
            div.appendChild(btn);
            $imagePreview.appendChild(div);
        });
    }

    // ===== 暴露全局接口（供 card-view.js 使用）=====
    window.switchConversation = switchConversation;
    window.getCurrentConvId = () => currentConvId;

    // ===== 启动 =====
    init();
})();
