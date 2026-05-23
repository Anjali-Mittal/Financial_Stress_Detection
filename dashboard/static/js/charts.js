/**
 * charts.js — Fintellix Risk Suite
 */

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const Charts = {
    instances: {},

    colors: {
        rose: '#e07088',
        sand: '#e0a060',
        green: '#50c878',
        blue: '#4f8ef7',
        line1: '#4f8ef7',
        line2: '#e07088',
        line3: '#e0a060',
        line4: '#a78bfa',
        line5: '#34d399',
        line6: '#f59e0b',
        line7: '#60a5fa',
    },

    _tooltip() {
        return {
            backgroundColor: '#1c2333',
            titleColor: '#e8eaf0',
            bodyColor: '#9ba3b8',
            borderColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            cornerRadius: 6,
            padding: 12,
            titleFont: { family: "'Inter', sans-serif", size: 12, weight: '500' },
            bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
            displayColors: false,
        };
    },

    _ticks() {
        return {
            color: '#6b7490',
            font: { family: "'JetBrains Mono', monospace", size: 11 },
        };
    },

    _destroy(id) {
        if (this.instances[id]) { this.instances[id].destroy(); delete this.instances[id]; }
    },

    /* ── Donut ── */
    renderRiskDonut(canvasId, data) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const total = (data.critical || 0) + (data.high || 0) + (data.moderate || 0) + (data.low || 0);

        this.instances[canvasId] = new Chart(el, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High', 'Moderate', 'Low'],
                datasets: [{
                    data: [data.critical || 0, data.high || 0, data.moderate || 0, data.low || 0],
                    backgroundColor: ['#e07088', '#a84455', '#e0a060', '#4f8ef7'],
                    borderColor: '#0f1117',
                    borderWidth: 3,
                    hoverOffset: 6,
                }]
            },
            plugins: [{
                id: 'centerText',
                afterDraw(chart) {
                    const { ctx, chartArea: { left, right, top, bottom } } = chart;
                    const cx = (left + right) / 2;
                    const cy = (top + bottom) / 2;
                    ctx.save();
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.font = "700 28px 'Inter', sans-serif";
                    ctx.fillStyle = '#e8eaf0';
                    ctx.fillText(total, cx, cy - 10);
                    ctx.font = "400 10px 'JetBrains Mono', monospace";
                    ctx.fillStyle = '#6b7490';
                    ctx.fillText('COMPANIES', cx, cy + 12);
                    ctx.restore();
                }
            }],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#9ba3b8',
                            font: { family: "'JetBrains Mono', monospace", size: 11 },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 8,
                        }
                    },
                    tooltip: {
                        ...this._tooltip(),
                        callbacks: {
                            label: (ctx) => {
                                const pct = total ? ((ctx.raw / total) * 100).toFixed(1) : '0.0';
                                return ` ${ctx.raw} companies (${pct}%)`;
                            }
                        }
                    },
                }
            }
        });
    },

    /* ── Sector Bars — blue accent, opacity = relative stress ── */
    renderSectorBars(canvasId, sectors) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const labels = Object.keys(sectors).map(l => l.replace('_', ' '));
        const values = Object.values(sectors);
        const max = Math.max(...values, 1);

        const bg = v => `rgba(79,142,247,${(0.3 + (v / max) * 0.7).toFixed(2)})`;
        const border = v => `rgba(79,142,247,${(0.5 + (v / max) * 0.5).toFixed(2)})`;

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: values.map(v => bg(v)),
                    borderColor: values.map(v => border(v)),
                    borderWidth: 1,
                    borderRadius: 4,
                    borderSkipped: false,
                    barThickness: 18,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        ...this._tooltip(),
                        callbacks: { label: ctx => ` avg stress: ${Number(ctx.raw).toFixed(1)}` }
                    },
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        border: { display: false },
                        ticks: this._ticks(),
                        min: 0,
                    },
                    y: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            color: '#9ba3b8',
                            font: { family: "'Inter', sans-serif", size: 12, weight: '500' },
                        },
                    }
                }
            }
        });
    },

    /* ── Score Distribution ── */
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

        // Blue → amber → rose as risk increases
        const color = i => {
            const mid = i * 10 + 5;
            if (mid >= 50) return '#e07088';
            if (mid >= 30) return '#e0a060';
            return '#4f8ef7';
        };

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    data: bins,
                    backgroundColor: bins.map((v, i) => v === 0 ? 'rgba(255,255,255,0.04)' : color(i)),
                    borderWidth: 0,
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
                        ...this._tooltip(),
                        callbacks: { label: ctx => ` ${ctx.raw} companies` },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: this._ticks(),
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        border: { display: false },
                        ticks: this._ticks(),
                        beginAtZero: true,
                    }
                }
            }
        });
    },

    /* ── History Line ── */
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

        const datasets = (metrics || ['altman_z', 'net_margin', 'current_ratio']).map(m => {
            const cfg = metricConfig[m] || { label: m, color: '#6b7490' };
            return {
                label: cfg.label,
                data: history.map(h => h[m] ?? null),
                borderColor: cfg.color,
                backgroundColor: cfg.color + '18',
                pointBackgroundColor: cfg.color,
                pointBorderColor: '#0f1117',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2,
                tension: 0.3,
                fill: false,
                spanGaps: true,
            };
        });

        this.instances[canvasId] = new Chart(el, {
            type: 'line',
            data: { labels: history.map(h => h.year), datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'top', align: 'end',
                        labels: {
                            color: '#9ba3b8',
                            font: { family: "'JetBrains Mono', monospace", size: 11 },
                            usePointStyle: true, pointStyleWidth: 8, padding: 16,
                        }
                    },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.04)' }, border: { display: false }, ticks: this._ticks() },
                    y: { grid: { color: 'rgba(255,255,255,0.04)' }, border: { display: false }, ticks: this._ticks() },
                }
            }
        });
    },

    /* ── Gauge ── */
    renderGauge(containerId, score, verdict) {
        const el = document.getElementById(containerId);
        if (!el) return;

        const s = Math.max(0, Math.min(100, score ?? 0));
        const color = s >= 50 ? '#e07088' : s >= 35 ? '#e0a060' : '#4f8ef7';
        const angle = (s / 100) * 180;
        const rad = (180 - angle) * Math.PI / 180;
        const cx = 150, cy = 150, r = 110;
        const nx = (cx + r * Math.cos(rad)).toFixed(2);
        const ny = (cy - r * Math.sin(rad)).toFixed(2);
        // arc path: radius 110, center 150,150
        const arcLen = Math.PI * 110; // semicircle = 345.4
        const filled = ((angle / 180) * arcLen).toFixed(2);
        const sans = "'Inter', sans-serif";
        const mono = "'JetBrains Mono', monospace";

        el.innerHTML = `
            <div class="gauge-container" style="padding: 16px 0 8px;">
                <svg width="300" height="180" viewBox="0 0 300 180">
                    <defs>
                        <linearGradient id="gg_${containerId}" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%"   stop-color="#4f8ef7"/>
                            <stop offset="50%"  stop-color="#e0a060"/>
                            <stop offset="100%" stop-color="#e07088"/>
                        </linearGradient>
                    </defs>
                    <!-- track -->
                    <path d="M 40 150 A 110 110 0 0 1 260 150"
                          fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="12" stroke-linecap="round"/>
                    <!-- fill -->
                    <path d="M 40 150 A 110 110 0 0 1 260 150"
                          fill="none" stroke="url(#gg_${containerId})" stroke-width="12" stroke-linecap="round"
                          stroke-dasharray="${filled} ${arcLen}"
                          style="transition:stroke-dasharray 1s cubic-bezier(0.4,0,0.2,1)"/>
                    <!-- needle -->
                    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}"
                          stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
                    <circle cx="${cx}" cy="${cy}" r="6" fill="${color}"/>
                    <circle cx="${cx}" cy="${cy}" r="3" fill="#0f1117"/>
                    <!-- score -->
                    <text x="${cx}" y="${cy - 20}"
                          text-anchor="middle" fill="${color}"
                          font-size="42" font-weight="700"
                          font-family="${sans}" letter-spacing="-0.04em">${s.toFixed(1)}</text>
                    <text x="${cx}" y="${cy - 2}"
                          text-anchor="middle" fill="#6b7490"
                          font-size="10" font-family="${mono}" letter-spacing="0.16em">SCORE / 100</text>
                </svg>
                <div class="gauge__label" style="color:${color};font-size:12px;letter-spacing:0.2em;font-family:${mono};margin-top:4px">${verdict || ''}</div>
            </div>`;
    },
};