/* Poranna Pigułka Przedsiębiorcy - Logika PWA */

const AVAILABLE_FILTERS = ["Wszystkie", "Zapisane ⭐", "VAT", "PIT", "CIT", "ZUS", "Ustawy", "Rynki", "KSeF"];
const DB_NAME = "PorannaPigulkaDB";
const STORE_SAVED = "savedItems";

const state = {
  daysIndex: [],
  loadedPills: {},
  currentDate: null,
  activeFilter: "Wszystkie",
  searchQuery: "",
  savedMap: {},
  selectedItem: null,
  shareTarget: null, // { type: "item" | "day", item?, pill? }
  shareVariant: "short" // "short" | "full"
};

/* --- IndexedDB dla zapisanych pozycji (offline) --- */
function openDb() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("Brak wsparcia IndexedDB"));
      return;
    }
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_SAVED)) {
        db.createObjectStore(STORE_SAVED, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function loadSavedItems() {
  try {
    const db = await openDb();
    const tx = db.transaction(STORE_SAVED, "readonly");
    const store = tx.objectStore(STORE_SAVED);
    const items = await new Promise((res, rej) => {
      const r = store.getAll();
      r.onsuccess = () => res(r.result || []);
      r.onerror = () => rej(r.error);
    });
    state.savedMap = {};
    items.forEach((it) => {
      state.savedMap[it.id] = it;
    });
  } catch (err) {
    console.warn("IndexedDB niedostępna:", err);
  }
}

async function toggleSavedItem(item) {
  const exists = Boolean(state.savedMap[item.id]);
  try {
    const db = await openDb();
    const tx = db.transaction(STORE_SAVED, "readwrite");
    const store = tx.objectStore(STORE_SAVED);
    if (exists) {
      store.delete(item.id);
      delete state.savedMap[item.id];
      showToast("Usunięto z zapisanych");
    } else {
      const copy = { ...item, saved_at: new Date().toISOString() };
      store.put(copy);
      state.savedMap[item.id] = copy;
      showToast("Zapisano w zakładce offline ⭐");
    }
  } catch {
    if (exists) delete state.savedMap[item.id];
    else state.savedMap[item.id] = item;
  }
  renderAll();
  if (state.selectedItem && state.selectedItem.id === item.id) {
    updateDetailSaveButton(item.id);
  }
}

/* --- Pomocnicze --- */
function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.classList.add("hidden"), 2500);
}

function importanceBadge(imp) {
  if (imp === "high") return '<span class="badge badge-high">Ważne</span>';
  if (imp === "medium") return '<span class="badge badge-medium">Średnie</span>';
  return '<span class="badge badge-low">Info</span>';
}

function confidenceLabel(conf) {
  if (conf === "high") return '<span class="badge badge-low">Pewność: Wysoka</span>';
  if (conf === "medium") return '<span class="badge badge-medium">Pewność: Średnia</span>';
  return '<span class="badge badge-high">Pewność: Niska (sprawdź źródło)</span>';
}

function relevanceBadge(rel) {
  if (!rel || rel.level === "none") return "";
  if (rel.level === "high") return '<span class="badge badge-high">Dla Ciebie: Wysokie</span>';
  if (rel.level === "medium") return '<span class="badge badge-medium">Dla Ciebie: Średnie</span>';
  return '<span class="badge badge-low">Dla Ciebie: Niskie</span>';
}

/* --- Pobieranie danych z JSON --- */
async function fetchJson(url) {
  const sep = url.includes("?") ? "&" : "?";
  const cacheBusted = `${url}${sep}v=${Date.now()}`;
  const resp = await fetch(cacheBusted, { cache: "no-store" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function ensureDayLoaded(dateStr, forceReload = false) {
  if (!forceReload && state.loadedPills[dateStr]) return state.loadedPills[dateStr];
  const pill = await fetchJson(`./data/${dateStr}.json`);
  state.loadedPills[dateStr] = pill;
  return pill;
}

async function preloadRecentArchive() {
  const toLoad = state.daysIndex.slice(0, 7);
  await Promise.allSettled(toLoad.map((d) => ensureDayLoaded(d.date)));
}

/* --- Renderowanie kart informacji głównych --- */
function renderWeatherCard(weather) {
  const el = document.getElementById("weather-card");
  if (!weather || weather.status !== "ok") {
    el.innerHTML = `
      <div class="section-header"><h2>🌤️ Pogoda — ${escapeHtml(weather?.city || "Brzesko")}</h2></div>
      <p class="card-summary">Źródło pogodowe chwilowo niedostępne.</p>
    `;
    return;
  }

  const hoursHtml = (weather.hourly_forecast || [])
    .filter((_, idx) => idx % 2 === 0)
    .map((h) => `
      <div class="hour-pill">
        <div>${escapeHtml(h.hour)}</div>
        <strong>${Math.round(h.temp)}°</strong>
        <div>💧${h.rain_prob}%</div>
      </div>
    `).join("");

  el.innerHTML = `
    <div class="weather-main">
      <div>
        <div class="eyebrow">POGODA • ${escapeHtml(weather.city)} (${escapeHtml(weather.postal_code || "32-800")})</div>
        <div>${escapeHtml(weather.condition)} • Odczuwalna ${weather.apparent_temp}°C</div>
        <div class="source-caption">Min ${weather.temp_min}°C / Max ${weather.temp_max}°C • Wiatr ${weather.wind_speed_kmh} km/h</div>
      </div>
      <div class="weather-temp">${weather.temp_now}°C</div>
    </div>
    <p class="weather-tip">${escapeHtml(weather.practical_tip)}</p>
    ${hoursHtml ? `<div class="hourly-strip">${hoursHtml}</div>` : ""}
  `;
}

function renderMarketsCard(markets) {
  const el = document.getElementById("markets-card");
  if (!markets || markets.status === "unavailable") {
    el.innerHTML = `
      <div class="section-header"><h2>💱 Kursy NBP i stopy</h2></div>
      <p class="card-summary">Dane NBP chwilowo niedostępne.</p>
    `;
    return;
  }

  const ratesHtml = (markets.rates || []).map((r) => `
    <div class="rate-box">
      <div class="rate-code">${escapeHtml(r.code)} / PLN</div>
      <div class="rate-val">${Number(r.mid).toFixed(4)}</div>
    </div>
  `).join("");

  const ref = markets.reference_rate;
  const refHtml = ref
    ? `<div class="rate-box"><div class="rate-code">Stopa ref. NBP</div><div class="rate-val">${ref.value_pct}%</div></div>`
    : "";

  el.innerHTML = `
    <div class="section-header">
      <h2>💱 Kursy NBP</h2>
      <span class="section-badge">${escapeHtml(markets.table_no || "")} (${escapeHtml(markets.effective_date || "")})</span>
    </div>
    <div class="markets-grid">${ratesHtml}${refHtml}</div>
  `;
}

function downloadDeadlinesIcs(deadlines) {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Poranna Pigulka//Terminy//PL"
  ];
  deadlines.forEach((d) => {
    const dt = d.date.replace(/-/g, "");
    lines.push("BEGIN:VEVENT");
    lines.push(`UID:${d.id}@poranna-pigulka`);
    lines.push(`DTSTART;VALUE=DATE:${dt}`);
    lines.push(`SUMMARY:${d.title}`);
    lines.push(`DESCRIPTION:${d.description} (Zweryfikuj u księgowego)`);
    lines.push("END:VEVENT");
  });
  lines.push("END:VCALENDAR");

  const blob = new Blob([lines.join("\r\n")], { type: "text/calendar;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "terminy-podatkowe.ics";
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("Pobrano kalendarz .ics");
}

function renderDeadlinesCard(deadlines) {
  const el = document.getElementById("deadlines-card");
  if (!deadlines || deadlines.length === 0) {
    el.innerHTML = `
      <div class="section-header"><h2>📅 Najbliższe terminy podatkowe i ZUS</h2></div>
      <p class="card-summary">Brak standardowych terminów w najbliższym oknie.</p>
    `;
    return;
  }

  const rowsHtml = deadlines.map((dl) => {
    const dayLabel = dl.days_remaining === 0 ? "DZIŚ" : (dl.days_remaining === 1 ? "Jutro" : `Za ${dl.days_remaining} dni`);
    const shiftedNote = dl.shifted ? " (przesunięty z dnia wolnego)" : "";
    return `
      <div class="deadline-row">
        <div>
          <strong>${escapeHtml(dl.date)}${shiftedNote} — ${escapeHtml(dl.title)}</strong>
          <div class="source-caption">${escapeHtml(dl.description)}</div>
        </div>
        <span class="deadline-days">${dayLabel}</span>
      </div>
    `;
  }).join("");

  el.innerHTML = `
    <div class="section-header">
      <h2>📅 Najbliższe terminy</h2>
      <button id="export-ics-btn" class="btn btn-secondary btn-small" type="button">Eksport .ics</button>
    </div>
    ${rowsHtml}
    <p class="source-caption" style="margin-top:8px;">Terminy zależą od formy opodatkowania — potwierdź je u księgowego.</p>
  `;

  document.getElementById("export-ics-btn")?.addEventListener("click", () => downloadDeadlinesIcs(deadlines));
}

/* --- Tworzenie karty pozycji --- */
function createItemCardElement(item, dayLabel = "") {
  const card = document.createElement("article");
  card.className = "item-card";
  card.tabIndex = 0;

  const isSaved = Boolean(state.savedMap[item.id]);
  const tagsHtml = (item.tags || []).map((t) => `<span class="badge badge-tag">${escapeHtml(t)}</span>`).join("");
  const firstSrc = (item.sources && item.sources[0]) ? item.sources[0] : { name: "Źródło", published: "" };

  card.innerHTML = `
    <div class="card-meta-top">
      <div class="badges-row">
        ${importanceBadge(item.importance)}
        ${relevanceBadge(item.relevance_for_profile)}
        ${tagsHtml}
      </div>
      <button class="btn btn-icon btn-small js-save-btn" type="button" aria-label="Zapisz">
        ${isSaved ? "⭐" : "☆"}
      </button>
    </div>
    <h3 class="card-headline">${escapeHtml(item.headline)}</h3>
    <p class="card-summary">${escapeHtml(item.summary)}</p>
    <div class="card-actions-bar">
      <span class="source-caption">${dayLabel ? `${escapeHtml(dayLabel)} • ` : ""}${escapeHtml(firstSrc.name)} (${escapeHtml(firstSrc.published || "")})</span>
      <button class="btn btn-secondary btn-small js-share-item-btn" type="button">Udostępnij</button>
    </div>
  `;

  card.addEventListener("click", (ev) => {
    if (ev.target.closest(".js-save-btn") || ev.target.closest(".js-share-item-btn")) return;
    openItemDetail(item);
  });
  card.querySelector(".js-save-btn").addEventListener("click", (ev) => {
    ev.stopPropagation();
    toggleSavedItem(item);
  });
  card.querySelector(".js-share-item-btn").addEventListener("click", (ev) => {
    ev.stopPropagation();
    openShareModal({ type: "item", item });
  });

  return card;
}

/* --- Filtrowanie i wyszukiwanie --- */
function matchesFilterAndSearch(item) {
  if (state.activeFilter !== "Wszystkie" && state.activeFilter !== "Zapisane ⭐") {
    const tagsLow = (item.tags || []).map((t) => t.toLowerCase());
    if (!tagsLow.includes(state.activeFilter.toLowerCase())) return false;
  }

  const q = state.searchQuery.trim().toLowerCase();
  if (!q) return true;

  const haystack = [
    item.headline,
    item.summary,
    ...(item.tags || []),
    item.details?.what_happened,
    item.details?.background,
    item.details?.what_it_means_for_business,
    ...(item.sources || []).map((s) => s.name)
  ].join(" ").toLowerCase();

  return haystack.includes(q);
}

/* --- Renderowanie widoku głównego --- */
function renderFilters() {
  const container = document.getElementById("tag-filters");
  container.innerHTML = "";
  AVAILABLE_FILTERS.forEach((f) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `chip ${state.activeFilter === f ? "active" : ""}`;
    btn.textContent = f;
    btn.addEventListener("click", () => {
      state.activeFilter = f;
      renderAll();
    });
    container.appendChild(btn);
  });
}

function renderAll() {
  renderFilters();
  const currentPill = state.loadedPills[state.currentDate];
  const recommendedSection = document.getElementById("recommended-section");
  const recommendedList = document.getElementById("recommended-list");
  const sectionsContainer = document.getElementById("sections-container");
  const savedSection = document.getElementById("saved-section");
  const savedList = document.getElementById("saved-list");

  recommendedList.innerHTML = "";
  sectionsContainer.innerHTML = "";
  savedList.innerHTML = "";

  // Tryb Zapisane ⭐
  if (state.activeFilter === "Zapisane ⭐") {
    recommendedSection.classList.add("hidden");
    savedSection.classList.remove("hidden");
    const savedItems = Object.values(state.savedMap).filter(matchesFilterAndSearch);
    if (savedItems.length === 0) {
      savedList.innerHTML = '<div class="info-card"><p class="card-summary">Brak zapisanych pozycji. Kliknij gwiazdkę ☆ na dowolnej karcie, aby zapisać ją offline.</p></div>';
    } else {
      savedItems.forEach((it) => savedList.appendChild(createItemCardElement(it)));
    }
    return;
  }
  savedSection.classList.add("hidden");

  if (!currentPill) return;

  document.getElementById("pill-date-title").textContent = currentPill.date;
  renderWeatherCard(currentPill.weather);
  renderMarketsCard(currentPill.markets);
  renderDeadlinesCard(currentPill.deadlines);

  const meta = currentPill.meta || {};
  document.getElementById("meta-info").textContent =
    `Wygenerowano: ${currentPill.generated_at || ""} • Model: ${meta.ai_model || "-"}`;

  // Jeśli użytkownik wpisuje frazę w wyszukiwarkę, szukaj w bieżącym dniu oraz w załadowanym archiwum
  const q = state.searchQuery.trim();
  if (q.length >= 2) {
    recommendedSection.classList.add("hidden");
    const resultsBlock = document.createElement("section");
    resultsBlock.className = "section-block";
    resultsBlock.innerHTML = `<div class="section-header"><h2>🔍 Wyniki wyszukiwania w archiwum</h2></div>`;
    const grid = document.createElement("div");
    grid.className = "cards-grid";

    let totalMatches = 0;
    const seenSearch = new Set();
    Object.keys(state.loadedPills).sort().reverse().forEach((dateKey) => {
      const p = state.loadedPills[dateKey];
      (p.sections || []).forEach((sec) => {
        (sec.items || []).forEach((it) => {
          if (!seenSearch.has(it.id) && matchesFilterAndSearch(it)) {
            seenSearch.add(it.id);
            totalMatches += 1;
            grid.appendChild(createItemCardElement(it, dateKey));
          }
        });
      });
    });

    if (totalMatches === 0) {
      grid.innerHTML = '<div class="info-card"><p class="card-summary">Brak wyników dla podanego zapytania.</p></div>';
    }
    resultsBlock.appendChild(grid);
    sectionsContainer.appendChild(resultsBlock);
    return;
  }

  // Sekcja "Najważniejsze dla Ciebie"
  const topForProfile = [];
  (currentPill.sections || []).forEach((sec) => {
    (sec.items || []).forEach((it) => {
      if (it.relevance_for_profile?.level === "high" && matchesFilterAndSearch(it)) {
        topForProfile.push(it);
      }
    });
  });

  if (topForProfile.length > 0 && state.activeFilter === "Wszystkie") {
    recommendedSection.classList.remove("hidden");
    topForProfile.slice(0, 3).forEach((it) => recommendedList.appendChild(createItemCardElement(it)));
  } else {
    recommendedSection.classList.add("hidden");
  }

  // Standardowe sekcje
  (currentPill.sections || []).forEach((sec) => {
    const filteredItems = (sec.items || []).filter(matchesFilterAndSearch);
    const block = document.createElement("section");
    block.className = "section-block";
    block.innerHTML = `<div class="section-header"><h2>${escapeHtml(sec.title)}</h2><span class="section-badge">${filteredItems.length} poz.</span></div>`;
    const grid = document.createElement("div");
    grid.className = "cards-grid";

    if (sec.status === "unavailable" && filteredItems.length === 0) {
      grid.innerHTML = `<div class="info-card"><p class="card-summary">⚠️ ${escapeHtml(sec.status_message || "Źródło chwilowo niedostępne.")}</p></div>`;
    } else if (filteredItems.length === 0) {
      grid.innerHTML = `<div class="info-card"><p class="card-summary">${escapeHtml(sec.status_message || "Brak pozycji spełniających wybrane filtry.")}</p></div>`;
    } else {
      filteredItems.forEach((it) => grid.appendChild(createItemCardElement(it)));
    }
    block.appendChild(grid);
    sectionsContainer.appendChild(block);
  });
}

/* --- Pełnoekranowy widok szczegółów (7 sekcji) --- */
function updateDetailSaveButton(itemId) {
  const btn = document.getElementById("detail-save-btn");
  btn.textContent = state.savedMap[itemId] ? "⭐" : "☆";
}

function openItemDetail(item) {
  state.selectedItem = item;
  const body = document.getElementById("detail-body");
  const d = item.details || {};

  const stepsHtml = (d.what_to_do && d.what_to_do.length)
    ? `<ul>${d.what_to_do.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
    : "<p>Brak szczególnych czynności do wykonania.</p>";

  const deadlinesHtml = (d.deadlines && d.deadlines.length)
    ? `<ul>${d.deadlines.map((dl) => `<li><strong>${escapeHtml(dl.date)}:</strong> ${escapeHtml(dl.description)}</li>`).join("")}</ul>`
    : "<p>Brak nowych terminów w źródle.</p>";

  const sourcesHtml = (item.sources || []).map((src) => `
    <li>
      <a class="source-link" href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(src.name)}
      </a>
      <span class="source-caption"> (opublikowano: ${escapeHtml(src.published || "brak daty")})</span>
    </li>
  `).join("");

  const relReason = item.relevance_for_profile?.reason
    ? `<p class="source-caption" style="margin-top:6px;">Dopasowanie do profilu firmy: ${escapeHtml(item.relevance_for_profile.reason)}</p>`
    : "";

  body.innerHTML = `
    <div class="badges-row">
      ${importanceBadge(item.importance)}
      ${relevanceBadge(item.relevance_for_profile)}
      ${confidenceLabel(item.confidence)}
      ${(item.tags || []).map((t) => `<span class="badge badge-tag">${escapeHtml(t)}</span>`).join("")}
    </div>
    <h2 id="detail-headline" class="detail-title">${escapeHtml(item.headline)}</h2>
    ${relReason}

    <div class="detail-section">
      <h3>1. Co się stało</h3>
      <p>${escapeHtml(d.what_happened || item.summary)}</p>
    </div>

    <div class="detail-section">
      <h3>2. Kontekst</h3>
      <p>${escapeHtml(d.background || "Brak danych.")}</p>
    </div>

    <div class="detail-section">
      <h3>3. Co to oznacza dla mojej firmy</h3>
      <p>${escapeHtml(d.what_it_means_for_business || "Brak danych.")}</p>
    </div>

    <div class="detail-section">
      <h3>4. Co zrobić</h3>
      ${stepsHtml}
    </div>

    <div class="detail-section">
      <h3>5. Terminy</h3>
      ${deadlinesHtml}
    </div>

    <div class="detail-section">
      <h3>6. Zastrzeżenia</h3>
      <p>${escapeHtml(d.caveats || "Brak dodatkowych zastrzeżeń.")}</p>
    </div>

    <div class="detail-section">
      <h3>7. Źródła i pewność</h3>
      <ul>${sourcesHtml}</ul>
      <div style="margin-top:10px;">${confidenceLabel(item.confidence)}</div>
    </div>
  `;

  updateDetailSaveButton(item.id);
  document.getElementById("detail-view").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  if (history.state?.view !== "detail") {
    history.pushState({ view: "detail" }, "");
  }
}

function closeItemDetail(fromPopState = false) {
  document.getElementById("detail-view").classList.add("hidden");
  document.body.style.overflow = "";
  state.selectedItem = null;
  if (!fromPopState && history.state?.view === "detail") {
    history.back();
  }
}

/* --- Udostępnianie (2 warianty: krótka SMS/WhatsApp + pełna E-mail) --- */
function buildShareText(target, variant) {
  if (!target) return "";
  if (target.type === "item") {
    const it = target.item;
    const d = it.details || {};
    const src = (it.sources && it.sources[0]) ? it.sources[0] : { name: "Źródło", url: "" };
    if (variant === "short") {
      return (
        `📌 ${it.headline}\n\n` +
        `${it.summary}\n\n` +
        `💼 Dla firmy: ${d.what_it_means_for_business || ""}\n` +
        `🔗 Źródło (${src.name}): ${src.url}\n` +
        `ℹ️ Opracowanie informacyjne (nie stanowi porady prawnej/podatkowej).`
      );
    }
    const steps = (d.what_to_do || []).map((s) => `- ${s}`).join("\n");
    return (
      `OPRACOWANIE INFORMACYJNE: ${it.headline}\n` +
      `========================================\n\n` +
      `1. Co się stało:\n${d.what_happened}\n\n` +
      `2. Kontekst:\n${d.background}\n\n` +
      `3. Co to oznacza dla firmy:\n${d.what_it_means_for_business}\n\n` +
      `4. Co zrobić:\n${steps || "- Brak szczególnych działań"}\n\n` +
      `5. Zastrzeżenia:\n${d.caveats}\n\n` +
      `Źródło: ${src.name} (${src.published || ""})\n${src.url}\n\n` +
      `Uwaga: Materiał ma charakter wyłącznie informacyjny i nie stanowi porady prawnej ani podatkowej.`
    );
  }

  // Udostępnienie całego dnia
  const pill = target.pill;
  if (!pill) return "";
  const w = pill.weather || {};
  const weatherLine = w.status === "ok"
    ? `🌤️ Pogoda (${w.city}): ${w.temp_now}°C, ${w.practical_tip}`
    : `🌤️ Pogoda: brak danych`;

  if (variant === "short") {
    const bullets = [];
    (pill.sections || []).forEach((sec) => {
      (sec.items || []).slice(0, 2).forEach((it) => {
        const url = it.sources?.[0]?.url || "";
        bullets.push(`• ${it.headline}${url ? ` (${url})` : ""}`);
      });
    });
    return (
      `☕ Poranna pigułka (${pill.date})\n` +
      `${weatherLine}\n\n` +
      `${bullets.join("\n")}\n\n` +
      `ℹ️ Opracowanie informacyjne (nie stanowi porady prawnej/podatkowej).`
    );
  }

  const sectionsTxt = (pill.sections || []).map((sec) => {
    const itemsTxt = (sec.items || []).map((it) => {
      const url = it.sources?.[0]?.url || "";
      return `• ${it.headline}\n  ${it.summary}\n  Źródło: ${url}`;
    }).join("\n\n");
    return `--- ${sec.title.toUpperCase()} ---\n${itemsTxt || "Brak nowych pozycji."}`;
  }).join("\n\n");

  return (
    `PORANNA PIGUŁKA PRZEDSIĘBIORCY — ${pill.date}\n` +
    `${weatherLine}\n\n` +
    `${sectionsTxt}\n\n` +
    `Uwaga: Opracowanie informacyjne. Materiał nie stanowi porady prawnej ani podatkowej.`
  );
}

function openShareModal(target) {
  state.shareTarget = target;
  state.shareVariant = "short";
  updateShareModalView();
  document.getElementById("share-modal").classList.remove("hidden");
}

function updateShareModalView() {
  const shortBtn = document.getElementById("variant-short-btn");
  const fullBtn = document.getElementById("variant-full-btn");
  shortBtn.classList.toggle("active", state.shareVariant === "short");
  fullBtn.classList.toggle("active", state.shareVariant === "full");
  document.getElementById("share-preview").value = buildShareText(state.shareTarget, state.shareVariant);
}

async function copyTextFallback(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast("Skopiowano notatkę do schowka");
  } catch {
    const ta = document.getElementById("share-preview");
    ta.select();
    document.execCommand("copy");
    showToast("Skopiowano do schowka");
  }
}

/* --- Inicjalizacja aplikacji --- */
async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }

  const updateOfflineUi = () => {
    document.getElementById("offline-banner").classList.toggle("hidden", navigator.onLine);
  };
  window.addEventListener("online", updateOfflineUi);
  window.addEventListener("offline", updateOfflineUi);
  updateOfflineUi();

  await loadSavedItems();

  const selectEl = document.getElementById("archive-select");

  async function refreshLatestIndex(isResume = false) {
    try {
      const idx = await fetchJson("./data/index.json");
      const freshDays = idx.days || [];
      if (freshDays.length === 0) {
        if (!isResume) {
          state.daysIndex = [];
          selectEl.innerHTML = "";
          document.getElementById("pill-date-title").textContent = "Brak wygenerowanych pigułek";
        }
        return;
      }

      const newest = freshDays[0];
      const cachedNewest = state.loadedPills[newest.date];
      const hasNewerDay = !isResume || state.currentDate !== newest.date;
      const hasUpdatedContent =
        isResume && cachedNewest && newest.generated_at && cachedNewest.generated_at !== newest.generated_at;

      state.daysIndex = freshDays;
      selectEl.innerHTML = "";
      state.daysIndex.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.date;
        opt.textContent = `${d.date} (${d.items_count} poz.)`;
        selectEl.appendChild(opt);
      });

      if (!isResume || hasNewerDay || hasUpdatedContent) {
        state.currentDate = newest.date;
        selectEl.value = state.currentDate;
        await ensureDayLoaded(state.currentDate, true);
        renderAll();
        preloadRecentArchive();
      } else {
        selectEl.value = state.currentDate;
      }
    } catch {
      if (!isResume && state.daysIndex.length === 0) {
        document.getElementById("pill-date-title").textContent = "Brak wygenerowanych pigułek";
      }
    }
  }

  await refreshLatestIndex(false);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && navigator.onLine) {
      refreshLatestIndex(true);
    }
  });

  selectEl.addEventListener("change", async (ev) => {
    state.currentDate = ev.target.value;
    await ensureDayLoaded(state.currentDate);
    renderAll();
  });

  document.getElementById("search-input").addEventListener("input", (ev) => {
    state.searchQuery = ev.target.value;
    renderAll();
  });

  document.getElementById("detail-back-btn").addEventListener("click", () => closeItemDetail(false));
  document.getElementById("detail-save-btn").addEventListener("click", () => {
    if (state.selectedItem) toggleSavedItem(state.selectedItem);
  });
  document.getElementById("detail-share-btn").addEventListener("click", () => {
    if (state.selectedItem) openShareModal({ type: "item", item: state.selectedItem });
  });
  document.getElementById("share-day-btn").addEventListener("click", () => {
    const pill = state.loadedPills[state.currentDate];
    if (pill) openShareModal({ type: "day", pill });
  });

  document.getElementById("share-close-btn").addEventListener("click", () => {
    document.getElementById("share-modal").classList.add("hidden");
  });
  document.getElementById("variant-short-btn").addEventListener("click", () => {
    state.shareVariant = "short";
    updateShareModalView();
  });
  document.getElementById("variant-full-btn").addEventListener("click", () => {
    state.shareVariant = "full";
    updateShareModalView();
  });
  document.getElementById("share-copy-btn").addEventListener("click", () => {
    copyTextFallback(document.getElementById("share-preview").value);
  });
  document.getElementById("share-native-btn").addEventListener("click", async () => {
    const text = document.getElementById("share-preview").value;
    if (navigator.share) {
      try {
        await navigator.share({ title: "Poranna Pigułka", text });
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return;
      }
    }
    await copyTextFallback(text);
  });

  window.addEventListener("popstate", () => {
    if (!document.getElementById("detail-view").classList.contains("hidden")) {
      closeItemDetail(true);
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
