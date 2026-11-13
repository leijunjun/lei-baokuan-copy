#!/usr/bin/env python3
"""Check local evidence tools; install a missing Hypit in a user-owned prefix."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HYPIT_PACKAGE = "@hypit/hypit@0.3.1"
MIN_NODE = (22, 15, 0)


class SetupError(RuntimeError):
    pass


def tools_directory():
    override = os.environ.get("LEI_BAOKUAN_COPY_TOOLS")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".cache" / "lei-baokuan-copy" / "tools"


def run(command, timeout=30):
    try:
        result = subprocess.run([str(item) for item in command], capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupError("无法执行 " + str(command[0]) + ": " + str(error)) from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise SetupError(str(command[0]) + " 失败（退出码 " + str(result.returncode)
                         + "）：" + detail)
    return result.stdout.strip()


def prepend_path(directory):
    # Only this process and its children; never edit shell profiles or system PATH.
    current = os.environ.get("PATH", "").split(os.pathsep)
    directory = str(directory)
    if directory not in current:
        os.environ["PATH"] = os.pathsep.join([directory, *current])


def find_tool(name):
    found = shutil.which(name)
    if found:
        return found
    # Common user and package-manager prefixes can exist outside the Agent's PATH.
    for directory in (Path.home() / ".npm-global" / "bin",
                      Path.home() / ".local" / "bin",
                      Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        found = shutil.which(str(directory / name))
        if found:
            prepend_path(directory)
            return found
    return None


def npm_command(arguments):
    npm = find_tool("npm")
    if not npm:
        raise SetupError("缺少 npm；请安装包含 npm 的 Node.js 22.15+ 后重新执行。")
    # npm.cmd cannot be launched directly with shell=False on Windows. Invoke its
    # Node entrypoint instead, keeping paths and arguments out of a command shell.
    if os.name == "nt":
        cli = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if not cli.is_file():
            raise SetupError("无法定位 npm-cli.js；请修复 Node.js/npm 安装：" + str(cli))
        return [find_tool("node"), str(cli), *arguments]
    return [npm, *arguments]


def prefix_launcher(prefix):
    # Use the package's JS entrypoint with the verified Node, avoiding .cmd shims.
    entry = Path(prefix) / "node_modules" / "@hypit" / "hypit" / "bin" / "hypit.mjs"
    if entry.is_file():
        return [find_tool("node"), str(entry)]
    return None


def find_hypit(hint=None):
    if hint:
        expanded = str(Path(hint).expanduser())
        if expanded.endswith(".mjs") and Path(expanded).is_file():
            return [find_tool("node"), str(Path(expanded).resolve())]
        found = shutil.which(expanded)
        if not found:
            raise SetupError("指定的 Hypit 不存在或不可执行：" + hint)
        if found.lower().endswith((".cmd", ".bat")):
            candidate = prefix_launcher(Path(found).parent)
            if candidate:
                return candidate
            raise SetupError("请用 --hypit 指定该安装的 bin/hypit.mjs。")
        return [found]
    found = shutil.which("hypit")
    if found:
        return find_hypit(found)
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = prefix_launcher(directory)
        if candidate:
            return candidate
    candidate = prefix_launcher(tools_directory())
    if candidate:
        return candidate
    found = find_tool("hypit")
    if found:
        return find_hypit(found)
    # Read npm's existing global prefix without installing or changing anything.
    if find_tool("npm"):
        prefix = run(npm_command(["prefix", "--global"])).strip()
        entry = Path(prefix) / "lib" / "node_modules" / "@hypit" / "hypit" / "bin" / "hypit.mjs"
        if entry.is_file():
            return [find_tool("node"), str(entry)]
        return prefix_launcher(prefix)
    return None


def install_hypit(prefix):
    print("未找到 Hypit，安装 " + HYPIT_PACKAGE + " 到 " + str(prefix),
          file=sys.stderr, flush=True)
    Path(prefix).mkdir(parents=True, exist_ok=True)
    # The Distribution declares its runtime dependencies. Avoid npm auto-resolving
    # optional development peers (e.g. Vite devtools/Vitest) for this tool prefix.
    # Bounded attempt; npm keeps its existing registry/proxy configuration.
    run(npm_command(["install", "--prefix", str(prefix), "--no-audit", "--no-fund",
                     "--no-update-notifier", "--fetch-retries=1", "--omit=dev",
                     "--legacy-peer-deps", HYPIT_PACKAGE]), timeout=600)
    command = prefix_launcher(prefix)
    if not command:
        raise SetupError("npm 已结束但 Hypit 入口缺失；请检查 " + str(prefix))
    return command


def smoke_test(command, ffmpeg):
    """Check the real probe/boundaries/tiles/audio path, without accounts or models."""
    with tempfile.TemporaryDirectory(prefix="lei-baokuan-copy-smoke-") as folder:
        root = Path(folder)
        source, audio, grids = root / "sample.mp4", root / "audio.wav", root / "grids"
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-f", "lavfi", "-i", "color=c=blue:s=96x96:r=10:d=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", source])
        probe = json.loads(run([*command, "media", "probe", source, "--json"]))
        if not probe.get("hasVideo") or not probe.get("hasAudio"):
            raise SetupError("Hypit 探测自检失败：测试片的视音轨未被识别。")
        json.loads(run([*command, "media", "boundaries", source, "--json"]))
        run([*command, "media", "tiles", source, "--start", "0", "--end", "1",
             "--every", "0.5", "--columns", "2", "--rows", "1", "--cell", "96",
             "--to", grids, "--json"])
        if not any(path.suffix.lower() in {".png", ".jpg", ".jpeg"}
                   for path in grids.rglob("*")):
            raise SetupError("Hypit 自检未生成拼图。")
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
             "-i", source, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", audio])
        audio_probe = json.loads(run([*command, "media", "probe", audio, "--json"]))
        if not audio_probe.get("hasAudio"):
            raise SetupError("Hypit 自检未识别音频副本。")


def ensure_environment(hypit=None, auto_install=True, smoke=False):
    if sys.version_info < (3, 9):
        raise SetupError("需要 Python 3.9+。")
    node = find_tool("node")
    if not node:
        raise SetupError("缺少 Node.js；请安装 Node.js 22.15+（含 npm）后重新执行。")
    node_version = run([node, "--version"])
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", node_version)
    if not match or tuple(map(int, match.groups())) < MIN_NODE:
        raise SetupError("Node.js 版本不满足 22.15+：" + node_version)
    media = {}
    for name in ("ffmpeg", "ffprobe"):
        executable = find_tool(name)
        if not executable:
            raise SetupError("缺少 " + name + "；请安装 FFmpeg（含 ffprobe）并加入 PATH。"
                             "macOS: brew install ffmpeg；Debian/Ubuntu: apt install ffmpeg；"
                             "Windows: winget install --id Gyan.FFmpeg -e。安装后重新执行。")
        media[name] = {"path": executable, "version": run([executable, "-version"]).splitlines()[0]}
    command = find_hypit(hypit)
    installed = False
    if command is None:
        if not auto_install:
            raise SetupError("Hypit 未安装；去掉 --check 重新执行，可自动安装。")
        command = install_hypit(tools_directory())
        installed = True
    version = run([*command, "version"])
    help_text = run([*command, "media", "--help"])
    if not all(name in help_text for name in ("probe", "boundaries", "tiles")):
        raise SetupError("现有 Hypit 缺少 probe/boundaries/tiles 接口：" + version
                         + "；请修复所选安装，或用 --hypit 指定兼容的安装。")
    if smoke:
        smoke_test(command, media["ffmpeg"]["path"])
    return {"status": "ready", "python": sys.version.split()[0], "node": node_version,
            "hypit_command": command, "hypit_version": version,
            "hypit_installed_now": installed, "tools_directory": str(tools_directory()),
            "media": media, "smoke_test": "passed" if smoke else "not_run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check only; never install")
    parser.add_argument("--smoke", action="store_true", help="exercise local media operations")
    parser.add_argument("--hypit", help="existing Hypit executable or bin/hypit.mjs")
    args = parser.parse_args()
    try:
        report = ensure_environment(args.hypit, auto_install=not args.check, smoke=args.smoke)
    except (SetupError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
