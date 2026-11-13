#!/usr/bin/env python3
"""Collect timed video evidence through Hypit; semantic reading is left to the Agent."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ensure_environment import SetupError, ensure_environment


class EvidenceError(Exception):
    pass


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Collector:
    def __init__(self, executable, out, timeout, source):
        self.executable = executable
        self.out = out
        self.timeout = timeout
        self.manifest = {
            "schema": "lei-baokuan-copy.evidence@1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "input": source,
            "status": "running",
            "steps": [],
            "warnings": [],
            "semantic_analysis": "not_performed",
        }
        (out / "logs").mkdir()

    def save(self):
        self.manifest["artifacts"] = sorted(
            str(path.relative_to(self.out))
            for path in self.out.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        )
        write_json(self.out / "manifest.json", self.manifest)

    def run(self, name, arguments, json_file=None, required=False, executable=None):
        command = ([executable] if executable else self.executable) + list(map(str, arguments))
        record = {"name": name, "command": command, "status": "running"}
        self.manifest["steps"].append(record)
        stdout_path = self.out / "logs" / (name + ".stdout.txt")
        stderr_path = self.out / "logs" / (name + ".stderr.txt")
        record.update(stdout=str(stdout_path.relative_to(self.out)),
                      stderr=str(stderr_path.relative_to(self.out)))
        self.save()
        print("Running: " + name, file=sys.stderr, flush=True)
        value = None
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout, \
                    stderr_path.open("w", encoding="utf-8") as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr,
                                        timeout=self.timeout, check=False)
            record["returncode"] = result.returncode
            if result.returncode:
                detail = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
                if not detail:
                    raw = stdout_path.read_text(encoding="utf-8", errors="replace")
                    try:
                        detail = json.loads(raw).get("error", {}).get("message", "")
                    except (ValueError, AttributeError):
                        detail = raw.strip()
                raise EvidenceError("command returned exit code " + str(result.returncode)
                                    + (": " + detail[:800] if detail else ""))
            if json_file:
                value = json.loads(stdout_path.read_text(encoding="utf-8"))
                write_json(self.out / json_file, value)
            record["status"] = "ok"
        except (OSError, subprocess.TimeoutExpired, ValueError, EvidenceError) as error:
            record["status"] = "failed"
            record["error"] = str(error)
            self.manifest["warnings"].append(name + ": " + str(error))
            if required:
                raise EvidenceError(name + " failed; inspect " + str(stderr_path)) from error
        finally:
            self.save()
        return record["status"] == "ok", value

    def require_file(self, step, path):
        if not path.is_file() or path.stat().st_size == 0:
            self.manifest["warnings"].append(step + ": expected file missing or empty")
            return False
        return True


def collect(args, collector, local_source, is_url):
    collector.run("version", ["version"], required=True)
    collector.manifest["hypit_version"] = (
        collector.out / "logs/version.stdout.txt"
    ).read_text(encoding="utf-8").strip()
    source = local_source
    if is_url:
        source = collector.out / "source.mp4"
        collector.run("download", ["download", args.source, "--to", source, "--json"],
                      json_file="download.json", required=True)
        if not collector.require_file("download", source):
            raise EvidenceError("download did not produce a usable source file")
    collector.manifest["source"] = {
        "path": str(source), "sha256": digest(source), "bytes": source.stat().st_size,
    }
    _, probe = collector.run("probe", ["media", "probe", source, "--json"],
                             json_file="probe.json", required=True)
    if not isinstance(probe, dict):
        raise EvidenceError("unsupported Hypit probe JSON; expected an object")
    duration = probe.get("duration")
    if not probe.get("hasVideo") or not isinstance(duration, (float, int)) \
            or not math.isfinite(duration) or duration <= 0:
        raise EvidenceError("source must contain video with a finite positive duration")

    collector.run("boundaries", ["media", "boundaries", source, "--json"],
                  json_file="boundaries.json")
    transcript = None
    if args.transcript:
        transcript = collector.out / "transcript.json"
        shutil.copyfile(Path(args.transcript).expanduser().resolve(), transcript)
        collector.manifest["transcript_origin"] = "user-supplied; verify same source clock"
    elif args.transcribe and probe.get("hasAudio"):
        target = collector.out / "transcript.json"
        command = ["transcribe", source, "--language", args.language, "--to", target]
        if args.runtime:
            command.extend(["--runtime", str(Path(args.runtime).expanduser().resolve())])
        if args.project:
            command.extend(["--project", str(Path(args.project).expanduser().resolve())])
        ok, _ = collector.run("transcribe", command)
        if ok and collector.require_file("transcribe", target):
            transcript = target
            collector.manifest["transcript_origin"] = "hypit transcribe"
    elif args.transcribe:
        collector.manifest["transcript_status"] = "skipped: source has no audio stream"

    # Starting at zero retains one valid sample even when a clip is very short.
    command = ["media", "tiles", source, "--start", "0", "--end", str(duration),
               "--every", str(args.every), "--columns", "3", "--rows", "3",
               "--cell", "480", "--to", collector.out / "grids", "--json"]
    if transcript:
        command.extend(["--transcript", transcript])
    grid_ok, _ = collector.run("tiles", command, json_file="tiles.json")
    # Transcript incompatibility should not prevent collecting visual evidence.
    if not grid_ok and transcript:
        collector.run("tiles-without-transcript", [
            "media", "tiles", source, "--start", "0", "--end", str(duration),
            "--every", str(args.every), "--columns", "3", "--rows", "3",
            "--cell", "480", "--to", collector.out / "grids-without-transcript", "--json",
        ], json_file="tiles-without-transcript.json")
    grid_files = [path for path in collector.out.glob("grids*/*")
                  if path.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    if not grid_files:
        collector.manifest["warnings"].append("no grid images produced; visual review unavailable")

    if probe.get("hasAudio"):
        # Hypit 0.3.1 cut retains video streams; use ffmpeg for an audio-only copy.
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            ok, _ = collector.run("audio", [
                "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", source,
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", collector.out / "audio.wav",
            ], executable=ffmpeg)
            if ok and collector.require_file("audio", collector.out / "audio.wav"):
                collector.run("audio-probe", ["media", "probe", collector.out / "audio.wav",
                                               "--json"], json_file="audio.json")
        else:
            collector.manifest["warnings"].append("ffmpeg unavailable; listen to the source audio")
        collector.manifest["audio_review"] = "required; listen to source or audio.wav"
        if transcript is None:
            collector.manifest["transcript_status"] = "not available; do not infer absence of speech"
    else:
        collector.manifest["audio_review"] = "source has no audio stream"
    collector.manifest["status"] = "partial" if collector.manifest["warnings"] else "complete"
    return 2 if collector.manifest["warnings"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="local video path or HTTP(S) video URL")
    parser.add_argument("--out", required=True, help="new evidence directory; never overwritten")
    parser.add_argument("--hypit", help="existing Hypit executable or bin/hypit.mjs")
    parser.add_argument("--no-install", action="store_true",
                       help="check dependencies without installing missing Hypit")
    parser.add_argument("--every", type=positive_number, default=1.0, help="grid interval in seconds")
    parser.add_argument("--timeout", type=positive_number, default=300, help="per-command seconds")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--transcript", help="existing same-source Hypit transcript JSON")
    group.add_argument("--transcribe", action="store_true",
                       help="explicitly invoke selected transcription service; may incur cost")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--runtime", help="existing selected Runtime Profile path")
    parser.add_argument("--project", help="existing Hypit project directory for transcription")
    args = parser.parse_args()
    if args.every < 0.001:
        parser.error("--every must be at least 0.001 seconds (Hypit minimum)")
    if (args.runtime or args.project) and not args.transcribe:
        parser.error("--runtime/--project require --transcribe")
    if args.transcript:
        transcript = Path(args.transcript).expanduser().resolve()
        if not transcript.is_file():
            parser.error("transcript does not exist")
        try:
            json.loads(transcript.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            parser.error("cannot read transcript JSON: " + str(error))
    is_url = urlsplit(args.source).scheme.lower() in {"http", "https"}
    source = None if is_url else Path(args.source).expanduser().resolve()
    if source is not None and not source.is_file():
        parser.error("source file does not exist")
    out = Path(args.out).expanduser().resolve()
    if out.exists():
        parser.error("output directory already exists; choose a new --out path")
    try:
        environment = ensure_environment(args.hypit, auto_install=not args.no_install)
    except (SetupError, OSError, ValueError) as error:
        print("Environment not ready: " + str(error), file=sys.stderr)
        return 1
    try:
        out.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print("Cannot create new output directory: " + str(error), file=sys.stderr)
        return 1
    collector = Collector(environment["hypit_command"], out, args.timeout, args.source)
    collector.manifest["environment"] = environment
    try:
        code = collect(args, collector, source, is_url)
    except (OSError, ValueError, EvidenceError) as error:
        collector.manifest["status"] = "failed"
        collector.manifest["error"] = str(error)
        print(str(error), file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        collector.manifest["status"] = "interrupted"
        code = 130
    finally:
        collector.save()
    print(str(out / "manifest.json"))
    return code


if __name__ == "__main__":
    sys.exit(main())
