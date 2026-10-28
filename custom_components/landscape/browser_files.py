"""Browse regular /config files and exchange their exact bytes with review."""

from __future__ import annotations

import ast
import base64
import difflib
import io
import json
import os
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from .configuration_files import (
    ConfigurationFiles,
    digest,
    filename_candidates,
    json_bytes,
)
from .configuration_yaml import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ConfigurationError,
    safe_path,
)

MAX_ENTRIES = 10_000
METADATA = ".landscape-browser/manifest.json"
EXCLUDED = {"deps", "venv", "node_modules", "__pycache__", "backups", "backup"}


def browser_path(value: str) -> str:
    """Confine all file types to regular, non-hidden configuration paths."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 240
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ConfigurationError("Bitte einen gültigen relativen Dateipfad angeben.")
    parts = value.split("/")
    if any(
        not part
        or part.startswith(".")
        or part in EXCLUDED
        or part.casefold() in {"secrets.yaml", "secrets.yml"}
        for part in parts
    ):
        raise ConfigurationError(f"Pfad nicht freigegeben: {value}")
    if parts[-1].startswith(("home-assistant_v2.db", "home-assistant.log")):
        raise ConfigurationError("Laufende HA-Datenbanken und Logs sind geschützt.")
    return PurePosixPath(value).as_posix()


def text_content(content: bytes | None) -> str | None:
    if content is None:
        return ""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        return None
    return text if not any(ord(c) < 32 and c not in "\n\r\t" for c in text) else None


def upload_bytes(item: dict) -> bytes:
    content = item.get("content")
    if not isinstance(content, str):
        raise ConfigurationError("Dateiinhalt fehlt.")
    if len(content) > 4 * MAX_FILE_BYTES // 3 + 4:
        raise ConfigurationError("Eine Datei darf höchstens 1 MB groß sein.")
    try:
        encoding = item.get("encoding", "utf-8")
        if encoding not in {"utf-8", "base64"}:
            raise ValueError
        raw = (
            base64.b64decode(content, validate=True)
            if encoding == "base64"
            else content.encode("utf-8")
        )
    except (ValueError, UnicodeError) as err:
        raise ConfigurationError(
            "Ungültiger Dateiinhalt oder ungültige Kodierung."
        ) from err
    if len(raw) > MAX_FILE_BYTES:
        raise ConfigurationError("Eine Datei darf höchstens 1 MB groß sein.")
    return raw


class BrowserFiles(ConfigurationFiles):
    """Reuse atomic writes, private backups, rollback and crash recovery."""

    backup_dir = ".storage/landscape_browser"

    def path(self, relative: str) -> Path:
        path = self.root
        for part in PurePosixPath(browser_path(relative)).parts:
            path /= part
            if path.is_symlink():
                raise ConfigurationError(
                    f"Symbolischer Link nicht freigegeben: {relative}"
                )
        if path.exists() and not path.is_file():
            raise ConfigurationError(f"Keine reguläre Datei: {relative}")
        return path

    def inventory(self) -> dict:
        """List metadata only; browsing never reads every file into memory."""
        files, directories, skipped = [], [], []
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                name
                for name in dirs
                if not name.startswith(".")
                and name not in EXCLUDED
                and not (Path(directory) / name).is_symlink()
            )
            for name in dirs:
                path = (Path(directory) / name).relative_to(self.root).as_posix()
                directories.append(path)
            if len(files) + len(directories) > MAX_ENTRIES:
                raise ConfigurationError(
                    "Browsergrenze von 10000 Einträgen überschritten."
                )
            for name in sorted(names):
                relative = (Path(directory) / name).relative_to(self.root).as_posix()
                try:
                    path = self.path(relative)
                    info = path.stat()
                    if not stat.S_ISREG(info.st_mode):
                        continue
                except (ConfigurationError, OSError):
                    continue
                files.append(
                    {
                        "path": relative,
                        "type": path.suffix.lstrip(".").lower() or "Datei",
                        "size": info.st_size,
                        "modified_at": datetime.fromtimestamp(
                            info.st_mtime, UTC
                        ).isoformat(),
                        "available": info.st_size <= MAX_FILE_BYTES,
                        "merge_supported": False,
                    }
                )
                if len(files) + len(directories) > MAX_ENTRIES:
                    raise ConfigurationError(
                        "Browsergrenze von 10000 Einträgen überschritten."
                    )
        # Reuse YAML roles for merge controls without reading unrelated binary files.
        try:
            yaml_inventory = ConfigurationFiles(str(self.root)).inventory()
            yaml_details = {item["path"]: item for item in yaml_inventory["files"]}
        except ConfigurationError:
            yaml_details = {}
        for item in files:
            item["merge_supported"] = yaml_details.get(item["path"], {}).get(
                "merge_supported", False
            )
        return {
            "files": sorted(files, key=lambda item: item["path"]),
            "directories": sorted(directories),
            "skipped": skipped,
            "backups": self.backups(),
        }

    def view(self, path: str) -> dict:
        raw = self.read(path)
        if raw is None:
            raise ConfigurationError("Datei nicht gefunden.")
        text = text_content(raw)
        return {
            "path": path,
            "type": PurePosixPath(path).suffix.lstrip(".") or "Datei",
            "size": len(raw),
            "sha256": digest(raw),
            "binary": text is None,
            "content": text,
        }

    def export(
        self, paths: list[str] | None, context: bool, dated: bool, bundle: bool = False
    ) -> dict:
        selected = (
            [item["path"] for item in self.inventory()["files"] if item["available"]]
            if paths is None
            else paths
        )
        if (
            not selected
            or len(selected) > MAX_FILES
            or len(set(selected)) != len(selected)
        ):
            raise ConfigurationError("Bitte 1 bis 250 Dateien eindeutig auswählen.")
        contents, total = {}, 0
        for path in selected:
            raw = self.read(path)
            if raw is None:
                raise ConfigurationError(f"Datei fehlt: {path}")
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ConfigurationError(
                    "Export ist größer als 2 MB; weniger Dateien auswählen."
                )
            contents[path] = raw
        now = datetime.now(UTC).isoformat()
        if len(selected) == 1 and not context and paths is not None and not bundle:
            name = PurePosixPath(selected[0])
            filename = f"{name.stem}_{now[:10]}{name.suffix}" if dated else name.name
            payload, mime = contents[selected[0]], "application/octet-stream"
        else:
            manifest = {
                "scope": "landscape_browser",
                "schema_version": 1,
                "exported_at": now,
                "files": [
                    {"path": path} | ({"source_sha256": digest(raw)} if context else {})
                    for path, raw in contents.items()
                ],
            }
            contents[METADATA] = json_bytes(manifest)
            if sum(map(len, contents.values())) > MAX_TOTAL_BYTES:
                raise ConfigurationError(
                    "Export einschließlich Kontext ist größer als 2 MB."
                )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path, raw in contents.items():
                    archive.writestr(path, raw)
            payload, mime = buffer.getvalue(), "application/zip"
            filename = f"landscape_browser_{now[:10]}.zip"
        return {
            "filename": filename,
            "mime": mime,
            "content": base64.b64encode(payload).decode("ascii"),
            "file_count": len(selected),
        }

    def inspect(self, uploads: list[dict], archive: str | None = None) -> dict:
        metadata = {}
        if archive is not None:
            if uploads:
                raise ConfigurationError("Bitte ZIP oder einzelne Dateien auswählen.")
            uploads, metadata = unpack_browser_archive(archive)
        if not uploads or len(uploads) > MAX_FILES:
            raise ConfigurationError("Bitte 1 bis 250 Dateien auswählen.")
        paths = [
            item["path"] for item in self.inventory()["files"] if item["available"]
        ]
        files, seen, total = [], set(), 0
        for item in uploads:
            name = browser_path(item.get("filename", ""))
            if name in seen:
                raise ConfigurationError(f"Dateiname mehrfach hochgeladen: {name}")
            seen.add(name)
            raw = upload_bytes(item)
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ConfigurationError("Import ist größer als 2 MB.")
            candidates, suggestion = filename_candidates(
                name,
                [
                    path
                    for path in paths
                    if PurePosixPath(path).suffix == PurePosixPath(name).suffix
                ],
            )
            target = (
                name
                if archive is not None or "/" in name
                else suggestion or ("" if candidates else name)
            )
            source = metadata.get(target)
            current = self.read(target) if target else None
            files.append(
                {
                    "filename": name,
                    "path": target,
                    "mode": "replace"
                    if current is not None or not target
                    else "create",
                    "content": base64.b64encode(raw).decode("ascii"),
                    "encoding": "base64",
                    "binary": text_content(raw) is None,
                    "candidates": candidates,
                    "suggested_path": suggestion if archive is None else None,
                    "source_path": target if source else None,
                    "source_sha256": source,
                    "source_matches": not source or digest(current) == source,
                }
            )
        return {"files": files}

    def prepare(self, imports: list[dict], *, restore: bool = False) -> dict:
        if not imports or len(imports) > MAX_FILES:
            raise ConfigurationError("Bitte 1 bis 250 Dateien auswählen.")
        changes, hashes, seen, yaml_imports, total = [], {}, set(), [], 0
        for item in imports:
            path = browser_path(item.get("path", ""))
            old = self.read(path)
            mode = item.get("mode", "replace")
            if path in seen:
                raise ConfigurationError(f"Ziel mehrfach gewählt: {path}")
            seen.add(path)
            if mode not in {"replace", "create", "merge"} and not (
                restore and mode == "delete"
            ):
                raise ConfigurationError("Unbekannter Importmodus.")
            if mode == "create" and old is not None:
                raise ConfigurationError(f"{path}: Ziel existiert; Ersetzen auswählen.")
            if mode != "create" and old is None:
                raise ConfigurationError(
                    f"{path}: Ziel fehlt; als neue Datei importieren."
                )
            if (
                item.get("source_sha256")
                and item.get("source_path") == path
                and digest(old) != item["source_sha256"]
            ):
                raise ConfigurationError(
                    f"{path}: Seit dem Export geändert. Neu exportieren und abgleichen."
                )
            raw = None if mode == "delete" else upload_bytes(item)
            total += len(raw or b"")
            if total > MAX_TOTAL_BYTES:
                raise ConfigurationError("Import ist größer als 2 MB.")
            supported_yaml = True
            try:
                safe_path(path)
            except ConfigurationError:
                supported_yaml = False
            if supported_yaml:
                text = text_content(raw)
                if text is None:
                    raise ConfigurationError(f"{path}: YAML muss UTF-8-Text sein.")
                yaml_imports.append({"path": path, "content": text, "mode": mode})
            elif mode == "merge":
                raise ConfigurationError(
                    "Zusammenführen ist nur für geeignete HA-YAML-Dateien möglich."
                )
            if raw is not None:
                validate_file(path, raw, yaml_checked=supported_yaml)
            hashes[path] = digest(old)
            changes.append({"path": path, "mode": mode, "before": old, "after": raw})
        yaml_files = ConfigurationFiles(str(self.root))
        yaml_plan = (
            yaml_files.prepare(yaml_imports, restore=restore) if yaml_imports else None
        )
        yaml_changes = (
            {change["path"]: change for change in yaml_plan["changes"]}
            if yaml_plan
            else {}
        )
        result = []
        for change in changes:
            path = change["path"]
            if change["mode"] == "merge":
                change["after"] = yaml_changes.get(path, {}).get(
                    "after", change["before"]
                )
            if change["before"] == change["after"]:
                continue
            before, after = (
                text_content(change["before"]),
                text_content(change["after"]),
            )
            binary = before is None or after is None
            diff, added, removed = "", 0, 0
            if not binary:
                diff = "".join(
                    line
                    if line.endswith("\n")
                    else line + "\n\\ No newline at end of file\n"
                    for line in difflib.unified_diff(
                        before.splitlines(True),
                        after.splitlines(True),
                        fromfile=f"aktuell/{path}",
                        tofile=f"import/{path}",
                    )
                )
                for tag, a, b, c, d in difflib.SequenceMatcher(
                    None, before.splitlines(), after.splitlines()
                ).get_opcodes():
                    if tag in {"insert", "replace"}:
                        added += d - c
                    if tag in {"delete", "replace"}:
                        removed += b - a
            change.update(
                {
                    "before_hash": digest(change["before"]),
                    "after_hash": digest(change["after"]),
                    "before_size": len(change["before"] or b""),
                    "after_size": len(change["after"] or b""),
                    "binary": binary,
                    "diff": diff,
                    "added": added,
                    "removed": removed,
                    "context": yaml_changes.get(path, {}).get(
                        "context",
                        {
                            "type": PurePosixPath(path).suffix.lstrip(".") or "Datei",
                            "warnings": [],
                        },
                    ),
                }
            )
            result.append(change)
        if yaml_plan is not None:
            yaml_paths = {item["path"] for item in yaml_imports}
            yaml_plan["changes"] = [
                change for change in result if change["path"] in yaml_paths
            ]
        return {
            "changes": result,
            "hashes": hashes,
            "skipped": [],
            "yaml_plan": yaml_plan,
        }

    def check_snapshot(self, plan: dict) -> None:
        if any(
            digest(self.read(path)) != expected
            for path, expected in plan["hashes"].items()
        ):
            raise ConfigurationError(
                "Datei seit der Vorschau geändert. Bitte erneut prüfen."
            )
        if plan.get("yaml_plan"):
            ConfigurationFiles(str(self.root)).check_snapshot(plan["yaml_plan"])

    def check_written(self, plan: dict) -> None:
        expected = plan["hashes"].copy()
        expected.update(
            {change["path"]: change["after_hash"] for change in plan["changes"]}
        )
        if any(digest(self.read(path)) != value for path, value in expected.items()):
            raise ConfigurationError(
                "Gleichzeitige Dateiänderung während der Übernahme erkannt."
            )
        if plan.get("yaml_plan"):
            ConfigurationFiles(str(self.root)).check_written(plan["yaml_plan"])

    def restore_plan(self, transaction_id: str) -> dict:
        report = self._load_report(transaction_id)
        if report["status"] != "applied":
            raise ConfigurationError(
                "Nur übernommene Importe können zurückgesetzt werden."
            )
        folder, imports = self._journal_path(transaction_id), []
        for item in report["files"]:
            current = self.read(item["path"])
            if digest(current) != item["after_hash"]:
                raise ConfigurationError(
                    f"{item['path']}: Seit diesem Import geändert; "
                    "Rücksetzung gesperrt."
                )
            raw = self._backup_content(folder, item) if item["backup"] else None
            imports.append(
                {
                    "path": item["path"],
                    "mode": "delete"
                    if raw is None
                    else "create"
                    if current is None
                    else "replace",
                    "content": base64.b64encode(raw or b"").decode("ascii"),
                    "encoding": "base64",
                }
            )
        return self.prepare(imports, restore=True)


def validate_file(path: str, raw: bytes, *, yaml_checked: bool) -> None:
    """Check known text syntax without executing code or constructing YAML tags."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in {".json", ".py", ".yaml", ".yml"} or yaml_checked:
        return
    try:
        text = raw.decode("utf-8-sig")
        if suffix == ".json":
            json.loads(text)
        elif suffix == ".py":
            ast.parse(text, filename=path)
        else:
            depth = 0
            for count, event in enumerate(yaml.parse(text, Loader=yaml.SafeLoader), 1):
                if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                    depth += 1
                elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                    depth -= 1
                if depth > 50 or count > 50000:
                    raise ValueError("YAML ist zu tief verschachtelt oder zu groß.")
            yaml.compose(text, Loader=yaml.SafeLoader)
    except (
        ValueError,
        SyntaxError,
        UnicodeError,
        yaml.YAMLError,
        RecursionError,
    ) as err:
        raise ConfigurationError(
            f"{path}: Syntaxprüfung fehlgeschlagen: {err}"
        ) from err


def unpack_browser_archive(encoded: str) -> tuple[list[dict], dict]:
    """Unpack bounded file bundles in memory, with optional source checksums."""
    if len(encoded) > 4 * MAX_TOTAL_BYTES // 3 + 10000:
        raise ConfigurationError("ZIP-Datei ist zu groß.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        files, metadata, seen, total = [], {}, set(), 0
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES * 2 + 1:
                raise ConfigurationError("ZIP enthält zu viele Einträge.")
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
                total += item.file_size
                if total > MAX_TOTAL_BYTES or item.file_size > MAX_FILE_BYTES:
                    raise ConfigurationError(
                        "ZIP überschreitet 2 MB entpackt oder 1 MB je Datei."
                    )
                if item.is_dir():
                    if name.rstrip("/") != ".landscape-browser":
                        browser_path(name.rstrip("/"))
                    continue
                if name == METADATA:
                    info = json.loads(archive.read(item))
                    if (
                        info.get("scope") != "landscape_browser"
                        or info.get("schema_version") != 1
                    ):
                        raise ValueError("Unbekanntes Browser-Bundle.")
                    for record in info["files"]:
                        path = browser_path(record["path"])
                        source = record.get("source_sha256")
                        if source is not None and (
                            not isinstance(source, str)
                            or len(source) != 64
                            or any(c not in "0123456789abcdef" for c in source)
                        ):
                            raise ValueError("Ungültige Quell-Prüfsumme.")
                        if path in metadata:
                            raise ValueError("Doppelter Kontextpfad.")
                        metadata[path] = source
                else:
                    browser_path(name)
                    files.append(
                        {
                            "filename": name,
                            "content": base64.b64encode(archive.read(item)).decode(
                                "ascii"
                            ),
                            "encoding": "base64",
                        }
                    )
        return files, metadata
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
    ) as err:
        raise ConfigurationError(
            "Ungültiges oder nicht unterstütztes Browser-ZIP."
        ) from err
