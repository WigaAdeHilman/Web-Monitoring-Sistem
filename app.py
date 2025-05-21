from flask import Flask, render_template, jsonify, send_from_directory
import psutil
import platform
import time
import logging
import subprocess
import os
import re
import datetime
from collections import defaultdict

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Global state for incremental speed calculation
_prev_disk_io = None
_prev_disk_time = None
_prev_net_io = None
_prev_net_time = None


# Konversi byte ke MB
def bytes_to_mb(bytes_value):
    return round(bytes_value / (1024 * 1024), 1)

# Konversi byte ke GB
def bytes_to_gb(bytes_value):
    return round(bytes_value / (1024 ** 3), 1)

# Format waktu uptime
def format_uptime(seconds):
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{int(days)}d {int(hours)}h {int(minutes)}m"
    elif hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(minutes)}m {int(seconds)}s"

# Fungsi untuk mendapatkan suhu dari berbagai sumber
def get_temperatures():
    cpu_temp = 'N/A'
    gpu_temp = 'N/A'
    
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if len(entries) > 0:
                    if any(key in name.lower() for key in ['core', 'cpu', 'k10temp', 'coretemp', 'cpu_thermal', 'soc_thermal', 'package']):
                        # Prioritize package/die temperatures if available
                        pkg_entry = next((e for e in entries if 'package' in e.label.lower() or 'die' in e.label.lower()), None)
                        if pkg_entry:
                             cpu_temp = pkg_entry.current
                        elif cpu_temp == 'N/A' or isinstance(cpu_temp, str): # Fallback to first core temp if no package/die
                             cpu_temp = entries[0].current
                    elif any(key in name.lower() for key in ['gpu', 'nvidia', 'amdgpu', 'radeon', 'nouveau']):
                        gpu_temp = entries[0].current
            if not isinstance(cpu_temp, str): logger.info(f"Got CPU temperature from psutil: {cpu_temp}")
            if not isinstance(gpu_temp, str): logger.info(f"Got GPU temperature from psutil: {gpu_temp}")
    except Exception as e:
        logger.warning(f"Could not get temperatures from psutil: {str(e)}")
    
    if platform.system() == 'Windows':
        if isinstance(cpu_temp, str) and cpu_temp == 'N/A':
            try:
                result = subprocess.check_output('wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature', shell=True, stderr=subprocess.DEVNULL)
                temp_str_lines = result.decode('utf-8', errors='ignore').strip().split('\n')
                if len(temp_str_lines) > 1 and temp_str_lines[1].strip().isdigit():
                    cpu_temp = (int(temp_str_lines[1].strip()) / 10) - 273.15
                    logger.info(f"Got CPU temperature from wmic: {cpu_temp:.1f}°C")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error getting CPU temperature from wmic: {str(e)}")
        
        if isinstance(gpu_temp, str) and gpu_temp == 'N/A':
            try:
                nvidia_smi_path = "nvidia-smi" 
                if 'PROGRAMFILES' in os.environ:
                    path_check = os.path.join(os.environ['PROGRAMFILES'], "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
                    if os.path.exists(path_check):
                        nvidia_smi_path = f'"{path_check}"' # Quotes for path with spaces

                result = subprocess.check_output(f'{nvidia_smi_path} --query-gpu=temperature.gpu --format=csv,noheader', shell=True, stderr=subprocess.DEVNULL)
                temp_str = result.decode('utf-8', errors='ignore').strip()
                if temp_str and temp_str.replace('.', '', 1).isdigit(): # Check if it's a number
                    gpu_temp = float(temp_str)
                    logger.info(f"Got GPU temperature from nvidia-smi: {gpu_temp:.1f}°C")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error getting GPU temperature from nvidia-smi: {str(e)}")
    
    elif platform.system() == 'Linux':
        if (isinstance(cpu_temp, str) and cpu_temp == 'N/A') or \
           (isinstance(gpu_temp, str) and gpu_temp == 'N/A'):
            try:
                result = subprocess.check_output('sensors', shell=True, stderr=subprocess.DEVNULL)
                output = result.decode('utf-8', errors='ignore')
                
                if isinstance(cpu_temp, str) and cpu_temp == 'N/A':
                    pkg_match = re.search(r'(?:Package id \d+|Tdie|Composite):\s*\+?(\d+\.\d+)°C', output, re.IGNORECASE)
                    if pkg_match:
                        cpu_temp = float(pkg_match.group(1))
                    else:
                        cpu_matches = re.findall(r'Core \d+:\s*\+?(\d+\.\d+)°C', output)
                        if cpu_matches:
                            cpu_temp = round(sum(float(t) for t in cpu_matches) / len(cpu_matches), 1)
                    if not isinstance(cpu_temp, str): logger.info(f"Got CPU temperature from sensors: {cpu_temp}°C")
                
                if isinstance(gpu_temp, str) and gpu_temp == 'N/A':
                    gpu_match = re.search(r'(?:amdgpu|nvidia|radeon|nouveau).*\n.*\s+temp1:\s*\+?(\d+\.\d+)°C', output, re.IGNORECASE | re.MULTILINE)
                    if not gpu_match:
                         gpu_match = re.search(r'(?:GPU Temperature|temp\d+):\s*\+?(\d+\.\d+)°C', output) # More generic
                    if gpu_match:
                        gpu_temp = float(gpu_match.group(1))
                        logger.info(f"Got GPU temperature from sensors: {gpu_temp}°C")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error getting temperatures from sensors: {str(e)}")
    
    elif platform.system() == 'Darwin':
        if isinstance(cpu_temp, str) and cpu_temp == 'N/A':
            try:
                # Try common sysctl keys for CPU temperature on macOS
                keys_to_try = [
                    "kern.thermal_cpu_level", # Might be a level, not temp
                    "machdep.xcpm.cpu_thermal_level", 
                    "hw.cpufrequency", # Not temp, but related
                    # For older Intel Macs, powermetrics might be needed, which is more complex
                ] # This part is tricky for macOS without external tools or more specific sysctls
                # A more reliable but external command:
                # osx-cpu-temp might require sudo or be from external source
                # For simplicity, this example will be limited.
                # A common approach is to use 'istats' or similar tools if allowed.
                # result = subprocess.check_output('sysctl -a | grep -E "cpu_temperature|thermal"', shell=True, stderr=subprocess.DEVNULL)
                # For Apple Silicon (M-series chips) specifically
                result_as = subprocess.check_output('sysctl -n hw.cpufrequency_max', shell=True, stderr=subprocess.DEVNULL) # Placeholder, real temp is harder
                # Actual M1/M2 temp needs pmset -g therm or sudo powermetrics -i 200 -n 1 --samplers smc | grep "CPU die temperature"
                # This is too complex for a simple check here.
                # Keeping cpu_temp as 'N/A' if psutil fails on macOS is safer for now.
                logger.warning("Reliable CPU temperature on macOS often requires specific tools or complex commands.")
            except Exception as e:
                logger.warning(f"Error getting CPU temperature from sysctl (macOS): {str(e)}")
    
    return cpu_temp, gpu_temp

# Info GPU menggunakan nvidia-smi
def get_gpu_info():
    info = {
        'name': 'N/A',
        'usage': 0.0, # Ensure usage is a float
        'mem_total': 0.0,
        'mem_used': 0.0,
        'mem_free': 0.0
    }
    
    try:
        nvidia_smi_path = "nvidia-smi"
        if platform.system() == 'Windows' and 'PROGRAMFILES' in os.environ:
             path_check = os.path.join(os.environ['PROGRAMFILES'], "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
             if os.path.exists(path_check):
                 nvidia_smi_path = f'"{path_check}"'

        result_str = subprocess.check_output(
            f"{nvidia_smi_path} --query-gpu=name,utilization.gpu,memory.total,memory.used,memory.free --format=csv,noheader,nounits",
            shell=True, stderr=subprocess.DEVNULL
        ).decode('utf-8', errors='ignore').strip()
        
        if result_str:
            first_gpu_line = result_str.splitlines()[0] # Handle multi-GPU systems, take first
            result = first_gpu_line.split(',')
            
            if len(result) >= 5:
                info['name'] = result[0].strip()
                info['usage'] = float(result[1].strip()) if result[1].strip().replace('.', '', 1).isdigit() else 0.0
                info['mem_total'] = float(result[2].strip()) if result[2].strip().replace('.', '', 1).isdigit() else 0.0
                info['mem_used'] = float(result[3].strip()) if result[3].strip().replace('.', '', 1).isdigit() else 0.0
                info['mem_free'] = float(result[4].strip()) if result[4].strip().replace('.', '', 1).isdigit() else 0.0
                logger.info(f"Got NVIDIA GPU info: {info['name']}, Usage: {info['usage']}%")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e: # Added ValueError for float conversion
        logger.warning(f"Error getting NVIDIA GPU info: {str(e)}")
        
        if platform.system() == 'Linux':
            try:
                card_path_base = "/sys/class/drm/card"
                gpu_card_device_path = None
                for i in range(4): # Check card0 to card3
                    # A simple check: if vendor file exists, it's likely a GPU
                    if os.path.exists(f"{card_path_base}{i}/device/vendor"):
                         # Try to determine if it's AMD; more robust checks needed for other vendors
                        try:
                            with open(f"{card_path_base}{i}/device/vendor", "r") as f:
                                vendor_id = f.read().strip()
                            if vendor_id == "0x1002": # AMD Vendor ID
                                gpu_card_device_path = f"{card_path_base}{i}/device"
                                break
                        except IOError:
                            continue # Cannot read vendor, try next card
                
                if gpu_card_device_path:
                    with open(f"{gpu_card_device_path}/gpu_busy_percent", "r") as f:
                        info['usage'] = float(f.read().strip())
                    
                    with open(f"{gpu_card_device_path}/mem_info_vram_total", "r") as f:
                        info['mem_total'] = bytes_to_mb(int(f.read().strip()))
                    with open(f"{gpu_card_device_path}/mem_info_vram_used", "r") as f:
                        info['mem_used'] = bytes_to_mb(int(f.read().strip()))
                    info['mem_free'] = round(info['mem_total'] - info['mem_used'], 1)
                    info['name'] = "AMD GPU" # Generic name
                    logger.info(f"Got AMD GPU info (sysfs): Usage: {info['usage']}%")
            except (IOError, FileNotFoundError, ValueError) as e_amd:
                logger.warning(f"Error getting AMD GPU info from sysfs: {str(e_amd)}")
    
    return info

# Disk I/O speed (incremental, non-blocking)
def get_disk_io_speed_incremental():
    global _prev_disk_io, _prev_disk_time
    current_time = time.time()
    try:
        current_disk_io = psutil.disk_io_counters()
    except Exception as e:
        logger.error(f"Failed to get disk_io_counters: {e}")
        return {'read': 0.0, 'write': 0.0}


    read_speed = 0.0
    write_speed = 0.0

    if _prev_disk_io is not None and _prev_disk_time is not None:
        time_diff = current_time - _prev_disk_time
        if time_diff > 0:
            read_bytes_diff = current_disk_io.read_bytes - _prev_disk_io.read_bytes
            write_bytes_diff = current_disk_io.write_bytes - _prev_disk_io.write_bytes
            
            read_speed = bytes_to_mb(max(0, read_bytes_diff) / time_diff)
            write_speed = bytes_to_mb(max(0, write_bytes_diff) / time_diff)
    
    _prev_disk_io = current_disk_io
    _prev_disk_time = current_time
    
    # logger.info(f"Disk I/O: Read={read_speed:.1f}MB/s, Write={write_speed:.1f}MB/s") # Too frequent logging
    return {'read': read_speed, 'write': write_speed}


# Info baterai
def get_battery_info():
    try:
        battery = psutil.sensors_battery()
        if battery:
            percent = battery.percent
            plugged = battery.power_plugged
            secsleft = battery.secsleft
            time_left_str = None

            if plugged:
                if secsleft == psutil.POWER_TIME_UNLIMITED or percent == 100: # Some systems might not report unlimited
                    time_left_str = "Terisi Penuh"
                elif secsleft != psutil.POWER_TIME_UNKNOWN and secsleft is not None and secsleft > 0 :
                     hours, remainder = divmod(secsleft, 3600)
                     minutes, _ = divmod(remainder, 60)
                     time_left_str = f"Pengisian ({int(hours)}j {int(minutes)}m)"
                else:
                    time_left_str = "Mengisi Daya" # Generic charging status
            elif secsleft != psutil.POWER_TIME_UNLIMITED and secsleft != psutil.POWER_TIME_UNKNOWN and secsleft is not None and secsleft > 0:
                hours, remainder = divmod(secsleft, 3600)
                minutes, _ = divmod(remainder, 60)
                time_left_str = f"{int(hours)}j {int(minutes)}m"
            
            # logger.info(f"Battery: {percent}%, Plugged: {plugged}, Time left: {time_left_str if time_left_str else 'N/A'}")
            return {'percent': percent, 'plugged': plugged, 'time_left': time_left_str}
        else:
            # logger.info("No battery detected or psutil.sensors_battery() returned None.")
            return {'percent': 'N/A', 'plugged': False, 'time_left': None}
    except (AttributeError, NotImplementedError):
        # logger.info("Battery information not available on this system (psutil attribute/not implemented).")
        return {'percent': 'N/A', 'plugged': False, 'time_left': None}
    except Exception as e:
        logger.error(f"Error getting battery info: {str(e)}")
        return {'percent': 'N/A', 'plugged': False, 'time_left': None}


# Informasi uptime dan boot time
def get_system_uptime():
    try:
        boot_timestamp = psutil.boot_time()
        boot_time = datetime.datetime.fromtimestamp(boot_timestamp)
        boot_time_str = boot_time.strftime('%d-%m-%Y %H:%M:%S') # Format Indonesia
        uptime_seconds = time.time() - boot_timestamp
        uptime_formatted = format_uptime(uptime_seconds)
        
        # logger.info(f"System boot time: {boot_time_str}, Uptime: {uptime_formatted}")
        return {
            'boot_timestamp': boot_timestamp,
            'boot_time': boot_time_str,
            'uptime_seconds': uptime_seconds,
            'uptime_formatted': uptime_formatted
        }
    except Exception as e:
        logger.error(f"Error getting system uptime: {str(e)}")
        return {
            'boot_timestamp': 0,
            'boot_time': 'N/A',
            'uptime_seconds': 0,
            'uptime_formatted': 'N/A'
        }

# Menentukan status umum sistem
def get_system_status(cpu_percent, ram_percent, disk_percent, gpu_usage, cpu_temp):
    status = "Normal"
    status_details = [] # Diubah menjadi list string, bukan objek
    
    if cpu_percent >= 90: status = "Kritis"; status_details.append("CPU Overload")
    elif cpu_percent >= 75: status = "Beban Tinggi" if status != "Kritis" else status; status_details.append("CPU Tinggi")
    
    if ram_percent >= 90: status = "Kritis"; status_details.append("RAM Hampir Penuh")
    elif ram_percent >= 80: status = "Beban Tinggi" if status != "Kritis" else status; status_details.append("RAM Tinggi")
    
    if disk_percent >= 95: status = "Kritis"; status_details.append("Disk Hampir Penuh")
    elif disk_percent >= 85: status = "Beban Tinggi" if status != "Kritis" else status; status_details.append("Disk Terbatas")
    
    if isinstance(gpu_usage, (int, float)) and gpu_usage >= 90 : status = "Beban Tinggi" if status != "Kritis" else status; status_details.append("GPU Sibuk")
    
    if isinstance(cpu_temp, (int, float)): # Hanya jika cpu_temp adalah angka
        if cpu_temp >= 85: status = "Kritis"; status_details.append("CPU Terlalu Panas")
        elif cpu_temp >= 75: status = "Beban Tinggi" if status != "Kritis" else status; status_details.append("CPU Panas")
    
    return {'status': status, 'details': status_details} # Mengirim 'details' sebagai list

# Menentukan rekomendasi untuk optimasi sistem
def get_system_recommendations(cpu_percent, ram_percent, disk_percent, gpu_usage, top_processes):
    recommendations = []
    
    if cpu_percent >= 80:
        recommendations.append("Pertimbangkan menutup aplikasi berat.")
        if top_processes and len(top_processes) > 0 and top_processes[0]['cpu_percent'] > 50:
            recommendations.append(f"Proses '{top_processes[0]['name']}' menggunakan banyak CPU.")
    
    if ram_percent >= 85: recommendations.append("RAM hampir habis, tutup aplikasi atau tambah RAM.")
    elif ram_percent >= 75: recommendations.append("Penggunaan RAM tinggi, tutup aplikasi tak terpakai.")
    
    if disk_percent >= 90: recommendations.append("Ruang disk hampir habis, bersihkan file.")
    elif disk_percent >= 80: recommendations.append("Ruang disk menipis, lakukan pembersihan.")
    
    if isinstance(gpu_usage, (int, float)) and gpu_usage >= 90: recommendations.append("GPU bekerja keras, tutup aplikasi grafis berat.")
    
    if not recommendations: recommendations.append("Sistem berjalan optimal.") # Diubah
    
    return recommendations[:3]

@app.route('/')
def index():
    # logger.info("Halaman index diakses")
    return render_template('index.html')

@app.route('/data')
def get_data():
    global _prev_net_io, _prev_net_time
    try:
        # logger.info("API data diakses")
        current_call_time = time.time()
        
        cpu_percent = psutil.cpu_percent(interval=0.1) # Blocking, tapi pendek

        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_total, ram_used, ram_free = bytes_to_gb(ram.total), bytes_to_gb(ram.used), bytes_to_gb(ram.available)

        disk_usage_obj = psutil.disk_usage('/') # Menggunakan objek disk_usage agar lebih jelas
        disk_percent = disk_usage_obj.percent
        disk_total = bytes_to_gb(disk_usage_obj.total)
        disk_used = bytes_to_gb(disk_usage_obj.used)
        disk_free = bytes_to_gb(disk_usage_obj.free)

        disk_io = get_disk_io_speed_incremental() # Non-blocking

        cpu_temp, gpu_temp = get_temperatures()
        gpu_info = get_gpu_info() # Pastikan usage selalu float
        battery_info = get_battery_info() # Pastikan percent selalu angka atau 'N/A'
        system_uptime = get_system_uptime()

        # Network totals & speed (non-blocking incremental)
        current_network_sample_time = time.time() # Timestamp SEBELUM mengambil data network
        current_net_io = psutil.net_io_counters()
        net_sent_total = bytes_to_mb(current_net_io.bytes_sent)
        net_recv_total = bytes_to_mb(current_net_io.bytes_recv)
        net_packets_sent = current_net_io.packets_sent
        net_packets_recv = current_net_io.packets_recv
        
        net_upload_speed, net_download_speed = 0.0, 0.0

        upload_unit = "MB/s"
        download_unit = "MB/s"

        logger.info(f"[NET_DEBUG] Panggilan ke /data. current_sample_time: {current_network_sample_time:.4f}")
        if _prev_net_io is not None and _prev_net_time is not None:
            logger.info(f"[NET_DEBUG] _prev_net_time: {_prev_net_time:.4f}, _prev_sent: {_prev_net_io.bytes_sent}, _prev_recv: {_prev_net_io.bytes_recv}")
        
            time_diff_net = current_network_sample_time - _prev_net_time 
            logger.info(f"[NET_DEBUG] time_diff_net: {time_diff_net:.4f}s")
        
            if time_diff_net > 0.01: 
                bytes_sent_diff = current_net_io.bytes_sent - _prev_net_io.bytes_sent
                bytes_recv_diff = current_net_io.bytes_recv - _prev_net_io.bytes_recv
                logger.info(f"[NET_DEBUG] current_sent: {current_net_io.bytes_sent}, current_recv: {current_net_io.bytes_recv}")
                logger.info(f"[NET_DEBUG] bytes_sent_diff: {bytes_sent_diff}, bytes_recv_diff: {bytes_recv_diff}")
                
                upload_bps = max(0, bytes_sent_diff) / time_diff_net
                download_bps = max(0, bytes_recv_diff) / time_diff_net
                logger.info(f"[NET_DEBUG] upload_Bps: {upload_bps:.2f}, download_Bps: {download_bps:.2f}")

                # Hitung kecepatan dalam MB/s dulu
                current_upload_mb_speed = upload_bps / (1024 * 1024)
                current_download_mb_speed = download_bps / (1024 * 1024)

                # Tentukan nilai dan unit untuk upload
                if current_upload_mb_speed < 0.01 and upload_bps > 0: # Jika MB/s sangat kecil (<0.01) tapi Bps ada
                    net_upload_speed_value = round(upload_bps / 1024, 1) # Konversi ke KB/s
                    upload_unit = "KB/s"
                else:
                    net_upload_speed_value = round(current_upload_mb_speed, 2) # Tetap MB/s, presisi

                # Tentukan nilai dan unit untuk download
                if current_download_mb_speed < 0.01 and download_bps > 0:
                    net_download_speed_value = round(download_bps / 1024, 1)
                    download_unit = "KB/s"
                else:
                    net_download_speed_value = round(current_download_mb_speed, 2)
                    # download_unit sudah "MB/s" (default)

                net_upload_speed = round(upload_bps / (1024 * 1024), 2) 
                net_download_speed = round(download_bps / (1024 * 1024), 2)
                logger.info(f"[NET_DEBUG] Hasil: net_upload_speed_MBs={net_upload_speed:.2f}, net_download_speed_MBs={net_download_speed:.2f}")
            else:
                logger.warning(f"[NET_DEBUG] time_diff_net ({time_diff_net:.4f}s) terlalu kecil. Kecepatan tidak dihitung.")
        else:
            logger.info("[NET_DEBUG] Panggilan pertama atau _prev_net_io/_prev_net_time belum ada.")
    
        _prev_net_io = current_net_io
        _prev_net_time = current_network_sample_time 
            
        processes = []
        # Ambil proses setelah CPU percent dihitung agar lebih akurat
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                p_info = proc.info
                # Pastikan nilai tidak None atau NaN dan merupakan float
                p_info['cpu_percent'] = p_info['cpu_percent'] if p_info['cpu_percent'] is not None else 0.0
                p_info['memory_percent'] = p_info['memory_percent'] if p_info['memory_percent'] is not None else 0.0
                processes.append(p_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass # Abaikan proses yang tidak bisa diakses
                
        processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        
        system_status_obj = get_system_status(cpu_percent, ram_percent, disk_percent, gpu_info['usage'], cpu_temp)
        recommendations_list = get_system_recommendations(cpu_percent, ram_percent, disk_percent, gpu_info['usage'], processes)

        response_data = {
            'cpu': {
                'percent': cpu_percent,
                'temperature': cpu_temp, # Bisa 'N/A'
            },
            'ram': {
                'percent': ram_percent,
                'total': ram_total,
                'used': ram_used,
                'free': ram_free,
            },
            'disk': {
                'percent': disk_percent,
                'total': disk_total,
                'used': disk_used,
                'free': disk_free,
            },
            'disk_io': disk_io, # {'read': float, 'write': float}
            'network': {
                'sent': net_sent_total, # Total sent
                'recv': net_recv_total, # Total recv
                'packets_sent': net_packets_sent,
                'packets_recv': net_packets_recv,
                'upload_speed': net_upload_speed, # float MB/s
                'upload_unit': upload_unit, # "MB/s" or "KB/s"
                'download_speed': net_download_speed, # float MB/s
                'download_unit': download_unit,   # string "MB/s" atau "KB/s"
            },
            'processes': processes,
            'gpu': {
                'temperature': gpu_temp, # Bisa 'N/A'
                'name': gpu_info['name'], # Bisa 'N/A'
                'usage': gpu_info['usage'], # Selalu float
                'mem_total': gpu_info['mem_total'], # float
                'mem_used': gpu_info['mem_used'], # float
                'mem_free': gpu_info['mem_free'] # float
            },
            'battery': battery_info, # percent bisa 'N/A'
            'system': {
                'uptime': system_uptime,
                'status': system_status_obj['status'], # string
                'status_details': system_status_obj['details'], # list of strings
                'recommendations': recommendations_list # list of strings
            }
        }
        
        # logger.info("Data monitoring berhasil dibuat")
        return jsonify(response_data)
        
    except Exception as e:
        logger.exception(f"Error pada /data endpoint") # Menggunakan logger.exception untuk stack trace
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Aplikasi monitoring dimulai")
    # Nonaktifkan reloader Flask saat debug=True untuk menghindari reset global var state (opsional, tapi bisa membantu utk _prev_ vars)
    # use_reloader=False penting saat debug variabel global
    app.run(debug=True, host='0.0.0.0', use_reloader=False if os.environ.get("WERKZEUG_RUN_MAIN") == "true" else True)