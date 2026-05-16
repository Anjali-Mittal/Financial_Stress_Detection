/**
 * charts.js — Chart.js rendering for Fintellix Risk Suite
 * All chart creation and update logic.
 */

const Charts = {
    instances: {},
    colors: {
        blue: '#00f2ff', /* Cyber Cyan */
        cyan: '#22d3ee',
        indigo: '#818cf8',
        green: '#00ff9f', /* Matrix Green */
        yellow: '#faff00', /* Neon Yellow */
        orange: '#ff9d00',
        red: '#ff0055', /* Cyber Red */
        purple: '#bc13fe',
        muted: '#5e707a',
        border: 'rgba(0, 242, 255, 0.2)',
        card: 'rgba(10, 18, 26, 0.8)',
        bg: '#05080a',
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
        this.instances[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High', 'Moderate', 'Low'],
                datasets: [{
                    data: [data.critical || 0, data.high || 0, data.moderate || 0, data.low || 0],
                    backgroundColor: [this.colors.red, this.colors.orange, this.colors.yellow, this.colors.green],
                    borderColor: this.colors.card,
                    borderWidth: 3,
                    hoverBorderColor: this.colors.bg,
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
                            color: '#94a3b8',
                            font: { family: 'Inter', size: 12 },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 8,
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(10, 18, 26, 0.95)',
                        titleColor: '#00f2ff',
                        bodyColor: '#e2f3f5',
                        borderColor: '#00f2ff',
                        borderWidth: 1,
                        cornerRadius: 2,
                        padding: 12,
                        titleFont: { family: 'JetBrains Mono', size: 13, weight: '800' },
                        bodyFont: { family: 'JetBrains Mono', size: 12 },
                    }
                }
            }
        });
    },

    /** Horizontal bar chart for sector stress */
    renderSectorBars(canvasId, sectors) {
        this._destroy(canvasId);
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        const labels = Object.keys(sectors);
        const values = Object.values(sectors);
        const barColors = values.map(v =>
            v >= 40 ? this.colors.red : v >= 30 ? this.colors.orange : v >= 27 ? this.colors.yellow : this.colors.green
        );

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: barColors,
                    borderRadius: 6,
                    borderSkipped: false,
                    barThickness: 28,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(10, 18, 26, 0.95)',
                        titleColor: '#00f2ff',
                        bodyColor: '#e2f3f5',
                        borderColor: '#00f2ff',
                        borderWidth: 1,
                        cornerRadius: 2,
                        padding: 12,
                        titleFont: { family: 'JetBrains Mono', size: 13, weight: '800' },
                        bodyFont: { family: 'JetBrains Mono', size: 12 },
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(0, 242, 255, 0.05)', drawBorder: false },
                        ticks: { color: '#5e707a', font: { family: 'JetBrains Mono', size: 10 } },
                        min: 20,
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: '#00f2ff', font: { family: 'JetBrains Mono', size: 11, weight: '700' } },
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

        const bins = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        const binLabels = ['0-10', '10-20', '20-30', '30-40', '40-50', '50-60', '60-70', '70-80', '80-90', '90-100'];
        companies.forEach(c => {
            const s = c.stress_score;
            if (s == null) return;
            const idx = Math.min(Math.floor(s / 10), 9);
            bins[idx]++;
        });

        const barColors = binLabels.map((_, i) => {
            if (i < 3) return this.colors.green;
            if (i < 5) return this.colors.yellow;
            if (i < 7) return this.colors.orange;
            return this.colors.red;
        });

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    label: 'Companies',
                    data: bins,
                    backgroundColor: barColors,
                    borderRadius: 4,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(10, 18, 26, 0.95)',
                        titleColor: '#00f2ff',
                        bodyColor: '#e2f3f5',
                        borderColor: '#00f2ff',
                        borderWidth: 1,
                        cornerRadius: 2,
                        padding: 12,
                        titleFont: { family: 'JetBrains Mono', size: 13, weight: '800' },
                        bodyFont: { family: 'JetBrains Mono', size: 12 },
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
                        title: { display: true, text: 'Stress Score Range', color: '#64748b', font: { family: 'Inter', size: 12 } }
                    },
                    y: {
                        grid: { color: '#1e293b', drawBorder: false },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 11 }, stepSize: 1 },
                        title: { display: true, text: 'Count', color: '#64748b', font: { family: 'Inter', size: 12 } },
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

        const metricConfig = {
            altman_z:          { label: 'Altman Z',          color: this.colors.blue },
            net_margin:        { label: 'Net Margin',        color: this.colors.cyan },
            current_ratio:     { label: 'Current Ratio',     color: this.colors.green },
            debt_to_equity:    { label: 'Debt/Equity',       color: this.colors.orange },
            roa:               { label: 'ROA',               color: this.colors.purple },
            interest_coverage: { label: 'Interest Coverage', color: this.colors.yellow },
            piotroski_f:       { label: 'Piotroski F',       color: this.colors.indigo },
        };

        const labels = history.map(h => h.year);
        const datasets = (metrics || ['altman_z', 'net_margin']).map(m => {
            const cfg = metricConfig[m] || { label: m, color: this.colors.muted };
            return {
                label: cfg.label,
                data: history.map(h => h[m] != null ? h[m] : null),
                borderColor: cfg.color,
                backgroundColor: cfg.color + '20',
                pointBackgroundColor: cfg.color,
                pointBorderColor: this.colors.card,
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2.5,
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
                            color: '#94a3b8',
                            font: { family: 'Inter', size: 11 },
                            usePointStyle: true,
                            pointStyleWidth: 8,
                            padding: 16,
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(10, 18, 26, 0.95)',
                        titleColor: '#00f2ff',
                        bodyColor: '#e2f3f5',
                        borderColor: '#00f2ff',
                        borderWidth: 1,
                        cornerRadius: 2,
                        padding: 12,
                        titleFont: { family: 'JetBrains Mono', size: 13, weight: '800' },
                        bodyFont: { family: 'JetBrains Mono', size: 12 },
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(0, 242, 255, 0.05)', drawBorder: false },
                        ticks: { color: '#5e707a', font: { family: 'JetBrains Mono', size: 10 } },
                    },
                    y: {
                        grid: { color: 'rgba(0, 242, 255, 0.05)', drawBorder: false },
                        ticks: { color: '#5e707a', font: { family: 'JetBrains Mono', size: 10 } },
                    }
                }
            }
        });
    },

    /** SVG gauge for stress score */
    renderGauge(containerId, score, verdict) {
        const el = document.getElementById(containerId);
        if (!el) return;

        const s = score != null ? score : 0;
        const color = s >= 75 ? this.colors.red : s >= 50 ? this.colors.orange : s >= 25 ? this.colors.yellow : this.colors.green;
        const angle = (s / 100) * 180;

        el.innerHTML = `
            <div class="gauge-container">
                <svg width="220" height="130" viewBox="0 0 220 130">
                    <defs>
                        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="${this.colors.green}"/>
                            <stop offset="33%" stop-color="${this.colors.yellow}"/>
                            <stop offset="66%" stop-color="${this.colors.orange}"/>
                            <stop offset="100%" stop-color="${this.colors.red}"/>
                        </linearGradient>
                    </defs>
                    <!-- Background arc -->
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="#1e293b" stroke-width="14" stroke-linecap="round"/>
                    <!-- Value arc -->
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="url(#gaugeGrad)" stroke-width="14" stroke-linecap="round"
                          stroke-dasharray="${angle / 180 * 283} 283"
                          style="transition: stroke-dasharray 1s ease"/>
                    <!-- Needle -->
                    <line x1="110" y1="120" x2="${110 + 70 * Math.cos((180 - angle) * Math.PI / 180)}" y2="${120 - 70 * Math.sin((180 - angle) * Math.PI / 180)}"
                          stroke="${color}" stroke-width="3" stroke-linecap="round"/>
                    <circle cx="110" cy="120" r="6" fill="${color}"/>
                    <!-- Score text -->
                    <text x="110" y="105" text-anchor="middle" fill="${color}" font-size="36" font-weight="800" font-family="Inter">${s}</text>
                    <text x="110" y="125" text-anchor="middle" fill="#64748b" font-size="11" font-family="Inter">/ 100</text>
                </svg>
                <div class="gauge__label" style="color: ${color}">${verdict || ''}</div>
            </div>`;
    },
};
