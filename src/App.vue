<script setup>
import { ref, onMounted, watch } from 'vue';
import initSqlJs from 'sql.js';
import wasmUrl from 'sql.js/dist/sql-wasm.wasm?url';

// App States
const db = ref(null);
const loading = ref(false); // Default to false since cloud mode doesn't load database
const downloadProgress = ref(0);
const totalDownloaded = ref("0 MB");
const totalSize = ref("35.5 MB");
const error = ref(null);
const isDarkMode = ref(false);

// Database Mode State
const dbMode = ref('cloud'); // 'cloud' | 'local'

// Query States
const searchQuery = ref('');
const searchMode = ref('name'); // 'name' | 'seating'
const nameMatchMode = ref('prefix'); // 'prefix' | 'exact' | 'contains'
const results = ref([]);
const searching = ref(false);
const showLeaderboard = ref(true);

// Filter States
const selectedSectors = ref(['cairo', 'alex', 'mansoura', 'assiut']);
const selectedStatuses = ref([1, 2, 3, 4]); // 1: ناجح, 2: دور ثان, 3: راسب, 4: غائب
const minGrade = ref(0);
const maxGrade = ref(320);

// Mobile Drawer State
const isDrawerOpen = ref(false);

// Detailed Modal States
const showModal = ref(false);
const selectedStudent = ref(null);
const studentRank = ref(0);
const studentPercentile = ref(0);
const loadingRank = ref(false);

// Chart Data States
const chartGradeData = ref({ g90: 0, g80: 0, g70: 0, g60: 0, g50: 0, g_fail: 0 });
const chartStatusData = ref({ passed: 0, second: 0, failed: 0, absent: 0 });

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

let downloadAbortController = null;

// Download database with progress (with AbortController support)
async function downloadAndDecompressDb() {
  try {
    downloadAbortController = new AbortController();
    const response = await fetch(`${import.meta.env.BASE_URL}students.db.gz`, {
      signal: downloadAbortController.signal
    });
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
    if (err.name === 'AbortError') {
      throw new Error('تم إلغاء تحميل قاعدة البيانات بطلب من المستخدم.');
    }
    console.error(err);
    throw new Error('حدث خطأ أثناء تحميل قاعدة البيانات أو فك ضغطها: ' + (err.message || err));
  } finally {
    downloadAbortController = null;
  }
}

// Lazy initializer for local offline SQLite database
async function initLocalDatabase() {
  if (db.value) return; // Already initialized
  
  loading.value = true;
  error.value = null;
  try {
    let dbBuffer = await getCachedDb();
    if (!dbBuffer) {
      dbBuffer = await downloadAndDecompressDb();
    }
    const SQL = await initSqlJs({
      locateFile: file => file.endsWith('.wasm') ? wasmUrl : `${import.meta.env.BASE_URL}${file}`
    });
    db.value = new SQL.Database(dbBuffer);
  } catch (err) {
    error.value = err.message;
    throw err;
  } finally {
    loading.value = false;
  }
}

// Prompt and switch DB Mode states
const showDownloadPrompt = ref(false);

async function startDbDownload() {
  showDownloadPrompt.value = false;
  try {
    await initLocalDatabase();
    dbMode.value = 'local';
    localStorage.setItem('db_mode', 'local');
    fetchResults();
  } catch (e) {
    console.error("Local DB download and init failed, falling back to Cloud:", e);
    dbMode.value = 'cloud';
  }
}

function cancelDownload() {
  if (downloadAbortController) {
    downloadAbortController.abort();
    downloadAbortController = null;
  }
  loading.value = false;
  showDownloadPrompt.value = false;
  dbMode.value = 'cloud';
  localStorage.setItem('db_mode', 'cloud');
  fetchResults();
}

async function setDbMode(mode) {
  if (mode === 'local') {
    const cached = await getCachedDb();
    if (cached) {
      try {
        await initLocalDatabase();
        dbMode.value = 'local';
        localStorage.setItem('db_mode', 'local');
        fetchResults();
      } catch (e) {
        console.error("Failed to load cached local DB:", e);
        dbMode.value = 'cloud';
      }
    } else {
      // Show confirmation prompt before downloading heavy database!
      showDownloadPrompt.value = true;
    }
  } else {
    // Return to Cloud mode
    dbMode.value = 'cloud';
    localStorage.setItem('db_mode', 'cloud');
    fetchResults();
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

  // Load Operation Mode
  const savedMode = localStorage.getItem('db_mode') || 'cloud';
  if (savedMode === 'local') {
    try {
      await initLocalDatabase();
      dbMode.value = 'local';
    } catch (e) {
      console.error("Failed to load local DB on mount, falling back to Cloud:", e);
      dbMode.value = 'cloud';
      fetchResults();
    }
  } else {
    dbMode.value = 'cloud';
    fetchResults();
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

// Normalize Arabic names
function normalizeArabic(text) {
  return text
    .replace(/[أإآا]/g, 'ا')
    .replace(/ة/g, 'ه')
    .replace(/ى/g, 'ي')
    .trim();
}

// Build SQL where conditions based on active filters (for local query)
function buildWhereClause() {
  let conditions = [];
  let params = [];

  if (selectedStatuses.value.length > 0) {
    const placeholders = selectedStatuses.value.map(() => '?').join(',');
    conditions.push(`s.status_id IN (${placeholders})`);
    params.push(...selectedStatuses.value);
  } else {
    return { clause: "WHERE 1=0", params: [] };
  }

  conditions.push("s.grade >= ? AND s.grade <= ?");
  params.push(minGrade.value, maxGrade.value);

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
    return { clause: "WHERE 1=0", params: [] };
  }

  const searchVal = searchQuery.value.trim();
  if (searchVal) {
    showLeaderboard.value = false;
    if (searchMode.value === 'seating') {
      const sno = parseInt(searchVal);
      if (!isNaN(sno)) {
        conditions.push("s.seating_no = ?");
        params.push(sno);
      } else {
        return { clause: "WHERE 1=0", params: [] };
      }
    } else {
      let prefix = normalizeArabic(searchVal);
      if (nameMatchMode.value === 'exact') {
        conditions.push("s.name = ?");
        params.push(prefix);
      } else if (nameMatchMode.value === 'contains') {
        conditions.push("s.name LIKE ?");
        params.push(`%${prefix}%`);
      } else {
        conditions.push("s.name >= ? AND s.name < ?");
        params.push(prefix);

        const lastChar = prefix.charCodeAt(prefix.length - 1);
        const prefixUpper = prefix.slice(0, -1) + String.fromCharCode(lastChar + 1);
        params.push(prefixUpper);
      }
    }
  } else {
    showLeaderboard.value = true;
  }

  const clause = conditions.length > 0 ? "WHERE " + conditions.join(" AND ") : "";
  return { clause, params };
}

// Fetch Results based on Search & Filters
async function fetchResults() {
  searching.value = true;

  if (dbMode.value === 'cloud') {
    try {
      const params = new URLSearchParams();
      params.append('q', searchQuery.value.trim());
      params.append('mode', searchMode.value);
      params.append('match', nameMatchMode.value);
      params.append('sectors', selectedSectors.value.join(','));
      params.append('statuses', selectedStatuses.value.join(','));
      params.append('min_grade', minGrade.value);
      params.append('max_grade', maxGrade.value);
      params.append('limit', 100);

      // Fetch from Serverless API
      const response = await fetch(`/api/search?${params.toString()}`);
      if (!response.ok) throw new Error('API request failed');

      const data = await response.json();
      results.value = data.results || [];
      chartGradeData.value = data.charts.grades || { g90: 0, g80: 0, g70: 0, g60: 0, g50: 0, g_fail: 0 };
      chartStatusData.value = data.charts.statuses || { passed: 0, second: 0, failed: 0, absent: 0 };
      showLeaderboard.value = !searchQuery.value.trim();
    } catch (err) {
      console.error("Cloud search error:", err);
      results.value = [];
    } finally {
      searching.value = false;
    }
  } else {
    // Local SQLite Mode
    if (!db.value) return;
    try {
      const { clause, params } = buildWhereClause();
      if (clause === "WHERE 1=0") {
        results.value = [];
        searching.value = false;
        return;
      }

      const query = `
        SELECT s.seating_no, s.name, s.grade, c.name as status_name 
        FROM students s 
        JOIN statuses c ON s.status_id = c.id
        ${clause}
        ORDER BY s.grade DESC
        LIMIT 100
      `;

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

      // Trigger debounced update of charts
      updateChartsData(clause, params);
    } catch (err) {
      console.error("Local Query Error:", err);
    } finally {
      searching.value = false;
    }
  }
}

// Debounced charts update to keep UI responsive
let chartTimeout = null;
function updateChartsData(clause, params) {
  if (chartTimeout) clearTimeout(chartTimeout);
  chartTimeout = setTimeout(() => {
    runChartsQuery(clause, params);
  }, 350);
}

// Aggregate data for SVG charts (Local Mode)
function runChartsQuery(clause, params) {
  if (!db.value) return;
  try {
    const gradeQuery = `
      SELECT 
        SUM(CASE WHEN grade >= 288 THEN 1 ELSE 0 END) as g90,
        SUM(CASE WHEN grade >= 256 AND grade < 288 THEN 1 ELSE 0 END) as g80,
        SUM(CASE WHEN grade >= 224 AND grade < 256 THEN 1 ELSE 0 END) as g70,
        SUM(CASE WHEN grade >= 192 AND grade < 224 THEN 1 ELSE 0 END) as g60,
        SUM(CASE WHEN grade >= 160 AND grade < 192 THEN 1 ELSE 0 END) as g50,
        SUM(CASE WHEN grade < 160 THEN 1 ELSE 0 END) as g_fail
      FROM students s
      ${clause}
    `;
    const gradeStmt = db.value.prepare(gradeQuery);
    gradeStmt.bind(params);
    if (gradeStmt.step()) {
      const row = gradeStmt.getAsObject();
      chartGradeData.value = {
        g90: row.g90 || 0,
        g80: row.g80 || 0,
        g70: row.g70 || 0,
        g60: row.g60 || 0,
        g50: row.g50 || 0,
        g_fail: row.g_fail || 0
      };
    }
    gradeStmt.free();

    const statusQuery = `
      SELECT s.status_id, COUNT(*) as cnt 
      FROM students s
      ${clause}
      GROUP BY s.status_id
    `;
    const statusStmt = db.value.prepare(statusQuery);
    statusStmt.bind(params);
    let counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    while (statusStmt.step()) {
      const row = statusStmt.getAsObject();
      counts[row.status_id] = row.cnt;
    }
    statusStmt.free();

    chartStatusData.value = {
      passed: counts[1],
      second: counts[2],
      failed: counts[3],
      absent: counts[4]
    };
  } catch (err) {
    console.error("Charts aggregation error:", err);
  }
}

// Watch filters for live updates
watch([selectedSectors, selectedStatuses, minGrade, maxGrade, searchMode, nameMatchMode], () => {
  fetchResults();
}, { deep: true });

// Handle search trigger
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
  if (!statusStr) return 'status-absent';
  if (statusStr.includes('ناجح')) return 'status-passed';
  if (statusStr.includes('ثان')) return 'status-second';
  if (statusStr.includes('راسب')) return 'status-failed';
  return 'status-absent';
}

// Circular progress dashoffset calculator
const dashArray = 440;
function getDashOffset(percentage) {
  return dashArray - (dashArray * percentage) / 100;
}

// Detailed modal calculations
async function openStudentDetails(student) {
  selectedStudent.value = student;
  showModal.value = true;
  loadingRank.value = true;
  studentRank.value = 0;
  studentPercentile.value = 0;

  setTimeout(async () => {
    if (!selectedStudent.value) return;
    
    if (dbMode.value === 'cloud') {
      try {
        const response = await fetch(`/api/rank?grade=${selectedStudent.value.grade}`);
        if (!response.ok) throw new Error();
        const data = await response.json();
        studentRank.value = data.rank;
        studentPercentile.value = data.percentile;
      } catch (e) {
        console.error("Cloud rank calculation error:", e);
      } finally {
        loadingRank.value = false;
      }
    } else {
      // Local SQLite Mode
      if (!db.value) return;
      try {
        const currentGrade = selectedStudent.value.grade;
        const rankQuery = "SELECT COUNT(*) + 1 as rank FROM students WHERE grade > ?";
        const stmt = db.value.prepare(rankQuery);
        stmt.bind([currentGrade]);
        if (stmt.step()) {
          const row = stmt.getAsObject();
          studentRank.value = row.rank;
          const percentile = ((919396 - row.rank) / 919396) * 100;
          studentPercentile.value = Math.max(0.1, Math.min(100, percentile));
        }
        stmt.free();
      } catch (err) {
        console.error("Local Rank calculation error:", err);
      } finally {
        loadingRank.value = false;
      }
    }
  }, 200);
}

function closeStudentDetails() {
  showModal.value = false;
  selectedStudent.value = null;
}

// Export data to CSV
function exportToCSV() {
  if (results.value.length === 0) return;
  try {
    let csvContent = "\uFEFF"; // UTF-8 BOM to fix Arabic excel rendering
    csvContent += "رقم الجلوس,الاسم الكامل,الدرجة الكلية,النسبة المئوية,حالة الطالب\n";

    results.value.forEach(row => {
      const percentage = ((row.grade / 320) * 100).toFixed(2) + "%";
      const cleanName = row.name.replace(/,/g, ' '); // Avoid CSV splitting on comma inside name
      csvContent += `${row.seating_no},${cleanName},${row.grade.toFixed(1)},${percentage},${row.status}\n`;
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "نتائج_البحث_الثانوية_العامة.csv");
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (err) {
    console.error("CSV Export error:", err);
    alert("حدث خطأ أثناء تصدير الملف.");
  }
}

// Helper to count totals in charts to prevent division by zero
const getSum = (obj) => Object.values(obj).reduce((a, b) => a + b, 0);

// Calculate donut segment path (with circular-collapse bug fix)
function getDonutSegment(percentage, previousPercentage, radius = 50) {
  const cx = 65;
  const cy = 80;
  const startAngle = (previousPercentage * 360) / 100 - 90;
  // Subtract 0.01 degree if it is a full circle (100%) so that start and end coords don't match exactly
  const endAngle = ((previousPercentage + percentage) * 360) / 100 - 90 - (percentage === 100 ? 0.01 : 0);

  const rad = Math.PI / 180;
  const x1 = cx + radius * Math.cos(startAngle * rad);
  const y1 = cy + radius * Math.sin(startAngle * rad);
  const x2 = cx + radius * Math.cos(endAngle * rad);
  const y2 = cy + radius * Math.sin(endAngle * rad);

  const largeArcFlag = percentage > 50 ? 1 : 0;
  return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2}`;
}

// Comparison Mode States & Functions
const comparedStudents = ref([]);
const showComparisonModal = ref(false);
const compareRanks = ref([0, 0]);
const comparePercentiles = ref([0, 0]);
const loadingCompare = ref(false);

function toggleCompare(student) {
  const idx = comparedStudents.value.findIndex(s => s.seating_no === student.seating_no);
  if (idx !== -1) {
    comparedStudents.value.splice(idx, 1);
  } else {
    if (comparedStudents.value.length < 2) {
      comparedStudents.value.push(student);
    }
  }
}

async function startComparison() {
  if (comparedStudents.value.length !== 2) return;
  showComparisonModal.value = true;
  loadingCompare.value = true;
  compareRanks.value = [0, 0];
  comparePercentiles.value = [0, 0];
  
  try {
    const [s1, s2] = comparedStudents.value;
    
    if (dbMode.value === 'cloud') {
      const [res1, res2] = await Promise.all([
        fetch(`/api/rank?grade=${s1.grade}`),
        fetch(`/api/rank?grade=${s2.grade}`)
      ]);
      if (!res1.ok || !res2.ok) throw new Error('API failed');
      const [d1, d2] = await Promise.all([res1.json(), res2.json()]);
      compareRanks.value = [d1.rank || 1, d2.rank || 1];
      comparePercentiles.value = [d1.percentile || 0.1, d2.percentile || 0.1];
    } else {
      if (!db.value) return;
      const rankQuery = "SELECT COUNT(*) + 1 as rank FROM students WHERE grade > ?";
      const stmt = db.value.prepare(rankQuery);
      
      // Student 1
      stmt.bind([s1.grade]);
      let r1 = 1;
      if (stmt.step()) r1 = stmt.getAsObject().rank;
      stmt.reset();
      
      // Student 2
      stmt.bind([s2.grade]);
      let r2 = 1;
      if (stmt.step()) r2 = stmt.getAsObject().rank;
      stmt.free();
      
      compareRanks.value = [r1, r2];
      const total = 919396;
      comparePercentiles.value = [
        Math.max(0.1, ((total - r1) / total) * 100),
        Math.max(0.1, ((total - r2) / total) * 100)
      ];
    }
  } catch (e) {
    console.error("Comparison ranking query failed:", e);
  } finally {
    loadingCompare.value = false;
  }
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
      <!-- Database Operation Mode Selector -->
      <div class="search-modes" style="margin-top: 0; background: var(--bg-card); padding: 3px; border-radius: 20px; border: 1px solid var(--border-color); display: flex; gap: 2px;">
        <button 
          class="mode-tab" 
          :class="{ active: dbMode === 'cloud' }" 
          @click="setDbMode('cloud')"
          style="padding: 4px 10px; font-size: 11px; border-radius: 16px;"
          title="التشغيل السحابي بدون تحميل بيانات"
        >
          سحابي ☁️
        </button>
        <button 
          class="mode-tab" 
          :class="{ active: dbMode === 'local' }" 
          @click="setDbMode('local')"
          style="padding: 4px 10px; font-size: 11px; border-radius: 16px;"
          title="تحميل قاعدة البيانات بالكامل وتصفحها أوفلاين"
        >
          أوفلاين 💾
        </button>
      </div>

      <!-- Clear Cache / Reload -->
      <button class="btn-control" @click="clearCacheAndReload" title="تحديث قاعدة البيانات" v-if="dbMode === 'local'">
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
        سيتم حفظ البيانات على جهازك لتصفحها فوراً في الزيارات القادمة بدون إنترنت وبسرعة فائقة.
      </p>
      <div class="loader-bar-outer">
        <div class="loader-bar-inner" :style="{ width: downloadProgress + '%' }"></div>
      </div>
      <div style="font-size: 12px; margin-top: 10px; color: var(--text-muted); font-family: var(--font-english);">
        {{ totalDownloaded }} / {{ totalSize }}
      </div>
      <button 
        class="btn-search" 
        style="margin-top: 20px; background: rgba(239, 68, 68, 0.1); color: var(--danger-color); border: 1px solid var(--danger-color); font-weight: 700;"
        @click="cancelDownload"
      >
        إلغاء التحميل والعودة للوضع السحابي ☁️
      </button>
    </div>

    <!-- Download Confirmation Prompt State -->
    <div v-else-if="showDownloadPrompt" class="db-loader-container glass-panel" style="text-align: center;">
      <div style="font-size: 54px; margin-bottom: 12px; animation: bounce 1.2s infinite alternate;">📥</div>
      <h2 class="loader-title" style="color: var(--text-main);">تفعيل وضع التشغيل المحلي (أوفلاين)</h2>
      <p class="loader-subtitle" style="max-width: 480px; margin: 12px auto; line-height: 1.6; color: var(--text-muted);">
        يتطلب الانتقال للوضع المحلي تحميل ملف قاعدة بيانات نتائج الشهادة الثانوية العامة (حوالي {{ totalSize }}). 
        سيتم تحميل وحفظ الملف في ذاكرة متصفحك لمرة واحدة فقط لتتمكن من التصفح والبحث بدون إنترنت وبسرعة فائقة جداً وبخصوصية تامة.
      </p>
      <div style="display: flex; gap: 12px; justify-content: center; margin-top: 24px; flex-wrap: wrap;">
        <button class="btn-search" @click="startDbDownload" style="margin: 0; padding: 10px 24px;">بدء تحميل قاعدة البيانات 💾</button>
        <button class="btn-export" @click="cancelDownload" style="margin: 0; padding: 10px 24px;">العودة للوضع السحابي ☁️</button>
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
      
      <!-- HERO SEARCH SECTION (First thing visible for UI/UX excellence) -->
      <section class="glass-panel" style="padding: 24px; display: flex; flex-direction: column; gap: 16px; border-radius: 20px; box-shadow: var(--shadow-sm);">
        <div class="search-container" style="box-shadow: none; padding: 0; background: transparent; border: none; margin: 0;">
          <div class="search-input-wrapper">
            <input 
              type="text" 
              v-model="searchQuery" 
              :placeholder="searchMode === 'name' ? 'أدخل اسم الطالب (مثال: نغم ياسر...)' : 'أدخل رقم الجلوس المكون من 7 أرقام...'"
              @keyup.enter="handleSearch"
            />
            <svg class="search-icon-svg" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          
          <button class="btn-search" @click="handleSearch">
            <span>ابحث الآن</span>
          </button>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
          <!-- Search mode: Name vs Seating -->
          <div class="search-modes" style="margin: 0;">
            <button 
              class="mode-tab" 
              :class="{ active: searchMode === 'name' }" 
              @click="handleSearchModeChange('name')"
            >
              البحث بالاسم
            </button>
            <button 
              class="mode-tab" 
              :class="{ active: searchMode === 'seating' }" 
              @click="handleSearchModeChange('seating')"
            >
              البحث برقم الجلوس
            </button>
          </div>

          <!-- Name matching options -->
          <div v-if="searchMode === 'name'" class="search-modes" style="margin: 0; background: var(--bg-card); padding: 4px; border-radius: 20px; border: 1px solid var(--border-color);">
            <button 
              class="mode-tab" 
              :class="{ active: nameMatchMode === 'prefix' }" 
              @click="nameMatchMode = 'prefix'"
              title="يبحث عن الأسماء التي تبدأ بالمدخل (سريع جداً)"
            >
              يبدأ بـ
            </button>
            <button 
              class="mode-tab" 
              :class="{ active: nameMatchMode === 'exact' }" 
              @click="nameMatchMode = 'exact'"
              title="مطابقة الاسم الكامل تماماً"
            >
              مطابقة تامة
            </button>
            <button 
              class="mode-tab" 
              :class="{ active: nameMatchMode === 'contains' }" 
              @click="nameMatchMode = 'contains'"
              title="يبحث عن أي جزء بالاسم (قد يستغرق ثوانٍ)"
            >
              يحتوي على
            </button>
          </div>
        </div>
      </section>

      <!-- Dashboard Grid Layout -->
      <div class="dashboard-layout">
        
        <!-- Filters Sidebar Drawer -->
        <div v-if="isDrawerOpen" class="drawer-backdrop" @click="isDrawerOpen = false"></div>
        
        <aside class="filters-sidebar glass-panel" :class="{ 'drawer-open': isDrawerOpen }">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;" v-if="isDrawerOpen">
            <h3 style="font-size: 16px; font-weight: 800;">تصفية وفرز النتائج</h3>
            <button class="btn-control" @click="isDrawerOpen = false" style="padding: 6px 12px; font-size: 12px;">إغلاق</button>
          </div>

          <!-- Sectors mapping -->
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

          <!-- Grade Range -->
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

          <!-- Status -->
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

        <!-- Main Query Results Area -->
        <div class="content-area" style="display: flex; flex-direction: column; gap: 24px;">
          
          <!-- Results Area -->
          <div class="glass-panel" style="padding: 20px; border-radius: 20px; display: flex; flex-direction: column; gap: 16px;">
            <div class="results-header" style="margin-top: 0; padding-bottom: 12px; border-bottom: 1px solid var(--border-color);">
              <div style="display: flex; align-items: center; gap: 8px;">
                <h2 class="results-title" style="font-size: 18px; font-weight: 800;">{{ showLeaderboard ? 'الطلاب الأوائل (حسب الفلترة)' : 'نتائج البحث الحالي' }}</h2>
                <span class="results-count" style="padding: 2px 10px;">{{ results.length }} طالب</span>
              </div>

              <!-- CSV Export button -->
              <button v-if="results.length > 0" class="btn-export" @click="exportToCSV" title="تصدير النتائج كملف Excel">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                <span>تحميل التقرير (Excel)</span>
              </button>
            </div>

            <!-- Loader inside results area -->
            <div v-if="searching" style="padding: 60px; text-align: center; color: var(--primary-color);">
              <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid var(--primary-glow); border-top-color: var(--primary-color); border-radius: 50%; animation: spin 1s infinite linear;"></div>
              <h4 style="margin-top: 16px; font-weight: 700; color: var(--text-main);">جاري جلب النتائج...</h4>
            </div>

            <div v-else>
              <!-- 1. Desktop Results Table (hidden on mobile) -->
              <div class="table-responsive-desktop">
                <table class="leaderboard-table" style="min-width: 100%;">
                  <thead>
                    <tr>
                      <th style="width: 60px; text-align: center;">#</th>
                      <th style="width: 120px;">رقم الجلوس</th>
                      <th>الاسم الكامل</th>
                      <th style="width: 100px; text-align: center;">الدرجة</th>
                      <th style="width: 100px; text-align: center;">النسبة</th>
                      <th style="width: 130px; text-align: center;">حالة الطالب</th>
                      <th style="width: 80px; text-align: center;">مقارنة</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(student, index) in results" :key="student.seating_no" @click="openStudentDetails(student)" style="cursor: pointer;">
                      <td style="text-align: center;">
                        <div class="rank-badge" :class="index < 3 ? 'rank-' + (index + 1) : 'rank-other'">
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
                      <td style="text-align: center;" @click.stop>
                        <input 
                          type="checkbox" 
                          :checked="comparedStudents.some(s => s.seating_no === student.seating_no)"
                          @change="toggleCompare(student)"
                          :disabled="comparedStudents.length >= 2 && !comparedStudents.some(s => s.seating_no === student.seating_no)"
                          style="cursor: pointer;"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- 2. Mobile Results Cards Fallback (hidden on desktop, beautiful on mobile) -->
              <div class="cards-responsive-mobile" style="padding: 0;">
                <div 
                  v-for="(student, index) in results" 
                  :key="student.seating_no" 
                  class="student-mobile-card glass-panel" 
                  @click="openStudentDetails(student)"
                  style="border-radius: 12px; padding: 14px;"
                >
                  <div class="card-header">
                    <span class="card-rank">#{{ index + 1 }}</span>
                    <div style="display: flex; gap: 6px; align-items: center; margin-right: auto; margin-left: 0;">
                      <button 
                        @click.stop="toggleCompare(student)"
                        style="padding: 2px 8px; font-size: 10px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--bg-card); cursor: pointer;"
                        :style="comparedStudents.some(s => s.seating_no === student.seating_no) ? 'border-color: var(--primary-color); background: var(--primary-glow); color: var(--primary-color); font-weight: 700;' : ''"
                        :disabled="comparedStudents.length >= 2 && !comparedStudents.some(s => s.seating_no === student.seating_no)"
                      >
                        ⚖️ مقارنة
                      </button>
                      <span class="student-badge-status" :class="getStatusClass(student.status)" style="position: static; font-size: 10px; padding: 2px 8px;">
                        {{ student.status }}
                      </span>
                    </div>
                  </div>
                  <h3 style="font-size: 15px; font-weight: 800; color: var(--text-main); margin: 6px 0;">{{ student.name }}</h3>
                  <div class="card-footer" style="padding-top: 8px;">
                    <span class="card-seating">جلوس: {{ student.seating_no }}</span>
                    <div class="card-grade-box">
                      <span class="card-grade-val" style="font-size: 16px;">{{ student.grade.toFixed(1) }}</span>
                      <span class="card-grade-pct" style="font-size: 11px;">{{ ((student.grade / 320) * 100).toFixed(1) }}%</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Empty State -->
              <div v-if="results.length === 0" class="empty-state" style="border: none; padding: 40px 20px;">
                <span class="empty-state-icon">🔍</span>
                <h3>لا توجد نتائج مطابقة</h3>
                <p>تأكد من خيارات الفلترة أو النص المدخل في شريط البحث.</p>
              </div>
            </div>
          </div>

          <!-- ANALYTICS DASHBOARD (Now pushed to bottom for better query UX) -->
          <div style="display: flex; flex-direction: column; gap: 24px;">
            <h2 style="font-size: 18px; font-weight: 800; padding: 0 4px;">📈 لوحة تحليلات البيانات الحالية</h2>
            
            <!-- Stats Dashboard Cards -->
            <section class="stats-grid" style="margin: 0; padding: 0; width: 100%;">
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
                  <h3>إجمالي الغياب</h3>
                  <div class="stat-val">{{ stats.absent.toLocaleString('ar-EG') }}</div>
                </div>
              </div>
            </section>

            <!-- Sector Geographic Breakdown (Premium Educational context) -->
            <section class="glass-panel" style="padding: 20px; border-radius: 20px; display: flex; flex-direction: column; gap: 12px; margin-bottom: 0;">
              <h3 style="font-size: 15px; font-weight: 800; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">🗺️ المؤشرات الجغرافية العامة للقطاعات</h3>
              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px;">
                <div style="padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 12px; text-align: center;">
                  <span style="font-size: 11px; color: var(--text-muted); font-weight: 700;">قطاع القاهرة</span>
                  <div style="font-size: 20px; font-weight: 800; color: var(--primary-color); margin-top: 4px; font-family: var(--font-english);">76.8%</div>
                </div>
                <div style="padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 12px; text-align: center;">
                  <span style="font-size: 11px; color: var(--text-muted); font-weight: 700;">قطاع الإسكندرية</span>
                  <div style="font-size: 20px; font-weight: 800; color: var(--primary-color); margin-top: 4px; font-family: var(--font-english);">74.2%</div>
                </div>
                <div style="padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 12px; text-align: center;">
                  <span style="font-size: 11px; color: var(--text-muted); font-weight: 700;">قطاع المنصورة</span>
                  <div style="font-size: 20px; font-weight: 800; color: var(--primary-color); margin-top: 4px; font-family: var(--font-english);">78.5%</div>
                </div>
                <div style="padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 12px; text-align: center;">
                  <span style="font-size: 11px; color: var(--text-muted); font-weight: 700;">قطاع أسيوط</span>
                  <div style="font-size: 20px; font-weight: 800; color: var(--primary-color); margin-top: 4px; font-family: var(--font-english);">71.9%</div>
                </div>
              </div>
            </section>

            <!-- SVG Charts (Visual Analytics) -->
            <section class="charts-container" style="margin: 0; padding: 0;">
              <!-- Grade Distribution Bar Chart -->
              <div class="chart-card glass-panel" style="min-height: 240px;">
                <h3 class="chart-title">📊 توزيع درجات الفئة المفلترة</h3>
                <div class="chart-wrapper">
                  <svg viewBox="0 0 400 200" width="100%" height="100%">
                    <g v-if="getSum(chartGradeData) > 0">
                      <line x1="40" y1="160" x2="380" y2="160" stroke="var(--border-color)" stroke-width="2" />
                      
                      <g v-for="(val, key, index) in chartGradeData" :key="key">
                        <rect
                          :x="55 + index * 55"
                          :y="160 - (val / Math.max(...Object.values(chartGradeData))) * 130"
                          width="30"
                          :height="(val / Math.max(...Object.values(chartGradeData))) * 130"
                          fill="url(#barGradient)"
                          rx="4"
                        />
                        <text :x="70 + index * 55" y="178" font-size="10" text-anchor="middle" fill="var(--text-muted)" font-weight="700">
                          {{ key === 'g90' ? '+90%' : key === 'g80' ? '80%' : key === 'g70' ? '70%' : key === 'g60' ? '60%' : key === 'g50' ? '50%' : 'رسوب' }}
                        </text>
                        <text :x="70 + index * 55" :y="150 - (val / Math.max(...Object.values(chartGradeData))) * 130" font-size="10" text-anchor="middle" fill="var(--text-main)" font-weight="700">
                          {{ val >= 1000 ? (val / 1000).toFixed(1) + 'k' : val }}
                        </text>
                      </g>
                    </g>
                    <text v-else x="200" y="100" text-anchor="middle" fill="var(--text-light)" font-size="14">لا توجد بيانات درجات للتمثيل البياني</text>
                    <defs>
                      <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--primary-color)" />
                        <stop offset="100%" stop-color="#818cf8" stop-opacity="0.3" />
                      </linearGradient>
                    </defs>
                  </svg>
                </div>
              </div>

              <!-- Status Distribution Donut Chart -->
              <div class="chart-card glass-panel" style="min-height: 240px;">
                <h3 class="chart-title">🍩 نسبة حالات طلاب الفئة المفلترة</h3>
                <div class="chart-wrapper">
                  <svg viewBox="0 0 200 160" width="100%" height="100%">
                    <g v-if="getSum(chartStatusData) > 0">
                      <path
                        v-if="chartStatusData.passed > 0"
                        :d="getDonutSegment((chartStatusData.passed / getSum(chartStatusData)) * 100, 0)"
                        fill="none"
                        stroke="var(--success-color)"
                        stroke-width="15"
                      />
                      <path
                        v-if="chartStatusData.second > 0"
                        :d="getDonutSegment((chartStatusData.second / getSum(chartStatusData)) * 100, (chartStatusData.passed / getSum(chartStatusData)) * 100)"
                        fill="none"
                        stroke="var(--warning-color)"
                        stroke-width="15"
                      />
                      <path
                        v-if="chartStatusData.failed > 0"
                        :d="getDonutSegment(
                          (chartStatusData.failed / getSum(chartStatusData)) * 100, 
                          ((chartStatusData.passed + chartStatusData.second) / getSum(chartStatusData)) * 100
                        )"
                        fill="none"
                        stroke="var(--danger-color)"
                        stroke-width="15"
                      />
                      <path
                        v-if="chartStatusData.absent > 0"
                        :d="getDonutSegment(
                          (chartStatusData.absent / getSum(chartStatusData)) * 100, 
                          ((chartStatusData.passed + chartStatusData.second + chartStatusData.failed) / getSum(chartStatusData)) * 100
                        )"
                        fill="none"
                        stroke="var(--absent-color)"
                        stroke-width="15"
                      />

                      <text x="65" y="85" text-anchor="middle" font-size="14" font-weight="800" fill="var(--text-main)">
                        {{ getSum(chartStatusData) >= 1000 ? (getSum(chartStatusData) / 1000).toFixed(1) + 'k' : getSum(chartStatusData) }}
                      </text>
                      <text x="65" y="98" text-anchor="middle" font-size="8" fill="var(--text-muted)">المجموع</text>

                      <g transform="translate(135, 30)" font-size="9" font-weight="700">
                        <circle cx="0" cy="0" r="4" fill="var(--success-color)" />
                        <text x="10" y="3" fill="var(--text-muted)">ناجح</text>

                        <circle cx="0" cy="20" r="4" fill="var(--warning-color)" />
                        <text x="10" y="23" fill="var(--text-muted)">دور ثان</text>

                        <circle cx="0" cy="40" r="4" fill="var(--danger-color)" />
                        <text x="10" y="43" fill="var(--text-muted)">راسب</text>

                        <circle cx="0" cy="60" r="4" fill="var(--absent-color)" />
                        <text x="10" y="63" fill="var(--text-muted)">غائب</text>
                      </g>
                    </g>
                    <text v-else x="100" y="80" text-anchor="middle" fill="var(--text-light)" font-size="14">لا توجد بيانات للتمثيل البياني</text>
                  </svg>
                </div>
              </div>
            </section>
          </div>

        </div>

      </div>

    </div>
  </main>

  <!-- Floating Action Button for Mobile Filters Drawer -->
  <button class="btn-fab" @click="isDrawerOpen = true" title="تصفية وتصنيف النتائج">
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
    </svg>
  </button>

  <!-- Detailed Student Report Modal -->
  <div v-if="showModal && selectedStudent" class="modal-backdrop" @click.self="closeStudentDetails">
    <div class="modal-content glass-panel">
      <button class="modal-close" @click="closeStudentDetails">✕</button>
      
      <div style="text-align: center; margin-bottom: 16px;">
        <span style="font-size: 11px; color: var(--text-light); font-weight: 600; font-family: var(--font-english);">رقم الجلوس: {{ selectedStudent.seating_no }}</span>
        <h2 style="font-size: 18px; font-weight: 800; color: var(--text-main); margin-top: 4px; line-height: 1.4;">{{ selectedStudent.name }}</h2>
      </div>

      <!-- Circular Grade Gauge -->
      <div class="gauge-container">
        <svg class="gauge-svg">
          <circle class="gauge-bg" cx="75" cy="75" r="70"></circle>
          <circle class="gauge-fill" cx="75" cy="75" r="70" :style="{ strokeDashoffset: getDashOffset((selectedStudent.grade / 320) * 100) }"></circle>
          
          <defs>
            <linearGradient id="gauge-gradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="var(--primary-color)" />
              <stop offset="100%" stop-color="var(--success-color)" />
            </linearGradient>
          </defs>
        </svg>
        <div class="gauge-text">
          <span class="gauge-percent">{{ ((selectedStudent.grade / 320) * 100).toFixed(1) }}%</span>
          <span class="gauge-label">{{ selectedStudent.grade.toFixed(1) }} / 320 درجة</span>
        </div>
      </div>

      <!-- Detailed Stats List -->
      <div class="modal-stats-list">
        <div class="modal-stat-row">
          <span class="modal-stat-label">الحالة العامة</span>
          <span class="student-badge-status" :class="getStatusClass(selectedStudent.status)" style="position: static; display: inline-block;">
            {{ selectedStudent.status }}
          </span>
        </div>

        <div class="modal-stat-row">
          <span class="modal-stat-label">الترتيب على الجمهورية</span>
          <span v-if="loadingRank" class="modal-stat-val" style="color: var(--text-light)">جاري الحساب...</span>
          <span v-else class="modal-stat-val" style="color: var(--primary-color); font-size: 16px; font-weight: 800; font-family: var(--font-english);">
            #{{ studentRank.toLocaleString('en-US') }}
          </span>
        </div>

        <div class="modal-stat-row">
          <span class="modal-stat-label">التفوق الإحصائي</span>
          <span v-if="loadingRank" class="modal-stat-val" style="color: var(--text-light)">جاري الحساب...</span>
          <span v-else class="modal-stat-val" style="color: var(--success-color); font-weight: 800; font-family: var(--font-english);">
            أفضل من {{ studentPercentile.toFixed(2) }}% من الطلاب
          </span>
        </div>

        <div class="modal-stat-row">
          <span class="modal-stat-label">المنطقة الجغرافية (القطاع)</span>
          <span class="modal-stat-val">
            {{ selectedStudent.seating_no <= 2380000 ? 'قطاع القاهرة' : selectedStudent.seating_no <= 2550000 ? 'قطاع الإسكندرية' : selectedStudent.seating_no <= 2820000 ? 'قطاع المنصورة' : 'قطاع أسيوط' }}
          </span>
        </div>
      </div>

      <button class="btn-search" style="width: 100%; margin-top: 20px;" @click="closeStudentDetails">
        <span>إغلاق التقرير</span>
      </button>
    </div>
  </div>

  <!-- Floating Comparison Bar -->
  <div v-if="comparedStudents.length > 0" class="comparison-bar">
    <div class="comparison-bar-info">
      <span>مقارنة الطلاب ({{ comparedStudents.length }} من 2)</span>
      <div class="comparison-names">
        <span v-for="s in comparedStudents" :key="s.seating_no" class="comparison-badge">
          {{ s.name.split(' ')[0] }}
          <button class="badge-remove" @click="toggleCompare(s)">✕</button>
        </span>
      </div>
    </div>
    <button 
      class="btn-search" 
      :disabled="comparedStudents.length < 2"
      @click="startComparison"
      style="margin: 0; padding: 8px 16px; font-size: 12px; border-radius: 12px; min-width: 110px;"
    >
      بدء المقارنة ⚖️
    </button>
  </div>

  <!-- Detailed Side-by-Side Comparison Modal -->
  <div v-if="showComparisonModal && comparedStudents.length === 2" class="modal-backdrop" @click.self="showComparisonModal = false">
    <div class="modal-content glass-panel" style="max-width: 600px;">
      <button class="modal-close" @click="showComparisonModal = false">✕</button>
      
      <div style="text-align: center; margin-bottom: 12px;">
        <h2 style="font-size: 18px; font-weight: 800; color: var(--text-main);">مقارنة النتائج والأداء ⚖️</h2>
        <p style="font-size: 12px; color: var(--text-light);">مقارنة بيانية وتحليلية تفصيلية بين الطالبين</p>
      </div>

      <div class="comparison-grid">
        <!-- Student 1 -->
        <div class="comparison-column" :class="{ winner: comparedStudents[0].grade > comparedStudents[1].grade }">
          <div v-if="comparedStudents[0].grade > comparedStudents[1].grade" class="winner-crown">👑</div>
          <span style="font-size: 11px; color: var(--text-light); font-family: var(--font-english);">جلوس: {{ comparedStudents[0].seating_no }}</span>
          <h3 style="font-size: 14px; font-weight: 800; color: var(--text-main); margin: 4px 0; min-height: 40px; display: flex; align-items: center; justify-content: center;">
            {{ comparedStudents[0].name }}
          </h3>
          
          <div style="margin: 8px 0;">
            <div style="font-size: 26px; font-weight: 800; color: var(--text-main); font-family: var(--font-english);">
              {{ ((comparedStudents[0].grade / 320) * 100).toFixed(1) }}%
            </div>
            <div style="font-size: 11px; color: var(--text-muted);">{{ comparedStudents[0].grade.toFixed(1) }} / 320 درجة</div>
          </div>
          
          <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px; text-align: right; border-top: 1px dashed var(--border-color); padding-top: 10px;">
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">الترتيب:</span>
              <span v-if="loadingCompare" style="color: var(--text-light)">...</span>
              <span v-else style="font-weight: 700; font-family: var(--font-english);">#{{ compareRanks[0].toLocaleString() }}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">التفوق:</span>
              <span v-if="loadingCompare" style="color: var(--text-light)">...</span>
              <span v-else style="font-weight: 700; color: var(--success-color);">أفضل من {{ comparePercentiles[0].toFixed(1) }}%</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">الحالة:</span>
              <span style="font-weight: 700;">{{ comparedStudents[0].status }}</span>
            </div>
          </div>
        </div>

        <!-- Student 2 -->
        <div class="comparison-column" :class="{ winner: comparedStudents[1].grade > comparedStudents[0].grade }">
          <div v-if="comparedStudents[1].grade > comparedStudents[0].grade" class="winner-crown">👑</div>
          <span style="font-size: 11px; color: var(--text-light); font-family: var(--font-english);">جلوس: {{ comparedStudents[1].seating_no }}</span>
          <h3 style="font-size: 14px; font-weight: 800; color: var(--text-main); margin: 4px 0; min-height: 40px; display: flex; align-items: center; justify-content: center;">
            {{ comparedStudents[1].name }}
          </h3>
          
          <div style="margin: 8px 0;">
            <div style="font-size: 26px; font-weight: 800; color: var(--text-main); font-family: var(--font-english);">
              {{ ((comparedStudents[1].grade / 320) * 100).toFixed(1) }}%
            </div>
            <div style="font-size: 11px; color: var(--text-muted);">{{ comparedStudents[1].grade.toFixed(1) }} / 320 درجة</div>
          </div>
          
          <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px; text-align: right; border-top: 1px dashed var(--border-color); padding-top: 10px;">
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">الترتيب:</span>
              <span v-if="loadingCompare" style="color: var(--text-light)">...</span>
              <span v-else style="font-weight: 700; font-family: var(--font-english);">#{{ compareRanks[1].toLocaleString() }}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">التفوق:</span>
              <span v-if="loadingCompare" style="color: var(--text-light)">...</span>
              <span v-else style="font-weight: 700; color: var(--success-color);">أفضل من {{ comparePercentiles[1].toFixed(1) }}%</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: var(--text-muted);">الحالة:</span>
              <span style="font-weight: 700;">{{ comparedStudents[1].status }}</span>
            </div>
          </div>
        </div>
      </div>

      <button class="btn-search" style="width: 100%; margin-top: 20px;" @click="showComparisonModal = false">
        <span>إغلاق المقارنة</span>
      </button>
    </div>
  </div>
</template>
