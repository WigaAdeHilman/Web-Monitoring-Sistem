let refreshInterval = 3000;
let intervalId = null;

// Deklarasikan variabel chart instance di scope global
let cpuChartInstance = null;
let ramChartInstance = null;
let diskChartInstance = null;
let gpuChartInstance = null;

let networkActivityData = [];
let oldNetSent = 0;
let oldNetRecv = 0;

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOMContentLoaded: Inisialisasi dimulai...");

    if (typeof Chart === 'undefined') {
        console.error("FATAL: Chart.js tidak dimuat. Pastikan CDN Chart.js terhubung dan tidak ada error jaringan atau interferensi ekstensi.");
        // UI feedback jika Chart.js tidak ada
        const body = document.querySelector('body');
        if (body) {
            const errorDiv = document.createElement('div');
            errorDiv.textContent = "Error Kritis: Pustaka Chart.js tidak berhasil dimuat. Grafik tidak akan dapat ditampilkan.";
            errorDiv.style.backgroundColor = "darkred";
            errorDiv.style.color = "white";
            errorDiv.style.padding = "15px";
            errorDiv.style.textAlign = "center";
            errorDiv.style.position = "fixed";
            errorDiv.style.top = "0";
            errorDiv.style.left = "0";
            errorDiv.style.width = "100%";
            errorDiv.style.zIndex = "10000"; // Pastikan paling atas
            body.prepend(errorDiv);
        }
        return; // Hentikan eksekusi jika Chart.js tidak ada
    }

    initCharts(); // Panggil inisialisasi chart

    // Hanya jalankan loadData jika Chart.js dan inisialisasi dasar berhasil
    // (Pengecekan instance chart akan ada di initCharts)
    setTimeout(() => {
        console.log("DOMContentLoaded: Memulai pemanggilan loadData periodik.");
        loadData(); // Panggil loadData pertama kali
        intervalId = setInterval(loadData, refreshInterval);
    }, 700); // Beri sedikit lebih banyak waktu jika ada proses render awal

    const intervalSelect = document.getElementById('intervalSelect');
    if (intervalSelect) {
        intervalSelect.addEventListener('change', () => {
            console.log("Interval diubah ke:", intervalSelect.value, "detik");
            clearInterval(intervalId);
            refreshInterval = parseInt(intervalSelect.value) * 1000;
            loadData(); // Langsung load data setelah interval diubah
            intervalId = setInterval(loadData, refreshInterval);
        });
    }

    document.querySelectorAll('#process-table th.sortable').forEach(header => {
        header.addEventListener('click', () => {
            const key = header.dataset.key;
            sortTableBy(key);
        });
    });
});

function initCharts() {
    console.log("initCharts: Memulai inisialisasi semua chart...");
    const baseOptions = {
        type: 'line',
        data: {
            labels: Array(10).fill(''),
            datasets: [{
                data: Array(10).fill(0),
                tension: 0.3,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    ticks: {
                        stepSize: 10,
                        callback: value => value + '%'
                    }
                },
                x: { display: false }
            },
            plugins: {
                legend: { display: false }
            }
        }
    };

    const chartConfigs = [
        { id: 'cpuChart', varName: 'cpuChartInstance', label: 'CPU %', borderColor: '#ef4444', bgColor: 'rgba(239, 68, 68, 0.1)' },
        { id: 'ramChart', varName: 'ramChartInstance', label: 'RAM %', borderColor: '#3b82f6', bgColor: 'rgba(59, 130, 246, 0.1)' },
        { id: 'diskChart', varName: 'diskChartInstance', label: 'DISK %', borderColor: '#eab308', bgColor: 'rgba(234, 179, 8, 0.1)' },
        { id: 'gpuChart', varName: 'gpuChartInstance', label: 'GPU %', borderColor: '#7c3aed', bgColor: 'rgba(124, 58, 237, 0.1)' },
    ];

    let allChartsInitializedSuccessfully = true;

    chartConfigs.forEach(config => {
        const chartId = config.id;
        const varName = config.varName;
        const ctx = document.getElementById(chartId);

        if (!ctx) {
            console.error(`initCharts: FATAL - Elemen canvas dengan ID '${chartId}' TIDAK DITEMUKAN.`);
            window[varName] = null; // Set instance global ke null
            allChartsInitializedSuccessfully = false;
            return; // Lanjut ke config berikutnya
        }

        console.log(`initCharts: Canvas '${chartId}' ditemukan. Mencoba membuat chart...`);
        try {
            const chartConfig = JSON.parse(JSON.stringify(baseOptions)); // Deep copy
            chartConfig.data.datasets[0].label = config.label;
            chartConfig.data.datasets[0].borderColor = config.borderColor;
            chartConfig.data.datasets[0].backgroundColor = config.bgColor;
            
            // Assign ke variabel global yang sudah dideklarasikan
            if (varName === 'cpuChartInstance') cpuChartInstance = new Chart(ctx.getContext('2d'), chartConfig);
            else if (varName === 'ramChartInstance') ramChartInstance = new Chart(ctx.getContext('2d'), chartConfig);
            else if (varName === 'diskChartInstance') diskChartInstance = new Chart(ctx.getContext('2d'), chartConfig);
            else if (varName === 'gpuChartInstance') gpuChartInstance = new Chart(ctx.getContext('2d'), chartConfig);
            
            console.log(`initCharts: Chart '${varName}' (${chartId}) berhasil dibuat.`);

        } catch (e) {
            console.error(`initCharts: Gagal membuat chart '${varName}' (${chartId}):`, e);
            // Set instance global ke null jika gagal
            if (varName === 'cpuChartInstance') cpuChartInstance = null;
            else if (varName === 'ramChartInstance') ramChartInstance = null;
            else if (varName === 'diskChartInstance') diskChartInstance = null;
            else if (varName === 'gpuChartInstance') gpuChartInstance = null;
            allChartsInitializedSuccessfully = false;
        }
    });

    if (allChartsInitializedSuccessfully) {
        console.log("initCharts: Semua charts yang dikonfigurasi berhasil diinisialisasi.");
    } else {
        console.warn("initCharts: Beberapa charts MUNGKIN GAGAL diinisialisasi. Periksa log di atas.");
        // Log status setiap instance untuk debugging
        console.log("initCharts: Status instance - cpuChartInstance:", cpuChartInstance ? "OK" : "GAGAL/NULL");
        console.log("initCharts: Status instance - ramChartInstance:", ramChartInstance ? "OK" : "GAGAL/NULL");
        console.log("initCharts: Status instance - diskChartInstance:", diskChartInstance ? "OK" : "GAGAL/NULL");
        console.log("initCharts: Status instance - gpuChartInstance:", gpuChartInstance ? "OK" : "GAGAL/NULL");
    }
}

function loadData() {
    // console.log("loadData: Meminta data dari server..."); // Uncomment untuk debugging frekuensi
    const statusEl = document.getElementById('connection-status');
    if (statusEl) {
        statusEl.classList.remove('hidden', 'offline', 'bg-green-500', 'bg-red-500');
        statusEl.classList.add('bg-blue-500');
        statusEl.textContent = 'Memuat data...';
    }

    fetch('/data')
        .then(res => {
            if (!res.ok) {
                return res.text().then(text => { // Baca response sebagai teks dulu
                    try {
                        const errorData = JSON.parse(text); // Coba parse sebagai JSON
                        throw new Error(`HTTP error! Status: ${res.status}. Server: ${errorData.error || text || 'Unknown server error'}`);
                    } catch (e) { // Jika bukan JSON atau parsing gagal
                        throw new Error(`HTTP error! Status: ${res.status}. Response server: ${text || 'Tidak ada detail error dari server.'}`);
                    }
                });
            }
            return res.json();
        })
        .then(data => {
            // console.log('loadData: Data diterima:', data); // Sangat berguna untuk debugging struktur data
            updateCharts(data);
            updateUI(data); // Panggil updateUI setelah chart diupdate
            if (statusEl) {
                statusEl.classList.remove('bg-blue-500', 'bg-red-500');
                statusEl.classList.add('bg-green-500');
                statusEl.textContent = 'Terhubung';
                setTimeout(() => statusEl.classList.add('hidden'), 1500);
            }
        })
        .catch(err => {
            console.error("loadData: Gagal mengambil atau memproses data:", err.message || err);
            if (statusEl) {
                statusEl.classList.remove('hidden', 'bg-blue-500', 'bg-green-500');
                statusEl.classList.add('bg-red-500');
                statusEl.textContent = 'Error Koneksi/Data!'; // Jangan sembunyikan pesan error
            }
        });
}

function updateCharts(data) {
    // console.log("updateCharts: Memulai update data untuk semua chart...");
    if (!data || typeof data !== 'object') {
        console.error("updateCharts: Data tidak valid atau tidak ada.", data);
        return;
    }
    // Pastikan data yang diperlukan ada sebelum mencoba mengaksesnya
    if (data.cpu) updateChart(cpuChartInstance, data.cpu.percent);
    else console.warn("updateCharts: Data CPU tidak ditemukan.");

    if (data.ram) updateChart(ramChartInstance, data.ram.percent);
    else console.warn("updateCharts: Data RAM tidak ditemukan.");

    if (data.disk) updateChart(diskChartInstance, data.disk.percent);
    else console.warn("updateCharts: Data Disk tidak ditemukan.");

    if (data.gpu) updateChart(gpuChartInstance, data.gpu.usage); // gpu.usage harus float dari backend
    else console.warn("updateCharts: Data GPU tidak ditemukan.");
}

function updateChart(chart, value) {
    // console.log(`updateChart: Mencoba update chart: ${chart ? chart.canvas.id : 'Chart NULL/INVALID'}, dengan nilai: ${value} (tipe: ${typeof value})`);
    if (!chart || typeof chart.update !== 'function' || !chart.data || !chart.data.datasets || !chart.data.datasets[0]) {
        // console.warn(`updateChart: Objek chart tidak valid atau tidak siap untuk update:`, chart ? chart.canvas.id : 'Objek Chart Tidak Diketahui');
        return;
    }

    const numericValue = parseFloat(value);
    if (isNaN(numericValue)) {
        console.warn(`updateChart: Nilai tidak valid untuk chart '${chart.canvas.id}':`, value, ". Menggunakan 0.");
        chart.data.datasets[0].data.push(0);
    } else {
        chart.data.datasets[0].data.push(numericValue);
    }
    
    if (chart.data.datasets[0].data.length > chart.data.labels.length) {
        chart.data.datasets[0].data.shift();
    }
    
    try {
        chart.update('none');
    } catch (e) {
        console.error(`updateChart: Error saat chart.update() untuk chart '${chart.canvas.id}':`, e);
    }
}

function updateUI(data) {
    if (!data || typeof data !== 'object') {
        console.error("updateUI: Data tidak valid atau tidak ada untuk update UI.", data);
        return;
    }
    // console.log("updateUI: Memperbarui elemen UI...");

    // Helper untuk memastikan nilai adalah angka sebelum toFixed
    const safeToFixed = (val, precision = 1) => {
        const num = parseFloat(val);
        return isNaN(num) ? 'N/A' : num.toFixed(precision);
    };
    const safeToFloat = (val) => { // Untuk progress bar
        const num = parseFloat(val);
        return isNaN(num) ? 0 : num; // Kembalikan 0 jika NaN untuk progress bar
    };


    // Progress Bars
    if (data.cpu) updateProgressBar('cpu-bar', safeToFloat(data.cpu.percent), '%');
    if (data.ram) updateProgressBar('ram-bar', safeToFloat(data.ram.percent), '%');
    if (data.disk) updateProgressBar('disk-bar', safeToFloat(data.disk.percent), '%');
    if (data.gpu) updateProgressBar('gpu-bar', safeToFloat(data.gpu.usage), '%');

    if (data.battery) updateBatteryInfo(data.battery);

    // Dashboard Meters
    if (data.cpu) {
        updateElement('dashboard-cpu-usage', `${safeToFixed(data.cpu.percent)}%`);
        updateElement('dashboard-cpu-temp', formatTemp(data.cpu.temperature));
    }
    if (data.ram) {
        updateElement('dashboard-ram-usage', `${safeToFixed(data.ram.percent)}%`);
        updateElement('dashboard-ram-free', `${safeToFixed(data.ram.free)} GB`);
    }
    if (data.disk) {
        updateElement('dashboard-disk-usage', `${safeToFixed(data.disk.percent)}%`);
        updateElement('dashboard-disk-free', `${safeToFixed(data.disk.free)} GB`);
    }
    if (data.gpu) {
        updateElement('dashboard-gpu-usage', `${safeToFixed(data.gpu.usage)}%`);
        updateElement('dashboard-gpu-temp', formatTemp(data.gpu.temperature));
    }
    if (data.network) {
        // Menggunakan unit yang dikirim dari backend
        updateElement('dashboard-network-download', `${safeToFixed(data.network.download_speed || 0, data.network.download_unit === "KB/s" ? 1 : 2)} ${data.network.download_unit || 'MB/s'}`);
        updateElement('dashboard-network-upload', `${safeToFixed(data.network.upload_speed || 0, data.network.upload_unit === "KB/s" ? 1 : 2)} ${data.network.upload_unit || 'MB/s'}`);
    }

    // Heaviest process
    if (data.processes && data.processes.length > 0) {
        const heaviest = data.processes[0];
        updateElement('dashboard-heaviest-process', `${heaviest.name} (${safeToFixed(heaviest.cpu_percent)}% CPU, ${safeToFixed(heaviest.memory_percent)}% MEM)`);
    } else {
        updateElement('dashboard-heaviest-process', 'Tidak ada data proses.');
    }

    // Detail Suhu
    if (data.cpu) updateElement('cpu-temp', formatTemp(data.cpu.temperature));
    if (data.gpu) updateElement('gpu-temp', formatTemp(data.gpu.temperature));

    // Detail GPU
    if (data.gpu) {
        updateElement('gpu-name', data.gpu.name || 'N/A');
        updateElement('gpu-usage', `${safeToFixed(data.gpu.usage)}%`);
        updateElement('gpu-mem-total', `${safeToFixed(data.gpu.mem_total)} MB`);
        updateElement('gpu-mem-used', `${safeToFixed(data.gpu.mem_used)} MB`);
        updateElement('gpu-mem-free', `${safeToFixed(data.gpu.mem_free)} MB`);
    }

    // Detail RAM
    if (data.ram) {
        updateElement('ram-total', `${safeToFixed(data.ram.total)} GB`);
        updateElement('ram-used', `${safeToFixed(data.ram.used)} GB`);
        updateElement('ram-free', `${safeToFixed(data.ram.free)} GB`);
        updateElement('ram-percent', `${safeToFixed(data.ram.percent)}%`);
    }

    // Detail Disk
    if (data.disk) {
        updateElement('disk-total', `${safeToFixed(data.disk.total,0)} GB`); // GB biasanya tanpa desimal
        updateElement('disk-used', `${safeToFixed(data.disk.used,0)} GB`);
        updateElement('disk-free', `${safeToFixed(data.disk.free,0)} GB`);
        updateElement('disk-percent', `${safeToFixed(data.disk.percent)}%`);
    }
    if (data.disk_io){
        updateElement('disk-read', `${safeToFixed(data.disk_io.read)} MB/s`);
        updateElement('disk-write', `${safeToFixed(data.disk_io.write)} MB/s`);
    }

    // Detail Network
    if (data.network) {
        updateElement('net-sent', `${safeToFixed(data.network.sent)} MB`);
        updateElement('net-recv', `${safeToFixed(data.network.recv)} MB`);
        updateElement('net-packets-sent', data.network.packets_sent != null ? data.network.packets_sent : 'N/A');
        updateElement('net-packets-recv', data.network.packets_recv != null ? data.network.packets_recv : 'N/A');
        updateNetworkActivity(safeToFloat(data.network.sent), safeToFloat(data.network.recv));
    }

    if (data.processes) updateProcessTable(data.processes);
    if (data.system) updateStatus(data);
}

function updateElement(id, text) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
    } else {
        // console.warn(`updateElement: Elemen dengan ID '${id}' tidak ditemukan.`);
    }
}

function updateProgressBar(id, value, suffix = '') { // value sudah dipastikan float atau 0 oleh safeToFloat
    const el = document.getElementById(id);
    if (!el) return;

    // value sekarang sudah pasti angka (atau 0 jika input awal NaN)
    el.style.width = `${value}%`;
    el.textContent = `${value.toFixed(1)}${suffix}`;
    el.classList.remove('bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-gray-400');

    if (value < 0.1 && id.includes('-bar')) { // Jika 0 untuk bar utama, beri warna netral
         el.classList.add('bg-gray-300'); // Atau warna progress bar kosong
         el.textContent = `0.0${suffix}`; // Tampilkan 0.0%
    } else if (value < 50) el.classList.add('bg-green-500');
    else if (value < 80) el.classList.add('bg-yellow-500');
    else el.classList.add('bg-red-500');
}

function updateBatteryInfo(battery) {
    const batteryContainer = document.getElementById('battery-container');
    if (!batteryContainer) return;

    if (!battery || battery.percent === 'N/A') {
        batteryContainer.classList.add('hidden');
        return;
    }
    
    batteryContainer.classList.remove('hidden');

    const percent = parseFloat(battery.percent);
    if (isNaN(percent)) {
        console.warn("updateBatteryInfo: Nilai persen baterai tidak valid:", battery.percent);
        batteryContainer.classList.add('hidden');
        return;
    }

    updateElement('battery-percent-text', `${percent.toFixed(0)}%`);
    updateProgressBar('battery-bar', percent, '%');
    updateElement('battery-status', `Status: ${battery.plugged ? 'Mengisi Daya' : 'Baterai'}`);
    updateElement('battery-time', `Sisa Waktu: ${battery.time_left || '-'}`);

    const chargingIcon = document.getElementById('battery-charging');
    if (chargingIcon) chargingIcon.classList.toggle('hidden', !battery.plugged);

    const batteryIcon = document.getElementById('battery-icon');
    if (batteryIcon) {
        batteryIcon.className = 'text-5xl'; // Reset kelas dasar
        if (percent <= 10) batteryIcon.classList.add('fas', 'fa-battery-empty', 'text-red-500');
        else if (percent <= 25) batteryIcon.classList.add('fas', 'fa-battery-quarter', 'text-red-400');
        else if (percent <= 50) batteryIcon.classList.add('fas', 'fa-battery-half', 'text-yellow-500');
        else if (percent <= 75) batteryIcon.classList.add('fas', 'fa-battery-three-quarters', 'text-green-400');
        else batteryIcon.classList.add('fas', 'fa-battery-full', 'text-green-500');
    }
}

function updateNetworkActivity(currentSentMB, currentRecvMB) { // Input sudah float
    const sentDiffMB = Math.max(0, currentSentMB - oldNetSent);
    const recvDiffMB = Math.max(0, currentRecvMB - oldNetRecv);
    oldNetSent = currentSentMB;
    oldNetRecv = currentRecvMB;

    const maxDiff = Math.max(sentDiffMB, recvDiffMB);
    // Jika tidak ada aktivitas sama sekali, scaleFactor bisa jadi Infinity atau NaN jika maxDiff 0.
    // Atur agar jika tidak ada perbedaan, tinggi bar adalah 0.
    const scaleFactor = maxDiff > 0.001 ? 100 / maxDiff : 0; // Threshold kecil untuk menghindari sensitivitas berlebih

    const sentHeight = Math.min(100, sentDiffMB * scaleFactor); // Batasi maksimal 100%
    const recvHeight = Math.min(100, recvDiffMB * scaleFactor);

    networkActivityData.push({ sent: sentHeight, recv: recvHeight });
    if (networkActivityData.length > 30) networkActivityData.shift();

    const container = document.getElementById('network-activity');
    if (!container) return;
    container.innerHTML = '';

    networkActivityData.forEach(dataPoint => {
        const bar = document.createElement('div');
        bar.className = 'inline-block w-2 mx-px h-full relative align-bottom';
        bar.innerHTML = `
            <div class="absolute bottom-0 w-full bg-green-500" style="height:${dataPoint.sent.toFixed(1)}%"></div>
            <div class="absolute bottom-0 w-full bg-blue-500 opacity-70" style="height:${dataPoint.recv.toFixed(1)}%"></div>
        `;
        container.appendChild(bar);
    });
}

function updateProcessTable(processes) {
    const tbody = document.querySelector('#process-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    if (!processes || processes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-gray-500">Tidak ada proses yang termonitor.</td></tr>';
        return;
    }
    const safeToFixed = (val, precision = 1) => {
        const num = parseFloat(val);
        return isNaN(num) ? 'N/A' : num.toFixed(precision);
    };
    processes.forEach(proc => {
        const row = `
            <tr class="text-center">
                <td class="px-4 py-2">${proc.pid}</td>
                <td class="px-4 py-2 text-left">${proc.name || 'N/A'}</td>
                <td class="px-4 py-2">${safeToFixed(proc.cpu_percent)}%</td>
                <td class="px-4 py-2">${safeToFixed(proc.memory_percent)}%</td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function updateStatus(data) {
    const indicator = document.getElementById('status-indicator');
    const statusEl = document.getElementById('system-status');
    const detailsEl = document.getElementById('status-details');

    if (!indicator || !statusEl || !detailsEl || !data.system) return;

    indicator.className = 'w-4 h-4 rounded-full pulse-status'; 
    if (data.system.status === 'Kritis') indicator.classList.add('bg-red-500');
    else if (data.system.status === 'Beban Tinggi') indicator.classList.add('bg-yellow-500');
    else indicator.classList.add('bg-green-500');

    statusEl.textContent = `Sistem ${data.system.status || 'N/A'}`;
    if (Array.isArray(data.system.status_details) && data.system.status_details.length > 0) {
        detailsEl.textContent = data.system.status_details.join(', ');
    } else {
        detailsEl.textContent = 'Semua komponen berjalan optimal.';
    }

    const list = document.getElementById('recommendations-list');
    if (list) {
        list.innerHTML = '';
        if (Array.isArray(data.system.recommendations) && data.system.recommendations.length > 0) {
            data.system.recommendations.forEach(r => {
                list.innerHTML += `<li class="recommendation-item p-1 rounded bg-blue-50 text-xs">
                    <i class="fas fa-circle-info text-blue-500 mr-1"></i> ${r}</li>`;
            });
        } else {
             list.innerHTML += `<li class="recommendation-item p-1 rounded bg-blue-50 text-xs">
                    <i class="fas fa-circle-info text-blue-500 mr-1"></i> Tidak ada rekomendasi khusus.</li>`;
        }
    }
    if (data.system.uptime) {
        updateElement('system-uptime', data.system.uptime.uptime_formatted || 'N/A');
        updateElement('system-boottime', data.system.uptime.boot_time || 'N/A');
    }
}

function formatTemp(val) {
    const numericVal = parseFloat(val);
    if (isNaN(numericVal) || val === 'N/A' || val === null || typeof val === 'undefined') {
        return 'N/A';
    }
    return `${numericVal.toFixed(1)} °C`;
}

let sortState = { key: null, ascending: false };

function sortTableBy(key) {
    const table = document.getElementById('process-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const placeholderRow = tbody.querySelector('td[colspan="4"]');
    if (placeholderRow || rows.length <= 1) return;

    let ascending = sortState.key === key ? !sortState.ascending : false;
    sortState = { key, ascending };

    rows.sort((a, b) => {
        const colIndex = key === 'pid' ? 0 : (key === 'name' ? 1 : (key === 'cpu_percent' ? 2 : 3));
        
        let aValueText = a.cells[colIndex] ? a.cells[colIndex].textContent : '';
        let bValueText = b.cells[colIndex] ? b.cells[colIndex].textContent : '';
        let aValue, bValue;

        if (key === 'cpu_percent' || key === 'memory_percent') {
            aValue = parseFloat(aValueText.replace('%', '')) || 0; // Default ke 0 jika NaN
            bValue = parseFloat(bValueText.replace('%', '')) || 0;
        } else if (key === 'pid') {
            aValue = parseInt(aValueText) || 0;
            bValue = parseInt(bValueText) || 0;
        } else { // Untuk 'name' (string)
            aValue = aValueText.toLowerCase();
            bValue = bValueText.toLowerCase();
        }

        if (aValue < bValue) return ascending ? -1 : 1;
        if (aValue > bValue) return ascending ? 1 : -1;
        return 0;
    });
    
    document.querySelectorAll('#process-table th.sortable i').forEach(icon => {
        icon.className = 'fas fa-sort text-gray-500 ml-1';
    });
    const headerIcon = document.querySelector(`#process-table th[data-key="${key}"] i`);
    if (headerIcon) {
        headerIcon.className = `fas ${ascending ? 'fa-sort-up' : 'fa-sort-down'} text-blue-500 ml-1`;
    }
    
    rows.forEach(row => tbody.appendChild(row)); // Re-append rows in sorted order
}