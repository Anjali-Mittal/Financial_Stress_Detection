# 🛡️ FinStress: Financial Stress Early Warning System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/backend-Flask-lightgrey.svg)](https://flask.palletsprojects.com/)
[![JS](https://img.shields.io/badge/frontend-Vanilla%20JS-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

> A sophisticated, AI-driven platform for real-time financial risk monitoring and stress detection in public companies.

---

## 🌟 Overview

**FinStress** (Financial Stress Early Warning System) is a production-grade analytical platform designed to identify corporate financial distress before it becomes critical. By leveraging multi-stage machine learning models and real-time financial data, the system provides investors and analysts with a "Stress Score" (0–100) that quantifies risk levels with high precision.

The project features a high-performance **Flask REST API** backend and a sleek, **dark-themed interactive dashboard** for visual data exploration.

---

## 🚀 Key Features

### 📊 1. Executive Dashboard
- **System-Wide KPIs**: Instant visibility into total companies tracked, average market stress, and critical risk counts.
- **Risk Distribution**: Interactive visualizations (Bar/Donut charts) showing the health of the entire portfolio.
- **Sector Analysis**: Comparative health metrics across different industries.

### 🔍 2. Deep-Dive Analytics
- **Stress Gauge**: A visual representation of a company's risk profile.
- **Ensemble ML Scoring**: Breakdown of scores from Classifier, Trend, and Clustering models.
- **Financial Ratios**: Real-time tracking of Altman Z-score, Piotroski F-score, Current Ratio, Net Margin, and more.
- **Historical Trends**: Interactive sparklines and charts showing financial health over the last decade.

### ⚡ 3. Live Ticker Scorer
- On-demand analysis of any ticker.
- Fetches real-time financial statements and computes a comprehensive stress report in seconds.
- Detects "Red Flags" automatically (e.g., negative ROA, high debt-to-equity, cash flow divergence).

### 🤖 4. Advanced ML Engine
- **Classifiers**: Predicts the probability of financial distress using XGBoost/RandomForest.
- **Clustering**: Groups companies by financial similarity to identify systemic risks.
- **Red Flag Logic**: Rule-based engine to flag accounting anomalies and liquidity traps.

---

## 🛠️ Tech Stack

### Backend
- **Core**: Python 3.10
- **Web Framework**: Flask
- **Data Science**: Pandas, NumPy, Scikit-Learn
- **ML Models**: XGBoost, LightGBM, Joblib
- **API Integration**: Yahoo Finance, FRED (Federal Reserve)

### Frontend
- **Interface**: Vanilla HTML5, CSS3 (Modular Layout)
- **Visualizations**: Chart.js (CDN-based)
- **Icons**: Lucide/FontAwesome
- **Design**: Dark-themed "Glassmorphism" UI with responsive grid layout

---

## 📂 Project Structure

```bash
financial_stress/
├── dashboard/           # Flask Application & Web Assets
│   ├── server.py        # API Endpoints & Static Server
│   └── static/          # HTML, CSS, JS frontend modules
├── src/                 # Core Analytical Engine
│   ├── models/          # Scorer & Live Scorer logic
│   ├── scrapers/        # Financial data acquisition
│   └── utils/           # Logging & Helper functions
├── models/              # Serialized ML Model files (.joblib)
├── data/                # Processed datasets & feature matrices
├── reports/             # Generated PDF/HTML risk reports
└── requirements.txt     # Dependency list
```

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- Python 3.10 or higher installed.
- A free FRED API Key (Optional, for macroeconomic data).

### 2. Clone & Install
```bash
# Clone the repository
git clone https://github.com/yourusername/finstress.git
cd finstress

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
FRED_API_KEY=your_api_key_here
```

---

## 🏃 Usage

### Start the Dashboard
```bash
python dashboard/server.py
```
Visit `http://localhost:8000` in your browser to view the interactive UI.

### Run Live Scorer (CLI)
```bash
python src/models/live_scorer.py --ticker AAPL
```

---

## 🛡️ License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

*Created with ❤️ by the [Anjali Mittal](https://github.com/Anjali-Mittal)*
