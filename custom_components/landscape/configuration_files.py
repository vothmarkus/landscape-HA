"""Bounded YAML file access, portable exports and recoverable transactions."""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .configuration_yaml import (
    EXCLUDED_DIRS,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ConfigurationError,
    describe,
    merge_yaml,
    safe_path,
    validate_context,
)

SCHEMA_VERSION = 1
BACKUP_DIR = ".storage/landscape_configuration"


def digest(content: bytes | str | None) -> str | None:
    if content is None:
        return None
    return hashlib.sha256(
        content.encode("utf-8") if isinstance(content, str) else content
    ).hexdigest()


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def filename_candidates(name: str, paths: list[str]) -> tuple[list[str], str]:
    """Rank whole filename terms; only a unique best match is preselected."""
    basename = PurePosixPath(name).name
    exact = sorted(path for path in paths if PurePosixPath(path).name == basename)
    if exact:
        return exact, exact[0] if len(exact) == 1 else ""

    def words(path: str) -> list[str]:
        return re.findall(r"[^\W_]+", PurePosixPath(path).stem.casefold())

    incoming = " " + " ".join(words(name)) + " "
    scores = {}
    for path in paths:
        terms = words(path)
        if terms and " " + " ".join(terms) + " " in incoming:
            scores[path] = sum(len(term) for term in terms)
    ranked = sorted(scores, key=lambda path: (-scores[path], path))
    if not ranked:
        return [], ""
    best = [path for path in ranked if scores[path] == scores[ranked[0]]]
    return ranked, best[0] if len(best) == 1 else ""


class ConfigurationFiles:
    """All filesystem methods run in HA's executor."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def path(self, relative: str) -> Path:
        path = self.root
        for part in PurePosixPath(safe_path(relative)).parts:
            path /= part
            if path.is_symlink():
                raise ConfigurationError(
                    f"Symbolische Links sind nicht freigegeben: {relative}"
                )
        if path.exists() and not path.is_file():
            raise ConfigurationError(f"Keine reguläre Datei: {relative}")
        return path

    def read(self, relative: str) -> bytes | None:
        path = self.path(relative)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ConfigurationError("Nur reguläre Dateien werden unterstützt.")
            content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ConfigurationError(f"{relative}: Datei größer als 1 MB.")
        return content

    def snapshot(self) -> tuple[dict, dict, list]:
        files, hashes, skipped, total = {}, {}, [], 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                name
                for name in dirs
                if not name.startswith(".")
                and name not in EXCLUDED_DIRS
                and not (Path(directory) / name).is_symlink()
            )
            for name in sorted(names):
                if (
                    name.startswith(".")
                    or Path(name).suffix not in {".yaml", ".yml"}
                    or name.lower() in {"secrets.yaml", "secrets.yml"}
                ):
                    continue
                path = (Path(directory) / name).relative_to(self.root).as_posix()
                try:
                    content = self.read(path)
                    if content is None:
                        continue
                    text = content.decode("utf-8-sig")
                except (ConfigurationError, UnicodeError, OSError) as err:
                    skipped.append(f"{path}: {type(err).__name__}")
                    continue
                total += len(content)
                if len(files) >= MAX_FILES or total > 20 * MAX_TOTAL_BYTES:
                    raise ConfigurationError(
                        "Inventargrenze überschritten (250 Dateien / 40 MB)."
                    )
                files[path], hashes[path] = text, digest(content)
        return files, hashes, skipped

    def inventory(self) -> dict:
        files, hashes, skipped = self.snapshot()
        details = describe(files)
        return {
            "files": [
                details[path]
                | {"sha256": hashes[path], "size": len(files[path].encode("utf-8"))}
                for path in sorted(files)
            ],
            "skipped": skipped,
            "backups": self.backups(),
        }

    def view(self, path: str) -> dict:
        files, hashes, _ = self.snapshot()
        if path not in files:
            raise ConfigurationError("Datei nicht gefunden oder nicht freigegeben.")
        return describe(files)[path] | {"content": files[path], "sha256": hashes[path]}

    def export(self, paths: list[str] | None, context: bool, dated: bool) -> dict:
        files, hashes, skipped = self.snapshot()
        selected = sorted(files) if paths is None else paths
        if not selected or len(set(selected)) != len(selected):
            raise ConfigurationError("Bitte mindestens eine Datei eindeutig auswählen.")
        if any(path not in files for path in selected):
            raise ConfigurationError(
                "Eine ausgewählte Datei fehlt oder ist nicht freigegeben."
            )
        now = datetime.now(UTC).isoformat()
        contents = {path: self.read(path) for path in selected}
        if any(
            value is None or digest(value) != hashes[path]
            for path, value in contents.items()
        ):
            raise ConfigurationError(
                "Während des Exports geändert. Bitte erneut exportieren."
            )
        if len(selected) == 1 and not context and paths is not None:
            path = PurePosixPath(selected[0])
            filename = f"{path.stem}_{now[:10]}{path.suffix}" if dated else path.name
            payload, mime = contents[selected[0]], "application/yaml"
        else:
            details = describe(files)
            names = [
                str(PurePosixPath(path).with_suffix(".landscape.json"))
                for path in selected
            ]
            if context:
                for path in selected:
                    name = str(PurePosixPath(path).with_suffix(".landscape.json"))
                    if names.count(name) > 1:
                        name = path + ".landscape.json"
                    contents[name] = json_bytes(
                        details[path]
                        | {
                            "schema_version": SCHEMA_VERSION,
                            "exported_at": now,
                            "source_sha256": hashes[path],
                        }
                    )
            contents["landscape-bundle.json"] = json_bytes(
                {
                    "schema_version": SCHEMA_VERSION,
                    "exported_at": now,
                    "files": selected,
                    "skipped": skipped,
                    "scope": "configuration_yaml",
                    "secrets_included": False,
                }
            )
            if sum(len(value) for value in contents.values()) > MAX_TOTAL_BYTES:
                raise ConfigurationError(
                    "Export einschließlich Kontext ist größer als 2 MB; "
                    "weniger Dateien auswählen."
                )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, content in contents.items():
                    archive.writestr(name, content)
            payload, mime = buffer.getvalue(), "application/zip"
            filename = f"landscape_configuration_{now[:10]}.zip"
        return {
            "filename": filename,
            "mime": mime,
            "content": base64.b64encode(payload).decode("ascii"),
            "file_count": len(selected),
        }

    def inspect(self, uploads: list[dict], archive: str | None = None) -> dict:
        """Suggest existing targets without guessing between equally good names."""
        if archive:
            if uploads:
                raise ConfigurationError("Bitte ZIP oder einzelne Dateien auswählen.")
            uploads = unpack_archive(archive)
        if not uploads or len(uploads) > MAX_FILES * 2 + 1:
            raise ConfigurationError(
                "Bitte YAML-Dateien oder ein Configuration-ZIP auswählen."
            )
        if any(
            not isinstance(item.get("content"), str)
            or not isinstance(item.get("filename"), str)
            for item in uploads
        ):
            raise ConfigurationError("Dateiname und Inhalt müssen Text sein.")
        if (
            sum(len(item["content"].encode("utf-8")) for item in uploads)
            > MAX_TOTAL_BYTES
        ):
            raise ConfigurationError("Import ist größer als 2 MB.")
        current, hashes, _ = self.snapshot()
        metadata, yaml_files, names = {}, [], set()
        for item in uploads:
            name, content = item["filename"], item["content"]
            if name in names:
                raise ConfigurationError(f"Dateiname mehrfach hochgeladen: {name}")
            names.add(name)
            if name.endswith(".landscape.json"):
                safe_path(name.removesuffix(".landscape.json") + ".yaml")
                try:
                    info = json.loads(content)
                    if (
                        not isinstance(info, dict)
                        or info.get("schema_version") != SCHEMA_VERSION
                    ):
                        raise ValueError
                    path = safe_path(info["path"])
                    source_hash = info.get("source_sha256")
                    if (
                        not isinstance(source_hash, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
                        or path in metadata
                    ):
                        raise ValueError
                    metadata[path] = info
                except (ValueError, KeyError, TypeError) as err:
                    raise ConfigurationError(f"Ungültige Kontextdatei: {name}") from err
            elif name == "landscape-bundle.json":
                try:
                    if json.loads(content).get("schema_version") != SCHEMA_VERSION:
                        raise ValueError
                except (ValueError, AttributeError) as err:
                    raise ConfigurationError("Unbekanntes Bundle-Format.") from err
            else:
                safe_path(name)
                yaml_files.append((name, content))
        if not yaml_files:
            raise ConfigurationError("Der Import enthält keine YAML-Dateien.")
        details, result = describe(current), []
        for name, content in yaml_files:
            matches, suggestion = filename_candidates(name, list(current))
            if archive or "/" in name:
                # Archive paths must round-trip, including files at the root.
                target = name
                suggested_path = None
            else:
                _, context_target = filename_candidates(name, list(metadata))
                target = context_target or suggestion or (name if not matches else "")
                suggested_path = suggestion if not context_target else None
            info = metadata.get(target, {})
            result.append(
                {
                    "filename": name,
                    "path": target,
                    "content": content,
                    "mode": "replace" if target in current or not target else "create",
                    "candidates": matches,
                    "suggested_path": suggested_path,
                    "type": details.get(target, {}).get("type", "yaml"),
                    "source_sha256": info.get("source_sha256"),
                    "source_path": info.get("path"),
                    "source_matches": not info
                    or hashes.get(target) == info.get("source_sha256"),
                }
            )
        return {"files": result}

    def prepare(self, imports: list[dict], *, restore: bool = False) -> dict:
        if not imports or len(imports) > MAX_FILES:
            raise ConfigurationError("Bitte 1 bis 250 Dateien auswählen.")
        current, hashes, skipped = self.snapshot()
        future, before_info = current.copy(), describe(current)
        changes, seen, total = [], set(), 0
        for item in imports:
            path = safe_path(item.get("path", ""))
            self.path(path)
            if path in seen:
                raise ConfigurationError(f"Ziel mehrfach gewählt: {path}")
            seen.add(path)
            old_bytes = self.read(path)
            if old_bytes is not None and path not in current:
                raise ConfigurationError(
                    f"{path}: Bestehende Datei kann nicht sicher gelesen werden."
                )
            mode = item.get("mode", "replace")
            if mode not in {"replace", "create", "merge"} and not (
                restore and mode == "delete"
            ):
                raise ConfigurationError("Unbekannter Importmodus.")
            if mode == "create" and old_bytes is not None:
                raise ConfigurationError(f"{path}: Ziel existiert; Ersetzen auswählen.")
            if mode in {"replace", "merge", "delete"} and old_bytes is None:
                raise ConfigurationError(
                    f"{path}: Ziel fehlt; als neue Datei importieren."
                )
            if (
                item.get("source_sha256")
                and item.get("source_path") == path
                and hashes.get(path) != item["source_sha256"]
            ):
                raise ConfigurationError(
                    f"{path}: Seit dem Export geändert. Neu exportieren und abgleichen."
                )
            content = item.get("content", "")
            if not isinstance(content, str):
                raise ConfigurationError("YAML-Inhalt muss Text sein.")
            total += len(content.encode("utf-8"))
            if total > MAX_TOTAL_BYTES:
                raise ConfigurationError("Import ist größer als 2 MB.")
            if mode == "merge":
                content = merge_yaml(current[path], content, before_info[path]["type"])
            if mode == "delete":
                future.pop(path)
                new_bytes = None
            else:
                future[path] = content
                new_bytes = (
                    item.get("_restore_bytes", content.encode("utf-8"))
                    if restore
                    else content.encode("utf-8")
                )
            if old_bytes == new_bytes:
                continue
            old_text, new_text = (
                current.get(path, ""),
                content if new_bytes is not None else "",
            )
            diff = "".join(
                difflib.unified_diff(
                    old_text.splitlines(True),
                    new_text.splitlines(True),
                    fromfile=f"aktuell/{path}",
                    tofile=f"import/{path}",
                )
            )
            added = removed = 0
            for tag, a, b, c, d in difflib.SequenceMatcher(
                None, old_text.splitlines(), new_text.splitlines()
            ).get_opcodes():
                if tag in {"insert", "replace"}:
                    added += d - c
                if tag in {"delete", "replace"}:
                    removed += b - a
            changes.append(
                {
                    "path": path,
                    "mode": mode,
                    "before_hash": digest(old_bytes),
                    "after_hash": digest(new_bytes),
                    "before": old_bytes,
                    "after": new_bytes,
                    "diff": diff,
                    "added": added,
                    "removed": removed,
                }
            )
        after_info = describe(future)
        for path, info in after_info.items():
            if path in seen or info["active"]:
                validate_context(path, future[path], info)
                for include in info["includes"]:
                    target = include["target"]
                    if include["tag"] != "!include":
                        target += "/landscape_include_check.yaml"
                    self.path(target)
        for change in changes:
            change["context"] = after_info.get(
                change["path"], before_info.get(change["path"], {})
            )
        return {"changes": changes, "hashes": hashes, "skipped": skipped}

    def check_snapshot(self, plan: dict) -> None:
        _, hashes, skipped = self.snapshot()
        if hashes != plan["hashes"] or skipped != plan["skipped"]:
            raise ConfigurationError(
                "Konfiguration seit der Vorschau geändert. Bitte erneut prüfen."
            )

    def _backup_root(self, *, create: bool = True) -> Path:
        path = self.root
        for part in BACKUP_DIR.split("/"):
            path /= part
            if path.is_symlink():
                raise ConfigurationError(
                    "Backup-Verzeichnis darf kein symbolischer Link sein."
                )
            if create:
                path.mkdir(mode=0o700, exist_ok=True)
        return path

    def _journal_path(self, transaction_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
            raise ConfigurationError("Ungültige Backup-ID.")
        path = self._backup_root(create=False) / transaction_id
        if path.is_symlink():
            raise ConfigurationError("Ungültiges Backup-Verzeichnis.")
        return path

    def _write_atomic(self, path: Path, content: bytes, mode: int = 0o600) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".landscape-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _save_report(self, report: dict) -> None:
        self._write_atomic(
            self._journal_path(report["id"]) / "manifest.json", json_bytes(report)
        )

    def begin(self, plan: dict, user_id: str) -> dict:
        self.check_snapshot(plan)
        self._backup_root()
        transaction_id = uuid4().hex
        folder = self._journal_path(transaction_id)
        folder.mkdir(mode=0o700)
        report = {
            "id": transaction_id,
            "created_at": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            "status": "prepared",
            "files": [],
            "rollback_errors": [],
        }
        for index, change in enumerate(plan["changes"]):
            path = self.path(change["path"])
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            entry = {key: change[key] for key in ("path", "before_hash", "after_hash")}
            entry["mode"] = mode
            entry["backup"] = f"{index}.bin" if change["before"] is not None else None
            if entry["backup"]:
                self._write_atomic(folder / entry["backup"], change["before"])
            report["files"].append(entry)
        self._save_report(report)
        return report

    def write(self, plan: dict, report: dict) -> None:
        self.check_snapshot(plan)
        report["status"] = "pending"
        self._save_report(report)
        for change, entry in zip(plan["changes"], report["files"], strict=True):
            path = self.path(change["path"])
            if digest(self.read(change["path"])) != entry["before_hash"]:
                raise ConfigurationError(f"{change['path']}: Gleichzeitig geändert.")
            if change["after"] is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                self.path(change["path"])
                self._write_atomic(path, change["after"], entry["mode"])

    def check_written(self, plan: dict) -> None:
        _, hashes, skipped = self.snapshot()
        expected = plan["hashes"].copy()
        for change in plan["changes"]:
            if change["after_hash"] is None:
                expected.pop(change["path"], None)
            else:
                expected[change["path"]] = change["after_hash"]
        if hashes != expected or skipped != plan["skipped"]:
            raise ConfigurationError(
                "Gleichzeitige Dateiänderung während der Übernahme erkannt."
            )

    def finish(self, report: dict) -> None:
        report["status"] = "applied"
        report["finished_at"] = datetime.now(UTC).isoformat()
        self._save_report(report)

    def _backup_content(self, folder: Path, item: dict) -> bytes:
        if not re.fullmatch(r"\d+\.bin", item["backup"] or ""):
            raise ConfigurationError("Ungültiger Backup-Dateiname.")
        path = folder / item["backup"]
        if path.is_symlink():
            raise ConfigurationError("Backup darf kein symbolischer Link sein.")
        with path.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        if digest(content) != item["before_hash"] or len(content) > MAX_FILE_BYTES:
            raise ConfigurationError("Backup-Prüfsumme stimmt nicht überein.")
        return content

    def rollback(self, report: dict) -> dict:
        errors, folder = [], self._journal_path(report["id"])
        for item in reversed(report["files"]):
            try:
                path = self.path(item["path"])
                current_hash = digest(self.read(item["path"]))
                if current_hash == item["before_hash"]:
                    continue
                if current_hash != item["after_hash"]:
                    raise ConfigurationError(
                        "Datei wurde außerhalb von Landscape geändert."
                    )
                if item["backup"]:
                    self._write_atomic(
                        path, self._backup_content(folder, item), item["mode"]
                    )
                else:
                    path.unlink()
            except (OSError, ConfigurationError):
                errors.append(item["path"])
        report["rollback_errors"] = errors
        report["status"] = "recovery_required" if errors else "rolled_back"
        report["finished_at"] = datetime.now(UTC).isoformat()
        self._save_report(report)
        return report

    def _load_report(self, transaction_id: str) -> dict:
        path = self._journal_path(transaction_id) / "manifest.json"
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_FILE_BYTES
        ):
            raise ConfigurationError("Backup-Protokoll fehlt oder ist ungültig.")
        report = json.loads(path.read_text())
        if report.get("id") != transaction_id:
            raise ConfigurationError("Backup-Protokoll passt nicht zur ID.")
        return report

    def backups(self) -> list[dict]:
        root = self._backup_root(create=False)
        if not root.exists():
            return []
        reports = []
        for path in root.iterdir():
            if path.is_symlink() or not re.fullmatch(r"[0-9a-f]{32}", path.name):
                continue
            try:
                report = self._load_report(path.name)
                reports.append(
                    {
                        key: report.get(key)
                        for key in (
                            "id",
                            "created_at",
                            "status",
                            "files",
                            "rollback_errors",
                            "error",
                            "validation",
                        )
                    }
                )
            except (OSError, ValueError):
                reports.append(
                    {
                        "id": path.name,
                        "created_at": "",
                        "status": "recovery_required",
                        "files": [],
                        "rollback_errors": ["Backup-Protokoll nicht lesbar."],
                    }
                )
        return sorted(reports, key=lambda item: item["created_at"], reverse=True)

    def recover(self) -> None:
        for summary in self.backups():
            if summary["status"] == "pending":
                self.rollback(self._load_report(summary["id"]))

    def restore_plan(self, transaction_id: str) -> dict:
        report = self._load_report(transaction_id)
        if report["status"] != "applied":
            raise ConfigurationError(
                "Nur erfolgreich übernommene Importe können zurückgesetzt werden."
            )
        folder, imports = self._journal_path(transaction_id), []
        for item in report["files"]:
            current = self.read(item["path"])
            if digest(current) != item["after_hash"]:
                raise ConfigurationError(
                    f"{item['path']}: Seit diesem Import geändert; "
                    "Rücksetzung gesperrt."
                )
            content = self._backup_content(folder, item) if item["backup"] else None
            mode = (
                "delete"
                if content is None
                else "create"
                if current is None
                else "replace"
            )
            imports.append(
                {
                    "path": item["path"],
                    "mode": mode,
                    "content": content.decode("utf-8-sig")
                    if content is not None
                    else "",
                    "_restore_bytes": content,
                }
            )
        return self.prepare(imports, restore=True)


def unpack_archive(encoded: str) -> list[dict]:
    """Read YAML ZIPs in memory; reject traversal, links and decompression bombs."""
    if len(encoded) > 4 * MAX_TOTAL_BYTES // 3 + 10000:
        raise ConfigurationError("ZIP-Datei ist zu groß.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > MAX_FILES * 2 + 1
                or sum(item.file_size for item in entries) > MAX_TOTAL_BYTES
            ):
                raise ConfigurationError(
                    "ZIP überschreitet 2 MB entpackt oder 501 Einträge."
                )
            result, seen = [], set()
            for item in entries:
                name = item.filename
                if (
                    name in seen
                    or item.flag_bits & 1
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise ConfigurationError(
                        "ZIP enthält doppelte, verschlüsselte oder verlinkte Einträge."
                    )
                seen.add(name)
                if item.is_dir():
                    safe_path(name.rstrip("/"), directory=True)
                    continue
                if item.file_size > MAX_FILE_BYTES:
                    raise ConfigurationError("Eine Datei überschreitet 1 MB.")
                if name.endswith(".landscape.json"):
                    safe_path(name.removesuffix(".landscape.json") + ".yaml")
                elif name != "landscape-bundle.json":
                    safe_path(name)
                result.append(
                    {
                        "filename": name,
                        "content": archive.read(item).decode("utf-8-sig"),
                    }
                )
            return result
    except (
        ValueError,
        UnicodeError,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
    ) as err:
        raise ConfigurationError(
            "Ungültiges oder nicht unterstütztes Configuration-ZIP."
        ) from err
