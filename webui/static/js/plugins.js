/**
 * Tale WebUI - 插件管理页面交互
 * 加载插件列表，展示内置/第三方插件，支持启用/禁用切换
 */

(function () {
    'use strict';

    const $status = document.getElementById('pluginstatus');
    const $list = document.getElementById('pluginlist');
    const $builtin = document.getElementById('builtin-grid');
    const $thirdparty = document.getElementById('thirdparty-grid');

    let plugins = [];
    let loadedSet = new Set();

    function showStatus(key) {
        $status.style.display = '';
        $status.textContent = t(key) || key;
        $list.style.display = 'none';
    }

    function showList() {
        $status.style.display = 'none';
        $list.style.display = '';
    }

    function badge(text, cls) {
        const span = document.createElement('span');
        span.className = 'badge ' + cls;
        span.textContent = text;
        return span;
    }

    function tag(text) {
        const span = document.createElement('span');
        span.className = 'hook-tag';
        span.textContent = text;
        return span;
    }

    function renderCard(p) {
        const isLoaded = loadedSet.has(p.id);
        const isBuiltin = p.builtin;

        const card = document.createElement('div');
        card.className = 'plugin-card';

        // header
        const header = document.createElement('div');
        header.className = 'plugin-card-header';

        const titleDiv = document.createElement('div');
        titleDiv.className = 'plugin-card-title';
        const h3 = document.createElement('h3');
        h3.textContent = p.name;
        titleDiv.appendChild(h3);

        if (isBuiltin) {
            titleDiv.appendChild(badge(t('plugins.builtinBadge'), 'badge-builtin'));
        }
        titleDiv.appendChild(badge(
            isLoaded ? t('card.status.enabled') : t('card.status.disabled'),
            isLoaded ? 'badge-enabled' : 'badge-disabled'
        ));

        header.appendChild(titleDiv);

        // meta
        const meta = document.createElement('div');
        meta.className = 'plugin-card-meta';
        if (p.version) {
            const v = document.createElement('span');
            v.textContent = t('plugins.version') + ' ' + p.version;
            meta.appendChild(v);
        }
        if (p.author) {
            const a = document.createElement('span');
            a.textContent = t('plugins.author') + ' ' + p.author;
            meta.appendChild(a);
        }

        // description
        const desc = document.createElement('div');
        desc.className = 'plugin-card-desc';
        desc.textContent = p.description || '';

        // hooks
        const hooksDiv = document.createElement('div');
        hooksDiv.className = 'plugin-card-hooks';
        if (p.hooks && p.hooks.length) {
            p.hooks.forEach(function (h) { hooksDiv.appendChild(tag(h)); });
        }

        // actions
        const actions = document.createElement('div');
        actions.className = 'plugin-card-actions';

        const label = document.createElement('label');
        label.className = 'toggle-switch';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = isLoaded;
        input.addEventListener('change', function () {
            togglePlugin(p.id, input.checked, input);
        });
        const slider = document.createElement('span');
        slider.className = 'toggle-slider';
        label.appendChild(input);
        label.appendChild(slider);
        actions.appendChild(label);

        const statusText = document.createElement('span');
        statusText.style.fontSize = '0.8rem';
        statusText.style.color = 'var(--text-secondary)';
        statusText.id = 'status-' + p.id;
        actions.appendChild(statusText);

        card.appendChild(header);
        card.appendChild(meta);
        card.appendChild(desc);
        card.appendChild(hooksDiv);
        card.appendChild(actions);

        return card;
    }

    function togglePlugin(id, enable, inputEl) {
        var statusEl = document.getElementById('status-' + id);
        if (statusEl) statusEl.textContent = '...';

        fetch('/api/plugins/' + id + '/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enable })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.ok) {
                if (enable) {
                    loadedSet.add(id);
                } else {
                    loadedSet.delete(id);
                }
                if (statusEl) statusEl.textContent = t('plugins.toggleSuccess');
                // refresh card badges
                loadList();
            } else {
                if (statusEl) statusEl.textContent = t('plugins.toggleFailed');
                // revert toggle
                if (inputEl) inputEl.checked = !enable;
            }
        })
        .catch(function () {
            if (statusEl) statusEl.textContent = t('plugins.toggleFailed');
            if (inputEl) inputEl.checked = !enable;
        });
    }

    function loadList() {
        fetch('/api/plugins')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) throw new Error(data.error);
                plugins = data.plugins || [];
                loadedSet = new Set(data.loaded || []);

                if (!plugins.length) {
                    showStatus('plugins.noPlugins');
                    return;
                }

                $builtin.innerHTML = '';
                $thirdparty.innerHTML = '';

                var anyBuiltin = false;
                var anyThird = false;

                plugins.forEach(function (p) {
                    var card = renderCard(p);
                    if (p.builtin) {
                        $builtin.appendChild(card);
                        anyBuiltin = true;
                    } else {
                        $thirdparty.appendChild(card);
                        anyThird = true;
                    }
                });

                // hide empty section titles
                document.querySelector('.section-title[data-i18n="plugins.builtin"]').style.display = anyBuiltin ? '' : 'none';
                document.querySelector('.section-title[data-i18n="plugins.thirdParty"]').style.display = anyThird ? '' : 'none';

                showList();
            })
            .catch(function (err) {
                showStatus('plugins.loadFailed');
                console.error('Failed to load plugins:', err);
            });
    }

    function init() {
        loadList();
        // re-apply i18n after dynamic rendering
        window.addEventListener('i18n:change', function () {
            setTimeout(loadList, 50);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
