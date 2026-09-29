// === WIKI LOVES MONUMENTS BELARUS (WLM) MAP APPLICATION ===

const state = {
  allMonuments: [],
  districtCommonsMap: {},
  heritagePortalsMap: {},
  filteredMonuments: [],
  filteredNoCoords: [],
  currentTab: 'map', // 'map' or 'nocoords'
  noCoordsPage: 1,
  noCoordsPageSize: 48,
  map: null,
  clusterGroup: null,
  userLocationMarker: null,
  userLocationCircle: null,
  selectedMonument: null,
  filters: {
    search: '',
    onlyNoPhoto: false,
    onlyGKK: false,
    form: 'immovable', // 'immovable' (default for WLM), 'movable', 'intangible', or 'all'
    region: '',
    district: '',
    category: '',
    type: ''
  }
};

// District mapping by region
const districtsByRegion = {};

// Verified bounding boxes for Belarus regions
const REGION_BOUNDS = {
  'Брэсцкая вобласць': [[51.2, 23.1], [53.5, 27.5]],
  'Віцебская вобласць': [[54.4, 26.5], [56.2, 31.0]],
  'Гомельская вобласць': [[51.2, 27.2], [53.4, 31.8]],
  'Гродзенская вобласць': [[52.7, 23.5], [54.5, 26.6]],
  'Магілёўская вобласць': [[52.7, 28.7], [54.5, 32.8]],
  'Мінская вобласць': [[52.4, 26.5], [55.0, 29.5]],
  'г. Мінск': [[53.82, 27.42], [53.98, 27.68]]
};

// Clean location formatter: prevents stutter like "г. Мінск, Савецкі раён, г. Мінск"
function formatLocation(m) {
  const parts = [];
  const add = (val) => {
    if (!val) return;
    const clean = String(val).trim();
    if (!clean) return;
    if (!parts.includes(clean)) {
      parts.push(clean);
    }
  };
  add(m.r);
  add(m.dst);
  add(m.loc);
  return parts.join(', ');
}

// Category metadata helper
function getCategoryInfo(rawCat) {
  if (!rawCat) return null;
  const s = String(rawCat).trim();
  if (s === '0' || s.includes('сусветны') || s.includes('юнеска')) {
    return {
      code: '0',
      badgeClass: 'badge-cat-0',
      shortText: '0-я катэгорыя',
      fullText: '0-я катэгорыя (сусветная спадчына ЮНЕСКА)',
      tooltip: 'Сусветная спадчына ЮНЕСКА (0-я катэгорыя)'
    };
  }
  if (s === '1' || s.includes('міжнароднага')) {
    return {
      code: '1',
      badgeClass: 'badge-cat-1',
      shortText: '1-я катэгорыя',
      fullText: '1-я катэгорыя (міжнароднае значэнне)',
      tooltip: 'Каштоўнасць міжнароднага значэння (1-я катэгорыя)'
    };
  }
  if (s === '2' || s.includes('нацыянальнага')) {
    return {
      code: '2',
      badgeClass: 'badge-cat-2',
      shortText: '2-я катэгорыя',
      fullText: '2-я катэгорыя (нацыянальнае значэнне)',
      tooltip: 'Каштоўнасць нацыянальнага значэння (2-я катэгорыя)'
    };
  }
  if (s === '3' || s.includes('рэгіянальнага')) {
    return {
      code: '3',
      badgeClass: 'badge-cat-3',
      shortText: '3-я катэгорыя',
      fullText: '3-я катэгорыя (рэгіянальнае значэнне)',
      tooltip: 'Каштоўнасць рэгіянальнага значэння (3-я катэгорыя)'
    };
  }
  if (s === 'А' || s.toUpperCase() === 'A' || s.includes('аўтэнтычныя')) {
    return {
      code: 'А',
      badgeClass: 'badge-cat-a',
      shortText: 'Катэгорыя «А»',
      fullText: 'Катэгорыя «А» (аўтэнтычная нематэрыяльная)',
      tooltip: 'Аўтэнтычныя і нязменныя нематэрыяльныя ГКК (Катэгорыя «А»)'
    };
  }
  if (s === 'Б' || s.toUpperCase() === 'B' || s.includes('адноўленыя')) {
    return {
      code: 'Б',
      badgeClass: 'badge-cat-b',
      shortText: 'Катэгорыя «Б»',
      fullText: 'Катэгорыя «Б» (адноўленая нематэрыяльная)',
      tooltip: 'Нематэрыяльныя ГКК адноўленыя ці зменлівыя з часам (Катэгорыя «Б»)'
    };
  }
  if (s.toLowerCase().includes('без')) {
    return {
      code: 'none',
      badgeClass: 'badge-cat-none',
      shortText: 'Без катэгорыі',
      fullText: 'Без катэгорыі',
      tooltip: 'Гісторыка-культурная каштоўнасць без катэгорыі'
    };
  }
  return {
    code: s,
    badgeClass: 'badge-cat',
    shortText: `${s}-я катэгорыя`,
    fullText: `${s}-я катэгорыя`,
    tooltip: `Каштоўнасць катэгорыі ${s}`
  };
}

// Wikimedia Commons Category helpers
function hasRealCommonsCategory(m) {
  return Boolean(m && m.ccat && m.ccat.trim() && m.ccat !== m.c);
}

function getDistrictCommonsCategory(m) {
  if (state.districtCommonsMap) {
    if (m.dst && state.districtCommonsMap[m.dst]) {
      return state.districtCommonsMap[m.dst];
    }
    if (m.r && state.districtCommonsMap[m.r]) {
      return state.districtCommonsMap[m.r];
    }
  }
  return 'Cultural heritage monuments in Belarus with known IDs';
}

function getCommonsCategoryName(m) {
  if (hasRealCommonsCategory(m)) {
    return m.ccat;
  }
  return getDistrictCommonsCategory(m);
}

function getCommonsCategoryUrl(m) {
  if (hasRealCommonsCategory(m)) {
    return `https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(m.ccat.replace(/ /g, '_'))}`;
  }
  const distCat = getDistrictCommonsCategory(m);
  return `https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(distCat.replace(/ /g, '_'))}`;
}

function getDefaultCategoryTitle(m) {
  if (hasRealCommonsCategory(m)) {
    return m.ccat;
  }
  // Standard format with heritage code: WLM Belarus <CODE>
  return `WLM Belarus ${m.c || m.id}`;
}

function generateCategoryWikitext(m) {
  const lines = [];

  // 1. Heritage ID template
  if (m.c) {
    lines.push(`{{Belarus heritage|${m.c}}}`);
  }

  // 2. Object GPS location (if available)
  if (m.lat && m.lon) {
    lines.push(`{{Object location dec|${Number(m.lat).toFixed(6)}|${Number(m.lon).toFixed(6)}}}`);
  }

  // 3. Belarusian description
  const descParts = [m.t];
  const locStr = formatLocation(m);
  if (locStr) descParts.push(locStr);
  if (m.a) descParts.push(m.a);
  if (m.d) descParts.push(`(${m.d})`);
  lines.push(`{{be|1=${descParts.filter(Boolean).join(', ')}}}`);
  lines.push('');

  // 4. Parent category:
  // If element of complex heritage site (underscore in code, e.g. 213В000758_1):
  if (m.c && m.c.includes('_')) {
    const parentCode = m.c.split('_')[0];
    const parent = state.allMonuments.find(x => x.c === parentCode);
    if (parent && hasRealCommonsCategory(parent)) {
      lines.push(`[[Category:${parent.ccat}]]`);
    } else {
      lines.push(`[[Category:WLM Belarus ${parentCode}]]`);
      const distCat = getDistrictCommonsCategory(m);
      if (distCat) {
        lines.push(`[[Category:${distCat}]]`);
      }
    }
  } else {
    // Top-level administrative unit category
    const distCat = getDistrictCommonsCategory(m);
    if (distCat) {
      lines.push(`[[Category:${distCat}]]`);
    }
  }

  // Country tracking category
  lines.push('[[Category:Cultural heritage monuments in Belarus with known IDs]]');

  return lines.join('\n');
}

function handleCreateOrOpenCategory(monumentId, event) {
  if (event) event.stopPropagation();
  const m = state.allMonuments.find(x => x.id === monumentId);
  if (!m) return;

  if (hasRealCommonsCategory(m)) {
    window.open(`https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(m.ccat.replace(/ /g, '_'))}`, '_blank');
    return;
  }

  openCreateCategoryModal(m);
}

function openCreateCategoryModal(m) {
  const catTitle = getDefaultCategoryTitle(m);
  const wikitext = generateCategoryWikitext(m);

  // Auto-copy to clipboard immediately
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(wikitext).catch(() => {});
  }

  const modal = document.getElementById('createCatModal');
  const titleInput = document.getElementById('createCatTitleInput');
  const textarea = document.getElementById('createCatWikitext');
  const openBtn = document.getElementById('createCatOpenCommonsBtn');
  const copyTitleBtn = document.getElementById('createCatCopyTitleBtn');
  const copyTextBtn = document.getElementById('createCatCopyTextBtn');
  const copyTextLabel = document.getElementById('createCatCopyTextLabel');

  if (titleInput) titleInput.value = catTitle;
  if (textarea) textarea.value = wikitext;

  const distCat = getDistrictCommonsCategory(m);
  const latStr = m.lat ? Number(m.lat).toFixed(6) : '';
  const lonStr = m.lon ? Number(m.lon).toFixed(6) : '';
  const titleStr = m.t || '';

  const editUrl = `https://commons.wikimedia.org/w/index.php?title=Category:${encodeURIComponent(catTitle.replace(/ /g, '_'))}&action=edit&preload=Template:Belarus_heritage_category_preload&preloadparams[]=${encodeURIComponent(m.c || '')}&preloadparams[]=${encodeURIComponent(latStr)}&preloadparams[]=${encodeURIComponent(lonStr)}&preloadparams[]=${encodeURIComponent(titleStr)}&preloadparams[]=${encodeURIComponent(distCat)}`;

  if (openBtn) openBtn.href = editUrl;

  if (copyTitleBtn) {
    copyTitleBtn.onclick = () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(catTitle).then(() => {
          showToast(`Назва катэгорыі «${catTitle}» скапіяваная!`);
        });
      }
    };
  }

  if (copyTextBtn) {
    copyTextBtn.onclick = () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(wikitext).then(() => {
          if (copyTextLabel) {
            copyTextLabel.innerText = 'Скапіявана!';
            setTimeout(() => copyTextLabel.innerText = 'Капіяваць Вікітэкст', 2500);
          }
          showToast('Вікітэкст паспяхова скапіяваны ў буфер абмену!');
        });
      }
    };
  }

  if (modal) modal.style.display = 'flex';
}

function closeCreateCategoryModal() {
  const modal = document.getElementById('createCatModal');
  if (modal) modal.style.display = 'none';
}

function copySuggestedPhotoTitle(monumentId, event) {
  if (event) event.stopPropagation();
  const m = state.allMonuments.find(x => x.id === monumentId);
  if (!m) return;

  const cleanTitle = (m.t || 'Помнік').replace(/[\\/:*?"<>|]/g, '').trim();
  const loc = m.loc ? ` (${m.loc})` : '';
  const code = m.c ? ` [${m.c}]` : '';
  const suggestedName = `${cleanTitle}${loc}${code}`;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(suggestedName).then(() => {
      showToast(`Рэкамендаваная назва файла «${suggestedName}» скапіяваная! Устаўце яе ў полі «Назва» на Вікісховішчы (Ctrl+V).`);
    });
  }
}

function showToast(msg) {
  const toast = document.getElementById('wlmToast');
  const toastMsg = document.getElementById('wlmToastMsg');
  if (!toast || !toastMsg) return;

  toastMsg.innerText = msg;
  toast.classList.add('show');
  clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.classList.remove('show');
  }, 5000);
}

// Custom Leaflet Icons
const redIcon = L.divIcon({
  className: 'wlm-marker-wrapper',
  html: '<div class="wlm-marker wlm-marker--red" title="Няма фота (патрабуецца)"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11]
});

const blueIcon = L.divIcon({
  className: 'wlm-marker-wrapper',
  html: '<div class="wlm-marker wlm-marker--blue" title="Ёсць фота"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11]
});

const orangeIcon = L.divIcon({
  className: 'wlm-marker-wrapper',
  html: '<div class="wlm-marker wlm-marker--orange" title="Помнік без ГКК (няма фота)"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11]
});

const greenIcon = L.divIcon({
  className: 'wlm-marker-wrapper',
  html: '<div class="wlm-marker wlm-marker--green" title="Помнік без ГКК (ёсць фота)"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11]
});

// App Initialization
document.addEventListener('DOMContentLoaded', async () => {
  initMap();
  setupEventListeners();
  await loadDataset();
  checkUrlHash();
});

// 1. Initialize Map
function initMap() {
  state.map = L.map('map', {
    center: [53.9006, 27.5590],
    zoom: 7,
    minZoom: 6,
    maxZoom: 19,
    zoomControl: false
  });

  L.control.zoom({ position: 'bottomright' }).addTo(state.map);

  const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  });

  const cartoPositron = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
  });

  const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 18,
    attribution: 'Tiles &copy; Esri'
  });

  osmLayer.addTo(state.map);

  const baseLayers = {
    "Карта (OpenStreetMap)": osmLayer,
    "Светлая (Carto)": cartoPositron,
    "Спадарожнік (Esri)": esriSatellite
  };
  L.control.layers(baseLayers, null, { position: 'bottomleft' }).addTo(state.map);

  state.clusterGroup = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: 60,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    iconCreateFunction: function (cluster) {
      const markers = cluster.getAllChildMarkers();
      let hasMissing = false;
      for (let i = 0; i < markers.length; i++) {
        if (markers[i].options.wlmHasPhoto === 0) {
          hasMissing = true;
          break;
        }
      }
      const c = hasMissing ? 'marker-cluster-wlm-red' : 'marker-cluster-wlm-blue';
      return new L.DivIcon({
        html: '<div><span>' + cluster.getChildCount() + '</span></div>',
        className: 'marker-cluster ' + c,
        iconSize: new L.Point(40, 40)
      });
    }
  });

  state.map.addLayer(state.clusterGroup);
}

// 2. Load Dataset
async function loadDataset() {
  const overlay = document.getElementById('loadingOverlay');
  try {
    const [resMonuments, resDistrictMap, resHeritagePortals] = await Promise.all([
      fetch('data/monuments.json?v=3'),
      fetch('data/district_commons_map.json').catch(() => null),
      fetch('data/heritage_portals_map.json').catch(() => null)
    ]);

    if (!resMonuments.ok) throw new Error('Не ўдалося загрузіць базу помнікаў');
    const data = await resMonuments.json();
    state.allMonuments = data;

    if (resDistrictMap && resDistrictMap.ok) {
      try {
        state.districtCommonsMap = await resDistrictMap.json();
      } catch (e) {
        console.warn('Не ўдалося разабраць district_commons_map.json', e);
      }
    }

    if (resHeritagePortals && resHeritagePortals.ok) {
      try {
        state.heritagePortalsMap = await resHeritagePortals.json();
      } catch (e) {
        console.warn('Не ўдалося разабраць heritage_portals_map.json', e);
      }
    }

    // Collect regions and districts
    let mappedCount = 0;
    let noCoordsCount = 0;

    data.forEach(m => {
      if (m.lat && m.lon) mappedCount++;
      else noCoordsCount++;

      if (m.r) {
        if (!districtsByRegion[m.r]) districtsByRegion[m.r] = new Set();
        if (m.dst) districtsByRegion[m.r].add(m.dst);
      }
    });

    document.getElementById('statTotal').innerText = data.length.toLocaleString('be-BY');
    document.getElementById('statMapped').innerText = mappedCount.toLocaleString('be-BY');
    document.getElementById('tabNoCoordsCount').innerText = noCoordsCount.toLocaleString('be-BY');

    populateRegionDropdown();
    applyFilters();

    if (overlay) {
      overlay.classList.add('hidden');
      setTimeout(() => overlay.style.display = 'none', 300);
    }
  } catch (err) {
    console.error(err);
    if (overlay) {
      overlay.innerHTML = `<div style="text-align:center;padding:20px;color:#dc2626;"><h3>Памылка загрузкі базы</h3><p>${err.message}</p></div>`;
    }
  }
}

// 3. Tab Switching (Map vs No-coords)
function switchTab(tab) {
  state.currentTab = tab;
  document.getElementById('tabMapBtn').classList.toggle('active', tab === 'map');
  document.getElementById('tabNoCoordsBtn').classList.toggle('active', tab === 'nocoords');

  const mapEl = document.getElementById('map');
  const noCoordsEl = document.getElementById('noCoordsSection');
  const locateBtn = document.getElementById('locateBtn');
  const legendEl = document.querySelector('.map-legend');

  if (tab === 'map') {
    mapEl.style.display = 'block';
    noCoordsEl.style.display = 'none';
    if (locateBtn) locateBtn.style.display = 'flex';
    if (legendEl) legendEl.style.display = 'flex';
    state.map.invalidateSize();
  } else {
    mapEl.style.display = 'none';
    noCoordsEl.style.display = 'block';
    if (locateBtn) locateBtn.style.display = 'none';
    if (legendEl) legendEl.style.display = 'none';
    state.noCoordsPage = 1;
    renderNoCoordsGrid();
  }
}

// 4. Populate Region & District Dropdowns
function populateRegionDropdown() {
  const regionSelect = document.getElementById('regionSelect');
  const regions = Object.keys(districtsByRegion).sort((a, b) => a.localeCompare(b, 'be'));

  regions.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r;
    opt.textContent = r;
    regionSelect.appendChild(opt);
  });
}

function updateDistrictDropdown(region) {
  const districtSelect = document.getElementById('districtSelect');
  districtSelect.innerHTML = '<option value="">Усе раёны</option>';

  if (!region || !districtsByRegion[region]) {
    districtSelect.disabled = true;
    return;
  }

  districtSelect.disabled = false;
  const districts = Array.from(districtsByRegion[region]).sort((a, b) => a.localeCompare(b, 'be'));
  districts.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    districtSelect.appendChild(opt);
  });
}

// 5. Filtering Logic
function applyFilters() {
  const { search, onlyNoPhoto, onlyGKK, form, region, district, category, type } = state.filters;
  const qLower = search.trim().toLowerCase();

  const passesCommonFilter = (m) => {
    // Heritage form filter (Default: 'immovable' for WLM)
    if (form && form !== 'all') {
      if (m.f !== form) return false;
    }
    if (onlyNoPhoto && m.p === 1) return false;
    if (onlyGKK && !m.c) return false;
    if (region && m.r !== region) return false;
    if (district && m.dst !== district) return false;
    if (category) {
      if (m.cat !== category) return false;
    }
    if (type) {
      const tp = (m.tp || '').toLowerCase();
      if (!tp.includes(type.toLowerCase())) return false;
    }
    if (qLower) {
      const matchTitle = (m.t || '').toLowerCase().includes(qLower);
      const matchCode = (m.c || '').toLowerCase().includes(qLower);
      const matchLoc = (m.loc || '').toLowerCase().includes(qLower);
      const matchAddr = (m.a || '').toLowerCase().includes(qLower);
      if (!matchTitle && !matchCode && !matchLoc && !matchAddr) return false;
    }
    return true;
  };

  // Mapped monuments
  state.filteredMonuments = state.allMonuments.filter(m => {
    if (!m.lat || !m.lon) return false;
    return passesCommonFilter(m);
  });

  // Non-mapped monuments
  state.filteredNoCoords = state.allMonuments.filter(m => {
    if (m.lat && m.lon) return false;
    return passesCommonFilter(m);
  });

  renderMarkers();
  updateStatsDisplay();
  updateResetButton();

  if (state.currentTab === 'nocoords') {
    state.noCoordsPage = 1;
    renderNoCoordsGrid();
  }
}

// 6. Render Markers on Map
function renderMarkers() {
  state.clusterGroup.clearLayers();

  const markers = [];
  state.filteredMonuments.forEach(m => {
    let icon = redIcon;
    if (m.c) {
      icon = (m.p === 1) ? blueIcon : redIcon;
    } else {
      icon = (m.p === 1) ? greenIcon : orangeIcon;
    }
    const marker = L.marker([m.lat, m.lon], {
      icon: icon,
      wlmHasPhoto: m.p,
      title: m.t
    });

    marker.on('click', () => {
      openDetailDrawer(m);
    });

    markers.push(marker);
  });

  state.clusterGroup.addLayers(markers);
}

// 7. Render No Coordinates Grid & Pagination
function renderNoCoordsGrid() {
  const grid = document.getElementById('noCoordsGrid');
  const pagination = document.getElementById('noCoordsPagination');
  const items = state.filteredNoCoords;

  if (items.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
        <h3>Аб’ектаў не знойдзена</h3>
        <p>Паспрабуйце змяніць параметры пошуку або скінуць фільтры.</p>
      </div>
    `;
    pagination.innerHTML = '';
    return;
  }

  const totalPages = Math.ceil(items.length / state.noCoordsPageSize);
  const start = (state.noCoordsPage - 1) * state.noCoordsPageSize;
  const pageItems = items.slice(start, start + state.noCoordsPageSize);

  grid.innerHTML = pageItems.map(m => {
    const uploadUrl = buildCommonsUploadUrl(m);
    const commonsCatUrl = getCommonsCategoryUrl(m);
    const catName = getCommonsCategoryName(m);
    const wikidataUrl = m.qid ? `https://www.wikidata.org/wiki/${m.qid}` : `https://www.wikidata.org/w/index.php?search=${encodeURIComponent(m.c || m.t)}`;
    const locParts = formatLocation(m);
    const catInfo = getCategoryInfo(m.cat);
    let imgThumb = null;
    if (m.img) {
      let u = m.img;
      if (u.startsWith('http://')) u = 'https://' + u.slice(7);
      imgThumb = (u.includes('Special:FilePath') && !u.includes('width=')) ? `${u}?width=400` : u;
    }

    const hasCat = hasRealCommonsCategory(m);
    const catBtnClass = hasCat ? 'btn-card-commons btn-card-commons--has-cat' : 'btn-card-commons btn-card-commons--create';
    const catBtnText = hasCat ? 'Катэгорыя' : '+ Катэгорыя';
    const catBtnTitle = hasCat
      ? `Катэгорыя на Вікісховішчы: ${escapeHtml(m.ccat)}`
      : `Катэгорыі яшчэ няма на Вікісховішчы. Націсніце, каб стварыць новую катэгорыю з гатовым шаблонам і апісаннем!`;

    return `
      <div class="monument-card" onclick="openDetailDrawerById('${escapeHtml(m.id)}')">
        ${imgThumb ? `
          <div class="monument-card__image">
            <img src="${escapeHtml(imgThumb)}" alt="${escapeHtml(m.t)}" loading="lazy">
          </div>
        ` : ''}
        <div class="monument-card__body">
          <div class="monument-card__header">
            <span class="badge badge-code">${escapeHtml(m.c || 'Без шыфра')}</span>
            ${catInfo ? `<span class="badge ${catInfo.badgeClass}" title="${escapeHtml(catInfo.tooltip)}">${escapeHtml(catInfo.shortText)}</span>` : ''}
          </div>
          <h4 class="monument-card__title">${escapeHtml(m.t)}</h4>
          <div class="monument-card__meta">
            ${locParts ? `<div class="monument-card__meta-item"><span class="meta-label">Месца:</span> <span>${escapeHtml(locParts)}</span></div>` : ''}
            ${m.a ? `<div class="monument-card__meta-item"><span class="meta-label">Адрас:</span> <span>${escapeHtml(m.a)}</span></div>` : ''}
            ${m.d ? `<div class="monument-card__meta-item"><span class="meta-label">Час:</span> <span>${escapeHtml(m.d)}</span></div>` : ''}
          </div>
          <div class="monument-card__actions" onclick="event.stopPropagation()">
            <a href="${escapeHtml(uploadUrl)}" target="_blank" rel="noopener" class="btn-card-upload" title="Загрузіць фота на Вікісховішча">
              Фота
            </a>
            <button type="button" onclick="handleCreateOrOpenCategory('${escapeHtml(m.id)}', event)" class="${catBtnClass}" title="${catBtnTitle}">
              ${catBtnText}
            </button>
            <a href="${escapeHtml(wikidataUrl)}" target="_blank" rel="noopener" class="btn-card-wikidata" title="Дадаць каардынаты ў Вікідадзеныя">
              Дадаць GPS
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Render pagination controls
  renderPagination(totalPages);
}

function renderPagination(totalPages) {
  const p = document.getElementById('noCoordsPagination');
  if (totalPages <= 1) {
    p.innerHTML = '';
    return;
  }

  let html = '';
  html += `<button class="page-btn" ${state.noCoordsPage === 1 ? 'disabled' : ''} onclick="goToPage(${state.noCoordsPage - 1})">&laquo; Назад</button>`;
  
  const startP = Math.max(1, state.noCoordsPage - 2);
  const endP = Math.min(totalPages, state.noCoordsPage + 2);

  if (startP > 1) html += `<button class="page-btn" onclick="goToPage(1)">1</button>`;
  if (startP > 2) html += `<span>...</span>`;

  for (let i = startP; i <= endP; i++) {
    html += `<button class="page-btn ${i === state.noCoordsPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }

  if (endP < totalPages - 1) html += `<span>...</span>`;
  if (endP < totalPages) html += `<button class="page-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;

  html += `<button class="page-btn" ${state.noCoordsPage === totalPages ? 'disabled' : ''} onclick="goToPage(${state.noCoordsPage + 1})">Наперад &raquo;</button>`;
  p.innerHTML = html;
}

function goToPage(page) {
  state.noCoordsPage = page;
  renderNoCoordsGrid();
  document.getElementById('noCoordsSection').scrollTo({ top: 0, behavior: 'smooth' });
}

function openDetailDrawerById(id) {
  const found = state.allMonuments.find(m => m.id === id);
  if (found) openDetailDrawer(found);
}

// 8. Update Stats Counters
function updateStatsDisplay() {
  let mapped = 0;
  let missing = 0;
  let withPhoto = 0;

  state.filteredMonuments.forEach(m => {
    mapped++;
    if (m.p === 1) withPhoto++;
    else missing++;
  });

  const totalCurrent = mapped + state.filteredNoCoords.length;

  document.getElementById('statTotal').innerText = totalCurrent.toLocaleString('be-BY');
  document.getElementById('statMapped').innerText = mapped.toLocaleString('be-BY');
  document.getElementById('statMissing').innerText = missing.toLocaleString('be-BY');
  document.getElementById('statWithPhoto').innerText = withPhoto.toLocaleString('be-BY');
  document.getElementById('tabNoCoordsCount').innerText = state.filteredNoCoords.length.toLocaleString('be-BY');
}

function updateResetButton() {
  const f = state.filters;
  const isFiltered = f.search || f.onlyNoPhoto || f.onlyGKK || f.region || f.district || f.category || f.type || (f.form !== 'immovable');
  document.getElementById('resetFiltersBtn').style.display = isFiltered ? 'block' : 'none';
}

function resetAllFilters() {
  state.filters = {
    search: '',
    onlyNoPhoto: false,
    onlyGKK: false,
    form: 'immovable',
    region: '',
    district: '',
    category: '',
    type: ''
  };

  document.getElementById('searchInput').value = '';
  document.getElementById('clearSearchBtn').style.display = 'none';
  document.getElementById('filterNoPhotoBtn').classList.remove('active');
  const gkkBtn = document.getElementById('filterOnlyGKKBtn');
  if (gkkBtn) gkkBtn.classList.remove('active');
  const formSel = document.getElementById('formSelect');
  if (formSel) formSel.value = 'immovable';
  document.getElementById('regionSelect').value = '';
  document.getElementById('districtSelect').value = '';
  document.getElementById('districtSelect').disabled = true;
  document.getElementById('categorySelect').value = '';
  document.getElementById('typeSelect').value = '';

  applyFilters();
  state.map.setView([53.9006, 27.5590], 7);
}

// 9. Detail Drawer Logic
function openDetailDrawer(m) {
  state.selectedMonument = m;
  window.location.hash = `id=${encodeURIComponent(m.id)}`;

  const drawer = document.getElementById('detailDrawer');
  const badgesBox = document.getElementById('drawerBadges');
  const titleEl = document.getElementById('drawerTitle');
  const imageBox = document.getElementById('drawerImageBox');
  const imageEl = document.getElementById('drawerImage');
  const bannerEl = document.getElementById('missingPhotoBanner');
  const uploadBtn = document.getElementById('drawerUploadBtn');

  titleEl.innerText = m.t || 'Помнік';

  badgesBox.innerHTML = '';
  if (m.c) {
    badgesBox.innerHTML += `<span class="badge badge-code">${escapeHtml(m.c)}</span>`;
  }
  const catInfo = getCategoryInfo(m.cat);
  if (catInfo) {
    badgesBox.innerHTML += `<span class="badge ${catInfo.badgeClass}" title="${escapeHtml(catInfo.tooltip)}">${escapeHtml(catInfo.shortText)}</span>`;
  }

  if (m.img && m.p === 1) {
    let imgUrl = m.img;
    if (imgUrl.startsWith('http://')) {
      imgUrl = 'https://' + imgUrl.slice(7);
    }
    const thumbUrl = (imgUrl.includes('Special:FilePath') && !imgUrl.includes('width='))
      ? `${imgUrl}?width=640`
      : imgUrl;
    const fullUrl = imgUrl.replace(/\?width=\d+/, '');

    imageBox.style.display = 'block';
    imageEl.src = thumbUrl;
    imageEl.alt = m.t || 'Фота помніка';
    imageEl.onerror = () => {
      if (imageEl.src !== fullUrl) {
        imageEl.src = fullUrl;
      } else {
        imageBox.style.display = 'none';
        bannerEl.style.display = 'flex';
      }
    };
    const imgLink = document.getElementById('drawerImageLink');
    if (imgLink) imgLink.href = fullUrl;
    bannerEl.style.display = 'none';
  } else {
    imageBox.style.display = 'none';
    bannerEl.style.display = 'flex';
  }

  uploadBtn.href = buildCommonsUploadUrl(m);

  // Helper button to copy suggested photo title
  const copyTitleBtn = document.getElementById('copyPhotoTitleBtn');
  if (copyTitleBtn) {
    copyTitleBtn.onclick = (e) => copySuggestedPhotoTitle(m.id, e);
  }

  setRow('infoCodeRow', 'infoCode', m.c);
  setRow('infoDatingRow', 'infoDating', m.d);
  setRow('infoTypeRow', 'infoType', m.tp);
  setRow('infoCategoryRow', 'infoCategory', catInfo ? catInfo.fullText : '');
  const infoCatEl = document.getElementById('infoCategory');
  if (infoCatEl && catInfo) {
    infoCatEl.title = catInfo.tooltip;
  }
  setRow('infoLocationRow', 'infoLocation', formatLocation(m));
  setRow('infoAddressRow', 'infoAddress', m.a);

  // 1. Google Maps Navigation Icon Button
  const navBtn = document.getElementById('linkNav');
  if (m.lat && m.lon) {
    setRow('infoCoordsRow', 'infoCoords', `${m.lat.toFixed(6)}, ${m.lon.toFixed(6)}`);
    navBtn.href = `https://www.google.com/maps/dir/?api=1&destination=${m.lat},${m.lon}`;
    navBtn.classList.remove('disabled');
    navBtn.removeAttribute('tabindex');
  } else {
    setRow('infoCoordsRow', 'infoCoords', 'Дакладныя GPS-каардынаты пакуль адсутнічаюць');
    navBtn.href = '#';
    navBtn.classList.add('disabled');
    navBtn.setAttribute('tabindex', '-1');
  }

  // 2. Commons Category Icon Button
  const commonsBtn = document.getElementById('linkCommonsCat');
  const commonsLabel = document.getElementById('linkCommonsCatLabel');
  const hasCat = hasRealCommonsCategory(m);

  if (hasCat) {
    commonsBtn.href = `https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(m.ccat.replace(/ /g, '_'))}`;
    commonsBtn.title = `Катэгорыя на Вікісховішчы: ${m.ccat}`;
    commonsBtn.onclick = null;
    commonsBtn.classList.add('ext-icon-btn--blue');
    if (commonsLabel) commonsLabel.innerText = 'Сховішча';
  } else {
    commonsBtn.href = '#';
    commonsBtn.title = 'Катэгорыі яшчэ няма на Вікісховішчы. Націсніце, каб стварыць новую катэгорыю з шаблонам';
    commonsBtn.onclick = (e) => {
      e.preventDefault();
      handleCreateOrOpenCategory(m.id, e);
    };
    commonsBtn.classList.remove('ext-icon-btn--blue');
    if (commonsLabel) commonsLabel.innerText = '+ Стварыць';
  }

  // 3. Wikidata Icon Button
  const wikiLink = document.getElementById('linkWikidata');
  if (m.qid) {
    wikiLink.href = `https://www.wikidata.org/wiki/${m.qid}`;
    wikiLink.title = `Элемент у Вікідадзеных (${m.qid})`;
  } else {
    wikiLink.href = `https://www.wikidata.org/w/index.php?search=${encodeURIComponent(m.c || m.t)}`;
    wikiLink.title = `Пошук у Вікідадзеных па шыфры`;
  }

  // 4. Official heritage.gov.by Icon Button
  const heritageBtn = document.getElementById('linkHeritage');
  heritageBtn.href = `https://heritage.gov.by/catalog/${m.id}`;
  heritageBtn.title = `Афіцыйная картка на сайце heritage.gov.by`;

  // 5. Regional Heritage Portals («Краязнаўчыя рэсурсы»)
  const portalsSection = document.getElementById('drawerPortalsSection');
  const portalsList = document.getElementById('drawerPortalsList');
  if (portalsSection && portalsList) {
    const portalLinks = getHeritagePortalLinks(m);
    if (portalLinks && portalLinks.length > 0) {
      portalsList.innerHTML = portalLinks.map(p => `
        <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener noreferrer" class="portal-btn ${p.cls}" title="${escapeHtml(p.name)}">
          <span class="portal-btn-icon-wrap">
            <img src="${p.logo}" alt="${escapeHtml(p.name)}" class="portal-btn-icon" onerror="this.onerror=null;this.src='${p.fallback}'">
          </span>
          <span class="portal-btn-title">${escapeHtml(p.name)}</span>
          <svg class="portal-btn-arrow" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
            <polyline points="15 3 21 3 21 9"></polyline>
            <line x1="10" y1="14" x2="21" y2="3"></line>
          </svg>
        </a>
      `).join('');
      portalsSection.style.display = 'block';
    } else {
      portalsList.innerHTML = '';
      portalsSection.style.display = 'none';
    }
  }

  drawer.classList.add('open');
}

// Helper to look up and format external regional heritage portal links
function getHeritagePortalLinks(m) {
  if (!state.heritagePortalsMap || !m) return null;

  const codeKey = m.c ? String(m.c).trim() : null;
  const idKey = m.id ? String(m.id).trim() : null;
  const qidKey = m.qid ? String(m.qid).trim() : null;
  const normCode = codeKey ? codeKey.replace(/[\s\-_]+/g, '') : null;

  const entry = (codeKey && state.heritagePortalsMap[codeKey]) ||
                (idKey && state.heritagePortalsMap[idKey]) ||
                (normCode && state.heritagePortalsMap[normCode]) ||
                (qidKey && state.heritagePortalsMap[qidKey]);

  if (!entry || typeof entry !== 'object') return null;

  const links = [];

  const extractVal = (val) => {
    if (!val) return '';
    if (typeof val === 'string' || typeof val === 'number') return String(val).trim();
    if (typeof val === 'object') return String(val.url || val.id || val.value || '').trim();
    return '';
  };

  // 1. Globus of Belarus (globustut.by)
  const globusRaw = extractVal(entry.globus || entry.globustut || entry.p2488);
  if (globusRaw) {
    let url = globusRaw;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://globustut.by/' + url.replace(/^\/+/, '');
    }
    url = url.replace('http://', 'https://').replace('globus.tut.by', 'globustut.by');
    links.push({
      id: 'globus',
      name: 'Глобус Беларусі',
      url: url,
      logo: 'assets/logos/globus.svg',
      fallback: 'assets/logos/globus.png',
      cls: 'portal-btn--globus'
    });
  }

  // 2. Radzima.org
  const radzimaRaw = extractVal(entry.radzima || entry.radzima_org || entry.p2491 || entry.p6822);
  if (radzimaRaw) {
    let url = radzimaRaw;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      if (url.endsWith('.html')) {
        url = 'https://www.radzima.org/be/' + url.replace(/^\/+/, '');
      } else {
        url = `https://www.radzima.org/be/object/${url}.html`;
      }
    }
    url = url.replace('http://', 'https://');
    links.push({
      id: 'radzima',
      name: 'Radzima.org',
      url: url,
      logo: 'assets/logos/radzima.svg',
      fallback: 'assets/logos/radzima.png',
      cls: 'portal-btn--radzima'
    });
  }

  // 3. Sobory.ru
  const soboryRaw = extractVal(entry.sobory || entry.sobory_ru || entry.p8316);
  if (soboryRaw) {
    let url = soboryRaw;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = `https://sobory.ru/article/?object=${url}`;
    }
    url = url.replace('http://', 'https://');
    links.push({
      id: 'sobory',
      name: 'Саборы.ру',
      url: url,
      logo: 'assets/logos/sobory.svg',
      fallback: 'assets/logos/sobory.png',
      cls: 'portal-btn--sobory'
    });
  }

  // 4. Archivarta (archivarta.by)
  const archivartaRaw = extractVal(entry.archivarta || entry.archivarta_by || entry.p11671);
  if (archivartaRaw) {
    let url = archivartaRaw;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = `https://archivarta.by/properties/${url}`;
    }
    url = url.replace('http://', 'https://');
    links.push({
      id: 'archivarta',
      name: 'Архіварта',
      url: url,
      logo: 'assets/logos/archivarta.svg',
      fallback: 'assets/logos/archivarta.png',
      cls: 'portal-btn--archivarta'
    });
  }

  return links.length > 0 ? links : null;
}

function closeDetailDrawer() {
  document.getElementById('detailDrawer').classList.remove('open');
  state.selectedMonument = null;
  history.replaceState(null, null, ' ');
}

function setRow(rowId, valId, value) {
  const row = document.getElementById(rowId);
  const val = document.getElementById(valId);
  if (value) {
    val.innerText = value;
    row.style.display = 'flex';
  } else {
    row.style.display = 'none';
  }
}

// 10. Build Commons UploadWizard URL
function buildCommonsUploadUrl(m) {
  const baseUrl = 'https://commons.wikimedia.org/wiki/Special:UploadWizard?';
  const descParts = [m.t];
  const locStr = formatLocation(m);
  if (locStr) descParts.push(locStr);
  if (m.a) descParts.push(m.a);
  const fullDesc = descParts.filter(Boolean).join(', ');

  // Collect valid, existing Commons categories:
  // 1. Specific monument category (ONLY if it exists and is not raw code!)
  // 2. District or city category (e.g. Cultural heritage monuments in Talačyn District)
  // 3. Country tracking category
  const catList = [];
  if (hasRealCommonsCategory(m)) {
    catList.push(m.ccat);
  }
  const distCat = getDistrictCommonsCategory(m);
  if (distCat) {
    catList.push(distCat);
  }
  catList.push('Cultural heritage monuments in Belarus with known IDs');
  const categoriesParam = Array.from(new Set(catList.filter(Boolean))).join('|');

  const params = new URLSearchParams({
    campaign: 'wlm-by',
    descriptionlang: 'be',
    description: fullDesc,
    captionlang: 'be',
    caption: m.t || 'Помнік гісторыка-культурнай спадчыны Беларусі',
    categories: categoriesParam
  });

  if (m.c) {
    params.set('id', m.c);
    params.set('fields[0]', m.c);
  }
  if (fullDesc) {
    params.set('id2', fullDesc);
    params.set('fields[1]', fullDesc);
  }
  if (m.lat && m.lon) {
    params.set('lat', m.lat.toString());
    params.set('lon', m.lon.toString());
  }

  return baseUrl + params.toString();
}

// 11. Setup Event Listeners
function setupEventListeners() {
  // View Switcher Tabs
  document.getElementById('tabMapBtn').addEventListener('click', () => switchTab('map'));
  document.getElementById('tabNoCoordsBtn').addEventListener('click', () => switchTab('nocoords'));

  // Search
  const searchInput = document.getElementById('searchInput');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  let searchTimer = null;

  searchInput.addEventListener('input', (e) => {
    const val = e.target.value;
    clearSearchBtn.style.display = val ? 'block' : 'none';
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.search = val;
      applyFilters();
    }, 250);
  });

  clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearSearchBtn.style.display = 'none';
    state.filters.search = '';
    applyFilters();
  });

  // Toggle Only No Photo
  const toggleBtn = document.getElementById('filterNoPhotoBtn');
  toggleBtn.addEventListener('click', () => {
    state.filters.onlyNoPhoto = !state.filters.onlyNoPhoto;
    toggleBtn.classList.toggle('active', state.filters.onlyNoPhoto);
    applyFilters();
  });

  const gkkToggleBtn = document.getElementById('filterOnlyGKKBtn');
  if (gkkToggleBtn) {
    gkkToggleBtn.addEventListener('click', () => {
      state.filters.onlyGKK = !state.filters.onlyGKK;
      gkkToggleBtn.classList.toggle('active', state.filters.onlyGKK);
      applyFilters();
    });
  }

  // To replace the old one, we just wrap the old one in a dummy if false
  if (false) {
    toggleBtn.addEventListener('click', () => {
    state.filters.onlyNoPhoto = !state.filters.onlyNoPhoto;
    toggleBtn.classList.toggle('active', state.filters.onlyNoPhoto);
    applyFilters();
  });
  }

  // Heritage Form Select
  const formSelect = document.getElementById('formSelect');
  if (formSelect) {
    formSelect.addEventListener('change', (e) => {
      state.filters.form = e.target.value;
      applyFilters();
    });
  }

  // Region
  const regionSelect = document.getElementById('regionSelect');
  regionSelect.addEventListener('change', (e) => {
    const val = e.target.value;
    state.filters.region = val;
    state.filters.district = '';
    updateDistrictDropdown(val);
    applyFilters();
    
    if (state.currentTab === 'map') {
      if (val && REGION_BOUNDS[val]) {
        state.map.fitBounds(REGION_BOUNDS[val], { padding: [20, 20], maxZoom: 10 });
      } else if (!val) {
        state.map.setView([53.9006, 27.5590], 7);
      }
    }
  });

  // District
  const districtSelect = document.getElementById('districtSelect');
  districtSelect.addEventListener('change', (e) => {
    state.filters.district = e.target.value;
    applyFilters();
    if (state.currentTab === 'map') {
      if (state.filters.district && state.filteredMonuments.length > 0) {
        zoomToFilteredBounds();
      } else if (state.filters.region && REGION_BOUNDS[state.filters.region]) {
        state.map.fitBounds(REGION_BOUNDS[state.filters.region], { padding: [20, 20], maxZoom: 10 });
      }
    }
  });

  // Category
  document.getElementById('categorySelect').addEventListener('change', (e) => {
    state.filters.category = e.target.value;
    applyFilters();
  });

  // Type
  document.getElementById('typeSelect').addEventListener('change', (e) => {
    state.filters.type = e.target.value;
    applyFilters();
  });

  // Reset Button
  document.getElementById('resetFiltersBtn').addEventListener('click', resetAllFilters);

  // Close Drawer Button
  document.getElementById('drawerCloseBtn').addEventListener('click', closeDetailDrawer);

  // Locate Button (GPS)
  document.getElementById('locateBtn').addEventListener('click', locateUser);

  // About Modal
  document.getElementById('openAboutBtn').addEventListener('click', () => {
    document.getElementById('aboutModal').style.display = 'flex';
  });
  document.getElementById('aboutCloseBtn').addEventListener('click', () => {
    document.getElementById('aboutModal').style.display = 'none';
  });
  document.getElementById('aboutModal').addEventListener('click', (e) => {
    if (e.target.id === 'aboutModal') {
      document.getElementById('aboutModal').style.display = 'none';
    }
  });

  // Create Category Modal
  const createCatCloseBtn = document.getElementById('createCatCloseBtn');
  if (createCatCloseBtn) {
    createCatCloseBtn.addEventListener('click', closeCreateCategoryModal);
  }
  const createCatModal = document.getElementById('createCatModal');
  if (createCatModal) {
    createCatModal.addEventListener('click', (e) => {
      if (e.target.id === 'createCatModal') {
        closeCreateCategoryModal();
      }
    });
  }

  // ESC to close drawer or modal
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDetailDrawer();
      document.getElementById('aboutModal').style.display = 'none';
      closeCreateCategoryModal();
    }
  });
}

// 12. Geolocation ("Каля мяне")
function locateUser() {
  if (!navigator.geolocation) {
    alert('Ваш браўзер не падтрымлівае геалакацыю.');
    return;
  }

  const locateBtn = document.getElementById('locateBtn');
  locateBtn.style.opacity = '0.5';

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      locateBtn.style.opacity = '1';
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const acc = pos.coords.accuracy;

      if (state.userLocationMarker) state.map.removeLayer(state.userLocationMarker);
      if (state.userLocationCircle) state.map.removeLayer(state.userLocationCircle);

      state.userLocationCircle = L.circle([lat, lon], {
        radius: acc,
        color: '#2563eb',
        fillColor: '#60a5fa',
        fillOpacity: 0.15,
        weight: 1
      }).addTo(state.map);

      state.userLocationMarker = L.circleMarker([lat, lon], {
        radius: 8,
        color: '#ffffff',
        fillColor: '#2563eb',
        fillOpacity: 1,
        weight: 3
      }).addTo(state.map).bindPopup('<b>Вы тут!</b>').openPopup();

      if (state.currentTab !== 'map') {
        switchTab('map');
      }
      state.map.setView([lat, lon], 14);
    },
    (err) => {
      locateBtn.style.opacity = '1';
      alert('Не ўдалося вызначыць ваша месцазнаходжанне. Праверце дазвол на доступ да геалакацыі.');
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

// 13. Helper: Zoom to filtered bounds
function zoomToFilteredBounds() {
  const valid = state.filteredMonuments.filter(m => m.lat >= 51.0 && m.lat <= 56.5 && m.lon >= 23.0 && m.lon <= 33.0);
  if (!valid.length) return;
  const lats = valid.map(m => m.lat);
  const lons = valid.map(m => m.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  state.map.fitBounds([
    [minLat, minLon],
    [maxLat, maxLon]
  ], { padding: [40, 40], maxZoom: 14 });
}

// 14. Helper: Check URL hash on load
function checkUrlHash() {
  const hash = window.location.hash;
  if (!hash) return;

  if (hash.startsWith('#id=')) {
    const id = decodeURIComponent(hash.replace('#id=', ''));
    const found = state.allMonuments.find(m => m.id === id);
    if (found) {
      if (found.lat && found.lon) {
        state.map.setView([found.lat, found.lon], 16);
      }
      openDetailDrawer(found);
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
