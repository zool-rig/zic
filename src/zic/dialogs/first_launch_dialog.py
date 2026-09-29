from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from zic.config import AppConfig
from zic.resources import get_resource
from zic.utils.db_utils import is_valid_sqlite_file
from zic.utils.qt_utils import set_label_font_size
from zic.widgets.path_selector import PathSelector
from zic.widgets.rules import HRule


class FirstLaunchDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()

        # Layouts
        self.main_v_layout = None
        self.form_layout = None
        self.bottom_h_layout = None

        # Widgets
        self.welcome_lbl = None
        self.instruction_lbl = None
        self.root_dir_path_selector = None
        self.db_path_selector = None
        self.error_message_lbl = None
        self.ok_btn = None
        self.cancel_btn = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()
        self.set_style_sheet()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        self.bottom_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.welcome_lbl = QLabel("Welcome to ZIC !")
        self.instruction_lbl = QLabel(
            "Before you start, please provide the locations of your music library and your database."
        )
        self.root_dir_path_selector = PathSelector()
        self.db_path_selector = PathSelector(browse_method=QFileDialog.getOpenFileName)
        self.error_message_lbl = QLabel()
        self.ok_btn = QPushButton("Ok")
        self.cancel_btn = QPushButton("Cancel")

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.welcome_lbl)
        self.main_v_layout.addWidget(self.instruction_lbl)
        self.main_v_layout.addLayout(self.form_layout)
        self.form_layout.addRow("Library root directory :", self.root_dir_path_selector)
        self.form_layout.addRow("Database location :", self.db_path_selector)
        self.main_v_layout.addWidget(self.error_message_lbl)
        self.main_v_layout.addWidget(HRule())
        self.main_v_layout.addLayout(self.bottom_h_layout)
        self.bottom_h_layout.addWidget(self.ok_btn)
        self.bottom_h_layout.addWidget(self.cancel_btn)

    def set_connections(self) -> None:
        self.ok_btn.clicked.connect(self.validate_inputs)
        self.cancel_btn.clicked.connect(self.reject)
        self.root_dir_path_selector.path_changed.connect(self.on_root_dir_changed)
        self.db_path_selector.path_changed.connect(self.check_inputs)

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignTop)
        self.welcome_lbl.setAlignment(Qt.AlignCenter)
        set_label_font_size(self.welcome_lbl, 12)
        self.instruction_lbl.setAlignment(Qt.AlignCenter)
        self.bottom_h_layout.setAlignment(Qt.AlignRight)
        self.ok_btn.setEnabled(False)
        self.error_message_lbl.hide()

    def set_style_sheet(self) -> None:
        qss_path = get_resource("style/style.qss")
        icons_path = get_resource("icons")
        with open(qss_path, "r") as f:
            stylesheet = f.read()
        # Replace placeholder with actual icon path
        stylesheet = stylesheet.replace("{ICON_PATH}", icons_path)
        self.setStyleSheet(stylesheet)
        self.error_message_lbl.setStyleSheet("color: red;")

    def on_root_dir_changed(self, path: Path) -> None:
        if path.exists():
            potential_db_path = path / ".db"
            if not self.db_path_selector.is_valid_path() and potential_db_path.exists():
                self.db_path_selector.path = potential_db_path
        self.check_inputs()

    def check_inputs(self) -> None:
        if not self.root_dir_path_selector.is_valid_path():
            self.error_message_lbl.setText("Root directory is not valid")
            self.error_message_lbl.show()
            self.ok_btn.setEnabled(False)
            return False
        if not self.db_path_selector.is_valid_path():
            self.error_message_lbl.setText("Database file path is not valid")
            self.error_message_lbl.show()
            self.ok_btn.setEnabled(False)
            return False
        if not is_valid_sqlite_file(self.db_path_selector):
            self.error_message_lbl.setText(
                "Database may be corrupted or not a valid ZIC's database"
            )
            self.error_message_lbl.show()
            self.ok_btn.setEnabled(False)
            return False
        self.error_message_lbl.hide()
        self.ok_btn.setEnabled(True)
        return True

    def validate_inputs(self) -> None:
        config = AppConfig(
            db_path=self.db_path_selector.path,
            root_dir=self.root_dir_path_selector.path,
        )
        config.dump()
        self.accept()
