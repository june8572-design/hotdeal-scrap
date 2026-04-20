window.HAD = (() => {
  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const raw = await response.text();

    let payload = null;
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch {
        payload = { message: raw };
      }
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
      const element = document.getElementById(elementId);
      if (!element) {
        return;
      }

      const value = data?.[key];
      element.textContent = key === 'success_rate' ? `${value ?? 0}%` : `${value ?? 0}`;
    });
  }

  return {
    fetchJson,
    fetchBrandconnectStats,
    applyBrandconnectStats,
  };
})();
