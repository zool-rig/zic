import threading
from pathlib import Path

import pytest

from zic.config import (
    AppConfig,
    ConfigNotFoundError,
    UserConfig,
    app_config_exists,
    get_app_config,
    get_user_config,
)


def test_app_config_round_trip(tmp_path, app_paths):
    app_config_path, _ = app_paths
    original = AppConfig(db_path=tmp_path / "library.db", root_dir=tmp_path / "music")
    original.dump()

    assert app_config_path.exists()
    loaded = AppConfig.load()

    assert loaded == original
    assert isinstance(loaded.db_path, Path)
    assert isinstance(loaded.root_dir, Path)


def test_app_config_load_missing_raises(app_paths):
    with pytest.raises(ConfigNotFoundError):
        AppConfig.load()


def test_app_config_exists_reflects_file_presence(tmp_path, app_paths):
    assert app_config_exists() is False
    AppConfig(db_path=tmp_path / "a.db", root_dir=tmp_path).dump()
    assert app_config_exists() is True


def test_get_app_config_is_cached(tmp_path, app_paths):
    app_config_path, _ = app_paths
    AppConfig(db_path=tmp_path / "a.db", root_dir=tmp_path).dump()

    first = get_app_config()
    # Mutate the file on disk directly; the cached singleton must not change.
    app_config_path.write_text(f'db_path = "{tmp_path / "b.db"}"\nroot_dir = "{tmp_path}"\n')
    second = get_app_config()

    assert first is second
    assert first.db_path == tmp_path / "a.db"


def test_get_app_config_thread_safe_single_load(tmp_path, app_paths, monkeypatch):
    """Regression test for the double-checked locking fix: concurrent
    first-time access should only hit disk once."""
    AppConfig(db_path=tmp_path / "a.db", root_dir=tmp_path).dump()

    load_calls = []
    original_load = AppConfig.load  # bound classmethod, cls already applied

    def counting_load():
        load_calls.append(1)
        return original_load()

    monkeypatch.setattr(AppConfig, "load", staticmethod(counting_load))

    results = []

    def worker():
        results.append(get_app_config())

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(load_calls) == 1
    assert all(r is results[0] for r in results)


def test_user_config_defaults_when_missing(app_paths):
    assert UserConfig.load() == UserConfig.default()


def test_user_config_save_and_load_round_trip(app_paths):
    config = UserConfig.load()
    config.volume = 77
    config.muted = True
    config.key_bindings["shuffle"] = 999
    config.save()

    reloaded = UserConfig.load()
    assert reloaded.volume == 77
    assert reloaded.muted is True
    assert reloaded.key_bindings["shuffle"] == 999


def test_get_user_config_is_cached(app_paths):
    first = get_user_config()
    first.volume = 12
    second = get_user_config()
    assert second is first
    assert second.volume == 12
