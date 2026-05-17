# Fintellix Risk: Financial Intelligence & Risk Suite

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![ML Accuracy](https://img.shields.io/badge/AUC--ROC-92.5%25-green.svg)](https://github.com/Anjali-Mittal/Financial_Stress_Detection)
[![Precision](https://img.shields.io/badge/Precision-86.4%25-blue.svg)](https://github.com/Anjali-Mittal/Financial_Stress_Detection)

> A production-grade, AI-driven platform for real-time financial risk monitoring and stress detection in public companies.

---

## 📈 Platform Performance (Verified)

| Metric | Specification |
| :--- | :--- |
| **Model Accuracy** | **92.5% AUC-ROC** (XGBoost Ensemble) |
| **Precision** | **86.4%** in identifying high-risk distress candidates |
| **F1 Score** | **73.1%** (optimized for recall in risk detection) |
| **Backtested Data** | **172 Companies** across 10+ years of financial history |
| **Live Capability** | **5,000+** US Public Equities (NYSE/NASDAQ) |
| **Scoring Latency** | **<300ms** (Cached) \| **5-15s** (Live XBRL Fetch) |
| **Risk Signals** | **10+** Automated Heuristic Red-Flags |

---

## 🛠️ Core Capabilities

### 1. Multi-Stage ML Risk Engine
- **Ensemble Scoring**: Triangulated risk assessment using a weighted architecture:
    - **XGBoost Classifier (80%)**: Trained on 18 key financial features with **SMOTE** for class imbalance handling.
    - **Trend Analysis (10%)**: Heuristic engine detecting accelerating financial deterioration over 3+ years.
    - **Peer Clustering (10%)**: **K-Means + PCA** architecture to identify systemic risks and peer-group anomalies.
- **Sector-Adjusted Intelligence**: Custom logic for **Technology** and **Financial Services** that normalizes Altman Z-Scores (Z * 1.8) to account for high-leverage/high-growth balance sheet structures.

### 2. Live Data Pipeline (The "XBRL" Edge)
- **SEC EDGAR Integration**: Native **XBRL Parser** that fetches 10-K/10-Q filings directly from the SEC API for high-fidelity statement data.
- **Real-Time Fallbacks**: Seamless integration with **Yahoo Finance** for price action and metadata metadata.
- **Macro Context**: Integration with **FRED (Federal Reserve)** to inject macroeconomic indicators (e.g., interest rates, inflation) into the risk context.

### 3. Institutional Terminal (UI/UX)
- **Glassmorphism Design**: Dense, high-contrast "Dark Mode" interface inspired by Bloomberg/Refinitiv terminals.
- **Interactive Visuals**: Real-time **Chart.js** implementations for risk distribution, sector health, and historical trend analysis.
- **On-Demand Scorer**: Instant analysis of any ticker with live progress tracking (Fetch -> Parse -> Compute -> Score).

---

## 🚩 Automated Risk Detection (Red Flags)

The system automatically triggers alerts for 10+ critical financial anomalies:
- **Altman Z-Score**: Adjusted for sector; flags Distress (<1.81) and Grey (<3.0) zones.
- **Piotroski F-Score**: Flags weak financial strength (Score ≤ 3).
- **Liquidity Traps**: Current Ratio < 1.0 or Cash Flow Divergence.
- **Profitability Crises**: Negative Net Margins or declining Interest Coverage (< 1.5).
- **Leverage Risks**: Debt-to-Equity > 3.0 or excessive debt-to-EBITDA ratios.

---

## 🏗️ Technical Architecture

```bash
financial_stress/
├── dashboard/           # Production Flask Application
│   ├── server.py        # High-concurrency REST API
│   └── static/          # Modular CSS/JS (Variables-based UI)
├── backend_core/        # Core Analytical Engine
│   ├── engine/          # Scorer, Trend Predictor, & Live Pipeline
│   ├── features/        # XBRL Parsing & 20+ Financial Ratios
│   └── utils/           # SMOTE-ready training & logging
├── models/              # Serialized XGBoost & K-Means artifacts
├── data/                # 10-Year historical feature matrices
└── reports/             # Auto-generated analytical plots
```

---

## 🌐 Deployment & Integration

This platform is architected for production environments (e.g., **Render**, **AWS**, **GCP**). It uses a hybrid storage model where core ML artifacts are synced from **Hugging Face** during deployment for high availability.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Built with ❤️ by [Anjali Mittal](https://github.com/Anjali-Mittal)*

