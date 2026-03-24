import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
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
    return None, f"ARIA2C_BIN 指向的文件不可执行或不存在: {candidate}"


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


def run_download(download_args, install=False, install_dir=None, proxy=None):
    binary_path = ensure_aria2_available(
        install=install,
        install_dir=install_dir,
        proxy=proxy,
    )
    if not binary_path:
        print("aria2 不可用，无法执行下载。")
        return 2

    cmd = [str(binary_path)]
    cmd.extend(download_args)

    if proxy:
        cmd.append(f"--all-proxy={proxy}")

    append_default_download_args(cmd)
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"aria2 执行失败(exit={result.returncode})")
    return result.returncode


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
        "download_args",
        nargs=argparse.REMAINDER,
        help="透传给 aria2c 的参数，例如 URL、-d、-o 等。",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

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
    )


if __name__ == "__main__":
    sys.exit(main())
