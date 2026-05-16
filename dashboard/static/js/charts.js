/**
 * charts.js — Premium Financial Intelligence Terminal
 * Dynamic Chart.js integration for Fintellix Risk Suite
 */

// Helper to read CSS theme variables
function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const Charts = {
    instances: {},

    /**
     * Theme-aware colors derived from variables.css
     */
    get colors() {
        return {
            accent: cssVar('--accent'),
            accentBright: cssVar('--accent-bright'),
            success: cssVar('--success'),
            warning: cssVar('--warning'),
            danger: cssVar('--danger'),
            orange: cssVar('--orange'),
            textPrimary: cssVar('--text-primary'),
            textSecondary: cssVar('--text-secondary'),
            textMuted: cssVar('--text-muted'),
            border: cssVar('--border'),
            bgElevated: cssVar('--bg-elevated'),
            bgCard: cssVar('--bg-card'),
            bgBase: cssVar('--bg-base'),
            // Extended palette
            blue: '#3b82f6',
            indigo: '#6366f1',
            purple: '#8b5cf6',
        };
    },

    /**
     * Map a stress score to its semantic color
     * Optimized: Scores 25-45 use Cyan (Accent) instead of Yellow
     */
    getScoreColor(score) {
        const c = this.colors;
        if (score >= 75) return c.danger;
        if (score >= 45) return c.orange;
        if (score >= 25) return c.accent; // Cyan dominant "safe-moderate" range
        return c.success;
    },

    _tooltip() {
        const mono = cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim();
        return {
            backgroundColor: 'rgba(9, 18, 32, 0.95)',
            titleColor: cssVar('--accent'),
            bodyColor: cssVar('--text-primary'),
            borderColor: cssVar('--border-bright'),
            borderWidth: 1,
            cornerRadius: 4,
            padding: 12,
            titleFont: { family: mono, size: 11, weight: '700' },
            bodyFont: { family: mono, size: 11 },
            displayColors: false,
        };
    },

    _tickStyle(isMono = true) {
        const font = isMono ? cssVar('--font-mono') : cssVar('--font-sans');
        return {
            color: cssVar('--text-muted'),
            font: { 
                family: font.split(',')[0].replace(/['"]/g, '').trim(), 
                size: 10,
                weight: '500'
            },
        };
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
        const el = document.getElementById(canvasId);
        if (!el) return;

        const c = this.colors;
        this.instances[canvasId] = new Chart(el, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High', 'Moderate', 'Low'],
                datasets: [{
                    data: [data.critical || 0, data.high || 0, data.moderate || 0, data.low || 0],
                    backgroundColor: [c.danger, c.orange, c.accent, c.success],
                    borderColor: c.bgCard,
                    borderWidth: 4,
                    hoverOffset: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: c.textSecondary,
                            font: { family: cssVar('--font-mono').split(',')[0].replace(/['"]/g, ''), size: 9 },
                            padding: 20,
                            usePointStyle: true,
                            pointStyleWidth: 6,
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
        const el = document.getElementById(canvasId);
        if (!el) return;

        const labels = Object.keys(sectors);
        const values = Object.values(sectors);
        const barColors = values.map(v => this.getScoreColor(v));

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: barColors,
                    borderRadius: 3,
                    borderSkipped: false,
                    barThickness: 20,
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
                        grid: { color: cssVar('--border-panel'), drawBorder: false },
                        ticks: this._tickStyle(),
                        min: 20,
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            color: cssVar('--text-secondary'),
                            font: { family: cssVar('--font-sans').split(',')[0].replace(/['"]/g, ''), size: 11, weight: '600' },
                        },
                    }
                }
            }
        });
    },

    /** Bar chart for score distribution */
    renderScoreDistribution(canvasId, companies) {
        this._destroy(canvasId);
        const el = document.getElementById(canvasId);
        if (!el) return;

        const bins = Array(10).fill(0);
        const binLabels = ['0-10', '10-20', '20-30', '30-40', '40-50', '50-60', '60-70', '70-80', '80-90', '90-100'];
        
        companies.forEach(co => {
            const s = co.stress_score;
            if (s == null) return;
            const idx = Math.min(Math.floor(s / 10), 9);
            bins[idx]++;
        });

        // Use getScoreColor for each bin center
        const barColors = binLabels.map((_, i) => this.getScoreColor(i * 10 + 5));

        this.instances[canvasId] = new Chart(el, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    label: 'Companies',
                    data: bins,
                    backgroundColor: barColors,
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
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: cssVar('--border-panel'), drawBorder: false },
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
        const el = document.getElementById(canvasId);
        if (!el || !history || history.length === 0) return;

        const c = this.colors;
        const metricConfig = {
            altman_z: { label: 'Altman Z', color: c.accentBright },
            net_margin: { label: 'Net Margin', color: '#10b981' },
            current_ratio: { label: 'Current Ratio', color: '#8b5cf6' },
            debt_to_equity: { label: 'Debt/Equity', color: '#f59e0b' },
            roa: { label: 'ROA', color: '#ec4899' },
            interest_coverage: { label: 'Interest Coverage', color: '#6366f1' },
            piotroski_f: { label: 'Piotroski F', color: '#14b8a6' },
        };

        const labels = history.map(h => h.year);
        const datasets = (metrics || ['altman_z', 'net_margin', 'current_ratio']).map(m => {
            const cfg = metricConfig[m] || { label: m, color: c.textMuted };
            return {
                label: cfg.label,
                data: history.map(h => h[m] != null ? h[m] : null),
                borderColor: cfg.color,
                backgroundColor: cfg.color + '10',
                pointBackgroundColor: cfg.color,
                pointBorderColor: c.bgCard,
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2,
                tension: 0.35,
                fill: true,
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
                            color: c.textSecondary,
                            font: { family: cssVar('--font-mono').split(',')[0].replace(/['"]/g, ''), size: 9 },
                            usePointStyle: true,
                            pointStyleWidth: 5,
                            padding: 15,
                        }
                    },
                    tooltip: this._tooltip(),
                },
                scales: {
                    x: {
                        grid: { color: cssVar('--border-panel'), drawBorder: false },
                        ticks: this._tickStyle(),
                    },
                    y: {
                        grid: { color: cssVar('--border-panel'), drawBorder: false },
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
        
        const s = score != null ? score : 0;
        const color = this.getScoreColor(s);
        const angle = (s / 100) * 180;
        const mono = cssVar('--font-mono').split(',')[0].replace(/['"]/g, '').trim();

        el.innerHTML = `
            <div class="gauge-container">
                <svg width="220" height="130" viewBox="0 0 220 130">
                    <defs>
                        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%"   stop-color="${this.colors.success}"/>
                            <stop offset="35%"  stop-color="${this.colors.accent}"/>
                            <stop offset="65%"  stop-color="${this.colors.orange}"/>
                            <stop offset="100%" stop-color="${this.colors.danger}"/>
                        </linearGradient>
                    </defs>
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="${cssVar('--bg-subtle')}" stroke-width="12" stroke-linecap="round"/>
                    <path d="M 20 120 A 90 90 0 0 1 200 120" fill="none" stroke="url(#gaugeGrad)" stroke-width="12" stroke-linecap="round"
                          stroke-dasharray="${angle / 180 * 283} 283"
                          style="transition: stroke-dasharray 1.2s cubic-bezier(0.4, 0, 0.2, 1)"/>
                    <line x1="110" y1="120"
                          x2="${110 + 72 * Math.cos((180 - angle) * Math.PI / 180)}"
                          y2="${120 - 72 * Math.sin((180 - angle) * Math.PI / 180)}"
                          stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
                    <circle cx="110" cy="120" r="4" fill="${color}"/>
                    <text x="110" y="102" text-anchor="middle" fill="${color}" font-size="28" font-weight="700" font-family="${mono}">${s}</text>
                    <text x="110" y="122" text-anchor="middle" fill="${cssVar('--text-muted')}" font-size="8" font-weight="600" font-family="${mono}">SCORE / 100</text>
                </svg>
                <div class="gauge__label" style="color:${color}">${verdict || ''}</div>
            </div>`;
    },
};