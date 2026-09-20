from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QWidget

from zic.utils.qt_utils import SignalsOFF, make_toolbutton


class PathSelector(QWidget):
    path_changed = Signal(Path)

    def __init__(
        self,
        browse_method: Callable = QFileDialog.getExistingDirectory,
        **browse_params,
    ) -> None:
        super().__init__()
        self.browse_method: Callable = browse_method
        self.browse_params: dict[str, Any] = browse_params

        # Layouts
        self.main_h_layout = None

        # Widgets
        self.path_edt = None
        self.browse_btn = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_h_layout = QHBoxLayout(self)

    def init_widgets(self) -> None:
        self.path_edt = QLineEdit()
        self.browse_btn = make_toolbutton(
            "icons/artist.png", tooltip="Browse"
        )  # TODO change icon

    def set_layout(self) -> None:
        self.main_h_layout.addWidget(self.path_edt)
        self.main_h_layout.addWidget(self.browse_btn)

    def set_connections(self) -> None:
        self.path_edt.textChanged.connect(self.check_path)
        self.browse_btn.clicked.connect(self.browse)

    def set_default(self) -> None:
        self.main_h_layout.setAlignment(Qt.AlignLeft)

    @property
    def path(self) -> Path:
        return Path(self.path_edt.text())

    @path.setter
    def path(self, path: str | Path) -> None:
        with SignalsOFF(self.path_edt):
            self.path_edt.setText(str(path))

    def is_valid_path(self) -> None:
        return bool(self.path_edt.text()) and self.path.exists()

    def check_path(self) -> None:
        self.setProperty("valid", self.is_valid_path())
        self.path_changed.emit(self.path)

    def browse(self) -> None:
        input_path = self.browse_method(**self.browse_params)
        if type(input_path) is tuple:
            input_path = input_path[0]

        if not input_path:
            return

        self.path_edt.setText(input_path)
