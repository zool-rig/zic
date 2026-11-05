import io

from PIL import Image, ImageOps

MOSAIC_SIZE = 200
MOSAIC_TILES = 4


def make_cover_mosaic(thumbnails: list[bytes]) -> bytes | None:
    """A square JPEG of up to 4 covers. A single cover fills it, and with 2 or 3
    of them some come back, so that the grid never has a hole. None if there's
    no cover, or none can be decoded."""
    images = []
    for thumbnail in thumbnails[:MOSAIC_TILES]:
        try:
            images.append(Image.open(io.BytesIO(thumbnail)).convert("RGB"))
        except Exception:  # noqa BLE001
            continue
    if not images:
        return None

    tile_size = MOSAIC_SIZE // 2
    mosaic = Image.new("RGB", (MOSAIC_SIZE, MOSAIC_SIZE))
    if len(images) == 1:
        mosaic.paste(ImageOps.fit(images[0], (MOSAIC_SIZE, MOSAIC_SIZE)))
    else:
        # Diagonal with 2 covers, the first one again in the corner with 3.
        order = {2: (0, 1, 1, 0), 3: (0, 1, 2, 0), 4: (0, 1, 2, 3)}[len(images)]
        for tile, image_index in enumerate(order):
            mosaic.paste(
                ImageOps.fit(images[image_index], (tile_size, tile_size)),
                ((tile % 2) * tile_size, (tile // 2) * tile_size),
            )

    buffer = io.BytesIO()
    mosaic.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
