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

        // Set action group states — start collapsed
        this._expandedGroups = { 
            'group-relink': false, 
            'group-capture': false,
            'group-manifest': false,
            'lib-group-main': false,
            'lib-group-dlc': false,
            'lib-group-pending': false,
            'help-relink': false,
            'help-move': false,
            'help-pc': false,
            'help-capture': false,
            'help-link': false,
            'help-fix-games': false,
            'help-fix-dlcs': false,
            'help-library': false,
            'help-manifest-tools': false
        };
        // Let the DOM settle before measuring
        requestAnimationFrame(() => {
            // Only animate open if default state was set to true
            for (const [id, isOpen] of Object.entries(this._expandedGroups)) {
                if (isOpen) this._setGroupHeight(id);
            }
        });
    },

    // ── Settings Panel ────────────────────────────────────────────────────────
    openSettings() {
        const overlay = document.getElementById('settingsOverlay');
        if (!overlay.classList.contains('hidden')) {
            this.closeSettings(null); // save + close
        } else {
            overlay.classList.remove('hidden');
        }
    },
    closeSettings(evt) {
        if (evt && evt.target !== document.getElementById('settingsOverlay')) return;
        document.getElementById('settingsOverlay').classList.add('hidden');
        
        const mPath = document.getElementById('manifestPath').value;
        const gPath = document.getElementById('gamesPath').value;
        const useDef = document.getElementById('useDefault').checked;
        window.pywebview.api.save_settings(mPath, gPath, useDef);
    },

    async resetSettings() {
        if (!confirm('Reset all settings to defaults?\n\nThis will clear your saved Manifests and Games paths and cannot be undone.')) return;
        // Clear UI immediately
        document.getElementById('useDefault').checked = true;
        document.getElementById('manifestPath').value = this._defaultManifestPath || '';
        document.getElementById('gamesPath').value = '';
        document.getElementById('themeSelect').value = 'Dark Blue';
        this.applyTheme('Dark Blue', true);
        // Persist the cleared state
        await window.pywebview.api.save_settings(this._defaultManifestPath || '', '', true);
        this.appendLog('Settings reset to defaults.', 'INFO');
    },

    async restoreSettings() {
        const res = await window.pywebview.api.get_initial_paths();
        const cfg = typeof res === 'string' ? JSON.parse(res) : res;
        if (cfg.manifestPath) document.getElementById('manifestPath').value = cfg.manifestPath;
        if (cfg.gamesPath)    document.getElementById('gamesPath').value    = cfg.gamesPath;
        document.getElementById('useDefault').checked = !!cfg.useDefault;
        this.appendLog('Settings restored from saved config.', 'INFO');
    },


    // ── Help Panel ────────────────────────────────────────────────────────────
    openHelp() {
        document.getElementById('helpOverlay').classList.remove('hidden');
    },
    closeHelp(evt) {
        if (evt && evt.target !== document.getElementById('helpOverlay')) return;
        document.getElementById('helpOverlay').classList.add('hidden');
    },

    // ── Theme ─────────────────────────────────────────────────────────────────
    applyTheme(name, save = true) {
        document.documentElement.setAttribute('data-theme', name);
        const sel = document.getElementById('themeSelect');
        if (sel) sel.value = name;
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
    _expandedGroups: {}, // defaults to false (collapsed)

    toggleGroup(id) {
        // Now defaults to false (collapsed)
        const isOpen = this._expandedGroups[id] === true;
        this._expandedGroups[id] = !isOpen;
        this._setGroupHeight(id);
    },

    _setGroupHeight(id) {
        const body    = document.getElementById('body-' + id);
        const chevron = document.getElementById('chevron-' + id);
        if (!body || !chevron) return;
        
        const isOpen  = this._expandedGroups[id] === true;

        if (isOpen) {
            body.classList.remove('collapsed');
            chevron.classList.remove('collapsed');
            
            // Measure scrollHeight (already correct because padding/max-height are removed by class change)
            // Need to temporarily remove inline max-height if any
            body.style.maxHeight = '';
            const fullHeight = body.scrollHeight;
            
            // Start from 0 to animate up
            body.style.maxHeight = '0px';
            body.offsetHeight; // Force reflow
            
            body.style.maxHeight = fullHeight + 'px';

            const onDone = (e) => {
                if (e.target !== body) return;
                if (this._expandedGroups[id] === true) {
                    body.style.maxHeight = 'none';
                }
                body.removeEventListener('transitionend', onDone);
            };
            body.addEventListener('transitionend', onDone);

        } else {
            // Pin current height before collapsing
            if (body.style.maxHeight === 'none' || body.style.maxHeight === '') {
                body.style.maxHeight = body.scrollHeight + 'px';
                body.offsetHeight; // force reflow
            }
            
            // Next frame set to 0
            requestAnimationFrame(() => {
                body.classList.add('collapsed');
                chevron.classList.add('collapsed');
                body.style.maxHeight = '0px';
            });
        }
    },

    // ── Log ───────────────────────────────────────────────────────────────────

    _terminalOn: true,

    toggleTerminalOff() {
        this._terminalOn = false;
        const panel = document.getElementById('terminalPanel');
        panel.classList.remove('log-showing');
        panel.classList.add('log-hiding');
        setTimeout(() => { panel.classList.add('hidden'); panel.classList.remove('log-hiding'); }, 320);
        // Update blob buttons to reflect new state (still on tools section)
        document.getElementById('hideLogBtn').style.display = 'none';
        document.getElementById('showLogBtn').style.display = '';
        document.getElementById('easterEggCorner').classList.remove('hidden');
    },

    toggleTerminalOn() {
        this._terminalOn = true;
        const panel = document.getElementById('terminalPanel');
        panel.classList.remove('hidden');
        panel.classList.remove('log-hiding');
        panel.classList.add('log-showing');
        setTimeout(() => { panel.classList.remove('log-showing'); }, 320);
        // Update blob buttons to reflect new state (still on tools section)
        document.getElementById('showLogBtn').style.display = 'none';
        document.getElementById('hideLogBtn').style.display = '';
        document.getElementById('easterEggCorner').classList.add('hidden');
        const lc = document.getElementById('logContent');
        if (lc) lc.scrollTop = lc.scrollHeight;
    },

    async copyLog() {
        const text = Array.from(document.querySelectorAll('.log-entry')).map(e => {
            const ts = e.querySelector('.log-ts')?.textContent || '';
            const txt = e.querySelector('.log-text')?.textContent || '';
            return `[${ts}] ${txt}`;
        }).join('\n');
        try {
            await navigator.clipboard.writeText(text);
            this.appendLog("Copied log to clipboard.", "SUCCESS");
        } catch (e) {
            this.appendLog("Failed to copy log.", "ERROR");
        }
    },

    async saveLog() {
        const text = Array.from(document.querySelectorAll('.log-entry')).map(e => {
            const ts = e.querySelector('.log-ts')?.textContent || '';
            const txt = e.querySelector('.log-text')?.textContent || '';
            return `[${ts}] ${txt}`;
        }).join('\n');
        if (window.pywebview?.api) {
            await window.pywebview.api.export_log(text);
        }
    },

    openLogFolder() {
        if (window.pywebview?.api) {
            window.pywebview.api.open_log_folder();
        }
    },

    clearLog() {
        document.getElementById('logContent').innerHTML = '';
        const count = document.getElementById('terminalLineCount');
        if (count) count.textContent = '';
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

        // Update line count badge
        const lineCount = lc.querySelectorAll('.log-entry').length;
        const countEl   = document.getElementById('terminalLineCount');
        if (countEl) countEl.textContent = `(${lineCount})`;

        if (this._terminalOn) {
            lc.scrollTop = lc.scrollHeight;
        }
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
    },

    // ── Sidebar Navigation ────────────────────────────────────────────────────
    switchNav(viewId) {
        // Update nav buttons
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.remove('active');
            btn.style.background = 'transparent';
            btn.style.color = 'var(--muted)';
        });
        const activeBtn = document.getElementById('nav-' + viewId);
        if (activeBtn) {
            activeBtn.classList.add('active');
            activeBtn.style.background = 'rgba(255,255,255,0.1)';
            activeBtn.style.color = 'white';
        }

        // Hide all views, show target view
        document.querySelectorAll('.app-view').forEach(v => v.classList.add('hidden'));
        const targetView = document.getElementById(viewId + 'View');
        if (targetView) targetView.classList.remove('hidden');

        // Show log blob only on Tools & Logs section
        const hideLogBtn = document.getElementById('hideLogBtn');
        const showLogBtn = document.getElementById('showLogBtn');
        const isTools = viewId === 'tools';
        if (hideLogBtn) hideLogBtn.style.display = isTools && this._terminalOn  ? '' : 'none';
        if (showLogBtn) showLogBtn.style.display = isTools && !this._terminalOn ? '' : 'none';

        if (viewId === 'library') {
            this.refreshLibrary();
        } else if (viewId === 'home') {
            this.loadReadme();
        }
    },

    async loadReadme() {
        if (window.pywebview?.api) {
            const readmeText = await window.pywebview.api.get_readme();
            const el = document.getElementById('readmeContent');
            if (el) el.textContent = readmeText;
        }
    },

    easterEgg() {
        alert("Easter egg found! This will be defined later.");
    },
    async refreshLibrary() {
        const m = document.getElementById('manifestPath').value;
        const g = document.getElementById('gamesPath').value;
        const grid = document.getElementById('libraryGrid');
        const dlcGrid = document.getElementById('dlcGrid');
        const dlcSection = document.getElementById('dlcSection');

        if (!m) {
            grid.innerHTML = '<div class="text-center muted" style="padding: 40px;">Configure your Manifests path in Settings first.</div>';
            dlcSection.classList.add('hidden');
            return;
        }

        grid.innerHTML = '<div class="text-center muted" style="padding: 40px;">Loading library...</div>';
        dlcSection.classList.add('hidden');

        try {
            const resJson = await window.pywebview.api.get_library_data(m, g);
            const res = JSON.parse(resJson);

            if (res.error) {
                grid.innerHTML = `<div class="text-center text-orange" style="padding: 40px;">Error: ${res.error}</div>`;
                return;
            }

            const hasGames   = res.games   && res.games.length   > 0;
            const hasDlcs    = res.dlcs    && res.dlcs.length    > 0;
            const hasPending = res.pending && res.pending.length > 0;

            if (!hasGames && !hasDlcs && !hasPending) {
                grid.innerHTML = '<div class="text-center muted" style="padding: 40px;">No games found.</div>';
                return;
            }

            // ── Main Games ──
            grid.innerHTML = '';
            const mgCount = document.getElementById('mainGamesCount');
            if (mgCount) mgCount.textContent = hasGames ? `(${res.games.length})` : '';

            if (hasGames) {
                res.games.forEach(game => {
                    grid.appendChild(this._createGameCard(game, false));
                });
            } else {
                grid.innerHTML = '<div class="text-center muted" style="padding: 40px;">No main games found.</div>';
            }

            // ── DLCs ──
            const dCount = document.getElementById('dlcCount');
            if (dCount) dCount.textContent = hasDlcs ? `(${res.dlcs.length})` : '';

            if (hasDlcs) {
                if (!this._dlcScanned) {
                    // First time: render automatically
                    this._dlcScanned = true;
                    this._renderDlcs(res.dlcs);
                } else if (arguments[0] === true) {
                    // Forced by clicking prompt button
                    this._renderDlcs(res.dlcs);
                } else {
                    // Prompt to load DLCs
                    dlcGrid.innerHTML = `
                        <div class="text-center" style="padding: 30px;">
                            <p class="muted mb-3" style="font-size: 13px;">DLCs and Add-ons are ready to be viewed.</p>
                            <button class="btn bg-purple" onclick="appCtrl.refreshLibrary(true)" style="display:inline-flex; align-items:center; gap:8px;">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/></svg>
                                Load DLCs
                            </button>
                        </div>
                    `;
                }
                dlcSection.classList.remove('hidden');
            } else {
                if (dCount) dCount.textContent = '';
            }

            // ── Pending Manifests ──
            const pendingGrid    = document.getElementById('pendingGrid');
            const pendingSection = document.getElementById('pendingSection');
            const pendingCount   = document.getElementById('pendingSectionCount');
            if (hasPending) {
                pendingGrid.innerHTML = '';
                res.pending.forEach(item => {
                    pendingGrid.appendChild(this._createGameCard(item, false));
                });
                pendingCount.textContent = `(${res.pending.length})`;
                pendingSection.classList.remove('hidden');
            } else {
                pendingSection.classList.add('hidden');
                pendingCount.textContent = '';
            }

            // Re-measure accordion heights since content changed
            requestAnimationFrame(() => {
                this._setGroupHeight('lib-group-main');
                this._setGroupHeight('lib-group-dlc');
                this._setGroupHeight('lib-group-pending');
            });

        } catch (e) {
            grid.innerHTML = `<div class="text-center text-orange" style="padding: 40px;">Failed to load library: ${e}</div>`;
        }
    },
    
    _renderDlcs(dlcs) {
        const dlcGrid = document.getElementById('dlcGrid');
        if (!dlcGrid) return;
        dlcGrid.innerHTML = '';
        dlcs.forEach(dlc => {
            dlcGrid.appendChild(this._createGameCard(dlc, true));
        });
    },

    _createGameCard(game, isDlc) {
        let statusClass = 'status-Broken';
        let statusText = game.status;
        let pendingHint = '';

        if (game.status === 'Linked') {
            statusClass = 'status-Linked';
        } else if (game.status === 'Missing Manifest') {
            statusClass = 'status-Missing';
            statusText = 'Missing .item';
        } else if (game.status === 'Pending Install') {
            statusClass = 'status-Pending';
            statusText = 'Pending Install';
            pendingHint = 'Download was interrupted — no root manifest yet. Use <b>Link</b> to register this game.';
        } else if (game.status === 'Pending Manifest') {
            statusClass = 'status-PendingDupe';
            statusText = 'Pending Manifest';
            pendingHint = 'Duplicate leftover from a cancelled download. Use <b>Manifest Cleanup → Duplicate Pending</b> to remove it.';
        }

        const safeGameName = game.name.replace(/'/g, "\\'").replace(/"/g, '\\"');
        const card = document.createElement('div');
        card.className = 'game-card';
        if (game.status === 'Pending Install')   card.classList.add('game-card-pending');
        if (game.status === 'Pending Manifest')  card.classList.add('game-card-pending-dupe');
        card.innerHTML = `
            <div class="game-card-header">
                <div class="game-title">${game.name}</div>
                <div class="game-status ${statusClass}">${statusText}</div>
            </div>
            <div class="game-path" title="${game.path}">${game.path}</div>
            ${pendingHint ? `<div class="game-pending-hint">${pendingHint}</div>` : ''}
            <div class="game-actions">
                ${game.app_name ? `<button class="btn-play" onclick="appCtrl.launchGame('${game.app_name}', '${safeGameName}', ${isDlc})">▶ Play</button>` : ''}
            </div>
        `;

        return card;
    },

    launchGame(appName, gameName, isDlc) {
        if (isDlc) {
            if (!confirm(`Notice: You are about to launch "${gameName}", which appears to be a DLC or add-on.\n\nDepending on the game, you may need to launch the Main Game instead for it to load properly.\n\nDo you want to attempt launching it anyway?`)) {
                return;
            }
        } else {
            if (!confirm(`Notice: Launching "${gameName}" will also automatically load any installed DLCs and add-ons associated with it.\n\nDo you want to continue?`)) {
                return;
            }
        }
        window.pywebview.api.launch_game(appName);
    },

    restartLauncher() {
        if (confirm("This will force-close and restart the Epic Games Launcher. Continue?")) {
            window.pywebview.api.restart_launcher();
        }
    },

    // ── Manifest Cleanup (#14) ────────────────────────────────────────────
    _cleanupOrphans: [],    // cached orphan scan results
    _cleanupPending: [],    // cached pending-duplicate scan results
    _cleanupActiveTab: 'orphans',

    async openManifestCleanup() {
        const m = document.getElementById('manifestPath').value;
        if (!m) { alert('Please set your Manifests folder in Settings first.'); return; }

        const overlay = document.getElementById('manifestCleanupOverlay');
        const summary = document.getElementById('cleanupSummary');

        // Reset to orphans tab
        this._cleanupActiveTab = 'orphans';
        this.cleanupSwitchTab('orphans', /*init=*/true);

        document.getElementById('cleanupOrphanList').innerHTML  = '<div class="muted text-center" style="padding:32px;">Scanning...</div>';
        document.getElementById('cleanupPendingList').innerHTML = '<div class="muted text-center" style="padding:32px;">Scanning...</div>';
        document.getElementById('cleanupCountOrphans').textContent = '';
        document.getElementById('cleanupCountPending').textContent = '';
        document.getElementById('cleanupSelectAllBtn').textContent = 'Select All';
        summary.textContent = '';
        overlay.classList.remove('hidden');

        try {
            const resJson = await window.pywebview.api.get_manifest_cleanup_data(m);
            const res = JSON.parse(resJson);

            if (res.error) {
                document.getElementById('cleanupOrphanList').innerHTML =
                    `<div class="muted text-center text-orange" style="padding:32px;">Error: ${res.error}</div>`;
                return;
            }

            this._cleanupOrphans = res.orphans       || [];
            this._cleanupPending = res.pending_dupes || [];

            // ── Render orphans ──
            this._renderOrphanList();

            // ── Render pending duplicates ──
            this._renderPendingList();

            // Update tab counts
            document.getElementById('cleanupCountOrphans').textContent =
                this._cleanupOrphans.length ? `(${this._cleanupOrphans.length})` : '';
            document.getElementById('cleanupCountPending').textContent =
                this._cleanupPending.length ? `(${this._cleanupPending.length})` : '';

            this._updateCleanupSummary();

        } catch (e) {
            document.getElementById('cleanupOrphanList').innerHTML =
                `<div class="muted text-center" style="padding:32px;">Failed to scan: ${e}</div>`;
        }
    },

    _renderOrphanList() {
        const list = document.getElementById('cleanupOrphanList');
        if (this._cleanupOrphans.length === 0) {
            list.innerHTML = '<div class="manifest-all-ok"><span>✔</span> No orphaned manifests found — root folder is clean!</div>';
            return;
        }
        list.innerHTML = '';
        this._cleanupOrphans.forEach((o, idx) => {
            const row = document.createElement('div');
            row.className = 'manifest-result-row orphan-row';
            row.innerHTML = `
                <label class="manifest-check-label">
                    <input type="checkbox" class="orphan-check" data-list="orphans" data-idx="${idx}">
                    <div class="manifest-row-info">
                        <div class="manifest-row-name">${o.display_name || o.file_name}</div>
                        <div class="manifest-row-file">${o.file_name}</div>
                        <div class="manifest-row-path">Missing path: ${o.install_location}</div>
                    </div>
                </label>`;
            list.appendChild(row);
        });
    },

    _renderPendingList() {
        const list = document.getElementById('cleanupPendingList');
        if (this._cleanupPending.length === 0) {
            list.innerHTML = '<div class="manifest-all-ok"><span>✔</span> No duplicate pending manifests found!</div>';
            return;
        }
        list.innerHTML = '';
        this._cleanupPending.forEach((p, idx) => {
            const rootOk = p.root_install_ok;
            const row = document.createElement('div');
            row.className = 'manifest-result-row orphan-row';
            row.innerHTML = `
                <label class="manifest-check-label">
                    <input type="checkbox" class="orphan-check" data-list="pending" data-idx="${idx}"
                        ${!rootOk ? 'disabled title="Root manifest has a broken path — fix it before deleting this pending copy."' : ''}>
                    <div class="manifest-row-info">
                        <div class="manifest-row-name">
                            ${p.display_name || p.file_name}
                            ${rootOk
                                ? '<span class="pending-root-badge ok">✔ Root OK</span>'
                                : '<span class="pending-root-badge broken">⚠ Root Broken — Fix First</span>'}
                        </div>
                        <div class="manifest-row-file">Pending: ${p.file_name}</div>
                        <div class="manifest-row-file" style="color: var(--muted);">Superseded by: ${p.root_file_name}</div>
                        <div class="manifest-row-path" style="color: var(--muted); font-style: normal;">AppName: ${p.app_name}</div>
                    </div>
                </label>`;
            list.appendChild(row);
        });
    },

    _updateCleanupSummary() {
        const summary = document.getElementById('cleanupSummary');
        const parts = [];
        if (this._cleanupOrphans.length) parts.push(`${this._cleanupOrphans.length} orphaned`);
        if (this._cleanupPending.length) parts.push(`${this._cleanupPending.length} duplicate pending`);
        summary.textContent = parts.length ? parts.join(', ') + ' manifest(s) found.' : 'No issues found — your manifest folder is clean!';
    },

    cleanupSwitchTab(tab, init = false) {
        this._cleanupActiveTab = tab;
        document.getElementById('cleanupPaneOrphans').classList.toggle('hidden', tab !== 'orphans');
        document.getElementById('cleanupPanePending').classList.toggle('hidden', tab !== 'pending');
        document.getElementById('cleanupTabOrphans').classList.toggle('active', tab === 'orphans');
        document.getElementById('cleanupTabPending').classList.toggle('active', tab === 'pending');
        if (!init) document.getElementById('cleanupSelectAllBtn').textContent = 'Select All';
    },

    closeManifestCleanup(evt) {
        if (evt && evt.target !== document.getElementById('manifestCleanupOverlay')) return;
        document.getElementById('manifestCleanupOverlay').classList.add('hidden');
    },

    cleanupSelectAll() {
        // Scope to checkboxes in the ACTIVE tab only
        const selector = this._cleanupActiveTab === 'orphans'
            ? '#cleanupOrphanList .orphan-check:not(:disabled)'
            : '#cleanupPendingList .orphan-check:not(:disabled)';
        const checks = document.querySelectorAll(selector);
        const allChecked = Array.from(checks).every(c => c.checked);
        checks.forEach(c => c.checked = !allChecked);
        document.getElementById('cleanupSelectAllBtn').textContent = allChecked ? 'Select All' : 'Deselect All';
    },

    async cleanupDeleteSelected() {
        // Collect from BOTH tabs so users can switch tabs and delete all at once
        const checked = Array.from(document.querySelectorAll('.orphan-check:checked:not(:disabled)'));
        if (checked.length === 0) {
            alert('No manifests selected. Check at least one row to delete.');
            return;
        }
        if (!confirm(`Permanently delete ${checked.length} manifest file${checked.length !== 1 ? 's' : ''}?\n\nThis cannot be undone. Only proceed if you are sure these files are no longer needed.`)) {
            return;
        }

        let deleted = 0;
        let failed  = 0;
        for (const cb of checked) {
            const list = cb.dataset.list;  // 'orphans' | 'pending'
            const idx  = parseInt(cb.dataset.idx);
            const item = list === 'orphans' ? this._cleanupOrphans[idx] : this._cleanupPending[idx];
            if (!item) continue;
            try {
                const resJson = await window.pywebview.api.delete_manifest_file(item.file_path);
                const res = JSON.parse(resJson);
                if (res.ok) {
                    const row = cb.closest('.manifest-result-row');
                    if (row) { row.classList.add('manifest-row-deleted'); row.style.pointerEvents = 'none'; }
                    deleted++;
                } else { failed++; }
            } catch (e) { failed++; }
        }

        const summary = document.getElementById('cleanupSummary');
        summary.textContent = `Done: ${deleted} deleted${failed > 0 ? `, ${failed} failed (check log)` : ''}.`;
        document.getElementById('cleanupSelectAllBtn').textContent = 'Select All';
    },

    // ── Manifest Validator (#14) ───────────────────────────────────────────
    async openManifestValidator() {
        const m = document.getElementById('manifestPath').value;
        if (!m) { alert('Please set your Manifests folder in Settings first.'); return; }

        const overlay = document.getElementById('manifestValidatorOverlay');
        const list    = document.getElementById('validatorIssueList');
        const summary = document.getElementById('validatorSummary');

        list.innerHTML = '<div class="muted text-center" style="padding:32px;">Scanning...</div>';
        summary.textContent = '';
        overlay.classList.remove('hidden');

        try {
            const resJson = await window.pywebview.api.get_manifest_validate_data(m);
            const res = JSON.parse(resJson);

            if (res.error) {
                list.innerHTML = `<div class="muted text-center text-orange" style="padding:32px;">Error: ${res.error}</div>`;
                return;
            }

            const issues = res.issues || [];

            if (issues.length === 0) {
                list.innerHTML = '<div class="manifest-all-ok"><span>✔</span> All manifests passed validation — no issues found!</div>';
                summary.textContent = '';
                return;
            }

            list.innerHTML = '';
            const errorCount   = issues.filter(i => i.severity === 'error').length;
            const warningCount = issues.filter(i => i.severity === 'warning').length;

            issues.forEach(item => {
                const row = document.createElement('div');
                const sev = item.severity; // 'error' | 'warning'
                row.className = `manifest-result-row validator-row severity-${sev}`;
                const issueHtml = item.issues.map(iss => `<div class="validator-issue">${iss}</div>`).join('');
                row.innerHTML = `
                    <div class="manifest-row-info">
                        <div class="manifest-row-name">
                            <span class="severity-badge severity-badge-${sev}">${sev.toUpperCase()}</span>
                            ${item.display_name || item.file_name}
                        </div>
                        <div class="manifest-row-file">${item.file_name}</div>
                        <div class="validator-issues-list">${issueHtml}</div>
                    </div>
                `;
                list.appendChild(row);
            });

            const parts = [];
            if (errorCount)   parts.push(`${errorCount} error${errorCount !== 1 ? 's' : ''}`);
            if (warningCount) parts.push(`${warningCount} warning${warningCount !== 1 ? 's' : ''}`);
            summary.textContent = parts.join(', ') + ' detected.';

        } catch (e) {
            list.innerHTML = `<div class="muted text-center" style="padding:32px;">Failed to scan: ${e}</div>`;
        }
    },

    closeManifestValidator(evt) {
        if (evt && evt.target !== document.getElementById('manifestValidatorOverlay')) return;
        document.getElementById('manifestValidatorOverlay').classList.add('hidden');
    }
};

// ── Boot ──────────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', () => {
    appCtrl.init();
    
    // Automatically fetch library on boot
    setTimeout(() => appCtrl.refreshLibrary(), 500);
    // Open home by default
    setTimeout(() => appCtrl.switchNav('home'), 100);

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
                    if (m.type === 'restart_prompt') {
                        if (confirm(m.msg)) {
                            window.pywebview.api.restart_launcher();
                        }
                    }
                });
            }
        } catch(e) {}

    }, 250);
});
