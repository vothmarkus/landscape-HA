"""Test actual configuration files, portable archives and transactional recovery."""

from __future__ import annotations

import base64
import io
import json
import os
import stat
import zipfile

import pytest
import yaml

from custom_components.landscape.configuration_files import (
    ConfigurationFiles,
    digest,
    unpack_archive,
)
from custom_components.landscape.configuration_yaml import (
    ConfigurationError,
    describe,
    merge_yaml,
    parse_yaml,
    safe_path,
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "configuration.yaml").write_text(
        "automation: !include automations.yaml\nscript: !include scripts.yaml\n"
        "homeassistant:\n  packages: !include_dir_named packages\n"
    )
    (tmp_path / "automations.yaml").write_text(
        "# Header\n- id: gas\n  alias: Gas alt\n  triggers: []\n  actions: []\n"
    )
    (tmp_path / "scripts.yaml").write_text("relax:\n  sequence: []\n")
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages/gas.yaml").write_text(
        "template: !include ../templates.yaml\n"
    )
    (tmp_path / "templates.yaml").write_text(
        "- sensor:\n    - name: Gas\n"
        "      state: '{{ states(\"sensor.gas_meter\") }}'\n"
    )
    (tmp_path / "secrets.yaml").write_text("password: never-export-this\n")
    return ConfigurationFiles(str(tmp_path))


def plan_for(workspace):
    return workspace.prepare(
        [
            {"path": "automations.yaml", "content": "[]\n"},
            {
                "path": "packages/new.yaml",
                "mode": "create",
                "content": "input_boolean:\n  hello:\n",
            },
        ]
    )


def test_nested_context_references_and_read_only_inventory(workspace):
    files = {item["path"]: item for item in workspace.inventory()["files"]}
    assert "secrets.yaml" not in files
    assert files["automations.yaml"]["type"] == "automations"
    assert files["automations.yaml"]["merge_supported"]
    assert files["packages/gas.yaml"]["type"] == "package"
    assert files["templates.yaml"]["type"] == "templates"
    assert files["templates.yaml"]["expected_shapes"] == ["list"]
    assert files["templates.yaml"]["referenced_entities"] == ["sensor.gas_meter"]
    assert not (workspace.root / ".storage").exists()


@pytest.mark.parametrize(
    "path",
    [
        "../configuration.yaml",
        "/config/a.yaml",
        "a/../../a.yaml",
        "a\\b.yaml",
        ".storage/auth.yaml",
        "secrets.yaml",
        "packages/secrets.yaml",
        "www/a.yaml",
        "custom_components/a.yaml",
        "esphome/a.yaml",
        "a//b.yaml",
        "a.json",
        "a\x00.yaml",
    ],
)
def test_unsafe_target_rejected(path):
    with pytest.raises(ConfigurationError):
        safe_path(path)


@pytest.mark.parametrize(
    "text",
    [
        "a: 1\na: 2\n",
        "x: &x [*x]\n",
        "x: !!python/object:os.system {}\n",
        "x: !unknown a\n",
        "a: [1\n",
        "a: 1\n---\nb: 2\n",
    ],
)
def test_bad_yaml_rejected(text):
    with pytest.raises(ConfigurationError):
        parse_yaml(text)


def test_ha_tags_are_not_dereferenced():
    node = parse_yaml("password: !secret test\nvalue: !env_var TEST\n")
    assert node.value[0][1].tag == "!secret"
    assert node.value[0][1].value == "test"


def test_dir_list_and_inline_package_context():
    files = {
        "configuration.yaml": "automation: !include_dir_list automations\n",
        "automations/a.yaml": "alias: Test\ntriggers: []\nactions: []\n",
        "automations/b.yml": "[]\n",
    }
    result = describe(files)
    assert result["automations/a.yaml"]["expected_shapes"] == ["mapping"]
    assert result["automations/a.yaml"]["type"] == "automation"
    assert not result["automations/b.yml"]["active"]
    files["configuration.yaml"] = (
        "homeassistant:\n  packages:\n    test:\n"
        "      automation: !include automations/a.yaml\n"
    )
    assert describe(files)["automations/a.yaml"]["type"] == "automations"


def test_wrong_shape_and_changed_include_block_preview(workspace):
    original = workspace.read("automations.yaml")
    with pytest.raises(ConfigurationError, match="Liste"):
        workspace.prepare([{"path": "automations.yaml", "content": "alias: Test\n"}])
    with pytest.raises(ConfigurationError, match="Zuordnung"):
        workspace.prepare(
            [
                {
                    "path": "configuration.yaml",
                    "content": "script: !include automations.yaml\n",
                }
            ]
        )
    assert workspace.read("automations.yaml") == original
    assert not (workspace.root / ".storage").exists()


def test_new_package_and_inactive_file_context(workspace):
    plan = workspace.prepare(
        [
            {
                "path": "packages/new.yaml",
                "mode": "create",
                "content": "input_boolean:\n  hello:\n",
            },
            {"path": "unused.yaml", "mode": "create", "content": "[]\n"},
        ]
    )
    assert plan["changes"][0]["context"]["active"]
    assert plan["changes"][0]["context"]["type"] == "package"
    assert not plan["changes"][1]["context"]["active"]
    assert "+input_boolean:" in plan["changes"][0]["diff"]
    assert not (workspace.root / "packages/new.yaml").exists()


def test_single_export_and_context_round_trip(workspace):
    original = b"\xef\xbb\xbf- id: 'a'\r\n  triggers: []\r\n  actions: []\r\n"
    (workspace.root / "automations.yaml").write_bytes(original)
    result = workspace.export(["automations.yaml"], False, False)
    assert result["filename"] == "automations.yaml"
    assert base64.b64decode(result["content"]) == original
    assert workspace.export(["automations.yaml"], False, True)["filename"].startswith(
        "automations_20"
    )
    bundle = workspace.export(["automations.yaml"], True, False)
    entries = unpack_archive(bundle["content"])
    assert {entry["filename"] for entry in entries} == {
        "automations.yaml",
        "automations.landscape.json",
        "landscape-bundle.json",
    }
    inspected = workspace.inspect([], bundle["content"])["files"][0]
    assert inspected["path"] == "automations.yaml"
    assert inspected["source_matches"]
    assert inspected["source_sha256"] == digest(original)


def test_bundle_excludes_secrets_and_sidecar_names_do_not_collide(workspace):
    (workspace.root / "www").mkdir()
    (workspace.root / "www/hidden.yaml").write_text("private: true")
    (workspace.root / "scripts.yml").write_text("{}\n")
    raw = unpack_archive(workspace.export(None, True, False)["content"])
    assert not any(item["filename"].startswith("www/") for item in raw)
    assert "never-export-this" not in json.dumps(raw)
    names = [item["filename"] for item in raw]
    assert len(names) == len(set(names))
    assert "scripts.yaml.landscape.json" in names
    assert "scripts.yml.landscape.json" in names


def test_ambiguous_basename_even_with_root_file(workspace):
    (workspace.root / "gas.yaml").write_text("{}\n")
    item = workspace.inspect([{"filename": "gas.yaml", "content": "{}\n"}])["files"][0]
    assert item["path"] == "" and len(item["candidates"]) == 2
    item = workspace.inspect(
        [{"filename": "automations_2026-09-15.yaml", "content": "[]\n"}]
    )["files"][0]
    assert item["path"] == "automations.yaml"


@pytest.mark.parametrize(
    "filename,target",
    [
        ("configuration_blitzer_korrigiert.yaml", "configuration.yaml"),
        ("meine-CONFIGURATION (9).yml", "configuration.yaml"),
        ("automations_ueberarbeitet_2026-09-15.yaml", "automations.yaml"),
        ("korrigiert_gas (2).yaml", "packages/gas.yaml"),
        ("templates.final.yaml", "templates.yaml"),
    ],
)
def test_renamed_upload_selects_existing_file_without_writing(
    workspace, filename, target
):
    before = workspace.snapshot()
    item = workspace.inspect([{"filename": filename, "content": "{}\n"}])["files"][0]
    assert item["path"] == item["suggested_path"] == target
    assert item["mode"] == "replace"
    assert item["candidates"][0] == target
    assert workspace.snapshot() == before
    assert not (workspace.root / ".storage").exists()


def test_more_specific_filename_wins_and_exact_names_take_precedence(workspace):
    for path in [
        "packages/sauna.yaml",
        "packages/sauna_manager.yaml",
        "automations_2026-09-15.yaml",
    ]:
        (workspace.root / path).write_text("{}\n")
    item = workspace.inspect(
        [{"filename": "sauna-manager_korrigiert.yaml", "content": "{}\n"}]
    )["files"][0]
    assert item["path"] == "packages/sauna_manager.yaml"
    assert item["candidates"] == ["packages/sauna_manager.yaml", "packages/sauna.yaml"]
    item = workspace.inspect(
        [{"filename": "automations_2026-09-15.yaml", "content": "[]\n"}]
    )["files"][0]
    assert item["path"] == "automations_2026-09-15.yaml"


@pytest.mark.parametrize("other", ["gas.yaml", "abc.yaml"])
def test_equally_good_terms_do_not_guess_a_target(workspace, other):
    (workspace.root / other).write_text("{}\n")
    item = workspace.inspect(
        [{"filename": "gas_abc_korrigiert.yaml", "content": "{}\n"}]
    )["files"][0]
    assert item["path"] == item["suggested_path"] == ""
    assert item["mode"] == "replace"
    assert set(item["candidates"]) == {other, "packages/gas.yaml"}


@pytest.mark.parametrize("name", ["gasmeter_neu.yaml", "shellscripts.yaml"])
def test_partial_words_do_not_replace_unrelated_files(workspace, name):
    item = workspace.inspect([{"filename": name, "content": "{}\n"}])["files"][0]
    assert item["path"] == name
    assert item["mode"] == "create"
    assert item["candidates"] == []


def test_explicit_and_zip_paths_override_filename_suggestions(workspace):
    item = workspace.inspect(
        [{"filename": "new/configuration_fixed.yaml", "content": "{}\n"}]
    )["files"][0]
    assert item["path"] == "new/configuration_fixed.yaml"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("configuration_fixed.yaml", "{}\n")
    item = workspace.inspect([], base64.b64encode(buffer.getvalue()).decode())["files"][
        0
    ]
    assert item["path"] == "configuration_fixed.yaml"
    assert item["mode"] == "create"


def test_context_still_protects_renamed_upload_with_duplicate_basenames(workspace):
    bundle = workspace.export(["packages/gas.yaml"], True, False)
    entries = unpack_archive(bundle["content"])
    for entry in entries:
        if entry["filename"] == "packages/gas.yaml":
            entry["filename"] = "gas_korrigiert.yaml"
    (workspace.root / "gas.yaml").write_text("{}\n")
    item = workspace.inspect(entries)["files"][0]
    assert item["path"] == item["source_path"] == "packages/gas.yaml"
    assert item["source_matches"]
    (workspace.root / "packages/gas.yaml").write_text("{}\n")
    with pytest.raises(ConfigurationError, match="Seit dem Export"):
        workspace.prepare([item])


def test_stale_context_is_rejected(workspace):
    bundle = workspace.export(["automations.yaml"], True, False)
    imports = workspace.inspect([], bundle["content"])["files"]
    (workspace.root / "automations.yaml").write_text("[]\n")
    with pytest.raises(ConfigurationError, match="Seit dem Export"):
        workspace.prepare(imports)


def test_merge_by_id_preserves_unrelated_content_and_comments():
    before = (
        "# header\n- id: 'one'\n  alias: Original\n  actions: []\n"
        "# keep second comment\n- id: two\n  alias: Keep me\n"
        "  description: !secret description\n  actions: []\n"
    )
    incoming = (
        "- id: one\n  alias: Replaced\n  actions: []\n- id: three\n  actions: []\n"
    )
    result = merge_yaml(before, incoming, "automations")
    assert result.startswith("# header\n")
    assert "# keep second comment" in result
    assert "description: !secret description" in result
    assert len(parse_yaml(result).value) == 3
    assert "Original" not in result and "Replaced" in result


def test_merge_scripts_with_block_scalar_does_not_remove_next_key():
    before = (
        "one:\n  description: |\n    a multiline value\n"
        "  sequence: []\ntwo:\n  sequence: []\n"
    )
    incoming = (
        "one:\n  sequence: []\n  description: |\n    changed\nthree:\n  sequence: []\n"
    )
    result = merge_yaml(before, incoming, "scripts")
    assert set(yaml.safe_load(result)) == {"one", "two", "three"}
    assert yaml.safe_load(result)["one"]["description"] == "changed\n"


@pytest.mark.parametrize(
    "incoming",
    ["- alias: no id\n", "- id: x\n- id: x\n", "[{id: flow}]\n", "- id: &id one\n"],
)
def test_merge_requires_unambiguous_identity(incoming):
    with pytest.raises(ConfigurationError):
        merge_yaml("- id: one\n", incoming, "automations")


@pytest.mark.parametrize(
    "name",
    [
        "../x.yaml",
        "/tmp/x.yaml",
        "a/../../x.yaml",
        "secrets.yaml",
        ".storage/x.yaml",
        "data.bin",
    ],
)
def test_hostile_zip_paths(name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "{}\n")
    with pytest.raises(ConfigurationError):
        unpack_archive(base64.b64encode(buffer.getvalue()).decode())


def test_zip_links_and_decompression_limit():
    for link in (True, False):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            entry = zipfile.ZipInfo("x.yaml")
            if link:
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, "/etc/passwd")
            else:
                archive.writestr("x.yaml", "a" * 2_000_001)
        with pytest.raises(ConfigurationError):
            unpack_archive(base64.b64encode(buffer.getvalue()).decode())


def test_symlink_and_include_cycle_rejected(workspace, tmp_path):
    (tmp_path / "link.yaml").symlink_to(tmp_path / "secrets.yaml")
    with pytest.raises(ConfigurationError):
        workspace.prepare([{"path": "link.yaml", "content": "{}\n"}])
    for text in ["x: !include ../secret.yaml\n", "x: !include configuration.yaml\n"]:
        with pytest.raises(ConfigurationError):
            workspace.prepare([{"path": "configuration.yaml", "content": text}])
    (tmp_path / "linked").symlink_to(tmp_path / "packages", target_is_directory=True)
    with pytest.raises(ConfigurationError):
        workspace.prepare(
            [
                {
                    "path": "configuration.yaml",
                    "content": (
                        "homeassistant:\n  packages: !include_dir_named linked\n"
                    ),
                }
            ]
        )


def test_backup_atomic_apply_restore_and_permissions(workspace):
    original = workspace.read("automations.yaml")
    os.chmod(workspace.root / "automations.yaml", 0o640)
    plan = plan_for(workspace)
    report = workspace.begin(plan, "admin")
    folder = workspace.root / ".storage/landscape_configuration" / report["id"]
    assert workspace.read("automations.yaml") == original
    assert (folder / "0.bin").read_bytes() == original
    assert stat.S_IMODE((folder / "0.bin").stat().st_mode) == 0o600
    workspace.write(plan, report)
    workspace.check_written(plan)
    workspace.finish(report)
    assert workspace.read("automations.yaml") == b"[]\n"
    assert stat.S_IMODE((workspace.root / "automations.yaml").stat().st_mode) == 0o640
    restore = workspace.restore_plan(report["id"])
    restoration = workspace.begin(restore, "admin")
    workspace.write(restore, restoration)
    workspace.finish(restoration)
    assert workspace.read("automations.yaml") == original
    assert workspace.read("packages/new.yaml") is None


def test_bom_exact_restoration(workspace):
    original = b"\xef\xbb\xbf[]\r\n"
    (workspace.root / "automations.yaml").write_bytes(original)
    plan = workspace.prepare([{"path": "automations.yaml", "content": "[]\r\n"}])
    report = workspace.begin(plan, "admin")
    workspace.write(plan, report)
    workspace.finish(report)
    restore = workspace.restore_plan(report["id"])
    workspace.write(restore, workspace.begin(restore, "admin"))
    assert workspace.read("automations.yaml") == original


def test_partial_write_failure_rolls_back(workspace, monkeypatch):
    original = workspace.read("automations.yaml")
    plan, writer = plan_for(workspace), workspace._write_atomic
    report = workspace.begin(plan, "admin")

    def fail_new(path, content, mode=0o600):
        if path.name == "new.yaml":
            raise OSError("disk full")
        return writer(path, content, mode)

    monkeypatch.setattr(workspace, "_write_atomic", fail_new)
    with pytest.raises(OSError):
        workspace.write(plan, report)
    workspace.rollback(report)
    assert report["status"] == "rolled_back"
    assert workspace.read("automations.yaml") == original
    assert workspace.read("packages/new.yaml") is None


def test_crash_recovery_preserves_concurrent_edits(workspace):
    plan = plan_for(workspace)
    report = workspace.begin(plan, "admin")
    workspace.write(plan, report)
    (workspace.root / "automations.yaml").write_text("# edited elsewhere\n[]\n")
    restarted = ConfigurationFiles(str(workspace.root))
    restarted.recover()
    summary = restarted.backups()[0]
    assert summary["status"] == "recovery_required"
    assert summary["rollback_errors"] == ["automations.yaml"]
    assert workspace.read("automations.yaml") == b"# edited elsewhere\n[]\n"
    assert workspace.read("packages/new.yaml") is None


def test_conflict_after_preview_prevents_write(workspace):
    plan = plan_for(workspace)
    (workspace.root / "scripts.yaml").write_text("{}\n")
    with pytest.raises(ConfigurationError, match="seit der Vorschau"):
        workspace.begin(plan, "admin")
    assert not (workspace.root / "packages/new.yaml").exists()
