window.HAD = (() => {
  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const raw = await response.text();
    let payload = null;
    if (raw) {
      try { payload = JSON.parse(raw); }
      catch { payload = { message: raw }; }
    }
    if (!response.ok) {
      const message = payload?.message || payload?.detail || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  async function fetchBrandconnectStats() {
    return fetchJson('/api/v1/brandconnect/stats');
  }

  function applyBrandconnectStats(data, mapping) {
    Object.entries(mapping).forEach(([key, elementId]) => {
      const el = document.getElementById(elementId);
      if (!el) return;
      const value = data?.[key];
      el.textContent = key === 'success_rate' ? `${value ?? 0}%` : `${value ?? 0}`;
    });
  }

  // Article Sources API
  async function fetchSources(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return fetchJson(`/api/v1/sources?${qs}`);
  }

  async function createSource(data) {
    return fetchJson('/api/v1/sources', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
  }

  async function deleteSource(id) {
    return fetchJson(`/api/v1/sources/${id}`, { method: 'DELETE' });
  }

  // Article Queue API
  async function fetchArticleQueue(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return fetchJson(`/api/v1/article-queue?${qs}`);
  }

  async function approveArticle(id, content) {
    return fetchJson(`/api/v1/article-queue/${id}/approve`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ content })
    });
  }

  async function rejectArticle(id) {
    return fetchJson(`/api/v1/article-queue/${id}/reject`, { method: 'POST' });
  }

  async function generateArticle(data) {
    return fetchJson('/api/v1/article-queue/generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
  }

  return {
    fetchJson, fetchBrandconnectStats, applyBrandconnectStats,
    fetchSources, createSource, deleteSource,
    fetchArticleQueue, approveArticle, rejectArticle, generateArticle
  };
})();
