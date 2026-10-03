from PySide6.QtCore import QModelIndex, QStringListModel, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from zic.api import ZicApi
from zic.utils.qt_utils import WaitCursor, style_completer_popup
from zic.utils.tags import TagWriteError
from zic.widgets.rules import HRule


class MultiValueCompleter(QCompleter):
    """Completes the last value of a comma-separated list."""

    def splitPath(self, path: str) -> list[str]:
        return [path.split(",")[-1].strip()]

    def pathFromIndex(self, index: QModelIndex) -> str:
        values = [v.strip() for v in self.widget().text().split(",")[:-1]]
        return ", ".join([*values, index.data()]) + ", "


def make_completer(
    values: list[str], widget: QLineEdit, multi_value: bool = False
) -> QCompleter:
    completer_type = MultiValueCompleter if multi_value else QCompleter
    completer = completer_type(QStringListModel(sorted(set(values))), widget)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    style_completer_popup(completer)
    widget.setCompleter(completer)
    return completer


def make_optional_spinbox(maximum: int, value: int | None) -> QSpinBox:
    """A spin box where 0 stands for "no value"."""
    spinbox = QSpinBox()
    spinbox.setButtonSymbols(QAbstractSpinBox.NoButtons)  # keyboard/wheel
    spinbox.setRange(0, maximum)
    spinbox.setSpecialValueText("—")
    spinbox.setValue(value or 0)
    return spinbox


def optional_value(spinbox: QSpinBox) -> int | None:
    return spinbox.value() or None


VALUE_MAX_WIDTH = 380


def make_value_label(text: str) -> QLabel:
    """A selectable read-only value. Long values (paths) are elided in the
    middle, the full text being in the tooltip."""
    label = QLabel()
    elided = QFontMetrics(label.font()).elidedText(
        text, Qt.ElideMiddle, VALUE_MAX_WIDTH
    )
    label.setText(elided)
    if elided != text:
        label.setToolTip(text)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class MetadataDialog(QDialog):
    """Base of the song/album info dialogs: an editable "Metadata" form, a
    read-only "Details" form, and Save/Cancel. Subclasses fill the forms
    and implement save()."""

    def __init__(self, api: ZicApi, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.api: ZicApi = api
        self.title: str = title
        # True once something was written, even if the dialog is cancelled
        # afterwards (e.g. a song shown again from the album dialog).
        self.changed: bool = False

        # Layouts
        self.main_v_layout = None
        self.metadata_form = None
        self.details_form = None

        # Widgets
        self.title_lbl = None
        self.note_lbl = None
        self.error_lbl = None
        self.button_box = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.metadata_form = QFormLayout()
        self.details_form = QFormLayout()

    def init_widgets(self) -> None:
        self.title_lbl = QLabel(self.title)
        self.note_lbl = QLabel()
        self.error_lbl = QLabel()
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addWidget(self.section_label("Metadata"))
        self.main_v_layout.addLayout(self.metadata_form)
        self.main_v_layout.addWidget(self.note_lbl)
        self.main_v_layout.addWidget(self.section_label("Details"))
        self.main_v_layout.addLayout(self.details_form)
        self.main_v_layout.addStretch()
        self.main_v_layout.addWidget(self.error_lbl)
        self.main_v_layout.addWidget(HRule())
        self.main_v_layout.addWidget(self.button_box)

    def set_connections(self) -> None:
        self.button_box.accepted.connect(self.on_save_clicked)
        self.button_box.rejected.connect(self.reject)

    def set_default(self) -> None:
        self.setWindowTitle(self.title)
        self.setMinimumWidth(520)
        self.title_lbl.setObjectName("DialogTitleLabel")
        self.title_lbl.setWordWrap(True)
        self.note_lbl.setObjectName("DialogNoteLabel")
        self.note_lbl.setWordWrap(True)
        self.note_lbl.hide()
        self.error_lbl.setObjectName("DialogErrorLabel")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.hide()
        for form in (self.metadata_form, self.details_form):
            form.setLabelAlignment(Qt.AlignRight)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    @staticmethod
    def section_label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("DialogSectionLabel")
        return label

    def add_detail(self, label: str, value: str | QWidget) -> None:
        if isinstance(value, str):
            value = make_value_label(value)
        self.details_form.addRow(f"{label} :", value)

    def set_note(self, text: str) -> None:
        self.note_lbl.setText(text)
        self.note_lbl.setVisible(bool(text))

    def show_error(self, message: str) -> None:
        self.error_lbl.setText(message)
        self.error_lbl.setVisible(bool(message))

    def on_save_clicked(self) -> None:
        self.show_error("")
        try:
            with WaitCursor():
                saved = self.save()
        except (TagWriteError, ValueError) as e:
            self.show_error(str(e))
            return
        if saved:
            self.accept()

    def save(self) -> bool:
        """Writes the edits; returns False to keep the dialog open."""
        raise NotImplementedError
