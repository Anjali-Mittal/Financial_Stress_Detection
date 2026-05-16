/**
 * charts.js — Chart.js rendering for Fintellix Risk Suite
 * All chart creation and update logic.
 */

// Read CSS variables at runtime so charts always match the theme
function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const Charts = {
    instances: {},

    get colors() {
        return {
            blue: '#6fa3d0',
            cyan: cssVar('--accent'),
            indigo: '#818cf8',
            green: cssVar('--success'),
            yellow: cssVar('--warning'),
            orange: cssVar('--orange'),
            red: cssVar('--danger'),
            purple: '#a78bfa',
            muted: cssVar('--text-muted'),
            border: cssVar('--border'),
            card: cssVar('--bg-card'),
            bg: cssVar('--bg-base'),
        };
    },

    // Shared tooltip style — reads CSS vars live
    _tooltip() {
        return {
            backgroundColor: cssVar('--bg-elevated'),
            titleColor: cssVar('--accent'),
            bodyColor: cssVar('--text-primary'),
            borderColor: cssVar('--border-mid'),
            borderWidth: 1,
            cornerRadius: 4,
            padding: 10,
            titleFont: { family: cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim(), size: 11, weight: '600' },
            bodyFont: { family: cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim(), size: 11 },
        };
    },

    _tickStyle() {
        return {
            color: cssVar('--text-muted'),
            font: { family: cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim(), size: 10 },
        };
    },

    _gridColor() {
        return cssVar('--border');
    },

    _destroy(id) {
        if (this.instances[id]) {
            this.instances[id].destroy();
            delete this.instances[id];
        }
    },

    /** Donut chart for risk distribution */
    renderRiskDonut(canvasId, data) {
        this._destroy(canvasId);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        const c = this.colors;
        this.instances[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High', 'Moderate', 'Low'],
                datasets: [{
                    data: [data.critical || 0, data.high || 0, data.moderate || 0, data.low || 0],
                    backgroundColor: [c.red, c.orange, c.yellow, c.green],
                    borderColor: c.card,
                    borderWidth: 3,
                    hoverBorderColor: c.bg,
                    hoverOffset: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: cssVar('--text-secondary'),
                            font: { family: cssVar('--font-sans').split(',')[0].replace(/['"]/g, '').trim(), size: 11 },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 7,
                        }
                    },
                    tooltip: this._tooltip(),
                }
            }
        });
    },

    /** Horizontal bar chart for sector stress */
    renderSectorBars(canvasId, sectors) {
        this._destroy(canvasId);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        const c = this.colors;
        const labels = Object.keys(sectors);
        const values = Object.values(sectors);
        const barColors = values.map(v =>
            v >= 40 ? c.red : v >= 30 ? c.orange : v >= 27 ? c.yellow : c.green
        );

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: barColors,
                    borderRadius: 4,
                    borderSkipped: false,
                    barThickness: 24,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: {
                        grid: { color: this._gridColor(), drawBorder: false },
                        ticks: this._tickStyle(),
                        min: 20,
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            color: cssVar('--text-secondary'),
                            font: { family: cssVar('--font-sans').split(',')[0].replace(/['"]/g, '').trim(), size: 11, weight: '500' },
                        },
                    }
                }
            }
        });
    },

    /** Bar chart for score distribution */
    renderScoreDistribution(canvasId, companies) {
        this._destroy(canvasId);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        const c = this.colors;
        const bins = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        const binLabels = ['0-10', '10-20', '20-30', '30-40', '40-50', '50-60', '60-70', '70-80', '80-90', '90-100'];
        companies.forEach(co => {
            const s = co.stress_score;
            if (s == null) return;
            const idx = Math.min(Math.floor(s / 10), 9);
            bins[idx]++;
        });

        const barColors = binLabels.map((_, i) => {
            if (i < 3) return c.green;
            if (i < 5) return c.yellow;
            if (i < 7) return c.orange;
            return c.red;
        });

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    label: 'Companies',
                    data: bins,
                    backgroundColor: barColors,
                    borderRadius: 3,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: this._gridColor(), drawBorder: false },
                        ticks: this._tickStyle(),
                        beginAtZero: true,
                    }
                }
            }
        });
    },

    /** Line chart for historical trends */
    renderHistoryChart(canvasId, history, metrics) {
        this._destroy(canvasId);
        const ctx = document.getElementById(canvasId);
        if (!ctx || !history || history.length === 0) return;
        const c = this.colors;

        const metricConfig = {
            altman_z: { label: 'Altman Z', color: c.blue },
            net_margin: { label: 'Net Margin', color: c.cyan },
            current_ratio: { label: 'Current Ratio', color: c.green },
            debt_to_equity: { label: 'Debt/Equity', color: c.orange },
            roa: { label: 'ROA', color: c.purple },
            interest_coverage: { label: 'Interest Coverage', color: c.yellow },
            piotroski_f: { label: 'Piotroski F', color: c.indigo },
        };

        const labels = history.map(h => h.year);
        const datasets = (metrics || ['altman_z', 'net_margin']).map(m => {
            const cfg = metricConfig[m] || { label: m, color: c.muted };
            return {
                label: cfg.label,
                data: history.map(h => h[m] != null ? h[m] : null),
                borderColor: cfg.color,
                backgroundColor: cfg.color + '18',
                pointBackgroundColor: cfg.color,
                pointBorderColor: c.card,
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2,
                tension: 0.3,
                fill: false,
                spanGaps: true,
            };
        });

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'end',
                        labels: {
                            color: cssVar('--text-secondary'),
                            font: { family: cssVar('--font-sans').split(',')[0].replace(/['"]/g, '').trim(), size: 11 },
                            usePointStyle: true,
                            pointStyleWidth: 7,
                            padding: 14,
                        }
                    },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: {
                        grid: { color: this._gridColor(), drawBorder: false },
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: this._gridColor(), drawBorder: false },
                        ticks: this._tickStyle(),
                    }
                }
            }
        });
    },

    /** SVG gauge for stress score */
    renderGauge(containerId, score, verdict) {
        const el = document.getElementById(containerId);
        if (!el) return;
        const c = this.colors;
        const s = score != null ? score : 0;
        const color = s >= 75 ? c.red : s >= 50 ? c.orange : s >= 25 ? c.yellow : c.green;
        const angle = (s / 100) * 180;
        const monoFont = cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim();

        el.innerHTML = `
            <div class="gauge-container">
                <svg width="220" height="130" viewBox="0 0 220 130">
                    <defs>
                        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%"   stop-color="${c.green}"/>
                            <stop offset="33%"  stop-color="${c.yellow}"/>
                            <stop offset="66%"  stop-color="${c.orange}"/>
                            <stop offset="100%" stop-color="${c.red}"/>
                        </linearGradient>
                    </defs>
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="${cssVar('--bg-elevated')}" stroke-width="14" stroke-linecap="round"/>
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="url(#gaugeGrad)" stroke-width="14" stroke-linecap="round"
                          stroke-dasharray="${angle / 180 * 283} 283"
                          style="transition: stroke-dasharray 1s ease"/>
                    <line x1="110" y1="120"
                          x2="${110 + 70 * Math.cos((180 - angle) * Math.PI / 180)}"
                          y2="${120 - 70 * Math.sin((180 - angle) * Math.PI / 180)}"
                          stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
                    <circle cx="110" cy="120" r="5" fill="${color}"/>
                    <text x="110" y="104" text-anchor="middle" fill="${color}" font-size="30" font-weight="600" font-family="${monoFont}">${s}</text>
                    <text x="110" y="124" text-anchor="middle" fill="${cssVar('--text-muted')}" font-size="9" font-family="${monoFont}">/ 100</text>
                </svg>
                <div class="gauge__label" style="color:${color}">${verdict || ''}</div>
            </div>`;
    },
};