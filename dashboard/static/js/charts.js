/**
 * charts.js — Fintellix Risk Suite
 * Rose / Sand / Green risk palette. Fragment Mono labels.
 */

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const Charts = {
    instances: {},

    get colors() {
        return {
            rose: '#c47a8a',
            sand: '#d4b483',
            green: '#4ade80',
            roseDim: 'rgba(196,122,138,0.5)',
            sandDim: 'rgba(212,180,131,0.45)',
            greenDim: 'rgba(74,222,128,0.45)',
            textPrimary: cssVar('--text-primary'),
            textSecondary: cssVar('--text-secondary'),
            textLabel: cssVar('--text-label'),
            divider: cssVar('--divider'),
            dividerRow: cssVar('--divider-row'),
            bgBase: cssVar('--bg-base'),
            bgElevated: cssVar('--bg-elevated'),
            // multi-series line chart palette
            line1: '#c47a8a',
            line2: '#4ade80',
            line3: '#d4b483',
            line4: '#7090c8',
            line5: '#a08cc8',
            line6: '#70b8b0',
            line7: '#c8a070',
        };
    },

    /**
     * Score → color
     * ≥75 rose (high/critical), ≥35 sand (moderate), <35 green (low)
     */
    getScoreColor(score) {
        if (score >= 75) return this.colors.rose;
        if (score >= 35) return this.colors.sand;
        return this.colors.green;
    },

    getScoreColorDim(score) {
        if (score >= 75) return this.colors.roseDim;
        if (score >= 35) return this.colors.sandDim;
        return this.colors.greenDim;
    },

    _tooltip() {
        return {
            backgroundColor: 'rgba(12, 12, 14, 0.97)',
            titleColor: '#e8e8ec',
            bodyColor: '#707070',
            borderColor: 'rgba(255,255,255,0.07)',
            borderWidth: 1,
            cornerRadius: 3,
            padding: 10,
            titleFont: { family: "'Fragment Mono', monospace", size: 10, weight: '400' },
            bodyFont: { family: "'Fragment Mono', monospace", size: 10 },
            displayColors: false,
        };
    },

    _tickStyle() {
        return {
            color: cssVar('--text-label'),
            font: { family: "'Fragment Mono', monospace", size: 9, weight: '400' },
        };
    },

    _destroy(id) {
        if (this.instances[id]) {
            this.instances[id].destroy();
            delete this.instances[id];
        }
    },

    /** Donut — risk distribution */
    renderRiskDonut(canvasId, data) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const c = this.colors;
        const total = (data.critical || 0) + (data.high || 0) + (data.moderate || 0) + (data.low || 0);

        this.instances[canvasId] = new Chart(el, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High', 'Moderate', 'Low'],
                datasets: [{
                    data: [data.critical || 0, data.high || 0, data.moderate || 0, data.low || 0],
                    backgroundColor: [c.rose, c.roseDim, c.sand, c.green],
                    borderColor: cssVar('--bg-base'),
                    borderWidth: 3,
                    hoverOffset: 4,
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
                            color: c.textLabel,
                            font: { family: "'Fragment Mono', monospace", size: 9 },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 5,
                        }
                    },
                    tooltip: this._tooltip(),
                }
            }
        });
    },

    /** Horizontal bars — sector avg stress */
    renderSectorBars(canvasId, sectors) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const labels = Object.keys(sectors);
        const values = Object.values(sectors);
        const barColors = values.map(v => this.getScoreColor(v));
        const barColorsDim = values.map(v => this.getScoreColorDim(v));

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: barColorsDim,
                    borderColor: barColors,
                    borderWidth: 0,
                    borderRadius: 2,
                    borderSkipped: false,
                    barThickness: 16,
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
                        grid: { color: 'rgba(255,255,255,0.025)', drawBorder: false },
                        ticks: this._tickStyle(),
                        min: 0,
                        border: { display: false },
                    },
                    y: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            color: cssVar('--text-secondary'),
                            font: { family: "'Bricolage Grotesque', sans-serif", size: 11, weight: '400' },
                        },
                    }
                }
            }
        });
    },

    /** Bar — score distribution */
    renderScoreDistribution(canvasId, companies) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const bins = Array(10).fill(0);
        const binLabels = ['0–10', '10–20', '20–30', '30–40', '40–50', '50–60', '60–70', '70–80', '80–90', '90–100'];

        companies.forEach(co => {
            const s = co.stress_score;
            if (s == null) return;
            bins[Math.min(Math.floor(s / 10), 9)]++;
        });

        const barColors = binLabels.map((_, i) => this.getScoreColorDim(i * 10 + 5));
        const borderColors = binLabels.map((_, i) => this.getScoreColor(i * 10 + 5));

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    label: 'Companies',
                    data: bins,
                    backgroundColor: barColors,
                    borderColor: borderColors,
                    borderWidth: 0,
                    borderRadius: 2,
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
                        border: { display: false },
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.025)', drawBorder: false },
                        border: { display: false },
                        ticks: this._tickStyle(),
                        beginAtZero: true,
                    }
                }
            }
        });
    },

    /** Line — historical trends */
    renderHistoryChart(canvasId, history, metrics) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el || !history || history.length === 0) return;

        const c = this.colors;
        const metricConfig = {
            altman_z: { label: 'Altman Z', color: c.line1 },
            net_margin: { label: 'Net Margin', color: c.line2 },
            current_ratio: { label: 'Current Ratio', color: c.line3 },
            debt_to_equity: { label: 'Debt/Equity', color: c.line4 },
            roa: { label: 'ROA', color: c.line5 },
            interest_coverage: { label: 'Int. Coverage', color: c.line6 },
            piotroski_f: { label: 'Piotroski F', color: c.line7 },
        };

        const labels = history.map(h => h.year);
        const datasets = (metrics || ['altman_z', 'net_margin', 'current_ratio']).map(m => {
            const cfg = metricConfig[m] || { label: m, color: c.textLabel };
            return {
                label: cfg.label,
                data: history.map(h => h[m] != null ? h[m] : null),
                borderColor: cfg.color,
                backgroundColor: cfg.color + '10',
                pointBackgroundColor: cfg.color,
                pointBorderColor: cssVar('--bg-base'),
                pointBorderWidth: 1.5,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 1.5,
                tension: 0.3,
                fill: false,
                spanGaps: true,
            };
        });

        this.instances[canvasId] = new Chart(el, {
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
                            color: c.textLabel,
                            font: { family: "'Fragment Mono', monospace", size: 9 },
                            usePointStyle: true,
                            pointStyleWidth: 5,
                            padding: 14,
                        }
                    },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.025)', drawBorder: false },
                        border: { display: false },
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.025)', drawBorder: false },
                        border: { display: false },
                        ticks: this._tickStyle(),
                    }
                }
            }
        });
    },

    /** SVG gauge */
    renderGauge(containerId, score, verdict) {
        const el = document.getElementById(containerId);
        if (!el) return;

        const s = score != null ? score : 0;
        const color = this.getScoreColor(s);
        const angle = (s / 100) * 180;
        const mono = "'Fragment Mono', monospace";
        const textLabel = cssVar('--text-label');
        const bgBase = cssVar('--bg-base');

        const needleX = 110 + 70 * Math.cos((180 - angle) * Math.PI / 180);
        const needleY = 120 - 70 * Math.sin((180 - angle) * Math.PI / 180);

        el.innerHTML = `
            <div class="gauge-container">
                <svg width="220" height="128" viewBox="0 0 220 128">
                    <defs>
                        <linearGradient id="gaugeGrad_${containerId}" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%"   stop-color="#4ade80"/>
                            <stop offset="45%"  stop-color="#d4b483"/>
                            <stop offset="100%" stop-color="#c47a8a"/>
                        </linearGradient>
                    </defs>
                    <path d="M 22 118 A 88 88 0 0 1 198 118"
                          fill="none"
                          stroke="rgba(255,255,255,0.05)"
                          stroke-width="8"
                          stroke-linecap="round"/>
                    <path d="M 22 118 A 88 88 0 0 1 198 118"
                          fill="none"
                          stroke="url(#gaugeGrad_${containerId})"
                          stroke-width="8"
                          stroke-linecap="round"
                          stroke-dasharray="${(angle / 180) * 276} 276"
                          style="transition: stroke-dasharray 1s cubic-bezier(0.4,0,0.2,1)"/>
                    <line x1="110" y1="118"
                          x2="${needleX}" y2="${needleY}"
                          stroke="${color}"
                          stroke-width="1.5"
                          stroke-linecap="round"/>
                    <circle cx="110" cy="118" r="3" fill="${color}"/>
                    <text x="110" y="98"
                          text-anchor="middle"
                          fill="${color}"
                          font-size="26"
                          font-weight="600"
                          font-family="${mono}">${s}</text>
                    <text x="110" y="116"
                          text-anchor="middle"
                          fill="${textLabel}"
                          font-size="7"
                          font-weight="400"
                          font-family="${mono}"
                          letter-spacing="0.1em">SCORE / 100</text>
                </svg>
                <div class="gauge__label" style="color:${color}">${verdict || ''}</div>
            </div>`;
    },
};