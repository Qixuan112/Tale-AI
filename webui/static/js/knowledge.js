/**
 * Tale WebUI - 知识库管理页面交互
 * 上传文档、管理索引、测试检索
 */

(function () {
    'use strict';

    const $status = document.getElementById('kbStatus');
    const $statusDot = document.getElementById('kbStatusDot');
    const $statusText = document.getElementById('kbStatusText');
    const $tabs = document.getElementById('kbTabs');
    const $uploadArea = document.getElementById('kbUploadArea');
    const $fileInput = document.getElementById('kbFileInput');
    const $docGrid = document.getElementById('kbDocGrid');
    const $docEmpty = document.getElementById('kbEmpty');
    const $rebuildBtn = document.getElementById('kbRebuildBtn');
    const $queryInput = document.getElementById('kbQueryInput');
    const $testBtn = document.getElementById('kbTestBtn');
    const $testResults = document.getElementById('kbTestResults');
    const $testEmpty = document.getElementById('kbTestEmpty');

    let currentKb = 'default';
    let kbNames = ['default'];

    function showStatus(enabled) {
        $statusDot.className = 'kb-status-dot ' + (enabled ? 'enabled' : 'disabled');
        $statusText.textContent = enabled ? t('knowledge.enabled') : t('knowledge.disabled');
    }

    function showLoading() {
        document.getElementById('kbPanel').style.display = 'none';
    }

    function showPanel() {
        document.getElementById('kbPanel').style.display = '';
    }

    // --- KB tabs ---
    function renderTabs(names) {
        $tabs.innerHTML = '';
        names.forEach(function (name) {
            var tab = document.createElement('button');
            tab.className = 'kb-tab' + (name === currentKb ? ' active' : '');
            tab.textContent = name;
            tab.addEventListener('click', function () {
                currentKb = name;
                document.querySelectorAll('.kb-tab').forEach(function (t) { t.classList.remove('active'); });
                tab.classList.add('active');
                loadDocuments();
            });
            $tabs.appendChild(tab);
        });
    }

    // --- Status ---
    function loadStatus() {
        return fetch('/api/knowledge/status')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                showStatus(data.enabled);
                if (data.knowledge_bases) {
                    kbNames = Object.keys(data.knowledge_bases);
                    if (kbNames.length === 0) kbNames = ['default'];
                    renderTabs(kbNames);
                    if (kbNames.indexOf(currentKb) === -1) currentKb = kbNames[0];
                }
                showPanel();
            })
            .catch(function () {
                showStatus(false);
                showPanel();
            });
    }

    // --- Documents ---
    function loadDocuments() {
        fetch('/api/knowledge/' + encodeURIComponent(currentKb) + '/documents')
            .then(function (r) { return r.json(); })
            .then(function (docs) {
                if (!docs || !docs.length) {
                    $docGrid.style.display = 'none';
                    $docEmpty.style.display = '';
                    return;
                }
                $docEmpty.style.display = 'none';
                $docGrid.style.display = '';
                $docGrid.innerHTML = '';

                docs.forEach(function (d) {
                    var card = document.createElement('div');
                    card.className = 'kb-doc-card';

                    // header
                    var header = document.createElement('div');
                    header.className = 'kb-doc-header';

                    var nameDiv = document.createElement('div');
                    nameDiv.className = 'kb-doc-name';
                    nameDiv.textContent = d.filename;

                    var typeBadge = document.createElement('span');
                    typeBadge.className = 'badge badge-' + d.file_type;
                    typeBadge.textContent = '.' + d.file_type;
                    nameDiv.appendChild(typeBadge);
                    header.appendChild(nameDiv);

                    var statusBadge = document.createElement('span');
                    statusBadge.className = 'badge badge-' + d.status;
                    statusBadge.textContent = d.status === 'indexed' ? t('knowledge.indexed') : d.status;
                    header.appendChild(statusBadge);

                    // meta
                    var meta = document.createElement('div');
                    meta.className = 'kb-doc-meta';
                    var sizeSpan = document.createElement('span');
                    sizeSpan.textContent = formatSize(d.file_size);
                    meta.appendChild(sizeSpan);
                    var chunkSpan = document.createElement('span');
                    chunkSpan.textContent = d.chunk_count + ' chunks';
                    meta.appendChild(chunkSpan);
                    if (d.uploaded_at) {
                        var timeSpan = document.createElement('span');
                        timeSpan.textContent = formatTime(d.uploaded_at);
                        meta.appendChild(timeSpan);
                    }
                    card.appendChild(meta);

                    // actions
                    var actions = document.createElement('div');
                    actions.style.cssText = 'display:flex;justify-content:flex-end;';

                    var delBtn = document.createElement('button');
                    delBtn.className = 'btn-delete';
                    delBtn.textContent = t('common.delete') || '删除';
                    delBtn.addEventListener('click', function () {
                        deleteDocument(d.id, d.filename);
                    });
                    actions.appendChild(delBtn);
                    card.appendChild(actions);

                    $docGrid.appendChild(card);
                });
            })
            .catch(function () {});
    }

    // --- Upload ---
    function handleUpload(file) {
        var formData = new FormData();
        formData.append('file', file);

        fetch('/api/knowledge/' + encodeURIComponent(currentKb) + '/upload', {
            method: 'POST',
            body: formData,
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok) {
                    loadDocuments();
                    loadStatus();
                } else {
                    alert(t('knowledge.uploadFailed') + ': ' + (data.error || ''));
                }
            })
            .catch(function (err) {
                alert(t('knowledge.uploadFailed') + ': ' + err.message);
            });
    }

    function uploadFiles(files) {
        for (var i = 0; i < files.length; i++) {
            handleUpload(files[i]);
        }
    }

    // --- Delete ---
    function deleteDocument(docId, filename) {
        if (!confirm((t('knowledge.deleteConfirm') || '确认删除文档 ') + filename + '?')) return;

        fetch('/api/knowledge/' + encodeURIComponent(currentKb) + '/documents/' + encodeURIComponent(docId), {
            method: 'DELETE',
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok) {
                    loadDocuments();
                    loadStatus();
                } else {
                    alert(t('knowledge.deleteFailed') + ': ' + (data.error || ''));
                }
            })
            .catch(function () {
                alert(t('knowledge.deleteFailed'));
            });
    }

    // --- Rebuild ---
    function rebuildIndex() {
        if (!confirm(t('knowledge.rebuildConfirm') || '确认重建知识库索引？')) return;

        fetch('/api/knowledge/' + encodeURIComponent(currentKb) + '/rebuild', {
            method: 'POST',
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok) {
                    alert(t('knowledge.rebuildSuccess') || '索引重建完成');
                    loadDocuments();
                    loadStatus();
                } else {
                    alert(t('knowledge.rebuildFailed') + ': ' + (data.error || ''));
                }
            })
            .catch(function () {
                alert(t('knowledge.rebuildFailed'));
            });
    }

    // --- Test retrieval ---
    function testRetrieval() {
        var query = $queryInput.value.trim();
        if (!query) return;

        $testResults.style.display = 'none';
        $testEmpty.style.display = 'none';

        fetch('/api/knowledge/' + encodeURIComponent(currentKb) + '/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok && data.results) {
                    $testResults.style.display = '';
                    $testResults.textContent = data.results || t('knowledge.noResults');
                } else {
                    $testResults.style.display = '';
                    $testResults.textContent = t('knowledge.noResults');
                }
            })
            .catch(function () {
                $testResults.style.display = '';
                $testResults.textContent = t('knowledge.testFailed');
            });
    }

    // --- Helpers ---
    function formatSize(bytes) {
        if (!bytes) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function formatTime(iso) {
        if (!iso) return '';
        try {
            var d = new Date(iso);
            return d.toLocaleString();
        } catch (e) {
            return iso;
        }
    }

    // --- Init upload area ---
    function initUpload() {
        $uploadArea.addEventListener('click', function () {
            $fileInput.click();
        });

        $uploadArea.addEventListener('dragover', function (e) {
            e.preventDefault();
            $uploadArea.classList.add('dragover');
        });

        $uploadArea.addEventListener('dragleave', function () {
            $uploadArea.classList.remove('dragover');
        });

        $uploadArea.addEventListener('drop', function (e) {
            e.preventDefault();
            $uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                uploadFiles(e.dataTransfer.files);
            }
        });

        $fileInput.addEventListener('change', function () {
            if ($fileInput.files.length) {
                uploadFiles($fileInput.files);
                $fileInput.value = '';
            }
        });
    }

    // --- Init ---
    function init() {
        loadStatus().then(function () {
            renderTabs(kbNames);
            loadDocuments();
        });

        initUpload();

        $rebuildBtn.addEventListener('click', rebuildIndex);

        $testBtn.addEventListener('click', testRetrieval);
        $queryInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') testRetrieval();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
