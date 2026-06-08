# tools/image_enhancer_tool.py

import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


class ImageEnhancerTool:
    """
    Progressive image enhancement for OCR retry pipeline.

    Strategy per attempt:
      - Attempt 1 : no enhancement — use original file as-is
      - Attempt 2 : moderate enhancement (contrast + sharpness)
      - Attempt 3 : aggressive enhancement (denoise + binarisation + upscale)

    Public API
    ----------
    load_image(file_path)                            -> PIL.Image | None
    enhance_for_attempt(file_path, attempt, ...)     -> (Path, bool)
    cleanup(path)                                    -> None
    """

    _LEVELS = {
        2: {
            "contrast":   1.5,
            "sharpness":  2.0,
            "brightness": 1.1,
            "upscale":    False,
        },
        3: {
            "contrast":   2.0,
            "sharpness":  3.0,
            "brightness": 1.2,
            "upscale":    True,
            "upscale_factor": 2,
        },
    }

    def load_image(self, file_path: Path) -> Optional[Image.Image]:
        """
        Load the source image once, before the retry loop.
        Returns a PIL Image object, or None if the file is not an image.
        """
        try:
            img = Image.open(file_path)
            img.load()
            logger.debug(f"Image loaded: {file_path.name} ({img.size}, {img.mode})")
            return img
        except Exception as e:
            logger.debug(
                f"Could not load '{file_path.name}' as image "
                f"(will use original): {e}"
            )
            return None

    def enhance_for_attempt(
        self,
        file_path: Path,
        attempt: int,
        base_image: Optional[Image.Image] = None,
    ) -> Tuple[Path, bool]:
        """
        Return the path to use for OCR and whether a temp file was created.

        - attempt == 1  -> (original path, False)
        - attempt >= 2  -> (enhanced temp path, True)
        """
        if attempt == 1 or base_image is None:
            return file_path, False

        level = min(attempt, max(self._LEVELS.keys()))
        params = self._LEVELS[level]

        try:
            enhanced = self._apply_enhancements(base_image, params)
            tmp_path = self._save_to_temp(enhanced, file_path.suffix)
            logger.info(
                f"  Image enhanced (attempt {attempt}): "
                f"contrast={params['contrast']}, "
                f"sharpness={params['sharpness']}, "
                f"upscale={params.get('upscale', False)}"
            )
            return tmp_path, True
        except Exception as e:
            logger.warning(
                f"Enhancement failed (attempt {attempt}), "
                f"falling back to original: {e}"
            )
            return file_path, False

    def cleanup(self, path: Path) -> None:
        """Delete a temporary enhanced file, silently ignoring errors."""
        try:
            if path and path.exists():
                path.unlink()
                logger.debug(f"Temp file deleted: {path.name}")
        except Exception as e:
            logger.debug(f"Could not delete temp file '{path}': {e}")

    def _apply_enhancements(
        self, image: Image.Image, params: dict
    ) -> Image.Image:
        """Apply the full enhancement chain and return a new PIL Image."""
        img = image.copy()

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # 1. Upscale first (better base for filtering)
        if params.get("upscale"):
            factor = params.get("upscale_factor", 2)
            new_size = (img.width * factor, img.height * factor)
            img = img.resize(new_size, Image.LANCZOS)

        # 2. Brightness
        if params.get("brightness", 1.0) != 1.0:
            img = ImageEnhance.Brightness(img).enhance(params["brightness"])

        # 3. Contrast
        img = ImageEnhance.Contrast(img).enhance(params["contrast"])

        # 4. Sharpness
        img = ImageEnhance.Sharpness(img).enhance(params["sharpness"])

        # 5. Noise reduction
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=100, threshold=3))

        # 6. Aggressive level: greyscale + binarise
        if params.get("upscale"):
            img = img.convert("L")
            img = img.point(lambda p: 255 if p > 128 else 0)
            img = img.convert("RGB")

        return img

    def _save_to_temp(self, image: Image.Image, original_suffix: str) -> Path:
        """Save image to a temporary file and return its Path."""
        suffix = original_suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"):
            suffix = ".png"

        fmt_map = {
            ".jpg":  "JPEG",
            ".jpeg": "JPEG",
            ".png":  "PNG",
            ".tiff": "TIFF",
            ".tif":  "TIFF",
            ".bmp":  "BMP",
        }
        fmt = fmt_map.get(suffix, "PNG")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)

        save_kwargs = {}
        if fmt == "JPEG":
            save_kwargs["quality"] = 95
            save_kwargs["optimize"] = True
            if image.mode != "RGB":
                image = image.convert("RGB")

        image.save(tmp_path, format=fmt, **save_kwargs)
        return tmp_path
