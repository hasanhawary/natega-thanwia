<script setup>
import { ref, onMounted, watch } from 'vue';
import initSqlJs from 'sql.js';
import wasmUrl from 'sql.js/dist/sql-wasm.wasm?url';

// App States
const db = ref(null);
const loading = ref(true);
const downloadProgress = ref(0);
const totalDownloaded = ref("0 MB");
const totalSize = ref("35.5 MB");
const error = ref(null);
const isDarkMode = ref(false);

// Query States
const searchQuery = ref('');
const searchMode = ref('name'); // 'name' | 'seating'
const results = ref([]);
const searching = ref(false);
const showLeaderboard = ref(true);

// Filter States
const selectedSectors = ref(['cairo', 'alex', 'mansoura', 'assiut']);
const selectedStatuses = ref([1, 2, 3, 4]); // 1: ناجح, 2: دور ثان, 3: راسب, 4: غائب
const minGrade = ref(0);
const maxGrade = ref(320);

// Global Stats (Pre-calculated for instant dashboard loading)
const stats = {
  total: 919396,
  passRate: "75.1%",
  avgGrade: "198.9 (62.1%)",
  absent: 4451
};

// Status mappings
const statusNames = {
  1: 'ناجح دور أول',
  2: 'دور ثان',
  3: 'راسب دور أول ',
  4: 'غياب كلى دور أول '
};

// Sector Info
const sectors = [
  { id: 'cairo', name: 'قطاع القاهرة', desc: 'القاهرة، الجيزة، الفيوم، بني سويف، المنوفية', range: '2,000,000 - 2,380,000' },
  { id: 'alex', name: 'قطاع الإسكندرية', desc: 'الإسكندرية، البحيرة، الغربية، كفر الشيخ، القليوبية', range: '2,380,001 - 2,550,000' },
  { id: 'mansoura', name: 'قطاع المنصورة', desc: 'الدقهلية، الشرقية، دمياط، الإسماعيلية، بورسعيد، السويس، سيناء', range: '2,550,001 - 2,820,000' },
  { id: 'assiut', name: 'قطاع أسيوط', desc: 'أسيوط، المنيا، سوهاج، قنا، الأقصر، أسوان، البحر الأحمر، الوادي الجديد', range: '2,820,001 - 3,000,000' }
];

// IndexedDB Helper functions
const DB_NAME = 'ThanawyaAmmaDB';
const STORE_NAME = 'db_store';
const KEY_NAME = 'students_db_file';

function getCachedDb() {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = (e) => {
      e.target.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = (e) => {
      const idb = e.target.result;
      const transaction = idb.transaction(STORE_NAME, 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const getReq = store.get(KEY_NAME);
      getReq.onsuccess = () => resolve(getReq.result);
      getReq.onerror = () => resolve(null);
    };
    request.onerror = () => resolve(null);
  });
}

function cacheDb(arrayBuffer) {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onsuccess = (e) => {
      const idb = e.target.result;
      const transaction = idb.transaction(STORE_NAME, 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      store.put(arrayBuffer, KEY_NAME);
      transaction.oncomplete = () => resolve(true);
    };
  });
}

// Download database with progress
async function downloadAndDecompressDb() {
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}students.db.gz`);
    if (!response.ok) throw new Error('فشل تحميل قاعدة البيانات من السيرفر (HTTP ' + response.status + ').');

    const reader = response.body.getReader();
    const contentLength = +response.headers.get('Content-Length') || 37280925; // Approx 35.5 MB
    let receivedLength = 0;
    let chunks = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      receivedLength += value.length;
      downloadProgress.value = Math.round((receivedLength / contentLength) * 100);
      totalDownloaded.value = (receivedLength / (1024 * 1024)).toFixed(1) + " MB";
    }

    // Concatenate chunks
    let allChunks = new Uint8Array(receivedLength);
    let position = 0;
    for (let chunk of chunks) {
      allChunks.set(chunk, position);
      position += chunk.length;
    }

    // Inspect magic bytes to verify data format
    const isSQLite = allChunks[0] === 83 && allChunks[1] === 81 && allChunks[2] === 76 && allChunks[3] === 105;
    const isGzip = allChunks[0] === 31 && allChunks[1] === 139;

    let decompressedBuffer;

    if (isSQLite) {
      console.log("Database received already decompressed (auto-decompressed by server/browser).");
      decompressedBuffer = allChunks;
    } else if (isGzip) {
      console.log("Database is compressed. Decompressing...");
      const ds = new DecompressionStream('gzip');
      const writer = ds.writable.getWriter();
      writer.write(allChunks);
      writer.close();

      // Robust stream reader for Safari/WebKit compatibility
      const readerDs = ds.readable.getReader();
      const decompressedChunks = [];
      let decompressedLength = 0;
      while (true) {
        const { done, value } = await readerDs.read();
        if (done) break;
        decompressedChunks.push(value);
        decompressedLength += value.length;
      }

      decompressedBuffer = new Uint8Array(decompressedLength);
      let pos = 0;
      for (let chunk of decompressedChunks) {
        decompressedBuffer.set(chunk, pos);
        pos += chunk.length;
      }
    } else {
      // Check if it is an HTML page (like 404 or router redirect)
      const sampleText = new TextDecoder('utf-8').decode(allChunks.subarray(0, 100));
      if (sampleText.trim().startsWith('<')) {
        throw new Error('الملف المحمل ليس قاعدة بيانات صالحة. يبدو أن الخادم قام بإرجاع صفحة HTML بدلاً من ملف البيانات (تأكد من إعدادات الاستضافة أو مسار الملف).');
      }
      throw new Error('الملف المحمل تالف أو غير صالح (صيغة غير مدعومة).');
    }

    // Save decompressed database to IndexedDB for subsequent visits
    await cacheDb(decompressedBuffer);
    return decompressedBuffer;
  } catch (err) {
    console.error(err);
    throw new Error('حدث خطأ أثناء تحميل قاعدة البيانات أو فك ضغطها: ' + (err.message || err));
  }
}

// Initialize Application
onMounted(async () => {
  // Load Theme
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    isDarkMode.value = true;
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  try {
    loading.value = true;
    // 1. Try to load from Cache (IndexedDB)
    let dbBuffer = await getCachedDb();
    
    // 2. If not cached, download and cache
    if (!dbBuffer) {
      dbBuffer = await downloadAndDecompressDb();
    }

    // 3. Initialize SQLite WASM
    const SQL = await initSqlJs({
      locateFile: file => file.endsWith('.wasm') ? wasmUrl : `${import.meta.env.BASE_URL}${file}`
    });
    
    db.value = new SQL.Database(dbBuffer);
    loading.value = false;
    
    // Initial fetch of leaderboard
    fetchResults();
  } catch (err) {
    error.value = err.message;
    loading.value = false;
  }
});

// Toggle Theme
function toggleTheme() {
  isDarkMode.value = !isDarkMode.value;
  const theme = isDarkMode.value ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

// Clear Cache & Reload
async function clearCacheAndReload() {
  if (confirm("هل تريد مسح قاعدة البيانات المحملة محلياً وإعادة تحميلها من جديد؟")) {
    loading.value = true;
    const request = indexedDB.deleteDatabase(DB_NAME);
    request.onsuccess = () => {
      window.location.reload();
    };
    request.onerror = () => {
      alert("فشل مسح الكاش.");
      window.location.reload();
    };
  }
}

// Fetch Results based on Search & Filters
function fetchResults() {
  if (!db.value) return;
  searching.value = true;

  try {
    let query = "";
    let params = [];

    // Base conditions
    let conditions = [];

    // 1. Status Filter
    if (selectedStatuses.value.length > 0) {
      const placeholders = selectedStatuses.value.map(() => '?').join(',');
      conditions.push(`s.status_id IN (${placeholders})`);
      params.push(...selectedStatuses.value);
    } else {
      results.value = [];
      searching.value = false;
      return;
    }

    // 2. Grade Filter
    conditions.push("s.grade >= ? AND s.grade <= ?");
    params.push(minGrade.value, maxGrade.value);

    // 3. Sector/Seating No Ranges Filter
    let sectorConditions = [];
    if (selectedSectors.value.includes('cairo')) {
      sectorConditions.push("(s.seating_no >= 2000000 AND s.seating_no <= 2380000)");
    }
    if (selectedSectors.value.includes('alex')) {
      sectorConditions.push("(s.seating_no >= 2380001 AND s.seating_no <= 2550000)");
    }
    if (selectedSectors.value.includes('mansoura')) {
      sectorConditions.push("(s.seating_no >= 2550001 AND s.seating_no <= 2820000)");
    }
    if (selectedSectors.value.includes('assiut')) {
      sectorConditions.push("(s.seating_no >= 2820001 AND s.seating_no <= 3000000)");
    }

    if (sectorConditions.length > 0) {
      conditions.push(`(${sectorConditions.join(' OR ')})`);
    } else {
      results.value = [];
      searching.value = false;
      return;
    }

    // 4. Search Filter
    const searchVal = searchQuery.value.trim();
    if (searchVal) {
      showLeaderboard.value = false;
      if (searchMode.value === 'seating') {
        const sno = parseInt(searchVal);
        if (!isNaN(sno)) {
          conditions.push("s.seating_no = ?");
          params.push(sno);
        } else {
          results.value = [];
          searching.value = false;
          return;
        }
      } else {
        // Range query to utilize the name index efficiently: name >= prefix AND name < prefix_upper
        // Normalizing the search text first
        let prefix = searchVal
          .replace(/[أإآا]/g, 'ا')
          .replace(/ة/g, 'ه')
          .replace(/ى/g, 'ي');
        
        conditions.push("s.name >= ? AND s.name < ?");
        params.push(prefix);

        // Calculate upper bound prefix
        const lastChar = prefix.charCodeAt(prefix.length - 1);
        const prefixUpper = prefix.slice(0, -1) + String.fromCharCode(lastChar + 1);
        params.push(prefixUpper);
      }
    } else {
      showLeaderboard.value = true;
    }

    // Assembly Query
    const whereClause = conditions.length > 0 ? "WHERE " + conditions.join(" AND ") : "";
    
    if (showLeaderboard.value) {
      // Show top 100 students matching the filters
      query = `
        SELECT s.seating_no, s.name, s.grade, c.name as status_name 
        FROM students s 
        JOIN statuses c ON s.status_id = c.id
        ${whereClause}
        ORDER BY s.grade DESC 
        LIMIT 100
      `;
    } else {
      // Normal search query
      query = `
        SELECT s.seating_no, s.name, s.grade, c.name as status_name 
        FROM students s 
        JOIN statuses c ON s.status_id = c.id
        ${whereClause}
        ORDER BY s.grade DESC
        LIMIT 100
      `;
    }

    const stmt = db.value.prepare(query);
    stmt.bind(params);

    const tempResults = [];
    while (stmt.step()) {
      const row = stmt.getAsObject();
      tempResults.push({
        seating_no: row.seating_no,
        name: row.name,
        grade: row.grade,
        status: row.status_name
      });
    }
    stmt.free();

    results.value = tempResults;
  } catch (err) {
    console.error("Query Error:", err);
  } finally {
    searching.value = false;
  }
}

// Watch filters for live updates
watch([selectedSectors, selectedStatuses, minGrade, maxGrade, searchMode], () => {
  fetchResults();
}, { deep: true });

// Handle search keyup / click
function handleSearch() {
  fetchResults();
}

function handleSearchModeChange(mode) {
  searchMode.value = mode;
  searchQuery.value = '';
  fetchResults();
}

// Helper to determine status class
function getStatusClass(statusStr) {
  if (statusStr.includes('ناجح')) return 'status-passed';
  if (statusStr.includes('ثان')) return 'status-second';
  if (statusStr.includes('راسب')) return 'status-failed';
  return 'status-absent';
}
</script>

<template>
  <!-- Header -->
  <header class="app-header glass-panel container">
    <div class="logo-section">
      <div class="logo-icon">ت</div>
      <div class="logo-text">
        <h1>بوابة نتائج الثانوية العامة 2026</h1>
        <p>البحث الذكي والسريع في نتائج امتحانات الثانوية العامة</p>
      </div>
    </div>
    
    <div class="header-controls">
      <!-- Clear Cache / Reload -->
      <button class="btn-control" @click="clearCacheAndReload" title="تحديث قاعدة البيانات">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
        </svg>
      </button>

      <!-- Theme Switcher -->
      <button class="btn-control" @click="toggleTheme" title="تغيير المظهر">
        <svg v-if="isDarkMode" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
        </svg>
      </button>
    </div>
  </header>

  <main class="container" style="flex-grow: 1; display: flex; flex-direction: column; gap: 24px; padding-top: 0;">
    <!-- Loading Database State -->
    <div v-if="loading" class="db-loader-container glass-panel">
      <div class="circular-loader">
        <svg>
          <circle class="bg-circle" cx="70" cy="70" r="66"></circle>
          <circle class="progress-circle" cx="70" cy="70" r="66" :style="{ strokeDashoffset: 414 - (414 * downloadProgress) / 100 }"></circle>
        </svg>
        <div class="loader-percentage">{{ downloadProgress }}%</div>
      </div>
      <h2 class="loader-title">جاري تحميل قاعدة البيانات...</h2>
      <p class="loader-subtitle">
        نقوم بتحميل وتجهيز قاعدة البيانات لنتائج امتحانات الثانوية العامة (حوالي {{ totalSize }}). 
        يتم هذا الإجراء مرة واحدة فقط، وسيتم حفظ البيانات على جهازك لتصفحها فوراً في الزيارات القادمة بدون إنترنت وبسرعة فائقة.
      </p>
      <div class="loader-bar-outer">
        <div class="loader-bar-inner" :style="{ width: downloadProgress + '%' }"></div>
      </div>
      <div style="font-size: 12px; margin-top: 10px; color: var(--text-muted); font-family: var(--font-english);">
        {{ totalDownloaded }} / {{ totalSize }}
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="db-loader-container glass-panel" style="color: var(--danger-color);">
      <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 16px;">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <h2 class="loader-title" style="color: var(--text-main);">فشل تشغيل التطبيق</h2>
      <p class="loader-subtitle" style="color: var(--text-muted);">{{ error }}</p>
      <button class="btn-search" style="margin-top: 24px;" @click="clearCacheAndReload">إعادة المحاولة</button>
    </div>

    <!-- Main Content Area -->
    <div v-else style="display: flex; flex-direction: column; gap: 24px;">
      
      <!-- Stats Dashboard Cards -->
      <section class="stats-grid">
        <div class="stat-card glass-panel">
          <div class="stat-icon primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="stat-details">
            <h3>إجمالي الطلاب</h3>
            <div class="stat-val">{{ stats.total.toLocaleString('ar-EG') }}</div>
          </div>
        </div>

        <div class="stat-card glass-panel">
          <div class="stat-icon success">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="stat-details">
            <h3>نسبة النجاح العامة</h3>
            <div class="stat-val">{{ stats.passRate }}</div>
          </div>
        </div>

        <div class="stat-card glass-panel">
          <div class="stat-icon warning">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="6" x2="12" y2="12"/><polyline points="12 12 16 14"/>
            </svg>
          </div>
          <div class="stat-details">
            <h3>متوسط الدرجات</h3>
            <div class="stat-val">{{ stats.avgGrade }}</div>
          </div>
        </div>

        <div class="stat-card glass-panel">
          <div class="stat-icon danger">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
          </div>
          <div class="stat-details">
            <h3>إجمالي الغياب الكلي</h3>
            <div class="stat-val">{{ stats.absent.toLocaleString('ar-EG') }}</div>
          </div>
        </div>
      </section>

      <!-- Search & Workspace Layout -->
      <div class="dashboard-layout">
        
        <!-- Sidebar Filter controls -->
        <aside class="filters-sidebar glass-panel">
          
          <!-- Sector Filters -->
          <div>
            <div class="filter-section-title">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
              </svg>
              <span>القطاعات والمحافظات</span>
            </div>
            <div class="filter-group">
              <label v-for="sec in sectors" :key="sec.id" class="checkbox-label" :title="sec.desc">
                <input type="checkbox" :value="sec.id" v-model="selectedSectors" />
                <div style="display: flex; flex-direction: column;">
                  <span style="font-weight: 700; color: var(--text-main)">{{ sec.name }}</span>
                  <span style="font-size: 10px; color: var(--text-light)">{{ sec.desc }}</span>
                </div>
              </label>
            </div>
          </div>

          <!-- Grade Ranges -->
          <div>
            <div class="filter-section-title">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>
              </svg>
              <span>معدل الدرجات والنسبة</span>
            </div>
            
            <div class="range-container">
              <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
                <span>الحد الأدنى</span>
                <span>الحد الأقصى</span>
              </div>
              <div class="range-inputs">
                <input type="number" min="0" max="320" step="0.5" v-model.number="minGrade" />
                <span style="color: var(--text-light)">إلى</span>
                <input type="number" min="0" max="320" step="0.5" v-model.number="maxGrade" />
              </div>
              
              <div style="margin-top: 10px; display: flex; justify-content: space-between; font-size: 11px; color: var(--primary-color); font-weight: 700;">
                <span>{{ ((minGrade / 320) * 100).toFixed(1) }}%</span>
                <span>{{ ((maxGrade / 320) * 100).toFixed(1) }}%</span>
              </div>
              <input type="range" min="0" max="320" step="0.5" class="range-slider" v-model.number="minGrade" />
              <input type="range" min="0" max="320" step="0.5" class="range-slider" v-model.number="maxGrade" />
            </div>
          </div>

          <!-- Status Filters -->
          <div>
            <div class="filter-section-title">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span>حالة الطالب</span>
            </div>
            <div class="filter-group">
              <label class="checkbox-label">
                <input type="checkbox" :value="1" v-model="selectedStatuses" />
                <span style="color: var(--success-color); font-weight: 700;">ناجح</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" :value="2" v-model="selectedStatuses" />
                <span style="color: var(--warning-color); font-weight: 700;">دور ثانٍ</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" :value="3" v-model="selectedStatuses" />
                <span style="color: var(--danger-color); font-weight: 700;">راسب</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" :value="4" v-model="selectedStatuses" />
                <span style="color: var(--absent-color); font-weight: 700;">غائب كلي</span>
              </label>
            </div>
          </div>

        </aside>

        <!-- Main Query and Dashboard Results -->
        <div class="content-area">
          
          <!-- Search Header Panel -->
          <section class="search-container glass-panel">
            <div class="search-input-wrapper">
              <input 
                type="text" 
                v-model="searchQuery" 
                :placeholder="searchMode === 'name' ? 'أدخل اسم الطالب (مثال: عبدالله محمود عمر...)' : 'أدخل رقم الجلوس المكون من 7 أرقام...'"
                @keyup.enter="handleSearch"
              />
              <svg class="search-icon-svg" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            
            <button class="btn-search" @click="handleSearch">
              <span>ابحث الآن</span>
            </button>
          </section>

          <div style="padding: 0 8px;">
            <div class="search-modes">
              <button 
                class="mode-tab" 
                :class="{ active: searchMode === 'name' }" 
                @click="handleSearchModeChange('name')"
              >
                البحث بالاسم ثنائي فأكثر
              </button>
              <button 
                class="mode-tab" 
                :class="{ active: searchMode === 'seating' }" 
                @click="handleSearchModeChange('seating')"
              >
                البحث برقم الجلوس
              </button>
            </div>
          </div>

          <!-- Leaderboard Panel (National / Filtered top list) -->
          <section v-if="showLeaderboard" class="leaderboard-panel glass-panel">
            <div class="leaderboard-header">
              <div class="leaderboard-title">
                <span style="font-size: 24px;">🏆</span>
                <h2>الطلاب الأوائل (حسب الفلترة الحالية)</h2>
              </div>
              <span class="results-count" style="font-size: 13px;">أعلى 100 طالب</span>
            </div>

            <div class="leaderboard-table-container">
              <table class="leaderboard-table">
                <thead>
                  <tr>
                    <th style="width: 70px; text-align: center;">الترتيب</th>
                    <th style="width: 120px;">رقم الجلوس</th>
                    <th>الاسم الكامل</th>
                    <th style="width: 100px; text-align: center;">الدرجة</th>
                    <th style="width: 100px; text-align: center;">النسبة</th>
                    <th style="width: 130px; text-align: center;">حالة الطالب</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(student, index) in results" :key="student.seating_no">
                    <td style="text-align: center;">
                      <div class="rank-badge" :class="'rank-' + (index + 1) <= 3 ? 'rank-' + (index + 1) : 'rank-other'">
                        {{ index + 1 }}
                      </div>
                    </td>
                    <td style="font-family: var(--font-english); font-weight: 600; color: var(--text-muted)">
                      {{ student.seating_no }}
                    </td>
                    <td style="font-weight: 700; color: var(--text-main)">
                      {{ student.name }}
                    </td>
                    <td style="text-align: center; font-family: var(--font-english); font-weight: 800; font-size: 15px;">
                      {{ student.grade.toFixed(1) }}
                    </td>
                    <td style="text-align: center; font-family: var(--font-english); font-weight: 700; color: var(--primary-color)">
                      {{ ((student.grade / 320) * 100).toFixed(1) }}%
                    </td>
                    <td style="text-align: center;">
                      <span class="student-badge-status" :class="getStatusClass(student.status)" style="position: static; display: inline-block;">
                        {{ student.status }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="results.length === 0" class="empty-state" style="border: none; border-radius: 0;">
                <span class="empty-state-icon">🔍</span>
                <h3>لا توجد نتائج مطابقة</h3>
                <p>يرجى تعديل خيارات الفلترة لعرض الأوائل.</p>
              </div>
            </div>
          </section>

          <!-- Search Results Layout -->
          <section v-else style="display: flex; flex-direction: column; gap: 16px;">
            <div class="results-header">
              <h2 class="results-title">نتائج البحث</h2>
              <span class="results-count">تم العثور على {{ results.length }} طالب</span>
            </div>

            <!-- List Grid -->
            <div v-if="results.length > 0" class="students-list-grid">
              <div v-for="student in results" :key="student.seating_no" class="student-card glass-panel">
                <span class="student-badge-status" :class="getStatusClass(student.status)">
                  {{ student.status }}
                </span>
                
                <div>
                  <div class="student-seating-no">رقم الجلوس: {{ student.seating_no }}</div>
                  <h3 class="student-name">{{ student.name }}</h3>
                </div>

                <div class="student-score-box">
                  <div class="student-grade">
                    <span class="label">المجموع الكلي</span>
                    <span class="val">{{ student.grade.toFixed(1) }} <span>/ 320</span></span>
                  </div>
                  <div class="student-percent">
                    <div class="val">{{ ((student.grade / 320) * 100).toFixed(1) }}%</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Empty Results -->
            <div v-else class="empty-state glass-panel">
              <span class="empty-state-icon">🔍</span>
              <h3>لم نجد أي طالب يطابق البحث</h3>
              <p>تأكد من كتابة الاسم بشكل صحيح بدون حروف الجر أو أخطاء إملائية، أو تأكد من إدخال رقم جلوس صحيح من 7 أرقام.</p>
            </div>
          </section>

        </div>

      </div>

    </div>
  </main>
</template>
