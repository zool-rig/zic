import os
import toml
import json

from pydantic import BaseModel
from pydantic import BaseModel
from appdirs import user_data_dir, user_config_dir
from pathlib import Path


APP_CONFIG_PATH = Path(user_config_dir("Zic")) / "app_config.toml"
print(f"APP CONFIG PATH: {APP_CONFIG_PATH}")
USER_CONFIG_PATH = Path(user_data_dir("Zic")) / "user_config.json"
print(f"USER CONFIG PATH: {USER_CONFIG_PATH}")


class ConfigNotFoundError(BaseException):
    pass


class AppConfig(BaseModel):
    db_path: Path
    root_dir: Path

    @classmethod
    def load(cls) -> "AppConfig":
        if not APP_CONFIG_PATH.exists():
            raise ConfigNotFoundError(f"App config file not found : {APP_CONFIG_PATH}")
        with APP_CONFIG_PATH.open("r") as f:
            return cls(**toml.load(f))


class UserConfig(BaseModel):
    pass

    @classmethod
    def default(cls) -> "UserConfig":
        return cls()

    @classmethod
    def load(cls) -> "UserConfig":
        if not USER_CONFIG_PATH.exists():
            return cls.default()
        with USER_CONFIG_PATH.open("r") as f:
            return cls(**json.load(f))

    def save(self) -> None:
        if not USER_CONFIG_PATH.parent.exists():
            os.makedirs(USER_CONFIG_PATH.parent)
        with USER_CONFIG_PATH.open("w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=4)


APP_CONFIG = AppConfig.load()
USER_CONFIG = UserConfig.load()
