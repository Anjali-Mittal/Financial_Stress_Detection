/**
 * components.js — Reusable UI component builders
 */

const Components = {
    Icons: {
        companies: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V7l8-4v18"/><path d="M19 21V11l-6-4"/><path d="M9 9h1"/><path d="M9 13h1"/><path d="M9 17h1"/></svg>`,
        stress: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
        risk: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
        flag: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`,
        error: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
    },

    /** Get risk level from score */
    riskLevel(score) {
        if (score == null) return { level: 'unknown', label: 'N/A', css: 'info' };
        if (score >= 75) return { level: 'critical', label: 'CRITICAL', css: 'critical' };
        if (score >= 50) return { level: 'high', label: 'HIGH', css: 'high' };
        if (score >= 25) return { level: 'moderate', label: 'MOD', css: 'moderate' };
        return { level: 'low', label: 'LOW', css: 'low' };
    },

    /** Format number safely */
    fmt(v, decimals = 2) {
        if (v == null || v === '') return '—';
        const n = Number(v);
        if (isNaN(n)) return '—';
        return n.toFixed(decimals);
    },

    /** KPI card HTML */
    kpiCard(label, value, iconClass, colorClass, meta = '') {
        return `
        <div class="kpi-card">
            <div class="kpi-card__icon kpi-card__icon--${colorClass}">${iconClass}</div>
            <div class="kpi-card__label">${label}</div>
            <div class="kpi-card__value">${value}</div>
            ${meta ? `<div class="kpi-card__meta">${meta}</div>` : ''}
        </div>`;
    },

    /** Badge HTML */
    badge(score) {
        const r = this.riskLevel(score);
        return `<span class="badge badge--${r.css}"><span class="badge__dot"></span>${r.label}</span>`;
    },

    /** Company table row */
    tableRow(c) {
        const r = this.riskLevel(c.stress_score);
        const scoreColor = r.css === 'critical' ? 'text-danger' : r.css === 'high' ? 'text-warning' : r.css === 'low' ? 'text-success' : '';
        return `
        <tr data-ticker="${c.ticker}" onclick="App.showCompany('${c.ticker}')">
            <td class="ticker-cell">${c.ticker}</td>
            <td>${(c.sector || '').replace('_', ' ')}</td>
            <td class="score-cell ${scoreColor}">${this.fmt(c.stress_score, 1)}</td>
            <td>${this.badge(c.stress_score)}</td>
            <td>${c.n_red_flags || 0}</td>
            <td class="text-mono">${this.fmt(c.altman_z)}</td>
            <td class="text-mono">${this.fmt(c.net_margin, 4)}</td>
        </tr>`;
    },

    /** Full company table */
    companyTable(companies) {
        if (!companies || companies.length === 0) {
            return `<div class="empty-state"><div class="empty-state__icon">${this.Icons.companies}</div><div class="empty-state__title">No companies found</div></div>`;
        }
        return `
        <div class="data-table-wrapper">
            <table class="data-table" id="companies-table">
                <thead>
                    <tr>
                        <th data-sort="ticker">Ticker <span class="sort-arrow"></span></th>
                        <th data-sort="sector">Sector</th>
                        <th data-sort="stress_score">Score <span class="sort-arrow">▼</span></th>
                        <th>Risk</th>
                        <th data-sort="n_red_flags">Flags</th>
                        <th data-sort="altman_z">Altman Z</th>
                        <th data-sort="net_margin">Margin</th>
                    </tr>
                </thead>
                <tbody>${companies.map(c => this.tableRow(c)).join('')}</tbody>
            </table>
        </div>`;
    },

    /** Red flags list */
    flagsList(flags) {
        if (!flags || flags.length === 0) {
            return `<div style="color:var(--success);font-size:var(--text-sm);display:flex;align-items:center;gap:var(--space-2)">${this.Icons.check} No red flags triggered</div>`;
        }
        return `<ul class="flag-list">${flags.map(f => `
            <li class="flag-item ${f.severity === 'MODERATE' ? 'flag-item--moderate' : ''}">
                <span class="flag-item__severity flag-item__severity--${f.severity}">${f.severity}</span>
                <div>
                    <div class="flag-item__message">${f.message}</div>
                    <div class="flag-item__value">Value: ${this.fmt(f.value, 3)} | Threshold: ${f.threshold}</div>
                </div>
            </li>`).join('')}</ul>`;
    },

    /** Ratio cards grid */
    ratioCards(ratios) {
        if (!ratios) return '';
        const items = [
            { key: 'altman_z', label: 'Altman Z-Score', sub: ratios.altman_z_label },
            { key: 'altman_z_adjusted', label: 'Altman Z (Adj)', sub: 'Sector-adjusted' },
            { key: 'piotroski_f', label: 'Piotroski F', sub: ratios.piotroski_label, fmt: 0 },
            { key: 'current_ratio', label: 'Current Ratio', sub: 'Liquidity' },
            { key: 'interest_coverage', label: 'Interest Coverage', sub: 'Debt service' },
            { key: 'debt_to_equity', label: 'Debt / Equity', sub: 'Leverage' },
            { key: 'net_margin', label: 'Net Margin', sub: 'Profitability', fmt: 4 },
            { key: 'cf_divergence', label: 'CF Divergence', sub: 'Earnings quality', fmt: 4 },
        ];
        return `<div class="ratio-grid">${items.map(it => {
            const v = ratios[it.key];
            let colorClass = '';
            if (it.key === 'altman_z' && v != null) {
                colorClass = v > 3 ? 'text-success' : v > 1.81 ? 'text-warning' : 'text-danger';
            }
            if (it.key === 'piotroski_f' && v != null) {
                colorClass = v >= 7 ? 'text-success' : v >= 4 ? 'text-warning' : 'text-danger';
            }
            return `
            <div class="ratio-card">
                <div class="ratio-card__label">${it.label}</div>
                <div class="ratio-card__value ${colorClass}">${this.fmt(v, it.fmt != null ? it.fmt : 2)}</div>
                ${it.sub ? `<div class="ratio-card__sub">${it.sub}</div>` : ''}
            </div>`;
        }).join('')}</div>`;
    },

    /** Model component bars */
    modelBars(components) {
        if (!components) return '';
        const items = [
            { key: 'classifier', label: 'Classifier', weight: '80%' },
            { key: 'trend', label: 'Trend', weight: '10%' },
            { key: 'cluster', label: 'Cluster', weight: '10%' },
        ];
        return items.map(it => {
            const comp = components[it.key] || {};
            const score = comp.score != null ? comp.score : 0;
            const color = score >= 75 ? Charts.colors.red : score >= 50 ? Charts.colors.orange : score >= 25 ? Charts.colors.yellow : Charts.colors.green;
            return `
            <div class="model-bar">
                <div class="model-bar__label">${it.label} (${it.weight})</div>
                <div class="model-bar__track">
                    <div class="model-bar__fill" style="width:${Math.min(score, 100)}%;background:${color}"></div>
                </div>
                <div class="model-bar__value">${this.fmt(score, 1)}</div>
            </div>`;
        }).join('');
    },

    /** Top stressed mini-table for overview */
    topStressedTable(companies) {
        if (!companies || companies.length === 0) return '';
        return `
        <div class="data-table-wrapper">
            <table class="data-table">
                <thead><tr>
                    <th>Ticker</th><th>Sector</th><th>Score</th><th>Risk</th><th>Flags</th>
                </tr></thead>
                <tbody>${companies.map(c => `
                    <tr onclick="App.showCompany('${c.ticker}')" style="cursor:pointer">
                        <td class="ticker-cell">${c.ticker}</td>
                        <td>${(c.sector || '').replace('_', ' ')}</td>
                        <td class="score-cell">${this.fmt(c.stress_score, 1)}</td>
                        <td>${this.badge(c.stress_score)}</td>
                        <td>${c.n_red_flags || 0}</td>
                    </tr>`).join('')}</tbody>
            </table>
        </div>`;
    },

    /** Sector cards */
    sectorCards(sectors) {
        if (!sectors || sectors.length === 0) return '';
        return `<div class="sector-grid">${sectors.map(s => `
            <div class="sector-card">
                <div class="sector-card__name">${(s.sector || '').replace('_', ' ')}</div>
                <div class="sector-card__stats">
                    <div class="sector-card__stat"><span class="sector-card__stat-label">Companies</span><span class="sector-card__stat-value">${s.count || 0}</span></div>
                    <div class="sector-card__stat"><span class="sector-card__stat-label">Avg Stress</span><span class="sector-card__stat-value">${this.fmt(s.avg_stress, 1)}</span></div>
                    <div class="sector-card__stat"><span class="sector-card__stat-label">Altman Z (med)</span><span class="sector-card__stat-value">${this.fmt(s.altman_z_median)}</span></div>
                    <div class="sector-card__stat"><span class="sector-card__stat-label">Net Margin</span><span class="sector-card__stat-value">${this.fmt(s.net_margin_median, 3)}</span></div>
                    <div class="sector-card__stat"><span class="sector-card__stat-label">Current Ratio</span><span class="sector-card__stat-value">${this.fmt(s.current_ratio_median)}</span></div>
                    <div class="sector-card__stat"><span class="sector-card__stat-label">D/E (med)</span><span class="sector-card__stat-value">${this.fmt(s.debt_to_equity_median)}</span></div>
                </div>
            </div>`).join('')}</div>`;
    },
};
