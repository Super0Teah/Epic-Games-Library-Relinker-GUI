const appCtrl = {

    _defaultManifestPath: '',

    // ── Init ──────────────────────────────────────────────────────────────────
    async init() {
        const paths = await window.pywebview.api.get_initial_paths();
        this._defaultManifestPath = paths.manifestPath;

        document.getElementById('manifestPath').value = paths.manifestPath;
        document.getElementById('useDefault').checked = paths.useDefault;
        document.getElementById('gamesPath').value   = paths.gamesPath;

        // Restore saved theme
        const savedTheme = localStorage.getItem('relinker_theme') || 'Dark Blue';
        document.getElementById('themeSelect').value = savedTheme;
        this.applyTheme(savedTheme, false);

        // Restore debug mode
        const savedDebug = localStorage.getItem('relinker_debug') === 'true';
        document.getElementById('debugMode').checked = savedDebug;

        // Set action group states — start expanded
        this._expandedGroups = { 'group-relink': true, 'group-capture': true };
        // Let the DOM settle before measuring
        requestAnimationFrame(() => {
            this._setGroupHeight('group-relink');
            this._setGroupHeight('group-capture');
        });
    },

    // ── Settings Panel ────────────────────────────────────────────────────────
    openSettings() {
        document.getElementById('settingsOverlay').classList.remove('hidden');
    },
    closeSettings(evt) {
        if (evt && evt.target !== document.getElementById('settingsOverlay')) return;
        document.getElementById('settingsOverlay').classList.add('hidden');
    },

    // ── Theme ─────────────────────────────────────────────────────────────────
    applyTheme(name, save = true) {
        document.documentElement.setAttribute('data-theme', name);
        if (save) localStorage.setItem('relinker_theme', name);
    },

    // ── Debug ─────────────────────────────────────────────────────────────────
    onDebugToggle() {
        const val = document.getElementById('debugMode').checked;
        localStorage.setItem('relinker_debug', val);
        this.appendLog(
            val ? 'Debug mode ENABLED — full tracebacks will show on error.'
                : 'Debug mode disabled.',
            'INFO'
        );
    },

    // ── Default path toggle ───────────────────────────────────────────────────
    toggleDefault() {
        const checked = document.getElementById('useDefault').checked;
        const field   = document.getElementById('manifestPath');
        if (checked) {
            field.value = this._defaultManifestPath;
        } else {
            field.value = '';
        }
    },

    // ── Path Browsing ─────────────────────────────────────────────────────────
    async browseManifests() {
        const path = await window.pywebview.api.browse_directory("Select Manifests Folder");
        if (path) {
            document.getElementById('manifestPath').value = path;
            document.getElementById('useDefault').checked = false;
        }
    },
    async browseGames() {
        const path = await window.pywebview.api.browse_directory("Select Games Folder");
        if (path) document.getElementById('gamesPath').value = path;
    },

    // ── Run Action ────────────────────────────────────────────────────────────
    runAction(action) {
        const m   = document.getElementById('manifestPath').value;
        const g   = document.getElementById('gamesPath').value;
        const d   = document.getElementById('useDefault').checked;
        const dbg = document.getElementById('debugMode').checked;
        window.pywebview.api.start_action(action, m, g, d, dbg);
    },

    // ── Accordion ─────────────────────────────────────────────────────────────
    _expandedGroups: {},

    toggleGroup(id) {
        const isOpen = this._expandedGroups[id] !== false;
        this._expandedGroups[id] = !isOpen;
        this._setGroupHeight(id);
    },

    _setGroupHeight(id) {
        const body    = document.getElementById('body-' + id);
        const chevron = document.getElementById('chevron-' + id);
        const isOpen  = this._expandedGroups[id] !== false;

        if (isOpen) {
            // Temporarily set to auto to measure the real full height
            body.style.transition = 'none';
            body.style.maxHeight  = 'none';
            body.style.overflow   = 'visible';
            const fullHeight = body.scrollHeight;

            // Snap back to 0 (or current) then animate up
            body.style.maxHeight = body.classList.contains('collapsed') ? '0px' : fullHeight + 'px';
            body.style.overflow  = 'hidden';

            // Force reflow then animate
            body.offsetHeight; // eslint-disable-line no-unused-expressions
            body.style.transition = '';
            body.style.maxHeight  = fullHeight + 'px';

            body.classList.remove('collapsed');
            chevron.classList.remove('collapsed');

            // After transition, release to auto so content can freely reflow
            const onDone = () => {
                body.style.maxHeight = 'none';
                body.style.overflow  = 'visible';
                body.removeEventListener('transitionend', onDone);
            };
            body.addEventListener('transitionend', onDone);

        } else {
            // Pin the current pixel height before collapsing so transition works
            body.style.transition = 'none';
            body.style.maxHeight  = body.scrollHeight + 'px';
            body.style.overflow   = 'hidden';

            body.offsetHeight; // force reflow
            body.style.transition = '';
            body.style.maxHeight  = '0px';

            body.classList.add('collapsed');
            chevron.classList.add('collapsed');
        }
    },

    // ── Log ───────────────────────────────────────────────────────────────────
    clearLog() {
        document.getElementById('logContent').innerHTML = '';
    },
    _ts() {
        const n = new Date();
        return [n.getHours(), n.getMinutes(), n.getSeconds()]
            .map(x => x.toString().padStart(2, '0')).join(':');
    },
    appendLog(msg, tag) {
        const entry = document.createElement('div');
        entry.className = 'log-entry log-' + (tag || 'INFO');

        const ts = document.createElement('span');
        ts.className   = 'log-ts';
        ts.textContent = this._ts();

        const text = document.createElement('span');
        text.className   = 'log-text';
        text.textContent = msg;

        entry.appendChild(ts);
        entry.appendChild(text);

        const lc = document.getElementById('logContent');
        lc.appendChild(entry);
        lc.scrollTop = lc.scrollHeight;
    },

    // ── Modal State ───────────────────────────────────────────────────────────
    currentManifests: [],
    currentGameList: [],

    // ── Link Modal ────────────────────────────────────────────────────────────
    openLinkModal(manifestsJson, gameListJson) {
        this.currentManifests = JSON.parse(manifestsJson);
        this.currentGameList  = JSON.parse(gameListJson);
        if (this.currentManifests.length === 0) {
            window.pywebview.api.resume_link(null);
            return;
        }
        const m = this.currentManifests[0];
        document.getElementById('linkModalTitle').innerText =
            `⬡ Link Pending Manifest (1/${this.currentManifests.length})`;
        document.getElementById('linkModalInfo').innerHTML =
            `<b>File:</b> ${m.file_name}<br><b>Game:</b> ${m.display_name || '(unknown)'}`;
        this.renderGameList('linkGameList', m, 'selected');
        document.getElementById('modalOverlay').classList.remove('hidden');
        document.getElementById('linkModal').classList.remove('hidden');
    },
    confirmLink() {
        const sel = document.querySelector('#linkGameList .selected');
        if (!sel) { window.pywebview.api.warn_user("Please select a game folder."); return; }
        document.getElementById('modalOverlay').classList.add('hidden');
        document.getElementById('linkModal').classList.add('hidden');
        window.pywebview.api.resume_link(sel.dataset.path);
    },

    // ── Fix Modal ─────────────────────────────────────────────────────────────
    openFixModal(manifestsJson, gameListJson, isDlc = false) {
        this.currentManifests = JSON.parse(manifestsJson);
        this.currentGameList  = JSON.parse(gameListJson);

        const title      = document.getElementById('fixModalTitle');
        const subtitle   = document.getElementById('fixModalSubtitle');
        const confirmBtn = document.getElementById('fixConfirmBtn');

        if (isDlc) {
            title.innerText      = '✦ Fix DLC Link';
            title.className      = 'text-orange';
            confirmBtn.innerText = '✦ Fix DLC Link';
            confirmBtn.className = 'btn bg-orange';
            subtitle.innerHTML   = 'Select the DLC manifest on the left, then the correct game folder on the right.<br>'
                + '<span class="muted">[ ★ ] exact match &nbsp;|&nbsp; [ ? ] likely guess / Possible DLC</span>';
        } else {
            title.innerText      = '✦ Fix Manifest Link';
            title.className      = 'text-amber';
            confirmBtn.innerText = '✦ Fix Link';
            confirmBtn.className = 'btn bg-amber';
            subtitle.innerHTML   = 'Select the incorrect manifest on the left, then the correct game folder on the right.<br>'
                + '<span class="muted">[ ★ ] exact match &nbsp;|&nbsp; [ ? ] likely guess / Possible DLC</span>';
        }

        document.getElementById('fixStatus').innerText =
            'Select a manifest to see its current install location.';

        this.renderFixManifests();
        this.renderGameList('fixGameList', null, 'selected-amber');
        document.getElementById('modalOverlay').classList.remove('hidden');
        document.getElementById('fixModal').classList.remove('hidden');
    },
    renderFixManifests() {
        const c = document.getElementById('fixManifestList');
        c.innerHTML = '';
        this.currentManifests.forEach((m, idx) => {
            const d = document.createElement('div');
            d.className    = 'list-item';
            d.innerText    = m.display_name || m.file_name;
            d.dataset.idx  = idx;
            d.onclick = () => {
                c.querySelectorAll('.list-item').forEach(x => x.classList.remove('selected-amber'));
                d.classList.add('selected-amber');
                document.getElementById('fixStatus').innerText =
                    'Current install: ' + (m.install_location || '(unknown)');
                this.renderGameList('fixGameList', m, 'selected-amber');
            };
            c.appendChild(d);
        });
    },
    confirmFix() {
        const sm = document.querySelector('#fixManifestList .selected-amber');
        const sf = document.querySelector('#fixGameList .selected-amber');
        if (!sm || !sf) {
            window.pywebview.api.warn_user("Please select both a manifest and the correct game folder.");
            return;
        }
        const m = this.currentManifests[parseInt(sm.dataset.idx)];
        document.getElementById('fixStatus').innerText = 'Fixing... check the log panel.';
        window.pywebview.api.resume_fix(m.file_path, sf.dataset.path);
    },
    markFixDone(manifestPath) {
        document.querySelectorAll('#fixManifestList .list-item').forEach(item => {
            const idx = parseInt(item.dataset.idx);
            if (this.currentManifests[idx]?.file_path === manifestPath) {
                item.classList.remove('selected-amber');
                item.classList.add('done-item');
                item.innerText = '[ ✓ ] ' + (this.currentManifests[idx].display_name || this.currentManifests[idx].file_name);
                item.onclick = null;
            }
        });
        document.querySelectorAll('#fixGameList .list-item')
            .forEach(x => x.classList.remove('selected-amber'));
        document.getElementById('fixStatus').innerText =
            'Done! Pick another to fix, or click Cancel to close.';
    },
    closeFixModal() {
        document.getElementById('modalOverlay').classList.add('hidden');
        document.getElementById('fixModal').classList.add('hidden');
        window.pywebview.api.abort_action();
    },

    // ── Move Modal ────────────────────────────────────────────────────────────
    async browseMoveDest() {
        const path = await window.pywebview.api.browse_directory("Select Destination Folder");
        if (path) document.getElementById('moveDestPath').value = path;
    },
    openMoveModal(gameListJson) {
        this.currentGameList = JSON.parse(gameListJson);
        const c = document.getElementById('moveGameList');
        c.innerHTML = '';
        this.currentGameList.forEach(g => {
            const d = document.createElement('div');
            d.className    = 'list-item';
            d.innerText    = g.name;
            d.dataset.path = g.path;
            d.onclick = () => d.classList.toggle('selected-amber');
            c.appendChild(d);
        });
        document.getElementById('moveDestPath').value = '';
        document.getElementById('modalOverlay').classList.remove('hidden');
        document.getElementById('moveModal').classList.remove('hidden');
    },
    confirmMove() {
        const sel  = Array.from(document.querySelectorAll('#moveGameList .selected-amber')).map(x => x.dataset.path);
        const dest = document.getElementById('moveDestPath').value;
        if (!sel.length) { window.pywebview.api.warn_user("Select at least one game to move."); return; }
        if (!dest)       { window.pywebview.api.warn_user("Select a destination path."); return; }
        document.getElementById('modalOverlay').classList.add('hidden');
        document.getElementById('moveModal').classList.add('hidden');
        window.pywebview.api.resume_move(sel, dest);
    },

    // ── Capture Modal ─────────────────────────────────────────────────────────
    openCaptureModal(msg) {
        document.getElementById('captureModalMsg').innerText = msg;
        document.getElementById('modalOverlay').classList.remove('hidden');
        document.getElementById('captureModal').classList.remove('hidden');
    },
    confirmCapture(action) {
        document.getElementById('modalOverlay').classList.add('hidden');
        document.getElementById('captureModal').classList.add('hidden');
        window.pywebview.api.resume_capture(action);
    },

    // ── Close all modals ──────────────────────────────────────────────────────
    closeModals() {
        document.getElementById('modalOverlay').classList.add('hidden');
        document.querySelectorAll('.modal-content').forEach(m => m.classList.add('hidden'));
        window.pywebview.api.abort_action();
    },

    // ── Game List Renderer ────────────────────────────────────────────────────
    renderGameList(containerId, activeManifest, selClass) {
        window.pywebview.api.get_predictions(
            activeManifest ? JSON.stringify(activeManifest) : null,
            JSON.stringify(this.currentGameList)
        ).then(res => {
            const pred = JSON.parse(res);
            const c    = document.getElementById(containerId);
            c.innerHTML = '';

            this.currentGameList.forEach((g, idx) => {
                let prefix = '     ';
                if (idx === pred.best)         prefix = '[ ★ ]';
                else if (idx === pred.closest) prefix = '[ ? ]';

                const d = document.createElement('div');
                d.className    = 'list-item';
                d.innerText    = `${prefix}  ${g.name}`;
                d.dataset.path = g.path;
                d.onclick = () => {
                    c.querySelectorAll('.list-item').forEach(x =>
                        x.classList.remove('selected', 'selected-amber'));
                    d.classList.add(selClass);
                };
                c.appendChild(d);

                if (idx === pred.best && activeManifest) {
                    d.classList.add(selClass);
                    setTimeout(() => d.scrollIntoView({ block: 'center' }), 10);
                } else if (idx === pred.closest && pred.best === -1 && activeManifest) {
                    setTimeout(() => d.scrollIntoView({ block: 'center' }), 10);
                }
            });
        });
    }
};

// ── Boot ──────────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', () => {
    appCtrl.init();

    setInterval(async () => {
        if (!window.pywebview?.api) return;

        try {
            const logsJson = await window.pywebview.api.get_logs();
            const logs = JSON.parse(logsJson);
            if (logs?.length) logs.forEach(l => appCtrl.appendLog(l.text, l.tag));
        } catch(e) {}

        try {
            const modalJson = await window.pywebview.api.get_modal();
            const modals = JSON.parse(modalJson);
            if (modals?.length) {
                modals.forEach(m => {
                    if (m.type === 'alert')          alert(m.msg);
                    if (m.type === 'link')           appCtrl.openLinkModal(JSON.stringify(m.manifests_json), JSON.stringify(m.games_json));
                    if (m.type === 'fix')            appCtrl.openFixModal(JSON.stringify(m.manifests_json), JSON.stringify(m.games_json), false);
                    if (m.type === 'fix_dlc')        appCtrl.openFixModal(JSON.stringify(m.manifests_json), JSON.stringify(m.games_json), true);
                    if (m.type === 'fix_done')       appCtrl.markFixDone(m.manifest_path, m.game_path);
                    if (m.type === 'capture_prompt') appCtrl.openCaptureModal(m.msg);
                    if (m.type === 'move')           appCtrl.openMoveModal(JSON.stringify(m.games_json));
                });
            }
        } catch(e) {}

    }, 250);
});
