"""
MEXUS Server Manager

Herramienta para descargar, configurar, iniciar y administrar servidores de
Minecraft: Paper, Purpur, Fabric, Quilt, Vanilla, Forge, NeoForge y proxies
(Velocity, Waterfall).

Uso rapido:
    python mexus.py                           # menu interactivo
    python mexus.py start                     # iniciar el servidor
    python mexus.py install                   # descargar/instalar archivos
    python mexus.py versions --type paper     # ver versiones disponibles
    python mexus.py plugins search luckperms  # buscar plugins o mods
    python mexus.py backups list              # listar backups
    python mexus.py info                      # informacion del entorno

Opciones globales: --root (carpeta del servidor), --yes (sin preguntas),
--no-color. Usa "python mexus.py --help" para ver todos los comandos.
"""

from __future__ import annotations

import argparse
import tarfile
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import NoneType
from typing import ClassVar, Iterable, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


APP_NAME = "MEXUS Server Manager"
APP_VERSION = "4.0.0"
CONFIG_FILE = "mexus_config.json"
LOCKED_TYPE = "fabric"
LOCKED_VERSION = "1.21.4"
SERVER_JAR = "server.jar"
QUILT_LAUNCH_JAR = "quilt-server-launch.jar"
FORGE_INSTALLER = "forge-installer.jar"
NEOFORGE_INSTALLER = "neoforge-installer.jar"
QUILT_INSTALLER = "quilt-installer.jar"
BACKUP_DIR = "backups"
LOGS_DIR = "logs"
PLUGINS_DIR = "plugins"
MODS_DIR = "mods"
DEFAULT_SERVER_PROPERTIES = "server.properties"
DEFAULT_SERVER_PORT = "25565"
DEFAULT_PROXY_PORT = "25577"
REQUEST_TIMEOUT = 30
PROGRESS_WIDTH = 64
ASSUME_YES = False
SERVER_TYPES: tuple[str, ...] = (
    "paper",
    "purpur",
    "fabric",
    "quilt",
    "vanilla",
    "forge",
    "neoforge",
    "velocity",
    "waterfall",
    "hybrid",
)
SERVER_TYPE_HINTS: dict[str, str] = {
    "paper": "plugins y rendimiento",
    "purpur": "plugins + opciones extra",
    "fabric": "mods ligeros",
    "quilt": "mods (fork de Fabric)",
    "vanilla": "oficial, sin mods ni plugins",
    "forge": "mods clasicos",
    "neoforge": "mods modernos (1.20.2+)",
    "velocity": "proxy para varios servidores",
    "waterfall": "proxy tipo BungeeCord",
    "hybrid": "mods + plugins (manual)",
}
PROXY_TYPES: tuple[str, ...] = ("velocity", "waterfall")
MODDED_TYPES: tuple[str, ...] = ("fabric", "quilt", "forge", "neoforge")
PLUGIN_TYPES: tuple[str, ...] = ("paper", "purpur", "hybrid")
INSTALLABLE_TYPES: tuple[str, ...] = (
    "paper",
    "purpur",
    "fabric",
    "quilt",
    "vanilla",
    "forge",
    "neoforge",
    "velocity",
    "waterfall",
)
PAPER_API = "https://fill.papermc.io/v3"
PURPUR_API = "https://api.purpurmc.org/v2/purpur"
VANILLA_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
FABRIC_META = "https://meta.fabricmc.net/v2"
FABRIC_MAVEN = "https://maven.fabricmc.net/net/fabricmc"
QUILT_MAVEN = "https://maven.quiltmc.org/repository/release/org/quiltmc"
MODRINTH_API = "https://api.modrinth.com/v2"
MOJANG_PROFILES_API = "https://api.mojang.com/users/profiles/minecraft"
MODRINTH_LOADERS: dict[str, str] = {
    "paper": "paper",
    "purpur": "purpur",
    "hybrid": "paper",
    "fabric": "fabric",
    "quilt": "quilt",
    "forge": "forge",
    "neoforge": "neoforge",
    "velocity": "velocity",
    "waterfall": "waterfall",
}
BACKUP_ITEMS: tuple[str, ...] = (
    "world",
    "world_nether",
    "world_the_end",
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-ips.json",
    "banned-players.json",
    "plugins",
    "mods",
    "config",
    "velocity.toml",
    "config.yml",
)
PROPERTY_PRESETS: dict[str, dict[str, str]] = {
    "survival": {
        "gamemode": "survival",
        "difficulty": "normal",
        "pvp": "true",
        "spawn-protection": "16",
    },
    "creative": {
        "gamemode": "creative",
        "difficulty": "peaceful",
        "pvp": "false",
        "spawn-protection": "0",
        "allow-flight": "true",
    },
    "hardcore": {
        "gamemode": "survival",
        "difficulty": "hard",
        "pvp": "true",
        "hardcore": "true",
        "spawn-protection": "16",
    },
    "skyblock": {
        "gamemode": "survival",
        "difficulty": "normal",
        "pvp": "false",
        "spawn-protection": "0",
        "generate-structures": "false",
    },
    "friendly": {
        "gamemode": "survival",
        "difficulty": "easy",
        "pvp": "false",
        "spawn-protection": "0",
        "white-list": "true",
    },
}
RAM_PATTERN = re.compile(r"^[1-9][0-9]*[MGmg]$")
MINECRAFT_RELEASE_PATTERN = re.compile(r"^1\.\d+(?:\.\d+)?$")
RELEASE_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")
NEOFORGE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+")
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

ConfigValue: TypeAlias = str | bool
ConfigData: TypeAlias = dict[str, ConfigValue]
JSONValue: TypeAlias = (
    NoneType | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)
JSONObject: TypeAlias = dict[str, JSONValue]
JSONArray: TypeAlias = list[JSONValue]

if os.name == "nt":
    # Enables ANSI colors in most modern Windows terminals.
    os.system("")


class UI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    ORANGE = "\033[38;5;208m"
    COLOR_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def style(cls, text: str, *codes: str) -> str:
        if not cls.COLOR_ENABLED:
            return text
        return "".join(codes) + text + cls.RESET

    @classmethod
    def success(cls, message: str) -> None:
        print(cls.style("[OK] ", cls.GREEN, cls.BOLD) + message)

    @classmethod
    def error(cls, message: str) -> None:
        print(cls.style("[ERROR] ", cls.RED, cls.BOLD) + message)

    @classmethod
    def warning(cls, message: str) -> None:
        print(cls.style("[WARN] ", cls.YELLOW, cls.BOLD) + message)

    @classmethod
    def info(cls, message: str) -> None:
        print(cls.style("[INFO] ", cls.BLUE, cls.BOLD) + message)

    @classmethod
    def title(cls, message: str) -> None:
        print(cls.style(message, cls.CYAN, cls.BOLD))

    @classmethod
    def dim(cls, message: str) -> str:
        return cls.style(message, cls.DIM)

    @staticmethod
    def visible_len(text: str) -> int:
        return len(ANSI_PATTERN.sub("", text))

    @classmethod
    def clear(cls) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    @classmethod
    def line(cls, width: int = 72) -> None:
        print(cls.style("-" * width, cls.DIM))

    @classmethod
    def box(cls, content: str | Iterable[str], width: int = 72) -> str:
        if isinstance(content, str):
            lines: list[str] = content.splitlines() or [""]
        else:
            lines = list(content)

        inner_width = max(width, *(cls.visible_len(line) for line in lines))
        top = "+" + "-" * (inner_width + 2) + "+"
        body: list[str] = []
        for line in lines:
            padding = inner_width - cls.visible_len(line)
            body.append(f"| {line}{' ' * padding} |")
        bottom = "+" + "-" * (inner_width + 2) + "+"
        return "\n".join([top, *body, bottom])

    @classmethod
    def banner(cls) -> str:
        title = cls.style("MEXUS", cls.ORANGE, cls.BOLD)
        subtitle = cls.style("Minecraft Server Manager", cls.MAGENTA, cls.BOLD)
        season = cls.style("HALLOWEEN", cls.YELLOW, cls.BOLD)
        return cls.box(
            [
                f"{title}  {subtitle}",
                f"{season}  |  Version {APP_VERSION} - Crear, configurar y publicar",
            ],
            width=58,
        )

    @classmethod
    def menu_item(cls, key: str, label: str, hint: str = "") -> None:
        key_text = cls.style(f"{key:>2}", cls.ORANGE, cls.BOLD)
        if hint:
            print(f"  {key_text}  {label:<32} {cls.dim(hint)}")
        else:
            print(f"  {key_text}  {label}")

    @classmethod
    def section(cls, title: str) -> None:
        print(cls.style(title, cls.MAGENTA, cls.BOLD))

    @classmethod
    def ask(cls, label: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        return value or default

    @classmethod
    def confirm(cls, label: str, default: bool = False) -> bool:
        if ASSUME_YES:
            print(f"{label}: si (--yes)")
            return True
        suffix = " (S/n)" if default else " (s/N)"
        value = input(f"{label}{suffix}: ").strip().lower()
        if not value:
            return default
        return yes(value)

    @classmethod
    def fields(cls, rows: Iterable[tuple[str, str]], label_width: int = 16) -> None:
        for label, value in rows:
            text = f"{label}:"
            padding = " " * max(label_width - len(text), 1)
            print(f"  {cls.style(text, cls.DIM)}{padding}{value}")

    @classmethod
    def progress(cls, message: str, width: int = PROGRESS_WIDTH) -> None:
        text = message[:width].ljust(width)
        sys.stdout.write("\r" + cls.style(text, cls.DIM))
        sys.stdout.flush()

    @classmethod
    def progress_done(cls, width: int = PROGRESS_WIDTH) -> None:
        sys.stdout.write("\r" + " " * width + "\r")
        sys.stdout.flush()


def normalize_ram(value: str) -> str:
    value = value.strip().upper()
    if not RAM_PATTERN.match(value):
        raise ValueError("Usa un valor como 2G, 4096M o 8G.")
    return value


def version_key(value: str) -> tuple[int, int, int, tuple[int, ...]]:
    numbers = [int(part) for part in re.findall(r"\d+", value.strip())]
    while len(numbers) < 3:
        numbers.append(0)
    return (numbers[0], numbers[1], numbers[2], tuple(numbers[3:]))


def is_minecraft_release(value: str) -> bool:
    return bool(MINECRAFT_RELEASE_PATTERN.match(value))


def is_release_version(value: str) -> bool:
    return bool(RELEASE_VERSION_PATTERN.match(value.strip()))


def yes(value: str) -> bool:
    return value.strip().lower() in {"s", "si", "y", "yes"}


def format_size(size: float) -> str:
    value = float(max(size, 0.0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return default


def is_proxy_type(server_type: str) -> bool:
    return server_type.strip().lower() in PROXY_TYPES


def is_modded_type(server_type: str) -> bool:
    return server_type.strip().lower() in MODDED_TYPES


def content_dir(server_type: str) -> str:
    return MODS_DIR if is_modded_type(server_type) else PLUGINS_DIR


def default_port(server_type: str) -> str:
    return DEFAULT_PROXY_PORT if is_proxy_type(server_type) else DEFAULT_SERVER_PORT


def neoforge_prefix(minecraft_version: str) -> str:
    parts = minecraft_version.strip().split(".")
    if len(parts) < 2 or not parts[1].isdigit():
        raise ValueError(f"Version de Minecraft invalida para NeoForge: {minecraft_version}")
    minor = parts[2] if len(parts) > 2 and parts[2].isdigit() else "0"
    return f"{parts[1]}.{minor}."


def split_args(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def log_files(root: Path) -> list[Path]:
    directory = Path(root) / LOGS_DIR
    if not directory.exists():
        return []
    files = [path for path in directory.glob("*.log*") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def read_json_list(path: Path) -> list[JSONObject]:
    if not Path(path).exists():
        return []
    try:
        raw = cast(object, json.loads(Path(path).read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    entries: list[JSONObject] = []
    for item in cast(list[object], raw):
        if isinstance(item, dict):
            entries.append(cast(JSONObject, item))
    return entries


def write_json_list(path: Path, entries: Iterable[JSONObject]) -> None:
    Path(path).write_text(
        json.dumps(list(entries), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def dashed_uuid(value: str) -> str:
    clean = value.replace("-", "").strip().lower()
    if len(clean) != 32:
        return value
    return "-".join(
        (clean[:8], clean[8:12], clean[12:16], clean[16:20], clean[20:])
    )


def find_quilt_launcher(root: Path) -> Path | None:
    root = Path(root)
    direct = root / QUILT_LAUNCH_JAR
    if direct.exists():
        return direct
    candidates = [
        path for path in root.rglob("quilt-server-launch*.jar") if path.is_file()
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: len(path.parts))[0]


def hybrid_server_recommendation(version: str) -> str:
    normalized = version.strip()
    if normalized == "1.20.1":
        return "Mohist (recomendado)"
    if normalized == "1.16.5":
        return "Arclight o Magma"
    return "Mohist (recomendado) o Arclight/Magma"


def expect_object(value: JSONValue, name: str) -> JSONObject:
    if isinstance(value, dict):
        return cast(JSONObject, value)
    raise RuntimeError(f"Respuesta invalida de {name}: se esperaba un objeto.")


def expect_list(value: JSONValue, name: str) -> JSONArray:
    if isinstance(value, list):
        return cast(JSONArray, value)
    raise RuntimeError(f"Respuesta invalida de {name}: se esperaba una lista.")


def network_error_message(url: str, exc: Exception) -> str:
    host = urlparse(url).netloc or url
    if isinstance(exc, HTTPError):
        return f"{host} respondio con HTTP {exc.code}. Intenta de nuevo mas tarde."
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return (
                f"No se pudo resolver {host}. Revisa tu internet o DNS y vuelve a intentar."
            )
        return f"No se pudo conectar con {host}: {reason}"
    return f"No se pudo conectar con {host}: {exc}"


class Config:
    DEFAULTS: ClassVar[ConfigData] = {
        "type": LOCKED_TYPE,
        "version": LOCKED_VERSION,
        "ram_min": "2G",
        "ram_max": "4G",
        "java_path": "java",
        "jvm_args": "",
        "auto_backup": True,
        "auto_restart": False,
        "max_restarts": "3",
        "backup_keep": "5",
        "installed_type": "",
        "installed_version": "",
    }

    def __init__(self, path: Path | str = CONFIG_FILE) -> None:
        self.path = Path(path)
        self.data: ConfigData = dict(self.DEFAULTS)
        self.load()

    def load(self) -> None:
        self.data = dict(self.DEFAULTS)
        if not self.path.exists():
            return
        try:
            saved = cast(object, json.loads(self.path.read_text(encoding="utf-8")))
            if isinstance(saved, dict):
                saved_config = cast(dict[object, object], saved)
                for key, value in saved_config.items():
                    if isinstance(key, str) and isinstance(value, (str, bool)):
                        self.data[key] = value
        except json.JSONDecodeError:
            UI.warning(f"No se pudo leer {self.path}. Se usara configuracion nueva.")
        # This template only runs Fabric 1.21.4, whatever an old config says.
        self.data["type"] = LOCKED_TYPE
        self.data["version"] = LOCKED_VERSION

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get(self, key: str, default: ConfigValue | None = None) -> ConfigValue | None:
        return self.data.get(key, default)

    def get_str(self, key: str, default: str = "") -> str:
        value = self.data.get(key)
        return value if isinstance(value, str) else default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.data.get(key)
        return value if isinstance(value, bool) else default

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.data.get(key)
        if isinstance(value, str):
            return parse_int(value, default)
        if isinstance(value, bool):
            return default
        return default

    def set(self, key: str, value: ConfigValue) -> None:
        self.data[key] = value
        self.save()

    def update(self, **values: ConfigValue) -> None:
        self.data.update(values)
        self.save()

    def reset(self) -> None:
        self.data = dict(self.DEFAULTS)
        self.save()

    def touch_install(self) -> None:
        self.update(installed_type="", installed_version="")

    def is_ready(self) -> bool:
        return self.get_str("type") in SERVER_TYPES and bool(self.get_str("version").strip())

    def mark_installed(self) -> None:
        self.update(
            installed_type=self.get_str("type"),
            installed_version=self.get_str("version"),
        )

    def install_matches_config(self) -> bool:
        return (
            self.get_str("installed_type") == self.get_str("type")
            and self.get_str("installed_version") == self.get_str("version")
        )


class HttpClient:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {
            "User-Agent": (
                f"{APP_NAME}/{APP_VERSION} "
                "(https://github.com/mexus-server-manager/mexus)"
            )
        }

    def json(self, url: str) -> JSONValue:
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(network_error_message(url, exc)) from exc

        return cast(JSONValue, json.loads(payload))

    def text(self, url: str) -> str:
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(network_error_message(url, exc)) from exc

    def download(
        self,
        url: str,
        target: Path,
        show_progress: bool = True,
        sha256: str | None = None,
    ) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(target.suffix + ".part")
        temp_target.unlink(missing_ok=True)
        progress = show_progress and sys.stdout.isatty()

        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                total = parse_int(response.headers.get("Content-Length") or "0", 0)
                downloaded = 0
                with temp_target.open("wb") as file:
                    while True:
                        chunk = response.read(512 * 1024)
                        if not chunk:
                            break
                        file.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            self.report_progress(target.name, downloaded, total)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            temp_target.unlink(missing_ok=True)
            raise RuntimeError(network_error_message(url, exc)) from exc
        finally:
            if progress:
                UI.progress_done()

        if temp_target.stat().st_size == 0:
            temp_target.unlink(missing_ok=True)
            raise RuntimeError("La descarga llego vacia.")

        if sha256:
            if file_sha256(temp_target).lower() != sha256.strip().lower():
                temp_target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"La descarga de {target.name} no coincide con el checksum esperado."
                )

        temp_target.replace(target)
        return target

    @staticmethod
    def report_progress(name: str, done: int, total: int) -> None:
        if total > 0:
            percent = min(done * 100 // total, 100)
            message = (
                f"{name}: {percent:3d}% ({format_size(done)} / {format_size(total)})"
            )
        else:
            message = f"{name}: {format_size(done)}"
        UI.progress(message)

    def json_with_params(self, url: str, params: dict[str, str]) -> JSONValue:
        query = urlencode(params)
        separator = "&" if "?" in url else "?"
        return self.json(f"{url}{separator}{query}")

    def mojang_profile(self, name: str) -> tuple[str, str] | None:
        player = name.strip()
        if not player:
            return None
        try:
            payload = self.json(f"{MOJANG_PROFILES_API}/{quote(player)}")
        except ValueError:
            return None
        except RuntimeError as exc:
            message = str(exc)
            if "HTTP 204" in message or "HTTP 404" in message:
                return None
            raise

        if not isinstance(payload, dict):
            return None
        identifier = payload.get("id")
        if not isinstance(identifier, str):
            return None
        resolved_name = payload.get("name")
        return (
            dashed_uuid(identifier),
            resolved_name if isinstance(resolved_name, str) else player,
        )


class ServerDownloader:
    def __init__(self) -> None:
        self.http = HttpClient()

    def _get_fabric_loader_candidates(self, game_version: str) -> list[str]:
        candidate_urls = [
            f"{FABRIC_META}/versions/loader/{game_version}",
            f"{FABRIC_META}/versions/loader",
        ]
        candidates: list[tuple[bool, tuple[int, int, int, tuple[int, ...]], str]] = []

        for url in candidate_urls:
            try:
                payload = expect_list(self.http.json(url), "loaders de Fabric")
            except RuntimeError:
                continue

            for item in payload:
                if not isinstance(item, dict):
                    continue

                loader_info = item.get("loader")
                if isinstance(loader_info, dict):
                    version_value = loader_info.get("version")
                    stable_value = loader_info.get("stable")
                else:
                    version_value = item.get("version")
                    stable_value = item.get("stable")

                if not isinstance(version_value, str):
                    continue

                stable = bool(stable_value) if isinstance(stable_value, bool) else False
                candidates.append((stable, version_key(version_value), version_value))

            if candidates:
                break

        if not candidates:
            raise RuntimeError("No se encontro una version valida de Fabric Loader.")

        stable_candidates = [candidate for candidate in candidates if candidate[0]]
        if stable_candidates:
            candidates = stable_candidates

        candidates.sort(key=lambda candidate: candidate[1], reverse=True)
        return [candidate[2] for candidate in candidates]

    def _latest_maven_version(self, metadata_url: str, name: str) -> str:
        root = ElementTree.fromstring(self.http.text(metadata_url))
        versions = [
            text
            for item in root.findall("./versioning/versions/version")
            if (text := (item.text or "").strip())
        ]
        if not versions:
            raise RuntimeError(f"No se encontro una version valida de {name}.")
        return sorted(set(versions), key=version_key, reverse=True)[0]

    def _get_fabric_installer_version(self) -> str:
        return self._latest_maven_version(
            f"{FABRIC_MAVEN}/fabric-installer/maven-metadata.xml", "Fabric Installer"
        )

    def _get_quilt_installer_version(self) -> str:
        return self._latest_maven_version(
            f"{QUILT_MAVEN}/quilt-installer/maven-metadata.xml", "Quilt Installer"
        )

    def install_fabric_server(self, version: str, root: Path, java_path: str = "java") -> Path:
        root = Path(root)
        loader_versions = self._get_fabric_loader_candidates(version)
        installer_version = self._get_fabric_installer_version()
        last_error: RuntimeError | None = None

        for loader_version in loader_versions:
            installer_name = f"fabric-installer-{installer_version}.jar"
            installer_path = root / installer_name
            installer_url = (
                f"{FABRIC_MAVEN}/fabric-installer/{installer_version}/{installer_name}"
            )

            try:
                UI.info(
                    f"Instalando Fabric {version} con loader {loader_version}..."
                )
                self.http.download(installer_url, installer_path)
                completed = subprocess.run(
                    [
                        java_path,
                        "-jar",
                        str(installer_path),
                        "server",
                        "-dir",
                        str(root),
                        "-mcversion",
                        version,
                        "-loader",
                        loader_version,
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if completed.returncode == 0 and (root / SERVER_JAR).exists():
                    installer_path.unlink(missing_ok=True)
                    return root / SERVER_JAR
                if completed.returncode == 0:
                    UI.warning(
                        "El instalador de Fabric termino, pero no se encontro server.jar."
                    )
            except (RuntimeError, TimeoutError, OSError, subprocess.SubprocessError) as exc:
                last_error = RuntimeError(str(exc))

        if last_error is not None:
            raise last_error
        raise RuntimeError("No se pudo instalar Fabric con ninguna version de loader.")

    def get_paper_like_versions(self, project: str) -> list[str]:
        label = project.capitalize()
        data = expect_object(
            self.http.json(f"{PAPER_API}/projects/{project}"),
            label,
        )
        version_groups = expect_object(data.get("versions"), f"versiones de {label}")
        versions: list[str] = []
        for group_versions in version_groups.values():
            if not isinstance(group_versions, list):
                continue
            versions.extend(
                item
                for item in group_versions
                if isinstance(item, str) and is_release_version(item)
            )
        return versions

    def get_paper_like_download(
        self, project: str, version: str
    ) -> tuple[str, str | None]:
        label = project.capitalize()
        builds = expect_list(
            self.http.json(f"{PAPER_API}/projects/{project}/versions/{version}/builds"),
            f"builds de {label}",
        )

        stable_builds: list[JSONObject] = []
        fallback_builds: list[JSONObject] = []
        for item in builds:
            if not isinstance(item, dict):
                continue
            build = cast(JSONObject, item)
            fallback_builds.append(build)
            if build.get("channel") == "STABLE":
                stable_builds.append(build)

        candidates = stable_builds or fallback_builds
        if not candidates:
            raise RuntimeError(f"No hay builds de {label} para {version}.")

        if not stable_builds:
            UI.warning(
                f"No se encontro build STABLE de {label} {version}; "
                "se usara el build disponible mas reciente."
            )

        build_downloads = expect_object(
            candidates[0].get("downloads"), f"descargas de {label}"
        )
        payload = build_downloads.get("server:default")
        if not isinstance(payload, dict):
            payload = next(
                (
                    value
                    for value in build_downloads.values()
                    if isinstance(value, dict)
                ),
                None,
            )
        if payload is None:
            raise RuntimeError(f"{label} {version} no tiene archivos descargables.")

        download = expect_object(payload, f"server.jar de {label}")
        url = download.get("url")
        if not isinstance(url, str):
            raise RuntimeError(f"{label} {version} no tiene URL de descarga.")

        sha256: str | None = None
        checksums = download.get("checksums")
        if isinstance(checksums, dict):
            value = checksums.get("sha256")
            if isinstance(value, str):
                sha256 = value
        return url, sha256

    def get_purpur_versions(self) -> list[str]:
        data = expect_object(self.http.json(PURPUR_API), "Purpur")
        raw_versions = expect_list(data.get("versions"), "versiones de Purpur")
        return [
            item
            for item in raw_versions
            if isinstance(item, str) and is_release_version(item)
        ]

    def get_purpur_download(self, version: str) -> tuple[str, str | None]:
        data = expect_object(
            self.http.json(f"{PURPUR_API}/{version}"), f"Purpur {version}"
        )
        builds = expect_object(data.get("builds"), f"builds de Purpur {version}")
        latest = builds.get("latest")
        if not isinstance(latest, str):
            raise RuntimeError(f"Purpur {version} no tiene builds disponibles.")
        UI.info(f"Purpur {version} build {latest}")
        return f"{PURPUR_API}/{version}/latest/download", None

    def get_neoforge_versions(self) -> list[str]:
        root = ElementTree.fromstring(
            self.http.text(f"{NEOFORGE_MAVEN}/maven-metadata.xml")
        )
        return [
            text
            for item in root.findall("./versioning/versions/version")
            if (text := (item.text or "").strip())
        ]

    def resolve_neoforge_version(self, minecraft_version: str) -> str:
        candidate = minecraft_version.strip()
        versions = self.get_neoforge_versions()
        if candidate in versions:
            return candidate

        if NEOFORGE_VERSION_PATTERN.fullmatch(candidate) and not is_minecraft_release(candidate):
            raise RuntimeError(f"No existe una build de NeoForge {candidate}.")

        version = self.normalize_minecraft_version(candidate)
        if not is_minecraft_release(version):
            raise RuntimeError("No se indico una version de Minecraft para NeoForge.")

        prefix = neoforge_prefix(version)
        matches = [
            item
            for item in versions
            if item.startswith(prefix) or item.startswith(f"{version}-")
        ]
        if not matches:
            raise RuntimeError(
                f"No existe una build de NeoForge para {version} (busqueda {prefix}x)."
            )

        stable = [item for item in matches if "beta" not in item.lower()]
        return sorted(stable or matches, key=version_key, reverse=True)[0]

    def install_quilt_server(
        self, version: str, root: Path, java_path: str = "java"
    ) -> Path:
        root = Path(root)
        installer_version = self._get_quilt_installer_version()
        installer_path = root / QUILT_INSTALLER
        installer_url = (
            f"{QUILT_MAVEN}/quilt-installer/{installer_version}/"
            f"quilt-installer-{installer_version}.jar"
        )

        UI.info(f"Instalando Quilt {version}...")
        self.http.download(installer_url, installer_path)
        try:
            completed = subprocess.run(
                [
                    java_path,
                    "-jar",
                    str(installer_path),
                    "install",
                    "server",
                    version,
                    "--download-server",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=600,
            )
        finally:
            installer_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            raise RuntimeError(
                "Quilt no se pudo instalar: "
                + (detail[-1] if detail else "error desconocido del instalador")
            )

        launcher = find_quilt_launcher(root)
        if launcher is None:
            raise RuntimeError(
                "El instalador de Quilt no genero quilt-server-launch.jar."
            )
        UI.success(f"Quilt instalado: {launcher.relative_to(root).as_posix()}")
        return launcher

    def normalize_minecraft_version(self, version: str) -> str:
        candidate = version.strip()
        if not candidate:
            return candidate
        return candidate.split("-", 1)[0]

    def resolve_forge_version(self, minecraft_version: str) -> str:
        candidate = minecraft_version.strip()
        version = self.normalize_minecraft_version(minecraft_version)
        if not is_minecraft_release(version):
            raise RuntimeError("No se indico una version de Minecraft para Forge.")

        text = self.http.text(f"{FORGE_MAVEN}/maven-metadata.xml")
        root = ElementTree.fromstring(text)
        versions: list[str] = []
        for item in root.findall("./versioning/versions/version"):
            version_text = (item.text or "").strip()
            if version_text:
                versions.append(version_text)

        if "-" in candidate:
            if candidate in versions:
                return candidate
            raise RuntimeError(f"No existe una build de Forge {candidate}.")

        candidates = [item for item in versions if item.startswith(version + "-")]

        if not candidates:
            raise RuntimeError(f"No existe una build de Forge para {version}.")

        return sorted(set(candidates), key=version_key, reverse=True)[0]

    def get_mojang_releases(self) -> list[str]:
        data = expect_object(
            self.http.json(VANILLA_MANIFEST),
            "manifest de versiones de Minecraft",
        )
        version_items = expect_list(data.get("versions"), "versiones de Minecraft")
        releases: list[str] = []
        for item in version_items:
            if not isinstance(item, dict):
                continue
            version = item.get("id")
            if item.get("type") == "release" and isinstance(version, str):
                releases.append(version)
        return releases

    def get_versions(self, server_type: str) -> list[str]:
        server_type = server_type.lower()
        versions: list[str]
        if server_type in ("paper", "velocity", "waterfall"):
            versions = self.get_paper_like_versions(server_type)

        elif server_type == "purpur":
            versions = self.get_purpur_versions()

        elif server_type == "fabric":
            data = expect_list(
                self.http.json(f"{FABRIC_META}/versions/game"),
                "versiones de Fabric",
            )
            versions = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                version = item.get("version")
                if item.get("stable") is True and isinstance(version, str):
                    versions.append(version)

        elif server_type in ("vanilla", "quilt", "hybrid"):
            versions = self.get_mojang_releases()

        elif server_type == "forge":
            root = ElementTree.fromstring(
                self.http.text(f"{FORGE_MAVEN}/maven-metadata.xml")
            )
            versions = []
            for item in root.findall("./versioning/versions/version"):
                version_text = (item.text or "").strip()
                if version_text and "-" in version_text:
                    versions.append(version_text)

        elif server_type == "neoforge":
            versions = self.get_neoforge_versions()

        else:
            raise ValueError(f"Tipo de servidor no soportado: {server_type}")

        return sorted(set(versions), key=version_key, reverse=True)

    def download(
        self,
        server_type: str,
        version: str,
        root: Path,
        java_path: str = "java",
        show_progress: bool = True,
    ) -> Path:
        server_type = server_type.lower()
        root = Path(root)
        sha256: str | None = None

        if server_type in ("paper", "velocity", "waterfall"):
            url, sha256 = self.get_paper_like_download(server_type, version)
            target = root / SERVER_JAR

        elif server_type == "purpur":
            url, sha256 = self.get_purpur_download(version)
            target = root / SERVER_JAR

        elif server_type == "fabric":
            return self.install_fabric_server(version, root, java_path)

        elif server_type == "quilt":
            return self.install_quilt_server(version, root, java_path)

        elif server_type == "vanilla":
            manifest = expect_object(
                self.http.json(VANILLA_MANIFEST),
                "manifest de Vanilla",
            )
            version_items = expect_list(manifest.get("versions"), "versiones de Vanilla")
            version_info: JSONObject | None = None
            for item in version_items:
                if isinstance(item, dict) and item.get("id") == version:
                    version_info = item
                    break
            if not version_info:
                raise RuntimeError(f"No se encontro Vanilla {version}.")
            version_url = version_info.get("url")
            if not isinstance(version_url, str):
                raise RuntimeError(f"Vanilla {version} no tiene URL de metadata.")

            package = expect_object(self.http.json(version_url), f"Vanilla {version}")
            downloads = expect_object(package.get("downloads"), "descargas de Vanilla")
            server_download = expect_object(downloads.get("server"), "server.jar Vanilla")
            url_value = server_download.get("url")
            if not isinstance(url_value, str):
                raise RuntimeError(f"Vanilla {version} no tiene server.jar.")
            url = url_value
            size = server_download.get("size")
            if isinstance(size, int):
                UI.info(f"server.jar de Vanilla {version}: {format_size(size)}")
            target = root / SERVER_JAR

        elif server_type == "forge":
            forge_version = self.resolve_forge_version(version)
            url = f"{FORGE_MAVEN}/{forge_version}/forge-{forge_version}-installer.jar"
            target = root / FORGE_INSTALLER

        elif server_type == "neoforge":
            neoforge_version = self.resolve_neoforge_version(version)
            url = (
                f"{NEOFORGE_MAVEN}/{neoforge_version}/"
                f"neoforge-{neoforge_version}-installer.jar"
            )
            target = root / NEOFORGE_INSTALLER

        elif server_type == "hybrid":
            recommendation = hybrid_server_recommendation(version)
            UI.info(
                f"Para mods y plugins en {version}, usa {recommendation}."
            )
            raise RuntimeError(
                "Los servidores híbridos como Mohist, Arclight o Magma no se descargan automáticamente desde MEXUS. "
                "Descarga el servidor manualmente y colócalo como server.jar."
            )

        else:
            raise ValueError(f"Tipo de servidor no soportado: {server_type}")

        UI.info(f"Descargando {server_type} {version}...")
        return self.http.download(
            url, target, show_progress=show_progress, sha256=sha256
        )


class ServerManager:
    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root).resolve()
        self.config = Config(self.root / CONFIG_FILE)
        self.process: subprocess.Popen[str] | None = None

    @property
    def server_type(self) -> str:
        return self.config.get_str("type")

    @property
    def is_proxy(self) -> bool:
        return is_proxy_type(self.server_type)

    @property
    def content_path(self) -> Path:
        return self.root / content_dir(self.server_type)

    @property
    def jar_name(self) -> str:
        if self.server_type == "quilt":
            launcher = find_quilt_launcher(self.root)
            if launcher is not None:
                return launcher.relative_to(self.root).as_posix()
        return SERVER_JAR

    @property
    def server_jar(self) -> Path:
        return self.root / self.jar_name

    @property
    def forge_installer(self) -> Path:
        return self.root / FORGE_INSTALLER

    @property
    def neoforge_installer(self) -> Path:
        return self.root / NEOFORGE_INSTALLER

    def jvm_args(self) -> list[str]:
        return [
            f"-Xms{self.config.get_str('ram_min')}",
            f"-Xmx{self.config.get_str('ram_max')}",
            "-XX:+UseG1GC",
            *split_args(self.config.get_str("jvm_args")),
        ]

    def server_port(self) -> int:
        properties = read_properties(self.root / DEFAULT_SERVER_PROPERTIES)
        fallback = parse_int(default_port(self.server_type), parse_int(DEFAULT_SERVER_PORT, 25565))
        return parse_int(properties.get("server-port", ""), fallback)

    def port_in_use(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1.0)
            return probe.connect_ex(("127.0.0.1", self.server_port())) == 0

    def check_java(self) -> bool:
        java_path = self.config.get_str("java_path", "java")
        if shutil.which(java_path) is None and not Path(java_path).exists():
            UI.error("Java no esta instalado o no esta en el PATH.")
            print("Instala Java 21 para Minecraft moderno: https://adoptium.net/")
            return False

        try:
            completed = subprocess.run(
                [java_path, "-version"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            UI.error(f"No se pudo ejecutar Java: {exc}")
            return False

        output = (completed.stderr or completed.stdout).splitlines()
        if output:
            UI.info(output[0])
        return completed.returncode == 0

    def ensure_eula(self) -> bool:
        eula_path = self.root / "eula.txt"
        if eula_path.exists() and "eula=true" in eula_path.read_text(
            encoding="utf-8", errors="ignore"
        ).lower():
            return True

        env_accept = os.environ.get("EULA", "").strip().lower() in {"true", "1", "yes", "si"}
        if env_accept or ASSUME_YES:
            eula_path.write_text("eula=true\n", encoding="utf-8")
            UI.success("EULA aceptada automaticamente (EULA=TRUE o --yes).")
            return True

        UI.warning("Para iniciar el servidor debes aceptar la EULA de Minecraft.")
        print("Lee: https://aka.ms/MinecraftEULA")
        answer = input("Aceptas la EULA? (s/N): ")
        if not yes(answer):
            UI.error("No se inicio el servidor porque la EULA no fue aceptada.")
            return False

        eula_path.write_text("eula=true\n", encoding="utf-8")
        UI.success("EULA aceptada y guardada en eula.txt.")
        return True

    def write_forge_jvm_args(self) -> None:
        (self.root / "user_jvm_args.txt").write_text(
            "\n".join(self.jvm_args()) + "\n", encoding="utf-8"
        )

    def install_forge(self) -> bool:
        return self.install_loader_server("forge")

    def install_loader_server(self, server_type: str) -> bool:
        java_path = self.config.get_str("java_path", "java")
        version = self.config.get_str("version")
        label = "NeoForge" if server_type == "neoforge" else "Forge"
        installer = (
            self.neoforge_installer if server_type == "neoforge" else self.forge_installer
        )

        if not installer.exists() or not self.config.install_matches_config():
            ServerDownloader().download(server_type, version, self.root, java_path)

        UI.info(f"Instalando {label}. Esto puede tardar unos minutos...")
        completed = subprocess.run(
            [java_path, "-jar", str(installer), "--installServer"],
            cwd=self.root,
            text=True,
        )
        if completed.returncode != 0:
            UI.error(f"{label} no se pudo instalar.")
            return False

        self.write_forge_jvm_args()
        self.config.mark_installed()
        UI.success(f"{label} instalado correctamente.")
        return True

    def ensure_server_files(self, force: bool = False) -> bool:
        self.config.load()
        server_type = self.config.get_str("type")
        version = self.config.get_str("version")

        if not self.config.is_ready():
            UI.error("Falta configurar tipo y version del servidor.")
            return False

        try:
            if server_type in ("forge", "neoforge"):
                run_script_exists = (self.root / "run.bat").exists() or (
                    self.root / "run.sh"
                ).exists()
                if (
                    force
                    or not run_script_exists
                    or not self.config.install_matches_config()
                ):
                    return self.install_loader_server(server_type)
                self.write_forge_jvm_args()
                return True

            if (
                force
                or not self.server_jar.exists()
                or not self.config.install_matches_config()
            ):
                ServerDownloader().download(
                    server_type,
                    version,
                    self.root,
                    self.config.get_str("java_path", "java"),
                )
                self.config.mark_installed()
            return True

        except Exception as exc:
            UI.error(f"No se pudo preparar el servidor: {exc}")
            return False

    def install_or_update(self, force: bool = False) -> bool:
        if force:
            self.config.touch_install()
        return self.ensure_server_files(force=force)

    def purge(self, remove_worlds: bool = False) -> list[str]:
        targets = [
            SERVER_JAR,
            QUILT_LAUNCH_JAR,
            FORGE_INSTALLER,
            NEOFORGE_INSTALLER,
            QUILT_INSTALLER,
            "run.bat",
            "run.sh",
            "user_jvm_args.txt",
            "libraries",
            "versions",
            "cache",
        ]
        if remove_worlds:
            targets.extend(
                [
                    "world",
                    "world_nether",
                    "world_the_end",
                    LOGS_DIR,
                    BACKUP_DIR,
                    PLUGINS_DIR,
                    MODS_DIR,
                    "config",
                ]
            )

        removed: list[str] = []
        for name in targets:
            path = self.root / name
            if not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(name)

        for leftover in self.root.glob("*.part"):
            leftover.unlink(missing_ok=True)
            removed.append(leftover.name)

        self.config.touch_install()
        return removed

    def build_command(self) -> list[str]:
        server_type = self.config.get_str("type")
        java_path = self.config.get_str("java_path", "java")

        if server_type in ("forge", "neoforge"):
            self.write_forge_jvm_args()
            if os.name == "nt" and (self.root / "run.bat").exists():
                return ["cmd.exe", "/c", "run.bat", "nogui"]
            if (self.root / "run.sh").exists():
                return ["sh", "run.sh", "nogui"]

            downloader = ServerDownloader()
            version = self.config.get_str("version")
            args_name = "win_args.txt" if os.name == "nt" else "unix_args.txt"
            if server_type == "neoforge":
                loader_version = downloader.resolve_neoforge_version(version)
                arg_file = (
                    self.root
                    / "libraries"
                    / "net"
                    / "neoforged"
                    / "neoforge"
                    / loader_version
                    / args_name
                )
            else:
                loader_version = downloader.resolve_forge_version(version)
                arg_file = (
                    self.root
                    / "libraries"
                    / "net"
                    / "minecraftforge"
                    / "forge"
                    / loader_version
                    / args_name
                )

            if arg_file.exists():
                relative_arg_file = arg_file.relative_to(self.root).as_posix()
                return [java_path, "@user_jvm_args.txt", f"@{relative_arg_file}", "nogui"]

            raise RuntimeError(
                f"No se encontro run.bat/run.sh ni los args de {server_type}."
            )

        command = [java_path, *self.jvm_args(), "-jar", self.jar_name]
        if not self.is_proxy:
            command.append("nogui")
        return command

    def create_backup(self, automatic: bool = False) -> Path | None:
        existing = [
            self.root / item for item in BACKUP_ITEMS if (self.root / item).exists()
        ]
        if not existing:
            if not automatic:
                UI.info("No hay mundos o archivos de servidor para respaldar todavia.")
            return None

        backups = self.root / BACKUP_DIR
        backups.mkdir(exist_ok=True)
        prefix = "auto" if automatic else "manual"
        backup_path = backups / f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}.zip"

        UI.info(f"Creando backup: {backup_path.name}")
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in existing:
                if item.is_dir():
                    for child in item.rglob("*"):
                        if child.is_file():
                            archive.write(child, child.relative_to(self.root))
                else:
                    archive.write(item, item.relative_to(self.root))

        UI.success(
            f"Backup guardado en {backup_path} "
            f"({format_size(backup_path.stat().st_size)})"
        )
        self.clean_backups(self.config.get_int("backup_keep", 5), quiet=True)
        return backup_path

    def all_backups(self) -> list[Path]:
        directory = self.root / BACKUP_DIR
        if not directory.exists():
            return []
        return sorted(
            (path for path in directory.glob("*.zip") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def list_backups(self) -> list[Path]:
        backups = self.all_backups()
        if not backups:
            UI.info("No hay backups todavia.")
            return backups

        UI.title(f"Backups en {self.root / BACKUP_DIR}")
        for index, path in enumerate(backups, start=1):
            created = datetime.fromtimestamp(path.stat().st_mtime)
            print(
                f"  {index:2}. {path.name:<34}"
                f"{format_size(path.stat().st_size):>9}  "
                f"{UI.dim(f'{created:%Y-%m-%d %H:%M}')}"
            )
        return backups

    def clean_backups(self, keep: int = 5, quiet: bool = False) -> list[Path]:
        backups = self.all_backups()
        removed = backups if keep <= 0 else backups[keep:]
        for path in removed:
            path.unlink(missing_ok=True)
        if removed and not quiet:
            UI.success(f"Backups eliminados: {len(removed)} (se conservan {keep}).")
        return removed

    def find_backup(self, name: str) -> Path | None:
        backups = self.all_backups()
        if not backups:
            return None
        query = name.strip()
        if query.lower() in ("", "latest", "ultimo"):
            return backups[0]
        if query.isdigit():
            index = int(query) - 1
            return backups[index] if 0 <= index < len(backups) else None
        for path in backups:
            if query in (path.name, path.stem):
                return path
        return None

    def restore_backup(self, name: str, safety_backup: bool = True) -> bool:
        target = self.find_backup(name)
        if target is None:
            UI.error(f"No se encontro el backup {name or 'latest'}.")
            return False

        if safety_backup:
            self.create_backup(automatic=True)

        UI.warning(
            f"Restaurando {target.name}: los archivos actuales se sobrescribiran."
        )
        with zipfile.ZipFile(target) as archive:
            for member in archive.infolist():
                parts = Path(member.filename).parts
                if member.is_dir() or not parts or ".." in parts:
                    continue
                archive.extract(member, self.root)

        UI.success(f"Backup restaurado: {target.name}")
        return True

    def tail_logs(self, lines: int = 40, follow: bool = False) -> None:
        files = log_files(self.root)
        if not files:
            UI.info("Todavia no hay archivos en logs/.")
            return

        latest = files[0]
        text = latest.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in text[-max(lines, 1) :]:
            print(line)

        if not follow:
            return

        UI.info("Siguiendo el log. Usa Ctrl+C para salir.")
        try:
            with latest.open("r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(0, os.SEEK_END)
                while True:
                    line = handle.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(1)
        except KeyboardInterrupt:
            UI.warning("Seguimiento del log detenido.")

    def start(self, restart_count: int = 0) -> bool:
        self.config.load()
        if not self.config.is_ready():
            UI.error("Primero configura el tipo y la version del servidor.")
            return False

        if not self.check_java():
            return False
        if not self.is_proxy and not self.ensure_eula():
            return False
        if self.config.get_bool("auto_backup", True) and restart_count == 0:
            self.create_backup(automatic=True)
        if not self.ensure_server_files():
            return False

        command = self.build_command()
        UI.success(
            f"Iniciando {self.config.get_str('type')} {self.config.get_str('version')} "
            f"con {self.config.get_str('ram_min')}-{self.config.get_str('ram_max')} RAM."
        )
        UI.info("Escribe comandos del servidor aqui. Usa 'stop' para apagar.")

        stop_sent = False
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.root,
                stdin=subprocess.PIPE,
                text=True,
            )

            while self.process.poll() is None:
                try:
                    command_text = input()
                except EOFError:
                    self.process.wait()
                    break

                if self.process.stdin is not None:
                    self.process.stdin.write(command_text + "\n")
                    self.process.stdin.flush()

                if command_text.strip().lower() == "stop":
                    stop_sent = True
                    break

        except KeyboardInterrupt:
            UI.warning("Interrupcion detectada. Deteniendo servidor...")
        except OSError as exc:
            UI.error(f"No se pudo iniciar el servidor: {exc}")
            return False
        finally:
            self.stop_gracefully(send_stop=not stop_sent)

        success = self.process is not None and self.process.returncode == 0
        if success or stop_sent or not self.config.get_bool("auto_restart", False):
            return success

        max_restarts = max(self.config.get_int("max_restarts", 3), 0)
        if restart_count >= max_restarts:
            UI.error("Se alcanzo el maximo de reinicios automaticos.")
            return False

        code = self.process.returncode if self.process is not None else "-"
        UI.warning(
            f"El servidor termino con codigo {code}. "
            f"Reiniciando ({restart_count + 1}/{max_restarts}) en 5 segundos..."
        )
        time.sleep(5)
        return self.start(restart_count + 1)

    def stop_gracefully(self, send_stop: bool = True) -> None:
        if self.process is None or self.process.poll() is not None:
            return

        if send_stop and self.process.stdin is not None:
            try:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
            except OSError:
                pass

        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            UI.warning("El servidor no se detuvo a tiempo. Cerrando proceso...")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def print_status(config: Config, manager: ServerManager | None = None) -> None:
    ready = "Configurado" if config.is_ready() else "Falta configurar"
    server_type = config.get_str("type")
    lines = [
        f"Estado: {ready}",
        f"Servidor: {server_type} {config.get_str('version') or '-'}",
        f"RAM: {config.get_str('ram_min')} - {config.get_str('ram_max')}",
        f"Java: {config.get_str('java_path')}",
        f"Auto backup: {'si' if config.get_bool('auto_backup') else 'no'} "
        f"(conserva {config.get_int('backup_keep', 5)})",
        f"Auto reinicio: {'si' if config.get_bool('auto_restart') else 'no'}",
    ]
    if manager is not None:
        lines.append(f"Carpeta: {manager.root}")
        lines.append(
            f"Puerto: {manager.server_port()} "
            f"({'ocupado' if manager.port_in_use() else 'libre'})"
        )
    print(UI.box(lines, width=58))


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_properties(path: Path, updates: dict[str, str]) -> None:
    current = read_properties(path)
    current.update(updates)

    preferred_order = [
        "server-name",
        "motd",
        "server-port",
        "max-players",
        "difficulty",
        "gamemode",
        "pvp",
        "online-mode",
        "white-list",
        "spawn-protection",
        "view-distance",
        "simulation-distance",
        "enable-command-block",
        "allow-flight",
    ]
    ordered_keys = [key for key in preferred_order if key in current]
    ordered_keys.extend(sorted(key for key in current if key not in ordered_keys))

    lines = [
        "# Minecraft server properties generated by MEXUS",
        f"# Updated {datetime.now():%Y-%m-%d %H:%M:%S}",
    ]
    lines.extend(f"{key}={current[key]}" for key in ordered_keys)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def configure_server_properties(
    manager: ServerManager,
    preset: str | None = None,
    changes: Iterable[str] = (),
    interactive: bool = True,
) -> bool:
    server_type = manager.server_type
    if manager.is_proxy:
        UI.warning(
            f"{server_type} no usa server.properties. Configura su archivo propio "
            "(velocity.toml o config.yml) despues del primer arranque."
        )
        return False

    path = manager.root / DEFAULT_SERVER_PROPERTIES
    current = read_properties(path)

    defaults = {
        "motd": current.get("motd", "Servidor MEXUS"),
        "server-port": current.get("server-port", default_port(server_type)),
        "max-players": current.get("max-players", "20"),
        "difficulty": current.get("difficulty", "normal"),
        "gamemode": current.get("gamemode", "survival"),
        "pvp": current.get("pvp", "true"),
        "online-mode": current.get("online-mode", "true"),
        "white-list": current.get("white-list", "false"),
        "view-distance": current.get("view-distance", "10"),
        "simulation-distance": current.get("simulation-distance", "10"),
        "enable-command-block": current.get("enable-command-block", "false"),
    }
    prompts = [
        ("motd", "Nombre/MOTD"),
        ("server-port", "Puerto"),
        ("max-players", "Jugadores maximos"),
        ("difficulty", "Dificultad (peaceful/easy/normal/hard)"),
        ("gamemode", "Modo (survival/creative/adventure/spectator)"),
        ("pvp", "PVP (true/false)"),
        ("online-mode", "Online mode premium (true/false)"),
        ("white-list", "Whitelist (true/false)"),
        ("view-distance", "View distance"),
        ("simulation-distance", "Simulation distance"),
        ("enable-command-block", "Command blocks (true/false)"),
    ]

    updates: dict[str, str] = {} if path.exists() else dict(defaults)
    if preset:
        if preset not in PROPERTY_PRESETS:
            UI.error("Preset invalido. Usa: " + ", ".join(sorted(PROPERTY_PRESETS)))
            return False
        updates.update(PROPERTY_PRESETS[preset])
        UI.info(f"Preset aplicado: {preset}")

    for item in changes:
        if "=" not in item:
            UI.error(f"Formato invalido: {item}. Usa clave=valor.")
            return False
        key, _, value = item.partition("=")
        updates[key.strip()] = value.strip()

    if interactive:
        UI.title("Configuracion rapida del servidor")
        print("Deja un campo vacio para conservar el valor actual.")
        print()
        for key, label in prompts:
            shown = updates.get(key, defaults[key])
            value = input(f"{label} [{shown}]: ").strip()
            if value:
                updates[key] = value
            else:
                updates.setdefault(key, shown)

    if not updates:
        UI.info("No se cambio ningun valor.")
        return False

    write_properties(path, updates)
    UI.success(f"Guardado: {path.name} ({len(updates)} valores)")
    return True


def configure_jvm_args(config: Config) -> None:
    UI.line()
    print("Argumentos JVM adicionales (ej: -XX:+UseZGC -Dfile.encoding=UTF-8)")
    print("Se agregaran despues de -Xms/-Xmx. Deja vacio para quitarlos.")
    current = config.get_str("jvm_args")
    value = input(f"Argumentos [{current or 'ninguno'}]: ").strip()
    config.set("jvm_args", value)
    UI.success("Argumentos JVM actualizados." if value else "Argumentos JVM limpiados.")


def make_start_script(
    config: Config, windows: bool, jar_name: str = SERVER_JAR, nogui: bool = True
) -> str:
    java_path = config.get_str("java_path", "java")
    args = " ".join(
        [
            f"-Xms{config.get_str('ram_min', '2G')}",
            f"-Xmx{config.get_str('ram_max', '4G')}",
            "-XX:+UseG1GC",
            *split_args(config.get_str("jvm_args")),
        ]
    )
    suffix = " nogui" if nogui else ""
    if windows:
        return (
            "@echo off\n"
            "title MEXUS Minecraft Server\n"
            f'"{java_path}" {args} -jar {jar_name}{suffix}\n'
            "pause\n"
        )
    return (
        "#!/usr/bin/env sh\n"
        f'exec "{java_path}" {args} -jar {jar_name}{suffix}\n'
    )


def generate_github_files(manager: ServerManager) -> None:
    config = manager.config
    server_type = config.get_str("type", "paper")
    version = config.get_str("version") or "sin configurar"

    files: dict[str, str] = {
        ".gitignore": "\n".join(
            [
                "# Server runtime",
                "world/",
                "world_nether/",
                "world_the_end/",
                "logs/",
                "crash-reports/",
                "backups/",
                "*.jar",
                "*.part",
                "libraries/",
                "versions/",
                "cache/",
                "eula.txt",
                "ops.json",
                "whitelist.json",
                "banned-ips.json",
                "banned-players.json",
                "plugins/",
                "mods/",
                "user_jvm_args.txt",
                ".mexus_java/",
                "",
            ]
        ),
        "README.md": "\n".join(
            [
                "# Minecraft Server",
                "",
                "Servidor generado con MEXUS Server Manager.",
                "",
                "## Configuracion",
                "",
                f"- Tipo: `{server_type}`",
                f"- Version: `{version}`",
                f"- RAM: `{config.get_str('ram_min')}` a `{config.get_str('ram_max')}`",
                f"- Java: `{config.get_str('java_path')}`",
                f"- Carpeta de contenido: `{content_dir(server_type)}`",
                f"- Args JVM extra: `{config.get_str('jvm_args') or 'ninguno'}`",
                "",
                "## Comandos utiles de MEXUS",
                "",
                "1. `python mexus.py install` descarga o reinstala los archivos del servidor.",
                "2. `python mexus.py plugins search <nombre>` busca plugins o mods en Modrinth.",
                "3. `python mexus.py backups list` lista respaldos y `backups restore latest` restaura.",
                "4. `python mexus.py logs --lines 80` muestra las ultimas lineas del log.",
                "",
                "## Recomendacion para mods + plugins",
                "",
                "Para combinar mods y plugins, lo mejor suele ser Mohist en 1.20.1. "
                "Alternativas viables son Arclight o Magma, especialmente en 1.16.5.",
                "",
                "## Uso",
                "",
                "1. Instala Java 21.",
                "2. Ejecuta `python mexus.py` para configurar o iniciar el servidor.",
                "3. Acepta la EULA solo si estas de acuerdo con los terminos de Mojang.",
                "",
                "Los mundos, backups, logs y archivos pesados no se suben a GitHub.",
                "",
            ]
        ),
        "altare-startup.md": "\n".join(
            [
                "# Altare (deploy desde GitHub)",
                "",
                "- Directorio raiz: `mcserver`",
                "- Comando de instalacion: `python3 mexus.py install --yes`",
                "- Comando de inicio: `python3 mexus.py start --yes --no-backup`",
                "- Variables: `EULA=TRUE`, `SERVER_MEMORY` (MB).",
                "- Version fija: Fabric 1.21.4. Java 21 se descarga solo si falta.",
                "",
            ]
        ),
        "start-server.bat": make_start_script(
            config, windows=True, jar_name=manager.jar_name, nogui=not manager.is_proxy
        ),
        "start-server.sh": make_start_script(
            config, windows=False, jar_name=manager.jar_name, nogui=not manager.is_proxy
        ),
    }

    created: list[str] = []
    for name, content in files.items():
        path = manager.root / name
        if path.exists():
            answer = input(f"{name} ya existe. Sobrescribir? (s/N): ")
            if not yes(answer):
                continue
        path.write_text(content, encoding="utf-8")
        created.append(name)

    if created:
        UI.success("Archivos listos para GitHub: " + ", ".join(created))
    else:
        UI.info("No se cambio ningun archivo.")


class ModrinthClient:
    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()

    def search(self, query: str, kind: str, limit: int = 10) -> list[JSONObject]:
        payload = self.http.json_with_params(
            f"{MODRINTH_API}/search",
            {
                "query": query,
                "limit": str(max(limit, 1)),
                "index": "relevance",
                "facets": json.dumps([[f"project_type:{kind}"]]),
            },
        )
        data = expect_object(payload, "busqueda de Modrinth")
        hits = expect_list(data.get("hits"), "resultados de Modrinth")
        return [cast(JSONObject, item) for item in hits if isinstance(item, dict)]

    def versions(self, slug: str, loader: str, game_version: str) -> list[JSONObject]:
        params: dict[str, str] = {"loaders": json.dumps([loader])}
        if game_version:
            params["game_versions"] = json.dumps([game_version])
        payload = self.http.json_with_params(
            f"{MODRINTH_API}/project/{quote(slug)}/version", params
        )
        data = expect_list(payload, f"versiones de {slug}")
        return [cast(JSONObject, item) for item in data if isinstance(item, dict)]

    def latest_file(
        self, slug: str, loader: str, game_version: str
    ) -> tuple[str, str] | None:
        for entry in self.versions(slug, loader, game_version):
            files = entry.get("files")
            if not isinstance(files, list):
                continue
            candidates = [item for item in files if isinstance(item, dict)]
            if not candidates:
                continue
            primary = next(
                (item for item in candidates if item.get("primary") is True), None
            )
            chosen = primary or candidates[0]
            url = chosen.get("url")
            filename = chosen.get("filename")
            if isinstance(url, str) and isinstance(filename, str):
                return url, filename
        return None


def resolve_content_kind(manager: ServerManager, kind: str | None) -> str:
    if kind:
        return kind
    return "mod" if is_modded_type(manager.server_type) else "plugin"


def plugins_search(
    manager: ServerManager, query: str, kind: str | None = None, limit: int = 10
) -> list[JSONObject]:
    content_kind = resolve_content_kind(manager, kind)
    hits = ModrinthClient().search(query, content_kind, limit)
    if not hits:
        UI.info("Sin resultados en Modrinth.")
        return []

    UI.title(f"Resultados de Modrinth ({content_kind}s)")
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or hit.get("slug") or "?"
        slug = hit.get("slug") or "?"
        downloads = hit.get("downloads")
        extra = f"{downloads:,} descargas" if isinstance(downloads, int) else ""
        print(f"  {index:2}. {title} {UI.dim(f'[{slug}]')} {UI.dim(extra)}")
        description = hit.get("description")
        if isinstance(description, str):
            print(f"      {UI.dim(description[:110])}")
    return hits


def plugins_install(
    manager: ServerManager,
    slug: str,
    kind: str | None = None,
    game_version: str | None = None,
) -> bool:
    server_type = manager.server_type
    content_kind = resolve_content_kind(manager, kind)
    loader = MODRINTH_LOADERS.get(server_type)
    if loader is None:
        UI.error(f"Modrinth no tiene loader registrado para {server_type}.")
        return False

    version = game_version if game_version is not None else manager.config.get_str("version")
    client = ModrinthClient()
    UI.info(f"Buscando {content_kind} {slug} para {loader} {version or 'cualquiera'}...")
    result = client.latest_file(slug, loader, version)
    if result is None and version:
        UI.warning(f"Sin versiones para {loader} {version}; se buscara la mas reciente.")
        result = client.latest_file(slug, loader, "")
    if result is None:
        UI.error(f"No hay archivos compatibles con {loader} para {slug}.")
        return False

    url, filename = result
    target_dir = manager.content_path
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if target.exists() and not UI.confirm(
        f"{filename} ya existe. Reemplazar?", default=True
    ):
        return False

    client.http.download(url, target)
    UI.success(f"Instalado: {target_dir.name}/{filename}")
    UI.info("Reinicia el servidor para aplicar el cambio.")
    return True


def plugins_list(manager: ServerManager) -> None:
    directory = manager.content_path
    if not directory.exists():
        UI.info(f"La carpeta {directory.name}/ todavia no existe.")
        return

    jars = sorted(
        (path for path in directory.glob("*.jar") if path.is_file()),
        key=lambda path: path.name.lower(),
    )
    if not jars:
        UI.info(f"No hay archivos en {directory.name}/.")
        return

    UI.title(f"Contenido en {directory.name}/ ({len(jars)})")
    for path in jars:
        print(f"  - {path.name} {UI.dim(f'({format_size(path.stat().st_size)})')}")


def plugins_remove(manager: ServerManager, name: str) -> bool:
    directory = manager.content_path
    matches = [
        path
        for path in directory.glob("*.jar")
        if path.is_file() and (name in (path.name, path.stem) or path.name.startswith(name))
    ]
    if not matches:
        UI.error(f"No se encontro {name} en {directory.name}/.")
        return False

    for path in matches:
        if not UI.confirm(f"Borrar {path.name}?", default=True):
            continue
        path.unlink(missing_ok=True)
        UI.success(f"Eliminado: {path.name}")
    return True


class PlayerStore:
    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.http = HttpClient()

    @property
    def whitelist(self) -> Path:
        return self.manager.root / "whitelist.json"

    @property
    def ops(self) -> Path:
        return self.manager.root / "ops.json"

    @property
    def banned(self) -> Path:
        return self.manager.root / "banned-players.json"

    @staticmethod
    def names(entries: Iterable[JSONObject]) -> str:
        found = [str(entry["name"]) for entry in entries if isinstance(entry.get("name"), str)]
        return ", ".join(found) if found else "-"

    @staticmethod
    def matches(entry: JSONObject, name: str) -> bool:
        value = entry.get("name")
        return isinstance(value, str) and value.lower() == name.strip().lower()

    def show(self) -> None:
        UI.title("Jugadores")
        UI.fields(
            [
                ("Whitelist", self.names(read_json_list(self.whitelist))),
                ("Operadores", self.names(read_json_list(self.ops))),
                ("Baneados", self.names(read_json_list(self.banned))),
            ]
        )

    def profile(self, name: str) -> tuple[str, str] | None:
        profile = self.http.mojang_profile(name)
        if profile is None:
            UI.error(f"No se encontro la cuenta premium {name} en Mojang.")
        return profile

    def add_whitelist(self, name: str) -> bool:
        profile = self.profile(name)
        if profile is None:
            return False
        uuid, resolved = profile
        entries = [
            entry for entry in read_json_list(self.whitelist) if entry.get("uuid") != uuid
        ]
        entry: JSONObject = {"uuid": uuid, "name": resolved}
        entries.append(entry)
        write_json_list(self.whitelist, entries)
        UI.success(f"{resolved} agregado a la whitelist.")
        return True

    def remove_whitelist(self, name: str) -> bool:
        entries = read_json_list(self.whitelist)
        remaining = [entry for entry in entries if not self.matches(entry, name)]
        if len(remaining) == len(entries):
            UI.error(f"{name} no esta en la whitelist.")
            return False
        write_json_list(self.whitelist, remaining)
        UI.success(f"{name} quitado de la whitelist.")
        return True

    def op(self, name: str, level: int = 4) -> bool:
        profile = self.profile(name)
        if profile is None:
            return False
        uuid, resolved = profile
        entries = [entry for entry in read_json_list(self.ops) if entry.get("uuid") != uuid]
        entry: JSONObject = {
            "uuid": uuid,
            "name": resolved,
            "level": level,
            "bypassesPlayerLimit": False,
        }
        entries.append(entry)
        write_json_list(self.ops, entries)
        UI.success(f"{resolved} ahora es operador (nivel {level}).")
        return True

    def deop(self, name: str) -> bool:
        entries = read_json_list(self.ops)
        remaining = [entry for entry in entries if not self.matches(entry, name)]
        if len(remaining) == len(entries):
            UI.error(f"{name} no es operador.")
            return False
        write_json_list(self.ops, remaining)
        UI.success(f"{name} ya no es operador.")
        return True

    def ban(self, name: str, reason: str = "Baneado con MEXUS") -> bool:
        profile = self.profile(name)
        if profile is None:
            return False
        uuid, resolved = profile
        entries = [
            entry for entry in read_json_list(self.banned) if entry.get("uuid") != uuid
        ]
        entry: JSONObject = {
            "uuid": uuid,
            "name": resolved,
            "created": f"{datetime.now():%Y-%m-%d %H:%M:%S %z}",
            "source": APP_NAME,
            "expires": "forever",
            "reason": reason,
        }
        entries.append(entry)
        write_json_list(self.banned, entries)
        UI.success(f"{resolved} baneado. Usa /kick en la consola para expulsarlo.")
        return True

    def unban(self, name: str) -> bool:
        entries = read_json_list(self.banned)
        remaining = [entry for entry in entries if not self.matches(entry, name)]
        if len(remaining) == len(entries):
            UI.error(f"{name} no estaba baneado.")
            return False
        write_json_list(self.banned, remaining)
        UI.success(f"{name} desbaneado.")
        return True


def players_command(
    manager: ServerManager,
    action: str,
    name: str = "",
    level: int = 4,
    reason: str = "",
) -> bool:
    if manager.is_proxy:
        UI.warning(
            "Los proxies gestionan permisos con su propio sistema; MEXUS no edita esos archivos."
        )
        return False

    store = PlayerStore(manager)
    if action == "list":
        store.show()
        return True
    if not name:
        UI.error("Indica el nombre del jugador.")
        return False
    if action == "add":
        return store.add_whitelist(name)
    if action == "remove":
        return store.remove_whitelist(name)
    if action == "op":
        return store.op(name, level)
    if action == "deop":
        return store.deop(name)
    if action == "ban":
        return store.ban(name, reason or "Baneado con MEXUS")
    if action == "unban":
        return store.unban(name)

    UI.error(f"Accion de jugadores no soportada: {action}")
    return False


def java_description(java_path: str) -> str:
    if shutil.which(java_path) is None and not Path(java_path).exists():
        return "no encontrado"
    try:
        completed = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "error al ejecutar"
    lines = (completed.stderr or completed.stdout).splitlines()
    return lines[0] if lines else "instalado"


def show_info(manager: ServerManager) -> None:
    config = manager.config
    root = manager.root if manager.root.exists() else Path.cwd()
    disk = shutil.disk_usage(root)
    backups = manager.all_backups()
    logs = log_files(manager.root)
    server_type = manager.server_type
    content = manager.content_path
    jars = len([path for path in content.glob("*.jar")]) if content.exists() else 0

    UI.title("Informacion del entorno")
    UI.fields(
        [
            ("Sistema", f"{platform.system()} {platform.release()} ({platform.machine()})"),
            ("Python", platform.python_version()),
            ("CPUs", str(os.cpu_count() or 0)),
            ("Disco libre", f"{format_size(disk.free)} de {format_size(disk.total)}"),
            ("Carpeta", str(manager.root)),
            ("Java", java_description(config.get_str("java_path", "java"))),
            (
                "Servidor",
                f"{server_type} {config.get_str('version') or '-'} "
                f"({SERVER_TYPE_HINTS.get(server_type, 'sin descripcion')})",
            ),
            ("Archivos", "listos" if manager.server_jar.exists() else "no instalados"),
            ("Contenido", f"{content.name}/ con {jars} jars"),
            (
                "Puerto",
                f"{manager.server_port()} "
                f"({'ocupado' if manager.port_in_use() else 'libre'})",
            ),
            (
                "Backups",
                f"{len(backups)} ({format_size(sum(path.stat().st_size for path in backups))})",
            ),
            ("Ultimo log", logs[0].name if logs else "ninguno"),
        ]
    )


def clean_installation(manager: ServerManager, remove_worlds: bool = False) -> bool:
    if remove_worlds:
        UI.warning("Se borraran mundos, logs, backups, plugins y mods de forma definitiva.")
        if not UI.confirm("Confirmas el borrado total?", default=False):
            UI.info("Cancelado.")
            return False
    elif not UI.confirm("Borrar solo los archivos instalados del servidor?", default=False):
        UI.info("Cancelado.")
        return False

    removed = manager.purge(remove_worlds=remove_worlds)
    if removed:
        UI.success("Eliminado: " + ", ".join(removed))
    else:
        UI.info("No habia nada que borrar.")
    return True


def accept_eula(manager: ServerManager) -> bool:
    eula_path = manager.root / "eula.txt"
    UI.info("EULA de Minecraft: https://aka.ms/MinecraftEULA")
    if not UI.confirm("Aceptas la EULA?", default=False):
        UI.warning("EULA no aceptada.")
        return False
    eula_path.write_text("eula=true\n", encoding="utf-8")
    UI.success(f"{eula_path.name} actualizado con eula=true.")
    return True


def pause() -> None:
    input("\nPresiona Enter para continuar...")


def choose_server_type(config: Config) -> None:
    UI.line()
    UI.title("Tipos disponibles")
    for index, server_type in enumerate(SERVER_TYPES, start=1):
        hint = SERVER_TYPE_HINTS.get(server_type, "")
        manual = "" if server_type in INSTALLABLE_TYPES else " (instalacion manual)"
        print(f"  {index:2}. {server_type:<10} {UI.dim(hint + manual)}")
    print("\nRecomendacion para mods + plugins: hybrid -> Mohist 1.20.1")
    UI.line()

    current_type = config.get_str("type", "paper")
    raw_type = input(f"Tipo [{current_type}]: ").strip().lower()
    if raw_type.isdigit():
        selected_index = int(raw_type) - 1
        if 0 <= selected_index < len(SERVER_TYPES):
            server_type = SERVER_TYPES[selected_index]
        else:
            UI.error("Numero invalido.")
            return
    else:
        server_type = raw_type or current_type

    if server_type not in SERVER_TYPES:
        UI.error("Tipo invalido. Usa: " + ", ".join(SERVER_TYPES))
        return

    downloader = ServerDownloader()
    versions: list[str] = []
    try:
        versions = downloader.get_versions(server_type)
    except Exception as exc:
        UI.warning(str(exc))
        UI.info(
            "Puedes escribir la version manualmente, pero para descargar el servidor "
            "necesitaras internet funcionando."
        )

    if versions:
        print("\nVersiones recientes:")
        for index, version in enumerate(versions[:25], start=1):
            print(f"  {index:2}. {version}")
        print("\nPuedes escribir un numero de la lista o una version exacta.")
    else:
        print("\nEscribe una version exacta, por ejemplo 1.21.4, 1.20.1 o 1.19.4.")

    raw_version = input("Version: ").strip()
    if not raw_version:
        UI.error("La version no puede estar vacia.")
        return

    if raw_version.isdigit() and versions:
        selected_index = int(raw_version) - 1
        if not 0 <= selected_index < len(versions):
            UI.error("Numero de version invalido.")
            return
        version = versions[selected_index]
    else:
        version = raw_version

    config.update(
        type=server_type,
        version=version,
        installed_type="",
        installed_version="",
    )
    UI.success(f"Configurado: {server_type} {version}")


def configure_ram(config: Config) -> None:
    UI.line()
    print("Presets:")
    print("  1. 2G - 4G  (servidor pequeno)")
    print("  2. 4G - 8G  (servidor mediano)")
    print("  3. 6G - 12G (mods o varios jugadores)")
    print("  4. 8G - 16G (servidor pesado)")
    print("  5. Personalizado")
    UI.line()
    choice = input("Opcion: ").strip()

    try:
        if choice == "1":
            ram_min, ram_max = "2G", "4G"
        elif choice == "2":
            ram_min, ram_max = "4G", "8G"
        elif choice == "3":
            ram_min, ram_max = "6G", "12G"
        elif choice == "4":
            ram_min, ram_max = "8G", "16G"
        elif choice == "5":
            ram_min = normalize_ram(input("RAM minima (ej. 2G): "))
            ram_max = normalize_ram(input("RAM maxima (ej. 4G): "))
        else:
            UI.error("Opcion invalida.")
            return
    except ValueError as exc:
        UI.error(str(exc))
        return

    config.update(ram_min=ram_min, ram_max=ram_max)
    UI.success(f"RAM configurada: {ram_min} - {ram_max}")


def configure_java(config: Config) -> None:
    current = config.get_str("java_path", "java")
    value = input(f"Ruta de Java [{current}]: ").strip() or current
    config.set("java_path", value)
    UI.success(f"Java configurado: {value}")


def toggle_backup(config: Config) -> None:
    new_value = not config.get_bool("auto_backup", True)
    config.set("auto_backup", new_value)
    UI.success(f"Auto backup: {'activado' if new_value else 'desactivado'}")


def doctor(manager: ServerManager) -> None:
    UI.title("Revision del entorno")
    print(f"Carpeta: {manager.root}")
    print(f"Config: {manager.config.path}")
    manager.check_java()
    UI.success("Dependencias Python externas: ninguna.")
    if manager.config.is_ready():
        UI.success("Configuracion lista.")
    else:
        UI.warning("Configura tipo y version antes de iniciar.")
    if manager.port_in_use():
        UI.warning(f"El puerto {manager.server_port()} esta en uso.")
    else:
        UI.success(f"Puerto {manager.server_port()} libre.")
    if manager.server_jar.exists():
        UI.success(f"Archivos del servidor presentes ({manager.jar_name}).")
    else:
        UI.warning("Todavia no hay archivos del servidor: usa install.")
    backups = manager.all_backups()
    if backups:
        UI.info(f"Backups disponibles: {len(backups)} ({backups[0].name} es el mas reciente).")
    if not manager.is_proxy:
        eula_path = manager.root / "eula.txt"
        if eula_path.exists():
            UI.success("EULA aceptada.")
        else:
            UI.warning("Falta aceptar la EULA: usa eula accept.")


def configure_properties_preset(manager: ServerManager) -> None:
    UI.title("Presets de server.properties")
    names = sorted(PROPERTY_PRESETS)
    for index, name in enumerate(names, start=1):
        values = PROPERTY_PRESETS[name]
        detail = ", ".join(f"{key}={value}" for key, value in values.items())
        print(f"  {index:2}. {name:<9} {UI.dim(detail)}")
    print(f"  {len(names) + 1:2}. Cancelar")

    choice = input("Preset: ").strip()
    if not choice.isdigit():
        UI.error("Opcion invalida.")
        return
    index = int(choice) - 1
    if not 0 <= index < len(names):
        UI.info("Sin cambios.")
        return
    configure_server_properties(manager, preset=names[index], interactive=False)


def backups_menu(manager: ServerManager) -> None:
    config = manager.config
    UI.title("Backups")
    UI.menu_item("1", "Crear backup manual")
    UI.menu_item("2", "Listar backups", f"{len(manager.all_backups())} guardados")
    UI.menu_item("3", "Restaurar backup", "se sobrescriben los archivos actuales")
    UI.menu_item("4", "Limpiar antiguos", f"conserva {config.get_int('backup_keep', 5)}")
    UI.menu_item("5", "Cambiar cuantos conservar")
    choice = input("Opcion: ").strip()

    if choice == "1":
        manager.create_backup(automatic=False)
    elif choice == "2":
        manager.list_backups()
    elif choice == "3":
        manager.list_backups()
        name = input("Nombre o numero del backup (vacio = ultimo): ").strip()
        manager.restore_backup(name)
    elif choice == "4":
        keep = config.get_int("backup_keep", 5)
        if UI.confirm(f"Borrar todos menos los {keep} mas recientes?", default=False):
            manager.clean_backups(keep)
    elif choice == "5":
        value = UI.ask("Backups a conservar", str(config.get_int("backup_keep", 5)))
        config.set("backup_keep", str(max(parse_int(value, 5), 0)))
        UI.success(f"Se conservaran {config.get_int('backup_keep', 5)} backups.")
    else:
        UI.info("Sin cambios.")


def players_menu(manager: ServerManager) -> None:
    if manager.is_proxy:
        UI.warning("Este tipo de servidor no usa whitelist.json ni ops.json.")
        return

    PlayerStore(manager).show()
    print()
    UI.menu_item("1", "Agregar a whitelist")
    UI.menu_item("2", "Quitar de whitelist")
    UI.menu_item("3", "Hacer operador")
    UI.menu_item("4", "Quitar operador")
    UI.menu_item("5", "Banear jugador")
    UI.menu_item("6", "Desbanear jugador")
    actions = {
        "1": "add",
        "2": "remove",
        "3": "op",
        "4": "deop",
        "5": "ban",
        "6": "unban",
    }
    choice = input("Opcion: ").strip()
    action = actions.get(choice)
    if action is None:
        UI.info("Sin cambios.")
        return

    name = input("Nombre del jugador: ").strip()
    players_command(manager, action, name)


def plugins_menu(manager: ServerManager) -> None:
    kind = resolve_content_kind(manager, None)
    UI.title(f"Plugins y mods ({manager.content_path.name}/)")
    UI.menu_item("1", "Buscar en Modrinth", kind)
    UI.menu_item("2", "Instalar por slug o nombre")
    UI.menu_item("3", "Listar instalados")
    UI.menu_item("4", "Borrar un archivo")
    print(f"\nSe usara el tipo '{kind}' con loader {MODRINTH_LOADERS.get(manager.server_type, '-')}.")
    choice = input("Opcion: ").strip()

    if choice == "1":
        query = input("Buscar: ").strip()
        if query:
            plugins_search(manager, query, None, 10)
    elif choice == "2":
        slug = input("Slug exacto (ej. luckperms, fabric-api): ").strip()
        if slug:
            plugins_install(manager, slug)
    elif choice == "3":
        plugins_list(manager)
    elif choice == "4":
        plugins_list(manager)
        name = input("Archivo a borrar: ").strip()
        if name:
            plugins_remove(manager, name)
    else:
        UI.info("Sin cambios.")


def toggle_auto_restart(config: Config) -> None:
    new_value = not config.get_bool("auto_restart", False)
    config.set("auto_restart", new_value)
    UI.success(f"Auto reinicio: {'activado' if new_value else 'desactivado'}")
    if new_value:
        UI.info(f"Maximo de reinicios por caida: {config.get_int('max_restarts', 3)}")


def interactive_menu() -> None:
    manager = ServerManager()
    config = manager.config

    while True:
        config.load()
        UI.clear()
        print(UI.banner())
        print()
        print_status(config, manager)
        print()
        UI.section("Servidor")
        UI.menu_item("1", "Iniciar servidor", "descarga e instala si hace falta")
        UI.menu_item("2", "Instalar o actualizar archivos", "sin iniciar el servidor")
        UI.menu_item("3", "Cambiar tipo/version", "Paper, Purpur, Fabric, Quilt, Forge...")
        UI.menu_item("4", "Configurar RAM", "presets o manual")
        UI.menu_item("5", "Editar server.properties", "MOTD, puerto, modo, whitelist")
        UI.menu_item("6", "Presets de server.properties", "survival, creative, hardcore...")
        UI.menu_item("7", "Jugadores", "whitelist, operadores y baneos")
        print()
        UI.section("Contenido")
        UI.menu_item("8", "Plugins y mods", "buscar e instalar desde Modrinth")
        UI.menu_item("9", "Backups", "crear, listar y restaurar")
        UI.menu_item("10", "Ver ultimas lineas del log")
        print()
        UI.section("Herramientas")
        UI.menu_item("11", "Informacion del entorno", "java, disco, puerto, backups")
        UI.menu_item("12", "Preparar archivos GitHub", "README, .gitignore, start scripts")
        UI.menu_item("13", "Cambiar ruta de Java")
        UI.menu_item("14", "Argumentos JVM extra")
        UI.menu_item("15", "Activar/desactivar auto backup")
        UI.menu_item("16", "Activar/desactivar auto reinicio")
        UI.menu_item("17", "Revisar entorno (doctor)")
        UI.menu_item("18", "Aceptar EULA")
        UI.menu_item("19", "Limpiar instalacion", "borra archivos del servidor")
        print()
        UI.menu_item("0", "Salir")
        print()

        choice = input("Selecciona una opcion: ").strip()
        print()

        if choice == "1":
            manager.start()
            pause()
        elif choice == "2":
            force = UI.confirm("Forzar reinstalacion completa?", default=False)
            manager.install_or_update(force=force)
            pause()
        elif choice == "3":
            choose_server_type(config)
            pause()
        elif choice == "4":
            configure_ram(config)
            pause()
        elif choice == "5":
            configure_server_properties(manager)
            pause()
        elif choice == "6":
            configure_properties_preset(manager)
            pause()
        elif choice == "7":
            players_menu(manager)
            pause()
        elif choice == "8":
            plugins_menu(manager)
            pause()
        elif choice == "9":
            backups_menu(manager)
            pause()
        elif choice == "10":
            lines = UI.ask("Lineas a mostrar", "40")
            manager.tail_logs(parse_int(lines, 40))
            pause()
        elif choice == "11":
            show_info(manager)
            pause()
        elif choice == "12":
            generate_github_files(manager)
            pause()
        elif choice == "13":
            configure_java(config)
            pause()
        elif choice == "14":
            configure_jvm_args(config)
            pause()
        elif choice == "15":
            toggle_backup(config)
            pause()
        elif choice == "16":
            toggle_auto_restart(config)
            pause()
        elif choice == "17":
            doctor(manager)
            pause()
        elif choice == "18":
            accept_eula(manager)
            pause()
        elif choice == "19":
            purge_all = UI.confirm(
                "Borrar tambien mundos, logs y backups?", default=False
            )
            clean_installation(manager, remove_worlds=purge_all)
            pause()
        elif choice == "0":
            UI.success("Hasta luego.")
            break
        else:
            UI.error("Opcion invalida.")
            time.sleep(1)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-d", "--root", default=".", help="Carpeta del servidor (por defecto la actual)."
    )
    common.add_argument(
        "-y", "--yes", action="store_true", help="Responde 'si' a todas las preguntas."
    )
    common.add_argument("--no-color", action="store_true", help="Desactiva los colores.")

    parser = argparse.ArgumentParser(
        prog="mexus.py",
        description=(
            "Descarga, configura, inicia y administra servidores de Minecraft "
            "(Paper, Purpur, Fabric, Quilt, Vanilla, Forge, NeoForge, Velocity, Waterfall)."
        ),
        parents=[common],
    )
    parser.add_argument(
        "--version", action="version", version=f"{APP_NAME} {APP_VERSION}"
    )
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser(
        "start", parents=[common], help="Inicia el servidor configurado."
    )
    start_parser.add_argument(
        "--no-backup", action="store_true", help="No crea backup antes de iniciar."
    )

    install_parser = subparsers.add_parser(
        "install",
        parents=[common],
        help="Descarga o instala los archivos del servidor sin iniciarlo.",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Borra el registro y reinstala todo."
    )

    backup_parser = subparsers.add_parser(
        "backup", parents=[common], help="Crea un backup manual."
    )
    backup_parser.add_argument("--keep", help="Cuantos backups conservar luego.")
    backup_parser.add_argument(
        "--clean", action="store_true", help="Solo aplica la rotacion, sin crear backup."
    )

    backups_parser = subparsers.add_parser(
        "backups", parents=[common], help="Lista, restaura o limpia backups."
    )
    backups_parser.add_argument(
        "action", nargs="?", choices=("list", "restore", "clean"), default="list"
    )
    backups_parser.add_argument(
        "name", nargs="?", default="", help="Nombre, numero de la lista o 'latest'."
    )
    backups_parser.add_argument("--keep", help="Backups a conservar al limpiar.")
    backups_parser.add_argument(
        "--no-safety",
        dest="no_safety",
        action="store_true",
        help="No crea backup de seguridad antes de restaurar.",
    )

    logs_parser = subparsers.add_parser(
        "logs", parents=[common], help="Muestra las ultimas lineas del log del servidor."
    )
    logs_parser.add_argument("-n", "--lines", type=int, default=40)
    logs_parser.add_argument("-f", "--follow", action="store_true")

    subparsers.add_parser(
        "info", parents=[common], help="Muestra informacion del sistema y del servidor."
    )

    eula_parser = subparsers.add_parser(
        "eula", parents=[common], help="Consulta o acepta la EULA de Minecraft."
    )
    eula_parser.add_argument(
        "action", nargs="?", choices=("status", "accept"), default="status"
    )

    subparsers.add_parser(
        "doctor", parents=[common], help="Revisa Java, puerto, archivos y configuracion."
    )
    subparsers.add_parser(
        "github-files",
        parents=[common],
        help="Genera README, .gitignore y scripts para subir el proyecto a GitHub.",
    )
    subparsers.add_parser(
        "menu", parents=[common], help="Abre el menu interactivo (comportamiento por defecto)."
    )

    plugins_parser = subparsers.add_parser(
        "plugins", parents=[common], help="Busca e instala plugins o mods desde Modrinth."
    )
    plugins_parser.add_argument("action", choices=("search", "install", "list", "remove"))
    plugins_parser.add_argument("name", nargs="?", default="")
    plugins_parser.add_argument("--mod", action="store_true", help="Forzar busqueda de mods.")
    plugins_parser.add_argument(
        "--plugin", action="store_true", help="Forzar busqueda de plugins."
    )
    plugins_parser.add_argument("--game-version", dest="game_version")
    plugins_parser.add_argument("--limit", type=int, default=10)

    players_parser = subparsers.add_parser(
        "players", parents=[common], help="Gestiona whitelist, operadores y baneos."
    )
    players_parser.add_argument(
        "action", choices=("list", "add", "remove", "op", "deop", "ban", "unban")
    )
    players_parser.add_argument("name", nargs="?", default="")
    players_parser.add_argument("--level", type=int, default=4)
    players_parser.add_argument("--reason", default="")

    clean_parser = subparsers.add_parser(
        "clean", parents=[common], help="Borra los archivos instalados del servidor."
    )
    clean_parser.add_argument(
        "--all", action="store_true", help="Borra tambien mundos, logs, backups y contenido."
    )

    properties_parser = subparsers.add_parser(
        "properties", parents=[common], help="Crea o edita server.properties."
    )
    properties_parser.add_argument(
        "--set",
        dest="changes",
        action="append",
        default=[],
        metavar="CLAVE=VALOR",
        help="Cambia un valor sin preguntas (se puede repetir).",
    )
    properties_parser.add_argument(
        "--preset", choices=tuple(sorted(PROPERTY_PRESETS)), help="Aplica un preset."
    )

    subparsers.add_parser(
        "presets", parents=[common], help="Lista los presets disponibles de server.properties."
    )

    versions_parser = subparsers.add_parser(
        "versions", parents=[common], help="Muestra versiones disponibles."
    )
    versions_parser.add_argument("--type", choices=SERVER_TYPES, default="paper")
    versions_parser.add_argument("--limit", type=int, default=25)
    versions_parser.add_argument(
        "--all", action="store_true", help="Muestra todas las versiones."
    )

    config_parser = subparsers.add_parser(
        "config", parents=[common], help="Consulta o actualiza la configuracion."
    )
    config_parser.add_argument("--type", choices=SERVER_TYPES)
    config_parser.add_argument("--version", dest="version")
    config_parser.add_argument("--ram-min")
    config_parser.add_argument("--ram-max")
    config_parser.add_argument("--java")
    config_parser.add_argument("--jvm-args", dest="jvm_args")
    config_parser.add_argument("--auto-backup", choices=("on", "off"))
    config_parser.add_argument("--auto-restart", choices=("on", "off"))
    config_parser.add_argument("--max-restarts")
    config_parser.add_argument("--backup-keep")
    config_parser.add_argument("--show", action="store_true", help="Muestra la configuracion.")
    config_parser.add_argument(
        "--reset", action="store_true", help="Vuelve a los valores por defecto."
    )

    return parser


def apply_hosting_env(config: Config) -> None:
    """Honors env vars set by hosts such as Altare (SERVER_MEMORY in MB)."""
    memory = os.environ.get("SERVER_MEMORY", "").strip()
    if memory.isdigit() and int(memory) >= 512:
        config.data["ram_max"] = f"{int(memory)}M"
        config.data["ram_min"] = f"{max(int(memory) // 2, 512)}M"
    config.data["type"] = LOCKED_TYPE
    config.data["version"] = LOCKED_VERSION
    config.save()


def ensure_portable_java(config: Config, root: Path) -> bool:
    """Downloads a portable Java 21 (Temurin) when the host has none installed."""
    current = config.get_str("java_path", "java")
    if current != "java" and Path(current).exists():
        return True
    if shutil.which(current or "java"):
        return True
    local = Path(root) / ".mexus_java"
    existing = next(local.glob("*/bin/java"), None)
    if existing is not None:
        config.set("java_path", str(existing.resolve()))
        return True
    if platform.system() != "Linux":
        return True  # let the normal Java check explain what to install
    arch = "aarch64" if platform.machine().lower() in {"aarch64", "arm64"} else "x64"
    url = (
        "https://api.adoptium.net/v3/binary/latest/21/ga/linux/"
        f"{arch}/jre/hotspot/normal/eclipse"
    )
    UI.info("Java no encontrado. Descargando Java 21 portable (Temurin)...")
    local.mkdir(parents=True, exist_ok=True)
    archive = local / "jre.tar.gz"
    try:
        HttpClient().download(url, archive, show_progress=False)
        with tarfile.open(archive) as tar:
            tar.extractall(local, filter="data")
    except (RuntimeError, tarfile.TarError, OSError) as exc:
        UI.error(f"No se pudo descargar Java 21: {exc}")
        return False
    finally:
        archive.unlink(missing_ok=True)
    found = next(local.glob("*/bin/java"), None)
    if found is None:
        UI.error("Java descargado pero no se encontro el ejecutable.")
        return False
    config.set("java_path", str(found.resolve()))
    UI.success(f"Java 21 listo en {found.parent.parent.name}.")
    return True


def run_cli(args: argparse.Namespace) -> int:
    root = cast(str | None, getattr(args, "root", None)) or "."
    manager = ServerManager(root)
    config = manager.config
    apply_hosting_env(config)
    if getattr(args, "command", None) in {"install", "start"}:
        if not ensure_portable_java(config, manager.root):
            return 1
    command = cast(str | None, getattr(args, "command", None))

    if command == "start":
        if bool(getattr(args, "no_backup", False)):
            config.set("auto_backup", False)
        return 0 if manager.start() else 1

    if command == "install":
        force = bool(getattr(args, "force", False))
        return 0 if manager.install_or_update(force=force) else 1

    if command == "backup":
        keep_arg = getattr(args, "keep", None)
        if keep_arg is not None:
            config.set("backup_keep", str(max(parse_int(str(keep_arg), 5), 0)))
        if bool(getattr(args, "clean", False)):
            manager.clean_backups(config.get_int("backup_keep", 5))
            return 0
        return 0 if manager.create_backup(automatic=False) else 1

    if command == "backups":
        action = cast(str, getattr(args, "action", "list") or "list")
        if action == "list":
            manager.list_backups()
            return 0
        if action == "restore":
            name = cast(str, getattr(args, "name", "") or "") or "latest"
            restored = manager.restore_backup(
                name, safety_backup=not bool(getattr(args, "no_safety", False))
            )
            return 0 if restored else 1
        keep_arg = getattr(args, "keep", None)
        keep = (
            config.get_int("backup_keep", 5)
            if keep_arg is None
            else max(parse_int(str(keep_arg), 5), 0)
        )
        manager.clean_backups(keep)
        return 0

    if command == "logs":
        manager.tail_logs(
            int(getattr(args, "lines", 40) or 40), bool(getattr(args, "follow", False))
        )
        return 0

    if command == "info":
        show_info(manager)
        return 0

    if command == "eula":
        action = cast(str, getattr(args, "action", "status") or "status")
        eula_path = manager.root / "eula.txt"
        accepted = eula_path.exists() and "eula=true" in eula_path.read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
        if action == "accept":
            return 0 if accept_eula(manager) else 1
        if accepted:
            UI.success(f"EULA aceptada ({eula_path.name}).")
            return 0
        UI.warning("EULA no aceptada todavia. Usa: mexus.py eula accept")
        return 1

    if command == "doctor":
        doctor(manager)
        return 0

    if command == "github-files":
        generate_github_files(manager)
        return 0

    if command == "properties":
        changes = cast(list[str], getattr(args, "changes", []) or [])
        preset = cast(str | None, getattr(args, "preset", None))
        interactive = not changes and preset is None
        updated = configure_server_properties(manager, preset, changes, interactive)
        return 0 if updated else 1

    if command == "presets":
        for name in sorted(PROPERTY_PRESETS):
            detail = ", ".join(
                f"{key}={value}" for key, value in PROPERTY_PRESETS[name].items()
            )
            print(f"{name}: {detail}")
        return 0

    if command == "plugins":
        action = cast(str, getattr(args, "action", ""))
        name = cast(str, getattr(args, "name", "") or "")
        kind: str | None = None
        if bool(getattr(args, "mod", False)):
            kind = "mod"
        elif bool(getattr(args, "plugin", False)):
            kind = "plugin"

        if action == "search":
            if not name:
                UI.error("Indica que buscar: mexus.py plugins search <texto>")
                return 1
            plugins_search(manager, name, kind, int(getattr(args, "limit", 10) or 10))
            return 0
        if action == "install":
            if not name:
                UI.error("Indica el slug: mexus.py plugins install <slug>")
                return 1
            game_version = cast(str | None, getattr(args, "game_version", None))
            return 0 if plugins_install(manager, name, kind, game_version) else 1
        if action == "list":
            plugins_list(manager)
            return 0
        if action == "remove":
            if not name:
                UI.error("Indica el archivo: mexus.py plugins remove <archivo>")
                return 1
            return 0 if plugins_remove(manager, name) else 1
        UI.error(f"Accion no soportada: {action}")
        return 1

    if command == "versions":
        downloader = ServerDownloader()
        server_type = cast(str, getattr(args, "type", "paper"))
        limit = int(getattr(args, "limit", 25) or 25)
        versions = downloader.get_versions(server_type)
        shown = versions if bool(getattr(args, "all", False)) else versions[: max(limit, 1)]
        for version in shown:
            print(version)
        return 0

    if command == "players":
        action = cast(str, getattr(args, "action", "list"))
        name = cast(str, getattr(args, "name", "") or "")
        level = int(getattr(args, "level", 4) or 4)
        reason = cast(str, getattr(args, "reason", "") or "")
        return 0 if players_command(manager, action, name, level, reason) else 1

    if command == "clean":
        remove_worlds = bool(getattr(args, "all", False))
        return 0 if clean_installation(manager, remove_worlds=remove_worlds) else 1

    if command == "config":
        if bool(getattr(args, "reset", False)):
            config.reset()
            UI.success("Configuracion restablecida.")
            print_status(config, manager)
            return 0

        updates: ConfigData = {}
        server_type = cast(str | None, getattr(args, "type", None))
        version = cast(str | None, getattr(args, "version", None))
        ram_min = cast(str | None, getattr(args, "ram_min", None))
        ram_max = cast(str | None, getattr(args, "ram_max", None))
        java_path = cast(str | None, getattr(args, "java", None))
        jvm_args = cast(str | None, getattr(args, "jvm_args", None))
        auto_backup = cast(str | None, getattr(args, "auto_backup", None))
        auto_restart = cast(str | None, getattr(args, "auto_restart", None))
        max_restarts = cast(str | None, getattr(args, "max_restarts", None))
        backup_keep = cast(str | None, getattr(args, "backup_keep", None))

        if server_type:
            updates["type"] = server_type
            updates["installed_type"] = ""
            updates["installed_version"] = ""
        if version:
            updates["version"] = version
            updates["installed_type"] = ""
            updates["installed_version"] = ""
        if ram_min:
            updates["ram_min"] = normalize_ram(ram_min)
        if ram_max:
            updates["ram_max"] = normalize_ram(ram_max)
        if java_path:
            updates["java_path"] = java_path
        if jvm_args is not None:
            updates["jvm_args"] = jvm_args
        if auto_backup:
            updates["auto_backup"] = auto_backup == "on"
        if auto_restart:
            updates["auto_restart"] = auto_restart == "on"
        if max_restarts is not None:
            updates["max_restarts"] = str(max(parse_int(max_restarts, 3), 0))
        if backup_keep is not None:
            updates["backup_keep"] = str(max(parse_int(backup_keep, 5), 0))

        if not updates:
            print_status(config, manager)
            return 0

        config.update(**updates)
        UI.success("Configuracion actualizada.")
        print_status(config, manager)
        return 0

    interactive_menu()
    return 0


def main(argv: list[str] | None = None) -> int:
    global ASSUME_YES

    parser = build_parser()
    args = parser.parse_args(argv)

    ASSUME_YES = bool(getattr(args, "yes", False))
    if bool(getattr(args, "no_color", False)):
        UI.COLOR_ENABLED = False

    try:
        return run_cli(args)
    except KeyboardInterrupt:
        UI.warning("Operacion cancelada.")
        return 130
    except Exception as exc:
        UI.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
