import os
import time
import platform
import psutil


def get_cpu_temp():
    system = platform.system().lower()

    if system == "linux":
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            try:
                with open(thermal_path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                return int(raw) / 1000.0
            except Exception:
                pass

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for entries in temps.values():
                    for entry in entries:
                        if getattr(entry, "current", None) is not None:
                            return float(entry.current)
        except Exception:
            pass

    elif system == "windows":
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for entries in temps.values():
                    for entry in entries:
                        if getattr(entry, "current", None) is not None:
                            return float(entry.current)
        except Exception:
            pass

    return None


def main():
    print("Ctrl+C para sair\n")
    psutil.cpu_percent(interval=None)  # descarta primeira leitura

    while True:
        temp = get_cpu_temp()
        cpu = psutil.cpu_percent(interval=1.0)
        ram = psutil.virtual_memory().percent

        temp_txt = f"{temp:.1f} °C" if temp is not None else "N/A"

        line = f"Temp CPU: {temp_txt} | CPU: {cpu:.1f}% | RAM: {ram:.1f}%"

        if platform.system().lower() == "windows":
            try:
                batt = psutil.sensors_battery()
                if batt is not None:
                    line += f" | Bat: {batt.percent:.0f}%"
            except Exception:
                pass

        print(line)


if __name__ == "__main__":
    main()