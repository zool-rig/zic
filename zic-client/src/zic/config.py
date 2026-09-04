import os
import toml
import json
import logging

from dataclasses import dataclass
from appdirs import user_data_dir, user_config_dir
from pathlib import Path


LOGGER = logging.getLogger("ZIC - Config")
APP_CONFIG_PATH = Path(user_config_dir("Zic")) / "app_config.toml"
USER_CONFIG_PATH = Path(user_data_dir("Zic")) / "user_config.json"


class ConfigNotFoundError(BaseException):
    pass


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


@dataclass
class UserConfig:
    artists_descending_order: bool = False
    genres_descending_order: bool = False
    volume: int = 50
    muted: bool = False

    @classmethod
    def default(cls) -> "UserConfig":
        return cls()

    @classmethod
    def load(cls) -> "UserConfig":
        if not USER_CONFIG_PATH.exists():
            config = cls.default()
            LOGGER.debug(f"User config path not found : {USER_CONFIG_PATH}, fallback to default")
            return config
        
        with USER_CONFIG_PATH.open("r") as f:
            config = cls(**json.load(f))
        LOGGER.debug(f"User config loaded : {USER_CONFIG_PATH}")
        return config

    def save(self) -> None:
        if not USER_CONFIG_PATH.parent.exists():
            os.makedirs(USER_CONFIG_PATH.parent)
        with USER_CONFIG_PATH.open("w") as f:
            json.dump(self.__dict__, f, indent=4)


APP_CONFIG: AppConfig | None = None
USER_CONFIG: UserConfig | None = None


def get_app_config() -> AppConfig:
    global APP_CONFIG
    if APP_CONFIG is None:
        APP_CONFIG = AppConfig.load()
    return APP_CONFIG


def get_user_config() -> UserConfig:
    global USER_CONFIG
    if USER_CONFIG is None:
        USER_CONFIG = UserConfig.load()
    return USER_CONFIG
