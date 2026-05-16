/**
 * app.js — Main application controller
 * Handles routing, view switching, data loading, and event binding.
 */

const App = {
    currentView: 'overview',
    sortState: { col: 'stress_score', order: 'desc' },
    filters: { sector: 'all', risk: 'all', search: '' },

    async init() {
        this.bindNav();
        this.bindSearch();
        this.showLoading(true);
        await this.loadOverview();
        this.showLoading(false);
    },

    // ── Navigation ───────────────────────────────────────────────────

    bindNav() {
        document.querySelectorAll('.nav-item[data-view]').forEach(el => {
            el.addEventListener('click', () => {
                const view = el.dataset.view;
                this.navigate(view);
            });
        });
    },

    navigate(view) {
        this.currentView = view;
        // Update nav active state
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        const active = document.querySelector(`.nav-item[data-view="${view}"]`);
        if (active) active.classList.add('active');

        // Show/hide views
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const target = document.getElementById(`view-${view}`);
        if (target) target.classList.add('active');

        // Update breadcrumb
        const names = { overview: 'Overview', companies: 'All Companies', sectors: 'Sectors', live: 'Live Scorer', detail: 'Company Detail' };
        const bc = document.getElementById('breadcrumb-page');
        if (bc) bc.textContent = names[view] || view;

        // Load data for view
        if (view === 'overview') this.loadOverview();
        if (view === 'companies') this.loadCompanies();
        if (view === 'sectors') this.loadSectors();
        if (view === 'live') this.initLive();
    },

    // ── Loading ──────────────────────────────────────────────────────

    showLoading(show) {
        const el = document.getElementById('loading-overlay');
        if (el) el.classList.toggle('hidden', !show);
    },

    // ── Search ───────────────────────────────────────────────────────

    bindSearch() {
        const input = document.getElementById('header-search');
        if (!input) return;
        let timer;
        input.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                const val = input.value.trim().toUpperCase();
                if (val.length >= 1) {
                    this.filters.search = val;
                    if (this.currentView !== 'companies') this.navigate('companies');
                    else this.loadCompanies();
                } else {
                    this.filters.search = '';
                    if (this.currentView === 'companies') this.loadCompanies();
                }
            }, 300);
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = input.value.trim().toUpperCase();
                if (val) this.showCompany(val);
            }
        });
    },

    // ── Overview View ────────────────────────────────────────────────

    async loadOverview() {
        const [overview, scoresData] = await Promise.all([
            API.getOverview(),
            API.getScores({ sort: 'stress_score', order: 'desc' }),
        ]);

        if (overview.error) return;

        // KPI cards
        const kpiGrid = document.getElementById('overview-kpis');
        if (kpiGrid) {
            kpiGrid.innerHTML = [
                Components.kpiCard('Total Companies', overview.total_companies, Components.Icons.companies, 'blue', 'Tracked in system'),
                Components.kpiCard('Avg Stress Score', overview.avg_stress_score, Components.Icons.stress, 'yellow', 'Across all companies'),
                Components.kpiCard('High / Critical Risk', (overview.risk_distribution.high + overview.risk_distribution.critical), Components.Icons.risk, 'red', `${overview.risk_distribution.critical} critical, ${overview.risk_distribution.high} high`),
                Components.kpiCard('Companies Flagged', overview.flagged_companies, Components.Icons.flag, 'yellow', 'With red flags'),
            ].join('');
        }

        // Risk donut
        Charts.renderRiskDonut('chart-risk-donut', overview.risk_distribution);

        // Sector bars
        Charts.renderSectorBars('chart-sector-bars', overview.sector_avg_stress);

        // Score distribution
        if (scoresData.companies) {
            Charts.renderScoreDistribution('chart-score-dist', scoresData.companies);
        }

        // Top stressed table
        const topEl = document.getElementById('overview-top-stressed');
        if (topEl) {
            topEl.innerHTML = Components.topStressedTable(overview.top_stressed);
        }
    },

    // ── Companies View ───────────────────────────────────────────────

    async loadCompanies() {
        const params = {
            sort: this.sortState.col,
            order: this.sortState.order,
        };
        if (this.filters.sector !== 'all') params.sector = this.filters.sector;
        if (this.filters.risk !== 'all') params.risk = this.filters.risk;
        if (this.filters.search) params.search = this.filters.search;

        const data = await API.getScores(params);
        if (data.error) return;

        const container = document.getElementById('companies-list');
        if (container) {
            container.innerHTML = Components.companyTable(data.companies);
            // Count
            const countEl = document.getElementById('companies-count');
            if (countEl) countEl.textContent = `${data.count} companies`;
        }

        this.bindTableSort();
        this.bindFilters();
    },

    bindTableSort() {
        document.querySelectorAll('.data-table th[data-sort]').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sort;
                if (this.sortState.col === col) {
                    this.sortState.order = this.sortState.order === 'desc' ? 'asc' : 'desc';
                } else {
                    this.sortState.col = col;
                    this.sortState.order = 'desc';
                }
                this.loadCompanies();
            });
        });
    },

    bindFilters() {
        const sectorSel = document.getElementById('filter-sector');
        const riskSel = document.getElementById('filter-risk');
        if (sectorSel) {
            sectorSel.value = this.filters.sector;
            sectorSel.onchange = () => {
                this.filters.sector = sectorSel.value;
                this.loadCompanies();
            };
        }
        if (riskSel) {
            riskSel.value = this.filters.risk;
            riskSel.onchange = () => {
                this.filters.risk = riskSel.value;
                this.loadCompanies();
            };
        }
    },

    // ── Company Detail View ──────────────────────────────────────────

    async showCompany(ticker) {
        this.navigate('detail');
        this.showLoading(true);

        const [report, histData] = await Promise.all([
            API.getCompany(ticker),
            API.getHistory(ticker),
        ]);

        this.showLoading(false);
        if (report.error) {
            document.getElementById('detail-content').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state__icon">${Components.Icons.error}</div>
                    <div class="empty-state__title">${report.error}</div>
                </div>`;
            return;
        }

        // Header
        const hdr = document.getElementById('detail-header');
        if (hdr) {
            hdr.innerHTML = `
                <button class="back-btn" onclick="App.navigate('companies')">← Back to Companies</button>
                <div class="section-header">
                    <div>
                        <h1 class="section-header__title">${report.ticker} <span style="color:var(--text-muted);font-weight:400">${(report.sector || '').replace('_',' ')}</span></h1>
                        <div class="section-header__subtitle">Stress Report · Year ${report.year || ''}</div>
                    </div>
                    <div>${Components.badge(report.stress_score)}</div>
                </div>`;
        }

        // Gauge
        Charts.renderGauge('detail-gauge', report.stress_score, report.verdict?.replace(/\[.*?\]\s*/, ''));

        // Model components
        const modelsEl = document.getElementById('detail-models');
        if (modelsEl) modelsEl.innerHTML = Components.modelBars(report.components);

        // Ratios
        const ratiosEl = document.getElementById('detail-ratios');
        if (ratiosEl) ratiosEl.innerHTML = Components.ratioCards(report.ratios);

        // Red flags
        const flagsEl = document.getElementById('detail-flags');
        if (flagsEl) flagsEl.innerHTML = Components.flagsList(report.red_flags);

        // History chart
        if (histData && histData.history && histData.history.length > 0) {
            Charts.renderHistoryChart('chart-history', histData.history, ['altman_z', 'net_margin', 'current_ratio']);
        }
    },

    // ── Sectors View ─────────────────────────────────────────────────

    async loadSectors() {
        const data = await API.getSectors();
        if (data.error) return;

        const container = document.getElementById('sectors-content');
        if (container) {
            container.innerHTML = Components.sectorCards(data.sectors);
        }
    },

    // ── Live Scorer View ─────────────────────────────────────────────

    initLive() {
        const form = document.getElementById('live-form');
        const input = document.getElementById('live-ticker-input');
        const progress = document.getElementById('live-progress');
        const result = document.getElementById('live-result');

        if (form) {
            form.onsubmit = async (e) => {
                e.preventDefault();
                const ticker = input.value.trim().toUpperCase();
                if (!ticker) return;

                progress.classList.remove('hidden');
                result.innerHTML = '';

                const report = await API.getLive(ticker);
                progress.classList.add('hidden');

                if (report.error) {
                    result.innerHTML = `<div class="card mt-6"><div class="empty-state"><div class="empty-state__icon">${Components.Icons.error}</div><div class="empty-state__title">${report.error}</div></div></div>`;
                    return;
                }

                // Render same as company detail
                result.innerHTML = `
                    <div class="card mt-6">
                        <div class="section-header">
                            <div>
                                <h2 class="section-header__title">${report.ticker} <span style="color:var(--text-muted);font-weight:400">${(report.sector||'').replace('_',' ')}</span></h2>
                                <div class="section-header__subtitle">${report.live ? 'Live fetch from SEC EDGAR' : 'From dataset'} · Year ${report.year||''}</div>
                            </div>
                            <div>${Components.badge(report.stress_score)}</div>
                        </div>
                    </div>
                    <div class="charts-grid mt-6">
                        <div class="card">
                            <h3 style="margin-bottom:var(--space-4);color:var(--text-secondary)">Financial Ratios</h3>
                            ${Components.ratioCards(report.ratios)}
                        </div>
                        <div class="card">
                            <div id="live-gauge"></div>
                            <h3 style="margin:var(--space-4) 0;color:var(--text-secondary)">Model Components</h3>
                            ${Components.modelBars(report.components)}
                        </div>
                    </div>
                    ${report.history && report.history.length > 0 ? `
                    <div class="card mt-6">
                        <h3 style="margin-bottom:var(--space-4);color:var(--text-secondary)">Historical Trends (Live Fetch)</h3>
                        <div class="chart-container" style="height:300px"><canvas id="live-chart-history"></canvas></div>
                    </div>
                    ` : ''}
                    <div class="card mt-6">
                        <h3 style="margin-bottom:var(--space-4);color:var(--text-secondary)">Red Flags (${report.n_red_flags || 0})</h3>
                        ${Components.flagsList(report.red_flags)}
                    </div>`;

                Charts.renderGauge('live-gauge', report.stress_score, report.verdict?.replace(/\[.*?\]\s*/, ''));
                if (report.history && report.history.length > 0) {
                    Charts.renderHistoryChart('live-chart-history', report.history, ['altman_z', 'net_margin', 'current_ratio']);
                }
            };
        }
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
