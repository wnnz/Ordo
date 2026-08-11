import os
import platform
import shutil
import socket
import subprocess


def _interfaces():
    result = []
    try:
        names = [name for _, name in socket.if_nameindex()]
    except (AttributeError, OSError):
        names = []
    for name in names:
        addresses = []
        try:
            with open(f"/proc/net/fib_trie", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    value = line.strip()
                    if value.count(".") == 3 and value.split()[0].replace(".", "").isdigit():
                        addresses.append(value.split()[0])
        except OSError:
            pass
        result.append({"name": name, "addresses": sorted(set(addresses))})
    return result


def main(inputs, context):
    del inputs, context
    hostname = socket.gethostname()
    interfaces = _interfaces()
    network = {
        "hostname": hostname,
        "fqdn": socket.getfqdn(),
        "interfaces": interfaces,
        "default_gateway": "",
    }
    ipconfig_lines = [f"Host Name . . . . . . . . . . . : {hostname}"]
    command = ["ipconfig", "/all"] if platform.system() == "Windows" else ["ip", "addr"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        if completed.stdout.strip():
            ipconfig_lines.append(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    for interface in interfaces:
        ipconfig_lines.append(f"{interface['name']}: " + ", ".join(interface["addresses"]) if interface["addresses"] else f"{interface['name']}: (no IPv4 address reported)")
    memory_bytes = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    memory_bytes = int(line.split()[1]) * 1024
                    break
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage("/")
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "container": bool(os.path.exists("/.dockerenv")),
        },
        "resources": {
            "cpu_count": os.cpu_count() or 0,
            "memory_bytes": memory_bytes,
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
        },
        "network": network,
        "ipconfig": "\n".join(ipconfig_lines),
    }
