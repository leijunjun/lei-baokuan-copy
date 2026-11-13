#!/usr/bin/env python3
"""Install the skill only after local dependencies pass a real media smoke test."""

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE / "scripts"))
from ensure_environment import SetupError, ensure_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--dest", type=Path, default=codex_root / "skills" / "lei-baokuan-copy")
    parser.add_argument("--hypit", help="reuse a selected Hypit executable or bin/hypit.mjs")
    args = parser.parse_args()
    target = args.dest.expanduser().absolute()
    try:
        # Validate the target before any installation side effects.
        if target.is_symlink() or (target.exists() and not (target / "SKILL.md").is_file()):
            raise SetupError("目标须为新目录或现有 Skill 目录，且不能是符号链接：" + str(target))
        if target.resolve() != SOURCE and (SOURCE in target.resolve().parents
                                           or target.resolve() in SOURCE.parents):
            raise SetupError("安装目标与源目录不能相互嵌套。")
        report = ensure_environment(args.hypit, smoke=True)
        print("环境自检通过：" + report["hypit_version"].splitlines()[0], flush=True)
        if target.resolve() == SOURCE:
            print("Skill 已在目标位置，已完成环境检查：" + str(target))
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".lei-baokuan-copy-install-", dir=target.parent) as folder:
            staged = Path(folder) / "lei-baokuan-copy"
            shutil.copytree(SOURCE, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            backup = None
            if target.exists():
                backup = target.parent.parent / "skill-backups" / (target.name + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.rename(backup)
            try:
                staged.rename(target)
            except OSError:
                if backup:
                    backup.rename(target)
                raise
        if backup:
            print("旧版备份：" + str(backup))
        print("Skill 安装完成，环境可用：" + str(target))
        return 0
    except (SetupError, OSError, ValueError) as error:
        print("安装未完成：" + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
