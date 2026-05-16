/**
 * api.js — API Client for Fintellix Risk Suite
 * All fetch calls to the Flask backend with error handling.
 */

const API = {
    BASE: '',

    async _fetch(url) {
        try {
            const res = await fetch(this.BASE + url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error(`API error [${url}]:`, err);
            return { error: err.message };
        }
    },

    getOverview()        { return this._fetch('/api/overview'); },
    getScores(params={}) {
        const q = new URLSearchParams(params).toString();
        return this._fetch('/api/scores' + (q ? '?' + q : ''));
    },
    getCompany(ticker)   { return this._fetch(`/api/company/${ticker}`); },
    getSectors()         { return this._fetch('/api/sectors'); },
    getHistory(ticker)   { return this._fetch(`/api/history/${ticker}`); },
    getLive(ticker)       { return this._fetch(`/api/live/${ticker}`); },
};
