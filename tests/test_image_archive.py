from io import BytesIO
from pathlib import Path
import stat
import unittest
import zipfile

from PIL import Image

from app.image_archive import ImageZipError, ZipLimits, validate_image_zip


def image_bytes(color: str, image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 48), color).save(buffer, format=image_format)
    return buffer.getvalue()


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class ImageArchiveTests(unittest.TestCase):
    def test_root_and_single_subfolder_are_resolved_by_basename(self):
        archive = zip_bytes({"cenas/gancho.png": image_bytes("blue"), "cenas/contexto.jpg": image_bytes("red", "JPEG")})
        result = validate_image_zip(archive, ["gancho.png", "contexto.jpg"])
        self.assertEqual(result.image_count, 2)
        self.assertEqual(result.image_for("gancho.png").width, 32)

    def test_extra_images_are_reported_but_not_required(self):
        archive = zip_bytes({"a.png": image_bytes("blue"), "extra.webp": image_bytes("red", "WEBP")})
        result = validate_image_zip(archive, ["a.png"])
        self.assertIn("extra.webp", result.warnings[0])

    def test_missing_and_duplicate_basenames_block_generation(self):
        missing = zip_bytes({"a.png": image_bytes("blue")})
        with self.assertRaisesRegex(ImageZipError, "ausentes"):
            validate_image_zip(missing, ["a.png", "b.png"])
        duplicate = zip_bytes({"cenas/a.png": image_bytes("blue"), "cenas/A.PNG": image_bytes("red")})
        with self.assertRaisesRegex(ImageZipError, "duplicado"):
            validate_image_zip(duplicate, ["a.png"])

    def test_unexpected_extension_and_nested_path_block(self):
        with self.assertRaisesRegex(ImageZipError, "inesperado"):
            validate_image_zip(zip_bytes({"notes.txt": b"text"}), ["a.png"])
        with self.assertRaisesRegex(ImageZipError, "somente a raiz"):
            validate_image_zip(zip_bytes({"one/two/a.png": image_bytes("blue")}), ["a.png"])

    def test_parent_path_and_symlink_are_rejected(self):
        with self.assertRaises(ImageZipError):
            validate_image_zip(zip_bytes({"../a.png": image_bytes("blue")}), ["a.png"])
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("link.png")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
        with self.assertRaisesRegex(ImageZipError, "simbólico"):
            validate_image_zip(buffer.getvalue(), ["link.png"])

    def test_file_count_limit_blocks_zip_bomb_shape(self):
        archive = zip_bytes({f"{index}.png": image_bytes("blue") for index in range(3)})
        with self.assertRaisesRegex(ImageZipError, "limite"):
            validate_image_zip(archive, ["0.png"], limits=ZipLimits(max_files=2))

    def test_invalid_image_bytes_are_rejected(self):
        with self.assertRaisesRegex(ImageZipError, "inválido"):
            validate_image_zip(zip_bytes({"a.png": b"not an image"}), ["a.png"])


if __name__ == "__main__":
    unittest.main()
