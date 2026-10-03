import json
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import toml
from appdirs import user_config_dir, user_data_dir
from PySide6.QtCore import Qt

from zic.logging import get_logger

LOGGER = get_logger("Config")
APP_CONFIG_PATH = Path(user_config_dir("Zic")) / "app_config.toml"
USER_CONFIG_PATH = Path(user_data_dir("Zic")) / "user_config.json"

_APP_CONFIG_LOCK = threading.RLock()
_USER_CONFIG_LOCK = threading.RLock()


class ConfigNotFoundError(Exception):
    pass


class ConfigEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        else:
            return super().default(obj)


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    root_dir: Path

    @classmethod
    def load(cls) -> "AppConfig":
        if not APP_CONFIG_PATH.exists():
            raise ConfigNotFoundError(f"App config file not found : {APP_CONFIG_PATH}.")
        with APP_CONFIG_PATH.open("r") as f:
            data = toml.load(f)
        data["db_path"] = Path(data["db_path"])
        data["root_dir"] = Path(data["root_dir"])
        config = cls(
            data["db_path"],
            data["root_dir"],
        )
        LOGGER.debug(f"App config loaded  : {APP_CONFIG_PATH}")
        return config

    def serialize(self) -> dict[str, str]:
        return {
            "db_path": str(self.db_path),
            "root_dir": str(self.root_dir),
        }

    def dump(self) -> None:
        os.makedirs(APP_CONFIG_PATH.parent, exist_ok=True)
        with APP_CONFIG_PATH.open("w") as f:
            toml.dump(self.serialize(), f)
        LOGGER.debug(f"App config saved  : {APP_CONFIG_PATH}")


def default_key_bindings() -> dict[str, int]:
    return {
        "play/pause": int(Qt.Key_Space),
        "mute": int(Qt.Key_M),
        "next-song": int(Qt.Key_N),
        "previous-song": int(Qt.Key_P),
        "reload": int(Qt.Key_F5),
        "shuffle": int(Qt.Key_S),
        "advance": int(Qt.Key_Right),
        "rewind": int(Qt.Key_Left),
        "volume_up": int(Qt.Key_Plus),
        "volume_down": int(Qt.Key_Minus),
        "like": int(Qt.Key_L),
        "dislike": int(Qt.Key_D),
    }


@dataclass
class UserConfig:
    artists_descending_order: bool = False
    genres_descending_order: bool = False
    volume: int = 50
    muted: bool = False
    explorer_sort_order: int = 1
    explorer_sorting_mode: int = 1
    key_bindings: dict[str, int] = field(default_factory=default_key_bindings)
    # Whether metadata edits are also written to the audio files' tags.
    write_file_tags: bool = True

    @classmethod
    def default(cls) -> "UserConfig":
        return cls()

    @classmethod
    def load(cls) -> "UserConfig":
        if not USER_CONFIG_PATH.exists():
            config = cls.default()
            LOGGER.debug(
                f"User config path not found : {USER_CONFIG_PATH}, fallback to default"
            )
            return config

        with USER_CONFIG_PATH.open("r") as f:
            data = json.load(f)
            config = cls(
                data["artists_descending_order"],
                data["genres_descending_order"],
                data["volume"],
                data["muted"],
                data["explorer_sort_order"],
                data["explorer_sorting_mode"],
                # Merge so actions added since the config was saved still
                # get their default key.
                {**default_key_bindings(), **data["key_bindings"]},
                data.get("write_file_tags", True),
            )
        LOGGER.debug(f"User config loaded : {USER_CONFIG_PATH}")
        return config

    def save(self) -> None:
        if not USER_CONFIG_PATH.parent.exists():
            os.makedirs(USER_CONFIG_PATH.parent)
        with USER_CONFIG_PATH.open("w") as f:
            json.dump(self.__dict__, f, indent=4, cls=ConfigEncoder)
        LOGGER.debug(f"user config loaded  : {USER_CONFIG_PATH}")


APP_CONFIG: AppConfig | None = None
USER_CONFIG: UserConfig | None = None


def get_app_config() -> AppConfig:
    global APP_CONFIG
    if APP_CONFIG is None:
        with _APP_CONFIG_LOCK:
            if APP_CONFIG is None:
                LOGGER.debug(f"App config path : {APP_CONFIG_PATH}")
                APP_CONFIG = AppConfig.load()

    return APP_CONFIG


def get_user_config() -> UserConfig:
    global USER_CONFIG
    if USER_CONFIG is None:
        with _USER_CONFIG_LOCK:
            if USER_CONFIG is None:
                LOGGER.debug(f"User config path : {USER_CONFIG_PATH}")
                USER_CONFIG = UserConfig.load()

    return USER_CONFIG


def app_config_exists() -> bool:
    return APP_CONFIG_PATH.exists()
