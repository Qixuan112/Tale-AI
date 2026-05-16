/**
 * Tale WebUI - 3D 环绕卡片模式
 * 核心：轨道整体移动，当前卡片始终位于视觉中心
 * 交互：Tab 进入, ←→ 切换, 滚轮切换, 拖拽滑动, Enter 打开, Esc 退出, 箭头按钮
 */

(function () {
    'use strict';

    const overlay = document.getElementById('cardOverlay');
    const container = document.getElementById('cardContainer');
    const btnCardView = document.getElementById('btnCardView');

    if (!overlay || !container) return;

    // ===== 常量 =====
    const CARD_WIDTH = 320;
    const CARD_MARGIN = 24; // 单侧
    const CARD_SPACING = CARD_WIDTH + CARD_MARGIN * 2; // 368px
    const DRAG_THRESHOLD = 80;
    const VELOCITY_THRESHOLD = 0.6;
    const FRICTION = 0.88;

    // ===== 状态 =====
    let currentIndex = 0;
    let convData = [];
    let isActive = false;
    let sceneEl = null;
    let trackEl = null;
    let indicatorEl = null;
    let hintEl = null;

    // 轨道位置状态
    let trackOffset = 0;      // 当前轨道的 translateX 偏移
    let targetOffset = 0;     // 目标偏移
    let isAnimating = false;

    // 拖拽状态
    let isDragging = false;
    let dragStartX = 0;
    let dragVelocity = 0;
    let lastDragX = 0;
    let lastDragTime = 0;
    let rafId = null;

    // ===== 入口 =====
    window.toggleCardView = async function () {
        if (isActive) { closeOverlay(); return; }
        await openOverlay();
    };

    async function openOverlay() {
        await loadData();
        if (!convData.length) return;

        const activeId = (typeof getCurrentConvId === 'function' ? getCurrentConvId() : null)
            || (convData[0] && convData[0].id);
        currentIndex = convData.findIndex(c => c.id === activeId);
        if (currentIndex < 0) currentIndex = 0;

        overlay.classList.remove('hidden');
        isActive = true;
        document.body.style.overflow = 'hidden';

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                buildScene();
                snapToCenter(currentIndex, true);
            });
        });
    }

    function closeOverlay() {
        overlay.classList.add('hidden');
        isActive = false;
        document.body.style.overflow = '';
        cancelAnimationFrame(rafId);
        isDragging = false;
        [sceneEl, indicatorEl, hintEl].forEach(el => el && el.remove());
        sceneEl = trackEl = indicatorEl = hintEl = null;
    }

    function openCurrentConversation() {
        const conv = convData[currentIndex];
        if (!conv) return;
        closeOverlay();
        if (typeof switchConversation === 'function') switchConversation(conv.id);
    }

    // ===== 数据 =====
    async function loadData() {
        try {
            const res = await fetch('/api/chat/conversations');
            convData = await res.json();
        } catch (e) { convData = []; }
    }

    // ===== 计算中心偏移 =====
    function getCenterOffset(index) {
        const viewportW = container.clientWidth || window.innerWidth;
        return -(index * CARD_SPACING) + (viewportW / 2 - CARD_WIDTH / 2);
    }

    // ===== 构建场景 =====
    function buildScene() {
        container.innerHTML = '';

        sceneEl = document.createElement('div');
        sceneEl.className = 'card-scene';

        // 左箭头
        const prevBtn = document.createElement('div');
        prevBtn.className = 'nav-arrow prev';
        prevBtn.innerHTML = '&#10094;';
        prevBtn.addEventListener('click', () => { if (!isDragging) goTo(currentIndex - 1); });
        sceneEl.appendChild(prevBtn);

        // 右箭头
        const nextBtn = document.createElement('div');
        nextBtn.className = 'nav-arrow next';
        nextBtn.innerHTML = '&#10095;';
        nextBtn.addEventListener('click', () => { if (!isDragging) goTo(currentIndex + 1); });
        sceneEl.appendChild(nextBtn);

        // 轨道
        trackEl = document.createElement('div');
        trackEl.className = 'card-track';

        convData.forEach((c, i) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'card-wrapper entering';
            wrapper.dataset.index = i;
            wrapper.style.width = CARD_WIDTH + 'px';

            const card = document.createElement('div');
            card.className = 'card';

            const firstMsg = c.last_message ? c.last_message.split('\n')[0] : (window.t ? window.t('card.noMessage') : '无消息');
            const previewLines = c.last_message ? c.last_message.split('\n').slice(-4) : [''];

            card.innerHTML = `
                <div class="card-header">
                    <span class="card-header-id">${escapeHtml(c.title)} #${c.id}</span>
                    <span class="card-header-time">${escapeHtml(c.time || '')}</span>
                </div>
                <div class="card-first-msg">${escapeHtml(firstMsg)}</div>
                <div class="card-divider"></div>
                <div class="card-preview-label">${window.t ? window.t('card.previewLabel') : '最后消息预览：'}</div>
                <div class="card-preview-text">${escapeHtml(previewLines.join('\n'))}</div>
                <div class="card-footer">
                    <span class="card-count">${c.count} ${window.t ? window.t('card.messageCount') : '条消息'}</span>
                </div>
            `;

            // 倒影
            const reflection = document.createElement('div');
            reflection.className = 'card-reflection';

            wrapper.appendChild(card);
            wrapper.appendChild(reflection);

            card.addEventListener('click', () => {
                if (isDragging) return;
                if (i !== currentIndex) goTo(i);
                else openCurrentConversation();
            });

            trackEl.appendChild(wrapper);

            // 移除 entering 动画
            setTimeout(() => wrapper.classList.remove('entering'), 50 + Math.abs(i - currentIndex) * 60);
        });

        sceneEl.appendChild(trackEl);
        container.appendChild(sceneEl);

        // 指示器
        indicatorEl = document.createElement('div');
        indicatorEl.className = 'card-indicator';
        convData.forEach((_, i) => {
            const dot = document.createElement('div');
            dot.className = 'indicator-dot ' + (i === currentIndex ? 'active' : 'inactive');
            indicatorEl.appendChild(dot);
        });
        overlay.appendChild(indicatorEl);

        // 提示
        hintEl = document.createElement('div');
        hintEl.className = 'card-hint';
        hintEl.textContent = window.t ? window.t('card.hint') : '键盘左右方向键 / 鼠标滚轮 切换会话，回车进入会话';
        overlay.appendChild(hintEl);
    }

    // ===== 吸附到中心（核心）=====
    function snapToCenter(index, animate = false) {
        currentIndex = Math.max(0, Math.min(index, convData.length - 1));
        targetOffset = getCenterOffset(currentIndex);

        if (animate) {
            animateTrack();
        } else {
            trackOffset = targetOffset;
            applyTrackTransform();
        }

        updateCardStates();
        updateControls();
    }

    function goTo(index) {
        if (index < 0 || index >= convData.length) return;
        snapToCenter(index, true);
    }

    function next() { goTo(currentIndex + 1); }
    function prev() { goTo(currentIndex - 1); }

    // ===== 轨道动画 =====
    function animateTrack() {
        if (isAnimating) return;
        isAnimating = true;

        const startOffset = trackOffset;
        const dist = targetOffset - startOffset;
        const duration = 450;
        const startTime = performance.now();

        function step(now) {
            const elapsed = now - startTime;
            const t = Math.min(elapsed / duration, 1);
            // easeOutCubic
            const ease = 1 - Math.pow(1 - t, 3);
            trackOffset = startOffset + dist * ease;
            applyTrackTransform();

            if (t < 1) {
                rafId = requestAnimationFrame(step);
            } else {
                isAnimating = false;
                trackOffset = targetOffset;
                applyTrackTransform();
            }
        }
        rafId = requestAnimationFrame(step);
    }

    function applyTrackTransform() {
        if (trackEl) {
            trackEl.style.transform = `translateX(${trackOffset}px)`;
        }
    }

    // ===== 更新卡片状态（CSS类控制3D效果）=====
    function updateCardStates() {
        if (!trackEl) return;
        const wrappers = trackEl.querySelectorAll('.card-wrapper');
        wrappers.forEach((wrapper, i) => {
            const offset = i - currentIndex;
            const absOffset = Math.abs(offset);

            wrapper.classList.remove('active', 'side-1', 'side-2', 'side-3');

            if (absOffset === 0) {
                wrapper.classList.add('active');
            } else if (absOffset === 1) {
                wrapper.classList.add('side-1');
                wrapper.style.setProperty('--rot', offset > 0 ? '-22deg' : '22deg');
            } else if (absOffset === 2) {
                wrapper.classList.add('side-2');
                wrapper.style.setProperty('--rot', offset > 0 ? '-35deg' : '35deg');
            } else {
                wrapper.classList.add('side-3');
            }
        });
    }

    function updateControls() {
        // 箭头
        if (sceneEl) {
            const prev = sceneEl.querySelector('.nav-arrow.prev');
            const next = sceneEl.querySelector('.nav-arrow.next');
            if (prev) prev.classList.toggle('disabled', currentIndex === 0);
            if (next) next.classList.toggle('disabled', currentIndex === convData.length - 1);
        }
        // 指示器
        if (indicatorEl) {
            indicatorEl.querySelectorAll('.indicator-dot').forEach((dot, i) => {
                dot.classList.toggle('active', i === currentIndex);
                dot.classList.toggle('inactive', i !== currentIndex);
            });
        }
    }

    // ===== 惯性动画（拖拽后）=====
    function inertiaLoop() {
        if (!isActive || isDragging) return;

        if (Math.abs(dragVelocity) > 0.05) {
            trackOffset += dragVelocity * 16;
            dragVelocity *= FRICTION;

            const nearestIndex = Math.round(-(trackOffset - getCenterOffset(0)) / CARD_SPACING);
            const clamped = Math.max(0, Math.min(nearestIndex, convData.length - 1));

            // 过阈值直接切换
            if (Math.abs(dragVelocity) < 1 && clamped !== currentIndex) {
                snapToCenter(clamped, false);
                dragVelocity = 0;
                return;
            }

            // 边界回拉
            const minOffset = getCenterOffset(convData.length - 1);
            const maxOffset = getCenterOffset(0);
            if (trackOffset > maxOffset + 100 || trackOffset < minOffset - 100) {
                dragVelocity *= 0.5;
            }

            applyTrackTransform();
            rafId = requestAnimationFrame(inertiaLoop);
        } else {
            // 吸附到最近
            const nearestIndex = Math.round(-(trackOffset - getCenterOffset(0)) / CARD_SPACING);
            snapToCenter(nearestIndex, true);
        }
    }

    // ===== 键盘 =====
    document.addEventListener('keydown', (e) => {
        if (!isActive) return;
        switch (e.key) {
            case 'ArrowRight': e.preventDefault(); next(); break;
            case 'ArrowLeft':  e.preventDefault(); prev(); break;
            case 'Enter':      e.preventDefault(); openCurrentConversation(); break;
            case 'Escape':     e.preventDefault(); closeOverlay(); break;
        }
    });

    // ===== 滚轮 =====
    let wheelAccum = 0;
    let wheelTimer = null;
    overlay.addEventListener('wheel', (e) => {
        if (!isActive) return;
        e.preventDefault();
        wheelAccum += e.deltaY;
        if (wheelTimer) clearTimeout(wheelTimer);
        if (Math.abs(wheelAccum) > 50) {
            wheelAccum > 0 ? next() : prev();
            wheelAccum = 0;
        }
        wheelTimer = setTimeout(() => wheelAccum = 0, 150);
    }, { passive: false });

    // ===== 拖拽 =====
    function onDragStart(clientX) {
        if (!isActive) return;
        isDragging = true;
        dragStartX = clientX;
        lastDragX = clientX;
        lastDragTime = performance.now();
        dragVelocity = 0;
        cancelAnimationFrame(rafId);
        isAnimating = false;
    }

    function onDragMove(clientX) {
        if (!isActive || !isDragging) return;
        const dx = clientX - dragStartX;
        trackOffset = targetOffset + dx;
        applyTrackTransform();

        const now = performance.now();
        const dt = now - lastDragTime;
        if (dt > 0) dragVelocity = (clientX - lastDragX) / dt * 16;
        lastDragX = clientX;
        lastDragTime = now;
    }

    function onDragEnd() {
        if (!isActive || !isDragging) return;
        isDragging = false;

        const dx = lastDragX - dragStartX;

        if (Math.abs(dragVelocity) > VELOCITY_THRESHOLD) {
            // 惯性滑行
            rafId = requestAnimationFrame(inertiaLoop);
        } else if (Math.abs(dx) > DRAG_THRESHOLD) {
            // 过阈值切换
            dx > 0 ? prev() : next();
        } else {
            // 回弹
            snapToCenter(currentIndex, true);
        }
    }

    // 鼠标
    overlay.addEventListener('mousedown', e => {
        if (e.target.closest('.nav-arrow')) return;
        onDragStart(e.clientX);
    });
    document.addEventListener('mousemove', e => { if (isDragging) onDragMove(e.clientX); });
    document.addEventListener('mouseup', onDragEnd);

    // 触摸
    overlay.addEventListener('touchstart', e => {
        if (e.target.closest('.nav-arrow')) return;
        onDragStart(e.touches[0].clientX);
    }, { passive: true });
    overlay.addEventListener('touchmove', e => {
        if (isDragging) { e.preventDefault(); onDragMove(e.touches[0].clientX); }
    }, { passive: false });
    overlay.addEventListener('touchend', onDragEnd);

    // 窗口大小变化时重新居中
    window.addEventListener('resize', () => {
        if (isActive) snapToCenter(currentIndex, true);
    });

    // ===== 按钮绑定 =====
    if (btnCardView) btnCardView.addEventListener('click', toggleCardView);
})();
