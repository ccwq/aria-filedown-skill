import argparse
import json
import os
import platform
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


ARIA2_VERSION = "1.37.0"
RELEASE_BASE = (
    f"https://github.com/aria2/aria2/releases/download/release-{ARIA2_VERSION}"
)
DEFAULT_PROXY_HINTS = [
    "http://localhost:7897",
    "socks5://localhost:7897",
    "http://host.docker.internal:7897",
    "socks5://host.docker.internal:7897",
]
PROGRESS_MODES = {"auto", "tty", "jsonl", "off"}


def get_system_type():
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    if system == "darwin":
        return "darwin"
    return "unknown"


def get_binary_name(system_type):
    return "aria2c.exe" if system_type == "windows" else "aria2c"


def get_release_filename(system_type):
    if system_type == "windows":
        return f"aria2-{ARIA2_VERSION}-win-64bit-build1.zip"
    if system_type == "linux":
        return f"aria2-{ARIA2_VERSION}.tar.xz"
    return None


def resolve_install_dir(explicit_dir=None):
    if explicit_dir:
        return Path(explicit_dir).expanduser().resolve()

    env_dir = os.environ.get("ARIA2C")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    env_bin = os.environ.get("ARIA2C_BIN")
    if env_bin:
        return Path(env_bin).expanduser().resolve().parent
    return None


def is_executable_file(path):
    return path.is_file() and os.access(path, os.X_OK)


def ensure_executable(path):
    if get_system_type() == "windows":
        return

    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def normalize_candidate(candidate):
    if not candidate:
        return None
    return Path(candidate).expanduser().resolve()


def find_via_env_bin():
    env_value = os.environ.get("ARIA2C_BIN")
    candidate = normalize_candidate(env_value)
    if not candidate:
        return None, "ARIA2C_BIN 未设置"
    if is_executable_file(candidate):
        return candidate, f"使用 ARIA2C_BIN 指定的 aria2c: {candidate}"
    return None, f"ARIA2C_BIN 指向的文件不可执行或不存在，将在后续安装阶段尝试自动补齐: {candidate}"


def find_via_path():
    binary_name = get_binary_name(get_system_type())
    found = shutil.which(binary_name)
    if not found:
        return None, f"PATH 中未找到 {binary_name}"

    candidate = normalize_candidate(found)
    if candidate and is_executable_file(candidate):
        return candidate, f"在 PATH 中找到 aria2c: {candidate}"
    return None, f"PATH 中的 {binary_name} 不可执行: {candidate}"


def find_in_install_dir(install_dir):
    if not install_dir:
        return None, "未提供安装目录"

    candidate = install_dir / get_binary_name(get_system_type())
    if is_executable_file(candidate):
        return candidate, f"在安装目录中找到 aria2c: {candidate}"
    return None, f"安装目录中未找到 aria2c: {candidate}"


def resolve_aria2_binary(install_dir=None):
    messages = []

    env_bin, env_msg = find_via_env_bin()
    messages.append(env_msg)
    if env_bin:
        return env_bin, "env_bin", messages

    path_bin, path_msg = find_via_path()
    messages.append(path_msg)
    if path_bin:
        return path_bin, "path", messages

    resolved_install_dir = resolve_install_dir(install_dir)
    if resolved_install_dir:
        install_bin, install_msg = find_in_install_dir(resolved_install_dir)
        messages.append(install_msg)
        if install_bin:
            return install_bin, "install_dir", messages
    else:
        messages.append("ARIA2C 未设置，尚无安装目录可检查")

    return None, None, messages


def build_proxy_opener(proxy):
    if not proxy:
        return urllib.request.build_opener()
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    return urllib.request.build_opener(handler)


def download_file(url, destination, proxy=None):
    opener = build_proxy_opener(proxy)
    with opener.open(url) as response, open(destination, "wb") as output_file:
        shutil.copyfileobj(response, output_file)


def extract_archive(archive_path, install_dir, system_type):
    install_dir.mkdir(parents=True, exist_ok=True)
    binary_name = get_binary_name(system_type)
    binary_path = install_dir / binary_name

    if system_type == "windows":
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.namelist():
                if member.endswith(binary_name):
                    with archive.open(member) as src, open(binary_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
    elif system_type == "linux":
        with tarfile.open(archive_path, "r:xz") as archive:
            for member in archive.getmembers():
                if member.name.endswith(binary_name):
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    with extracted as src, open(binary_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
    else:
        raise RuntimeError(f"当前系统暂不支持自动解压: {system_type}")

    if not binary_path.exists():
        raise FileNotFoundError(f"解压后未找到 {binary_name}")

    ensure_executable(binary_path)
    return binary_path


def get_download_url(system_type):
    filename = get_release_filename(system_type)
    if not filename:
        return None
    return f"{RELEASE_BASE}/{filename}"


def print_proxy_hint():
    print("下载失败，可能是网络问题。建议提供代理后重试。")
    print("可选代理示例:")
    for item in DEFAULT_PROXY_HINTS:
        print(f"  - {item}")


def install_aria2(install_dir=None, proxy=None):
    system_type = get_system_type()
    if system_type not in {"windows", "linux"}:
        print(f"当前系统暂不支持自动下载 aria2: {system_type}")
        return None

    target_dir = resolve_install_dir(install_dir)
    if not target_dir:
        print("安装失败: 未提供安装目录，且环境变量 ARIA2C 未设置。")
        print("请先设置 ARIA2C，或在 skill 流程中先确认使用 ./bin/aria 作为下载目录。")
        return None

    url = get_download_url(system_type)
    archive_name = get_release_filename(system_type)
    archive_path = target_dir / archive_name

    print(f"准备下载 aria2 到: {target_dir}")
    print(f"下载地址: {url}")

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        download_file(url, archive_path, proxy=proxy)
    except urllib.error.URLError as error:
        print(f"下载失败(network): {error}")
        print_proxy_hint()
        return None
    except OSError as error:
        print(f"下载失败(io): {error}")
        print_proxy_hint()
        return None

    try:
        binary_path = extract_archive(archive_path, target_dir, system_type)
    except (tarfile.TarError, zipfile.BadZipFile, FileNotFoundError, OSError) as error:
        print(f"解压失败(extract): {error}")
        return None
    finally:
        if archive_path.exists():
            archive_path.unlink()

    print(f"aria2 安装成功: {binary_path}")
    return binary_path


def maybe_prompt_default_install_dir():
    prompt = "未找到 aria2，且未设置 ARIA2C。是否下载到当前目录的 ./bin/aria ? [y/N]: "
    answer = input(prompt).strip().lower()
    if answer not in {"y", "yes"}:
        print("已取消自动下载。可先设置 ARIA2C 或 ARIA2C_BIN 后重试。")
        return None
    return (Path.cwd() / "bin" / "aria").resolve()


def ensure_aria2_available(install=False, install_dir=None, proxy=None):
    binary_path, source, messages = resolve_aria2_binary(install_dir=install_dir)
    for message in messages:
        print(message)

    if binary_path:
        print(f"最终使用的 aria2c: {binary_path} (source={source})")
        return binary_path

    if not install:
        print("未找到可用的 aria2c。")
        return None

    target_dir = resolve_install_dir(install_dir)
    if not target_dir:
        target_dir = maybe_prompt_default_install_dir()
        if not target_dir:
            return None

    binary_path = install_aria2(install_dir=target_dir, proxy=proxy)
    if binary_path:
        print(f"最终使用的 aria2c: {binary_path} (source=download)")
    return binary_path


def append_default_download_args(cmd):
    has_split = "-s" in cmd or "--split" in cmd
    has_max_conn = "-x" in cmd or "--max-connection-per-server" in cmd
    has_continue = "-c" in cmd or "--continue=true" in cmd

    if not has_split:
        cmd.extend(["-s", "10"])
    if not has_max_conn:
        cmd.extend(["-x", "10"])
    if not has_continue:
        cmd.append("-c")


def iter_option_values(args):
    index = 0
    while index < len(args):
        item = args[index]
        if item.startswith("--") and "=" in item:
            name, value = item.split("=", 1)
            yield name, value
        elif item.startswith("--") and index + 1 < len(args):
            yield item, args[index + 1]
            index += 1
        index += 1


def find_option_value(args, option_name):
    for name, value in iter_option_values(args):
        if name == option_name:
            return value
    return None


def has_flag(args, option_name):
    return option_name in args or any(item.startswith(f"{option_name}=") for item in args)


def reserve_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def create_rpc_config(download_args):
    warnings = []
    user_enable_rpc = find_option_value(download_args, "--enable-rpc")
    if user_enable_rpc == "false":
        warnings.append("检测到用户传入 --enable-rpc=false，无法启用统一进度输出。")
        return None, warnings

    port = find_option_value(download_args, "--rpc-listen-port")
    if port is None:
        port = str(reserve_local_port())
    else:
        warnings.append(f"沿用用户指定的 RPC 端口: {port}")

    secret = find_option_value(download_args, "--rpc-secret")
    if secret is None:
        secret = secrets.token_hex(16)
    else:
        warnings.append("沿用用户指定的 RPC secret。")

    if has_flag(download_args, "--show-console-readout"):
        warnings.append("检测到用户显式配置 --show-console-readout，可能与 wrapper 进度输出叠加。")
    if has_flag(download_args, "--summary-interval"):
        warnings.append("检测到用户显式配置 --summary-interval，可能影响 wrapper 进度节奏。")

    rpc_args = []
    if not has_flag(download_args, "--enable-rpc"):
        rpc_args.append("--enable-rpc=true")
    if not has_flag(download_args, "--rpc-listen-port"):
        rpc_args.append(f"--rpc-listen-port={port}")
    if not has_flag(download_args, "--rpc-secret"):
        rpc_args.append(f"--rpc-secret={secret}")
    if not has_flag(download_args, "--rpc-listen-all"):
        rpc_args.append("--rpc-listen-all=false")
    if not has_flag(download_args, "--show-console-readout"):
        rpc_args.append("--show-console-readout=false")
    if not has_flag(download_args, "--summary-interval"):
        rpc_args.append("--summary-interval=0")
    if not has_flag(download_args, "--console-log-level"):
        rpc_args.append("--console-log-level=warn")

    return {
        "port": int(port),
        "secret": secret,
        "args": rpc_args,
    }, warnings


def rpc_request(port, secret, method, params=None, timeout=3):
    payload = {
        "jsonrpc": "2.0",
        "id": method,
        "method": method,
        "params": [f"token:{secret}", *(params or [])],
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/jsonrpc",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"RPC 错误: {data['error']}")
    return data["result"]


def wait_for_rpc_ready(process, rpc_config, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            rpc_request(
                rpc_config["port"],
                rpc_config["secret"],
                "aria2.getVersion",
            )
            return True
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError):
            time.sleep(0.2)
    return False


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def extract_primary_file(item):
    files = item.get("files") or []
    if files:
        file_path = files[0].get("path")
        if file_path:
            return file_path
        uris = files[0].get("uris") or []
        if uris:
            return uris[0].get("uri")
    return None


def build_progress_snapshot(items):
    if not items:
        return None

    completed_bytes = sum(safe_int(item.get("completedLength")) for item in items)
    total_bytes = sum(safe_int(item.get("totalLength")) for item in items)
    download_speed = sum(safe_int(item.get("downloadSpeed")) for item in items)
    connections = sum(safe_int(item.get("connections")) for item in items)
    percent = 0.0
    if total_bytes > 0:
        percent = round((completed_bytes / total_bytes) * 100, 2)

    remaining = max(total_bytes - completed_bytes, 0)
    eta_seconds = None
    if download_speed > 0:
        eta_seconds = int(remaining / download_speed)

    primary = items[0]
    file_name = extract_primary_file(primary)
    gid = primary.get("gid")
    status = primary.get("status", "active")
    if len(items) > 1:
        file_name = f"{file_name or 'multi-download'} (+{len(items) - 1})"

    return {
        "gid": gid,
        "file": file_name,
        "status": status,
        "percent": percent,
        "completed_bytes": completed_bytes,
        "total_bytes": total_bytes,
        "download_speed": download_speed,
        "eta_seconds": eta_seconds,
        "connections": connections,
        "timestamp": int(time.time()),
    }


def collect_progress_state(rpc_config):
    active_items = rpc_request(
        rpc_config["port"],
        rpc_config["secret"],
        "aria2.tellActive",
    )
    snapshot = build_progress_snapshot(active_items)
    if snapshot:
        return snapshot, "active"

    waiting_items = rpc_request(
        rpc_config["port"],
        rpc_config["secret"],
        "aria2.tellWaiting",
        [0, 10],
    )
    snapshot = build_progress_snapshot(waiting_items)
    if snapshot:
        return snapshot, "waiting"

    stopped_items = rpc_request(
        rpc_config["port"],
        rpc_config["secret"],
        "aria2.tellStopped",
        [0, 10],
    )
    snapshot = build_progress_snapshot(stopped_items)
    if snapshot:
        return snapshot, "stopped"
    return None, None


def format_bytes(value):
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    number = float(value)
    unit_index = 0
    while number >= 1024 and unit_index < len(units) - 1:
        number /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(number)} {units[unit_index]}"
    return f"{number:.1f} {units[unit_index]}"


def format_eta(seconds):
    if seconds is None:
        return "--:--"
    minutes, sec = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


class ProgressReporter:
    def __init__(self, mode, interval, progress_file=None):
        self.mode = mode
        self.interval = interval
        self.progress_file = Path(progress_file).expanduser().resolve() if progress_file else None
        self._last_line_length = 0
        self._file_handle = None
        self._is_tty = sys.stdout.isatty()
        if self.mode == "auto":
            self.render_mode = "tty" if self._is_tty else "text"
        elif self.mode == "tty":
            self.render_mode = "tty" if self._is_tty else "text"
        elif self.mode == "jsonl":
            self.render_mode = "jsonl"
        else:
            self.render_mode = "off"

    def open(self):
        if self.progress_file:
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = self.progress_file.open("a", encoding="utf-8")

    def close(self):
        if self.render_mode == "tty" and self._last_line_length:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_line_length = 0
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def emit_progress(self, snapshot):
        if self.render_mode == "off" or not snapshot:
            return
        if self.render_mode == "jsonl":
            self._write_json({"type": "progress", **snapshot})
            return

        line = (
            f"{snapshot['percent']:6.2f}% | "
            f"{format_bytes(snapshot['completed_bytes'])}/"
            f"{format_bytes(snapshot['total_bytes']) if snapshot['total_bytes'] else '?'} | "
            f"{format_bytes(snapshot['download_speed'])}/s | "
            f"ETA {format_eta(snapshot['eta_seconds'])} | "
            f"{snapshot['file'] or 'unknown'}"
        )
        if self.render_mode == "tty":
            padded = line.ljust(self._last_line_length)
            sys.stdout.write(f"\r{padded}")
            sys.stdout.flush()
            self._last_line_length = len(padded)
        else:
            print(line)

    def emit_terminal(self, event_type, snapshot, returncode):
        snapshot = snapshot or {}
        if self.render_mode == "jsonl":
            payload = {
                "type": event_type,
                "returncode": returncode,
                **snapshot,
                "timestamp": int(time.time()),
            }
            self._write_json(payload)
            return

        if self.render_mode == "tty" and self._last_line_length:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_line_length = 0

        if event_type == "completed":
            print(
                "下载完成: "
                f"{snapshot.get('file') or 'unknown'} | "
                f"{format_bytes(snapshot.get('total_bytes', 0))} | "
                f"exit={returncode}"
            )
        elif event_type == "error":
            print(
                "下载失败: "
                f"{snapshot.get('file') or 'unknown'} | "
                f"status={snapshot.get('status', 'unknown')} | "
                f"exit={returncode}"
            )

    def _write_json(self, payload):
        line = json.dumps(payload, ensure_ascii=False)
        print(line)
        if self._file_handle:
            self._file_handle.write(f"{line}\n")
            self._file_handle.flush()


def stream_process_output(pipe, buffer):
    if pipe is None:
        return
    try:
        for line in pipe:
            text = line.rstrip()
            if text:
                buffer.append(text)
                print(f"[aria2] {text}", file=sys.stderr)
    finally:
        pipe.close()


def launch_download_process(cmd):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines = []
    stderr_thread = threading.Thread(
        target=stream_process_output,
        args=(process.stderr, stderr_lines),
        daemon=True,
    )
    stderr_thread.start()
    return process, stderr_lines, stderr_thread


def monitor_download_process(process, rpc_config, reporter):
    last_snapshot = None
    while process.poll() is None:
        try:
            snapshot, source = collect_progress_state(rpc_config)
            if snapshot:
                last_snapshot = snapshot
                if source != "stopped":
                    reporter.emit_progress(snapshot)
                else:
                    # aria2 开启 RPC 后在下载完成时可能继续驻留，这里主动 shutdown 收尾。
                    try:
                        rpc_request(
                            rpc_config["port"],
                            rpc_config["secret"],
                            "aria2.shutdown",
                        )
                    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError):
                        pass
                    break
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError) as error:
            print(f"进度轮询失败: {error}", file=sys.stderr)
        time.sleep(reporter.interval)
    return last_snapshot


def run_download(download_args, install=False, install_dir=None, proxy=None, progress="auto", progress_interval=1.0, progress_file=None):
    binary_path = ensure_aria2_available(
        install=install,
        install_dir=install_dir,
        proxy=proxy,
    )
    if not binary_path:
        print("aria2 不可用，无法执行下载。")
        return 2

    if progress_file and progress != "jsonl":
        print("--progress-file 仅能与 --progress jsonl 一起使用。")
        return 2

    cmd = [str(binary_path)]
    cmd.extend(download_args)

    if proxy:
        cmd.append(f"--all-proxy={proxy}")

    append_default_download_args(cmd)

    reporter = ProgressReporter(
        mode=progress,
        interval=progress_interval,
        progress_file=progress_file,
    )
    reporter.open()

    try:
        if progress == "off":
            print(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"aria2 执行失败(exit={result.returncode})")
            return result.returncode

        rpc_config, warnings = create_rpc_config(cmd)
        for warning in warnings:
            print(f"提示: {warning}")
        if not rpc_config:
            print("无法为当前下载启用统一进度输出，请调整参数后重试。")
            return 2

        cmd.extend(rpc_config["args"])
        print(f"执行命令: {' '.join(cmd)}")

        process, stderr_lines, stderr_thread = launch_download_process(cmd)
        try:
            if not wait_for_rpc_ready(process, rpc_config):
                process.wait(timeout=2)
                print("aria2 RPC 未能成功启动，无法输出统一进度。", file=sys.stderr)
                if stderr_lines:
                    print("最近的 aria2 输出:", file=sys.stderr)
                    for line in stderr_lines[-10:]:
                        print(f"  {line}", file=sys.stderr)
                return process.returncode if process.returncode is not None else 2

            last_snapshot = monitor_download_process(process, rpc_config, reporter)
            returncode = process.wait()
            stderr_thread.join(timeout=1)

            try:
                final_snapshot, _ = collect_progress_state(rpc_config)
                final_snapshot = final_snapshot or last_snapshot
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError):
                final_snapshot = last_snapshot

            if returncode == 0:
                reporter.emit_terminal("completed", final_snapshot, returncode)
            else:
                reporter.emit_terminal("error", final_snapshot, returncode)
                print(f"aria2 执行失败(exit={returncode})")
            return returncode
        finally:
            if process.poll() is None:
                process.terminate()
    finally:
        reporter.close()


def build_parser():
    parser = argparse.ArgumentParser(
        description="发现、安装并调用 aria2c 的包装脚本。"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查当前是否能找到可用 aria2c，不执行下载。",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="若未找到 aria2c，则按规则下载并安装。",
    )
    parser.add_argument(
        "--install-dir",
        help="显式指定 aria2 下载/解压目录。默认读取环境变量 ARIA2C。",
    )
    parser.add_argument(
        "--proxy",
        help="下载 aria2 或执行下载时使用的代理，例如 http://localhost:7897。",
    )
    parser.add_argument(
        "--progress",
        choices=sorted(PROGRESS_MODES),
        default="auto",
        help="进度输出模式: auto/tty/jsonl/off。默认 auto。",
    )
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=1.0,
        help="进度轮询间隔(秒)，默认 1.0。",
    )
    parser.add_argument(
        "--progress-file",
        help="在 jsonl 模式下将进度事件追加写入文件。",
    )
    parser.add_argument(
        "download_args",
        nargs=argparse.REMAINDER,
        help="透传给 aria2c 的参数，例如 URL、-d、-o 等。",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.progress_interval <= 0:
        print("--progress-interval 必须大于 0。")
        return 1

    download_args = list(args.download_args)
    if download_args and download_args[0] == "--":
        download_args = download_args[1:]

    if args.check:
        binary_path = ensure_aria2_available(
            install=False,
            install_dir=args.install_dir,
            proxy=args.proxy,
        )
        return 0 if binary_path else 1

    if args.install and not download_args:
        binary_path = ensure_aria2_available(
            install=True,
            install_dir=args.install_dir,
            proxy=args.proxy,
        )
        return 0 if binary_path else 1

    if not download_args:
        parser.print_help()
        return 1

    return run_download(
        download_args=download_args,
        install=args.install,
        install_dir=args.install_dir,
        proxy=args.proxy,
        progress=args.progress,
        progress_interval=args.progress_interval,
        progress_file=args.progress_file,
    )


if __name__ == "__main__":
    sys.exit(main())
