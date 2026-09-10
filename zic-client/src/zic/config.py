import os
import toml
import json
import logging

from dataclasses import dataclass, field
from appdirs import user_data_dir, user_config_dir
from pathlib import Path
from enum import Enum
from PySide6.QtCore import Qt


LOGGER = logging.getLogger("ZIC - Config")
APP_CONFIG_PATH = Path(user_config_dir("Zic")) / "app_config.toml"
USER_CONFIG_PATH = Path(user_data_dir("Zic")) / "user_config.json"


class ConfigNotFoundError(BaseException):
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
            config = cls(**toml.load(f))
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
            config = cls(**json.load(f))
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
        LOGGER.debug(f"App config path : {APP_CONFIG_PATH}")
        APP_CONFIG = AppConfig.load()
    return APP_CONFIG


def get_user_config() -> UserConfig:
    global USER_CONFIG
    if USER_CONFIG is None:
        LOGGER.debug(f"User config path : {USER_CONFIG_PATH}")
        USER_CONFIG = UserConfig.load()
    return USER_CONFIG


def app_config_exists() -> bool:
    return APP_CONFIG_PATH.exists()
