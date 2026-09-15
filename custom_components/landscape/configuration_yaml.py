"""Inspect Home Assistant YAML without constructing tags or loading secrets."""

from __future__ import annotations

import re
from collections import deque
from pathlib import PurePosixPath

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 2_000_000
MAX_FILES = 250
INCLUDE_TAGS = {
    "!include",
    "!include_dir_list",
    "!include_dir_named",
    "!include_dir_merge_list",
    "!include_dir_merge_named",
}
HA_TAGS = INCLUDE_TAGS | {"!secret", "!env_var", "!input"}
EXCLUDED_DIRS = {
    "custom_components",
    "deps",
    "www",
    "tts",
    "backups",
    "backup",
    "esphome",
    "blueprints",
    "node_modules",
    "venv",
    "__pycache__",
}
ENTITY_RE = re.compile(r"\b[a-z][a-z0-9_]*\.[a-z0-9_]+\b")


class ConfigurationError(ValueError):
    """An actionable configuration import error."""


def safe_path(value: str, *, directory: bool = False) -> str:
    """Allow only relative YAML paths in the configuration workspace."""
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ConfigurationError("Bitte einen relativen Zielpfad angeben.")
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise ConfigurationError("Ungültiger Dateipfad.")
    parts = value.split("/")
    if any(not part or part.startswith(".") or part in EXCLUDED_DIRS for part in parts):
        raise ConfigurationError(f"Pfad nicht freigegeben: {value}")
    if any(part.lower() in {"secrets.yaml", "secrets.yml"} for part in parts):
        raise ConfigurationError("secrets.yaml wird nicht exportiert oder importiert.")
    path = PurePosixPath(value)
    if path.is_absolute() or (not directory and path.suffix not in {".yaml", ".yml"}):
        raise ConfigurationError("Nur relative .yaml- und .yml-Dateien sind erlaubt.")
    return path.as_posix()


def include_path(parent: str, value: str, *, directory: bool = False) -> str:
    """Resolve includes relative to their source file, confined to /config."""
    if value.startswith("/") or "\\" in value:
        raise ConfigurationError("Includes müssen innerhalb von /config liegen.")
    parts = list(PurePosixPath(parent).parent.parts)
    for part in value.rstrip("/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ConfigurationError("Include verlässt /config.")
            parts.pop()
        else:
            parts.append(part)
    return safe_path("/".join(parts), directory=directory)


def parse_yaml(text: str) -> Node | None:
    """Compose bounded YAML; reject duplicate keys, recursive aliases and tags."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ConfigurationError("Eine YAML-Datei darf höchstens 1 MB groß sein.")
    try:
        depth = 0
        for count, event in enumerate(yaml.parse(text, Loader=yaml.SafeLoader), 1):
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
            if depth > 50 or count > 50000:
                raise ConfigurationError("YAML ist zu tief verschachtelt oder zu groß.")
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as err:
        mark = getattr(err, "problem_mark", None)
        where = f" (Zeile {mark.line + 1}, Spalte {mark.column + 1})" if mark else ""
        raise ConfigurationError(
            f"YAML-Syntaxfehler{where}: {getattr(err, 'problem', None) or 'ungültig'}"
        ) from err
    _validate_node(node, set(), [0])
    return node


def _validate_node(node: Node | None, parents: set[int], count: list[int]) -> None:
    if node is None:
        return
    count[0] += 1
    if id(node) in parents or count[0] > 50000:
        raise ConfigurationError(
            "Rekursive oder zu viele YAML-Aliase sind nicht erlaubt."
        )
    if node.tag.startswith("!") and node.tag not in HA_TAGS:
        raise ConfigurationError(f"Nicht unterstütztes YAML-Tag: {node.tag}")
    if (
        node.tag.startswith("tag:") and not node.tag.startswith("tag:yaml.org,2002:")
    ) or node.tag.startswith("tag:yaml.org,2002:python"):
        raise ConfigurationError("Nicht unterstütztes YAML-Tag.")
    if node.tag in HA_TAGS and not isinstance(node, ScalarNode):
        raise ConfigurationError(f"{node.tag} benötigt einen einzelnen Wert.")
    parents = parents | {id(node)}
    if isinstance(node, MappingNode):
        keys = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode):
                raise ConfigurationError("YAML-Schlüssel müssen einzelne Werte sein.")
            if key.value in keys:
                raise ConfigurationError(f"Doppelter YAML-Schlüssel: {key.value}")
            keys.add(key.value)
            _validate_node(key, parents, count)
            _validate_node(value, parents, count)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            _validate_node(value, parents, count)


def walk(node: Node | None, keys: tuple[str, ...] = ()):
    if node is None:
        return
    yield keys, node
    if isinstance(node, MappingNode):
        for key, value in node.value:
            yield from walk(value, (*keys, key.value))
    elif isinstance(node, SequenceNode):
        for value in node.value:
            yield from walk(value, (*keys, "[]"))


def role(keys: tuple[str, ...], tag: str) -> tuple[str, str | None]:
    keys = tuple(key.split(" ", 1)[0] for key in keys)
    if len(keys) > 3 and keys[:2] == ("homeassistant", "packages"):
        keys = keys[3:]
    if not keys:
        return "configuration", "mapping"
    if keys == ("homeassistant", "packages"):
        return (
            ("package", "mapping")
            if tag == "!include_dir_named"
            else ("packages", "mapping")
        )
    if len(keys) == 3 and keys[:2] == ("homeassistant", "packages"):
        return "package", "mapping"
    if len(keys) == 2 and keys[0] in {"automation", "scene", "template", "script"}:
        return keys[0], "mapping"
    if len(keys) != 1:
        return "fragment", None
    domain = keys[0]
    kind = {
        "automation": "automations",
        "scene": "scenes",
        "script": "scripts",
        "template": "templates",
    }.get(domain, domain)
    shape = "mapping" if domain in {"script", "mqtt", "homeassistant"} else None
    if domain in {"automation", "scene", "template", "sensor", "binary_sensor"}:
        shape = "list"
    if tag in {"!include_dir_list", "!include_dir_named"}:
        return domain, "mapping"
    return kind, shape


def describe(files: dict[str, str]) -> dict[str, dict]:
    """Resolve include contexts and identify inactive files."""
    details = {}
    edges = {}
    for path, text in files.items():
        info = details[path] = {
            "path": path,
            "type": "yaml",
            "included_by": [],
            "includes": [],
            "active": path == "configuration.yaml",
            "expected_shapes": [],
            "syntax_error": None,
            "warnings": [],
            "context_errors": [],
            "referenced_entities": [],
            "referenced_services": [],
            "merge_supported": False,
        }
        edges[path] = []
        try:
            node = parse_yaml(text)
        except ConfigurationError as err:
            info["syntax_error"] = str(err)
            continue
        entities, services = set(), set()
        for keys, item in walk(node):
            if isinstance(item, ScalarNode) and item.tag not in HA_TAGS:
                refs = set(ENTITY_RE.findall(item.value))
                (
                    services if keys and keys[-1] in {"action", "service"} else entities
                ).update(refs)
            if item.tag not in INCLUDE_TAGS:
                continue
            try:
                target = include_path(
                    path, item.value, directory=item.tag != "!include"
                )
            except ConfigurationError as err:
                info["context_errors"].append(str(err))
                continue
            record = {"tag": item.tag, "target": target, "key": ".".join(keys)}
            info["includes"].append(record)
            children = (
                [target]
                if item.tag == "!include"
                else sorted(
                    name
                    for name in files
                    if name.startswith(target + "/") and name.endswith(".yaml")
                )
            )
            if item.tag == "!include_dir_named":
                names = [PurePosixPath(name).stem for name in children]
                if len(names) != len(set(names)):
                    info["context_errors"].append(
                        f"{target}: Gleiche Dateinamen in !include_dir_named."
                    )
            for child in children:
                if child not in files:
                    info["context_errors"].append(
                        f"Include fehlt oder ist nicht freigegeben: {child}"
                    )
                else:
                    edges[path].append((child, keys, item.tag))
        info["referenced_entities"] = sorted(entities - services)
        info["referenced_services"] = sorted(services)
    for path, children in edges.items():
        for child, keys, tag in children:
            record = {"path": path, "key": ".".join(keys), "tag": tag}
            if record not in details[child]["included_by"]:
                details[child]["included_by"].append(record)
    queue = deque([("configuration.yaml", (), "configuration", "mapping", ())])
    visited = set()
    while queue:
        path, context, kind, shape, parents = queue.popleft()
        if path not in details:
            continue
        info = details[path]
        if path in parents or len(parents) > 50:
            info["context_errors"].append(f"Zyklische oder zu tiefe Einbindung: {path}")
            continue
        if (path, context) in visited:
            continue
        visited.add((path, context))
        if len(visited) > 5000:
            raise ConfigurationError("Include-Baum ist zu groß.")
        info["active"] = True
        if kind != "fragment" or info["type"] == "yaml":
            info["type"] = kind
        if shape and shape not in info["expected_shapes"]:
            info["expected_shapes"].append(shape)
        for child, keys, tag in edges[path]:
            child_context = (*context, *keys)
            child_kind, child_shape = role(child_context, tag)
            if tag == "!include_dir_merge_list":
                child_shape = "list"
            elif tag == "!include_dir_merge_named":
                child_shape = "mapping"
            if child_kind == "package":
                child_context = ()
            elif child_kind == "packages":
                child_context = ("homeassistant", "packages")
            elif tag in {"!include_dir_list", "!include_dir_named"}:
                child_context = (*child_context, "[]")
            queue.append(
                (child, child_context, child_kind, child_shape, (*parents, path))
            )
    for info in details.values():
        info["merge_supported"] = info["type"] in {"automations", "scripts", "scenes"}
        if not info["active"]:
            info["warnings"].append(
                "Keine Einbindung aus configuration.yaml erkannt; "
                "Import bindet die Datei nicht automatisch ein."
            )
    return details


def validate_context(path: str, text: str, info: dict) -> None:
    node = parse_yaml(text)
    if info["context_errors"]:
        raise ConfigurationError(f"{path}: " + " ".join(info["context_errors"]))
    expected = info["expected_shapes"]
    if len(expected) > 1:
        raise ConfigurationError(f"{path}: Widersprüchliche Include-Kontexte.")
    shape = (
        "mapping"
        if isinstance(node, MappingNode)
        else "list"
        if isinstance(node, SequenceNode)
        else "scalar"
    )
    if (
        node is not None
        and expected
        and shape not in expected
        and not (isinstance(node, ScalarNode) and node.tag in INCLUDE_TAGS)
    ):
        label = (
            "Liste mit '-'-Einträgen" if expected == ["list"] else "Zuordnung (Mapping)"
        )
        raise ConfigurationError(f"{path}: Hier wird eine {label} erwartet.")
    if (
        info["type"] in {"configuration", "package", "packages"}
        and isinstance(node, MappingNode)
        and any(
            key.value in {"alias", "trigger", "triggers", "actions", "action"}
            for key, _ in node.value
        )
    ):
        raise ConfigurationError(
            f"{path}: Eine einzelne Automation ist keine "
            "Konfiguration oder kein Package."
        )


def merge_yaml(before: str, incoming: str, kind: str) -> str:
    """Replace complete entries by stable IDs/keys; retain unrelated source bytes."""
    if kind not in {"automations", "scripts", "scenes"}:
        raise ConfigurationError(
            "Zusammenführen ist nur für Automationen, Szenen und Skripte verfügbar."
        )
    old, new = parse_yaml(before), parse_yaml(incoming)
    if any(
        isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None)
        for source in (before, incoming)
        for event in yaml.parse(source)
    ):
        raise ConfigurationError("Dateien mit YAML-Ankern bitte vollständig ersetzen.")
    expected = MappingNode if kind == "scripts" else SequenceNode
    if (
        not isinstance(old, expected)
        or not isinstance(new, expected)
        or old.flow_style
        or new.flow_style
    ):
        raise ConfigurationError(
            "Zusammenführen benötigt gleichartige Container in Blockschreibweise."
        )

    def blocks(node: Node, text: str):
        if isinstance(node, MappingNode):
            values = [(key.value, key, value) for key, value in node.value]
        else:
            values = []
            for item in node.value:
                if not isinstance(item, MappingNode):
                    raise ConfigurationError(
                        "Jeder Listeneintrag benötigt eine Zuordnung mit id."
                    )
                ids = [value for key, value in item.value if key.value == "id"]
                if (
                    len(ids) != 1
                    or not isinstance(ids[0], ScalarNode)
                    or ids[0].tag.startswith("!")
                    or not ids[0].value
                ):
                    raise ConfigurationError(
                        "Jeder Listeneintrag benötigt eine eindeutige id; "
                        "Aliase reichen nicht aus."
                    )
                values.append((ids[0].value, item, item))
        result, seen = [], set()
        for identity, start_node, end_node in values:
            if identity in seen:
                raise ConfigurationError(f"Doppelte ID: {identity}")
            seen.add(identity)
            start = text.rfind("\n", 0, start_node.start_mark.index) + 1
            # Container end marks may include the next entry's leading comments.
            leaves = [
                item
                for _, item in walk(end_node)
                if isinstance(item, ScalarNode) or not item.value
            ]
            end = max(
                (item.end_mark.index for item in leaves),
                default=end_node.end_mark.index,
            )
            if not end or text[end - 1] not in "\r\n":
                newline = text.find("\n", end)
                end = len(text) if newline < 0 else newline + 1
            result.append((identity, start, end, text[start:end]))
        return result

    old_blocks, new_blocks = blocks(old, before), blocks(new, incoming)
    replacements = {identity: text for identity, _, _, text in new_blocks}
    result, old_ids = before, set()
    for identity, start, end, _ in reversed(old_blocks):
        old_ids.add(identity)
        if identity in replacements:
            result = (
                result[:start]
                + replacements[identity].rstrip("\n")
                + "\n"
                + result[end:]
            )
    for identity, _, _, text in new_blocks:
        if identity not in old_ids:
            result = result.rstrip("\n") + "\n" + text.rstrip("\n") + "\n"
    parse_yaml(result)
    return result
