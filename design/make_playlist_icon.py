"""Draws the playlists icon: a list with a music note, the same size and color
as the other icons of the app.

    uv run python design/make_playlist_icon.py
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

SIZE = 512
COLOR = QColor("#E6E9EE")
LINE_WIDTH = 44
OUTPUT = Path(__file__).parents[1] / "src" / "zic" / "resources" / "icons"


def draw_playlist_icon() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # The list: shorter and shorter lines, leaving room for the note.
    painter.setPen(QPen(COLOR, LINE_WIDTH, Qt.SolidLine, Qt.RoundCap))
    for y, end in ((96, 456), (196, 296), (296, 216)):
        painter.drawLine(QPointF(60, y), QPointF(end, y))

    # The note: its stem, its flag, then its tilted head.
    painter.setPen(Qt.NoPen)
    painter.setBrush(COLOR)
    painter.drawRect(QRectF(366, 176, 40, 214))
    painter.drawRoundedRect(QRectF(366, 176, 104, 52), 20, 20)
    painter.save()
    painter.translate(336, 404)
    painter.rotate(-22)
    painter.drawEllipse(QPointF(0, 0), 78, 58)
    painter.restore()

    painter.end()
    return image


if __name__ == "__main__":
    path = OUTPUT / "playlist.png"
    if not draw_playlist_icon().save(str(path)):
        raise SystemExit(f"Could not save {path}")
    print(f"Saved {path}")
