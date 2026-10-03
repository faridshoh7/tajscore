/* Обёртка над JSON API сайта. */
window.API = (function () {
  async function get(path, params) {
    const url = new URL(path, location.origin);
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
    const r = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  const tz = () => Settings.get().tz;

  return {
    matches: (tab, date) => get("/api/matches", { tab, tz: tz(), date }),
    liveScores: () => get("/api/matches/live"),
    match: id => get("/api/matches/" + id),
    matchesBrief: ids => get("/api/matches/brief", { ids: ids.join(",") }),
    leagues: () => get("/api/leagues"),
    league: id => get("/api/leagues/" + id),
    leaguePlayers: (id, category) => get(`/api/leagues/${id}/players`, { category }),
    popular: () => get("/api/popular"),
    team: id => get("/api/teams/" + id),
    search: q => get("/api/search", { q }),
    ads: () => get("/api/ads"),
    status: () => get("/adminpanel/api/status")
  };
})();
