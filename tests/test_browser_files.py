"""Exercise real file bundles, mixed imports and recoverable byte-exact writes."""

from __future__ import annotations

import base64
import io
import json
import os
import stat
import zipfile

import pytest

from custom_components.landscape.browser_files import (
    METADATA,
    BrowserFiles,
    browser_path,
    unpack_browser_archive,
)
from custom_components.landscape.configuration_files import ConfigurationFiles, digest
from custom_components.landscape.configuration_yaml import ConfigurationError


def upload(path, raw, mode="replace"):
    return {
        "path": path,
        "filename": path,
        "content": base64.b64encode(raw).decode(),
        "encoding": "base64",
        "mode": mode,
    }


def put(root, path, raw):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def commit(files, plan):
    report = files.begin(plan, "admin")
    files.write(plan, report)
    files.check_written(plan)
    files.finish(report)
    return report


@pytest.fixture
def files(tmp_path):
    put(tmp_path, "configuration.yaml", b"script: !include scripts.yaml\n")
    put(tmp_path, "scripts.yaml", b"relax:\n  sequence: []\n")
    put(tmp_path, "www/style.css", b"body { color: red; }\r\n")
    put(tmp_path, "www/icon.png", b"\x89PNG\r\n\x1a\n\x00\xff")
    put(tmp_path, "custom_components/example/__init__.py", b"VALUE = 1\n")
    put(tmp_path, "blueprints/example.yaml", b"blueprint:\n  name: Test\n")
    put(tmp_path, "esphome/test.yaml", b"sensor: !include sensor.yaml\n")
    return BrowserFiles(str(tmp_path))


def test_inventory_includes_programs_assets_and_empty_folders(files):
    for path in [
        "secrets.yaml",
        "www/secrets.yml",
        ".storage/auth",
        "www/.hidden",
        "node_modules/module.js",
        "home-assistant_v2.db-wal",
        "home-assistant.log.1",
    ]:
        put(files.root, path, b"never-export")
    (files.root / "empty").mkdir()
    put(files.root, "www/large.bin", b"x" * 1_000_001)
    inventory = files.inventory()
    paths = {item["path"]: item for item in inventory["files"]}
    assert set(paths) == {
        "configuration.yaml",
        "scripts.yaml",
        "www/style.css",
        "www/icon.png",
        "custom_components/example/__init__.py",
        "blueprints/example.yaml",
        "esphome/test.yaml",
        "www/large.bin",
    }
    assert not paths["www/large.bin"]["available"]
    assert paths["scripts.yaml"]["merge_supported"]
    assert "empty" in inventory["directories"]
    assert not (files.root / ".storage/landscape_browser").exists()


@pytest.mark.parametrize(
    "path,raw",
    [
        ("www/icon.png", b"\x00\xff\x80"),
        ("LICENSE", b"\xef\xbb\xbfGruesse\r\n"),
        ("www/scene.json", b'{"name":"Test"}\r\n'),
        ("www/archive.zip", b"PK\x00\xff"),
    ],
)
def test_single_download_preserves_name_and_bytes(files, path, raw):
    put(files.root, path, raw)
    exported = files.export([path], False, False)
    assert exported["filename"] == path.split("/")[-1]
    assert exported["mime"] == "application/octet-stream"
    assert base64.b64decode(exported["content"]) == raw
    view = files.view(path)
    assert view["sha256"] == digest(raw)
    assert view["binary"] == (path.endswith(("png", "zip")))


def test_bundle_roundtrip_retains_json_files_paths_and_source_hashes(files):
    put(files.root, "landscape-bundle.json", b'{"ordinary":true}')
    paths = ["www/icon.png", "www/style.css", "landscape-bundle.json"]
    exported = files.export(paths, True, False)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["content"]))) as archive:
        assert set(archive.namelist()) == {*paths, METADATA}
        assert archive.read("www/icon.png") == files.read("www/icon.png")
    imported = files.inspect([], exported["content"])["files"]
    assert {item["path"] for item in imported} == set(paths)
    assert all(item["source_matches"] for item in imported)
    assert files.prepare(imported)["changes"] == []
    put(files.root, "www/style.css", b"changed externally")
    stale = files.inspect([], exported["content"])["files"]
    assert not next(item for item in stale if item["path"].endswith("css"))[
        "source_matches"
    ]
    with pytest.raises(ConfigurationError, match="Seit dem Export"):
        files.prepare(stale)


def test_raw_file_target_suggestions_match_the_extension(files):
    put(files.root, "www/style.json", b"{}")
    inspected = files.inspect([upload("style_optimiert.css", b"new")])["files"][0]
    assert inspected["path"] == "www/style.css"
    assert inspected["candidates"] == ["www/style.css"]
    assert files.inspect([upload("other.json", b"{}")])["files"][0]["mode"] == "create"


def test_single_file_folder_export_is_a_bundle_and_compact_json_diff_is_readable(files):
    put(files.root, "www/settings.json", b'{"value":1}')
    exported = files.export(["www/settings.json"], False, False, True)
    assert exported["mime"] == "application/zip"
    plan = files.prepare([upload("www/settings.json", b'{"value":2}')])
    diff = plan["changes"][0]["diff"]
    assert '-{"value":1}\n\\ No newline at end of file\n' in diff
    assert '+{"value":2}\n\\ No newline at end of file\n' in diff


def test_mixed_import_diff_backup_and_full_restore_are_byte_exact(files):
    original = {
        path: files.read(path)
        for path in ["www/style.css", "www/icon.png", "scripts.yaml"]
    }
    os.chmod(files.root / "www/style.css", 0o640)
    plan = files.prepare(
        [
            upload("www/style.css", b"\xef\xbb\xbfbody { color: blue; }\r\n"),
            upload("www/icon.png", b"\x00new\xff"),
            upload("scripts.yaml", b"\xef\xbb\xbfrelax:\r\n  sequence: []\r\n"),
            upload("new/subfolder/README", b"new\n", "create"),
        ]
    )
    changes = {change["path"]: change for change in plan["changes"]}
    assert "+body { color: blue; }" in changes["www/style.css"]["diff"]
    assert changes["www/icon.png"]["binary"]
    assert changes["www/icon.png"]["after_hash"] == digest(b"\x00new\xff")
    report = commit(files, plan)
    assert stat.S_IMODE((files.root / "www/style.css").stat().st_mode) == 0o640
    assert files.read("scripts.yaml").startswith(b"\xef\xbb\xbf")
    assert files.backups()[0]["id"] == report["id"]
    assert ConfigurationFiles(str(files.root)).backups() == []
    commit(files, files.restore_plan(report["id"]))
    assert all(files.read(path) == raw for path, raw in original.items())
    assert not (files.root / "new/subfolder/README").exists()


def test_yaml_merge_keeps_existing_entries_and_validates_the_include(files):
    plan = files.prepare([upload("scripts.yaml", b"new:\n  sequence: []\n", "merge")])
    commit(files, plan)
    assert b"relax:" in files.read("scripts.yaml")
    assert b"new:" in files.read("scripts.yaml")
    with pytest.raises(ConfigurationError, match="Zuordnung"):
        files.prepare([upload("scripts.yaml", b"[]\n")])
    with pytest.raises(ConfigurationError, match="Zusammenf"):
        files.prepare([upload("www/style.css", b"new", "merge")])


def test_stale_preview_and_restore_do_not_overwrite_external_changes(files):
    plan = files.prepare([upload("www/icon.png", b"new")])
    put(files.root, "www/icon.png", b"external")
    with pytest.raises(ConfigurationError, match="Vorschau"):
        files.begin(plan, "admin")
    report = commit(files, files.prepare([upload("www/icon.png", b"new")]))
    put(files.root, "www/icon.png", b"other")
    with pytest.raises(ConfigurationError, match="Rücksetzung gesperrt"):
        files.restore_plan(report["id"])
    assert files.read("www/icon.png") == b"other"


def test_interrupted_binary_import_recovers_without_touching_yaml_history(files):
    original = files.read("www/icon.png")
    plan = files.prepare([upload("www/icon.png", b"\x00changed")])
    report = files.begin(plan, "admin")
    files.write(plan, report)
    assert files.read("www/icon.png") != original
    BrowserFiles(str(files.root)).recover()
    assert files.read("www/icon.png") == original
    assert files.backups()[0]["status"] == "rolled_back"


@pytest.mark.parametrize(
    "path",
    [
        "../file.txt",
        "/config/file.txt",
        "www/../../file.txt",
        "www\\file.txt",
        ".storage/auth",
        "secrets.yaml",
        "www/secrets.yml",
        "www/.hidden",
        "a//b.txt",
        "a\x00.txt",
        "home-assistant_v2.db",
        "home-assistant.log.1",
    ],
)
def test_disallowed_paths_cannot_be_viewed_exported_or_imported(files, path):
    with pytest.raises(ConfigurationError):
        browser_path(path)
    with pytest.raises(ConfigurationError):
        files.view(path)
    with pytest.raises(ConfigurationError):
        files.export([path], False, False)
    with pytest.raises(ConfigurationError):
        files.prepare([upload(path, b"anything", "create")])


def test_symlink_files_and_directories_are_rejected(files, tmp_path):
    (files.root / "www/link.txt").symlink_to(files.root / "scripts.yaml")
    (files.root / "linked").symlink_to(files.root / "www", target_is_directory=True)
    for path in ["www/link.txt", "linked/style.css"]:
        with pytest.raises(ConfigurationError):
            files.view(path)
        with pytest.raises(ConfigurationError):
            files.prepare([upload(path, b"new")])
    assert not any("link" in item["path"] for item in files.inventory()["files"])


@pytest.mark.parametrize(
    "path,raw",
    [
        ("www/test.json", b'{"broken":'),
        ("custom_components/example/bad.py", b"def broken(:"),
        ("blueprints/bad.yaml", b"x: ["),
        ("scripts.yaml", b"\x00\xff"),
    ],
)
def test_invalid_known_syntax_is_rejected_before_writes(files, path, raw):
    with pytest.raises(ConfigurationError):
        files.prepare(
            [upload(path, raw, "replace" if files.read(path) is not None else "create")]
        )
    assert not files.backups()


def test_external_yaml_tags_and_python_are_parsed_without_execution(files):
    plan = files.prepare(
        [
            upload("esphome/test.yaml", b"value: !lambda 'return 1;'\n"),
            upload(
                "custom_components/example/__init__.py",
                b"raise RuntimeError('must not execute')\n",
            ),
        ]
    )
    assert len(plan["changes"]) == 2


@pytest.mark.parametrize(
    "problem",
    ["traversal", "link", "duplicate", "oversized", "invalid_metadata", "bad_hash"],
)
def test_unsafe_or_malformed_archives_are_rejected(files, problem):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if problem == "traversal":
            archive.writestr("../escape.txt", b"bad")
        elif problem == "link":
            entry = zipfile.ZipInfo("www/link")
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, b"target")
        elif problem == "duplicate":
            archive.writestr("a.txt", b"one")
            with pytest.warns(UserWarning):
                archive.writestr("a.txt", b"two")
        elif problem == "oversized":
            archive.writestr("a.txt", b"x" * 1_000_001)
        elif problem == "invalid_metadata":
            archive.writestr(METADATA, b"[]")
        else:
            archive.writestr(
                METADATA,
                json.dumps(
                    {
                        "scope": "landscape_browser",
                        "schema_version": 1,
                        "files": [{"path": "a.txt", "source_sha256": "bad"}],
                    }
                ),
            )
    with pytest.raises(ConfigurationError):
        files.inspect([], base64.b64encode(buffer.getvalue()).decode())


def test_import_limits_modes_and_invalid_encoding(files):
    for item in [
        upload("www/style.css", b"x", "create"),
        upload("missing.txt", b"x"),
        {**upload("new.txt", b"x", "create"), "content": "***"},
        {**upload("new.txt", b"x", "create"), "encoding": "unknown"},
        upload("new.txt", b"x" * 1_000_001, "create"),
    ]:
        with pytest.raises(ConfigurationError):
            files.prepare([item])
    with pytest.raises(ConfigurationError, match="mehrfach"):
        files.prepare(
            [upload("www/style.css", b"one"), upload("www/style.css", b"two")]
        )
    with pytest.raises(ConfigurationError):
        unpack_browser_archive("not base64")
