import unittest

from app.renderer import (
    camera_crop_for_frame,
    camera_crop_rect,
    exif_oriented_dimensions,
    interpolate_camera_pose,
    minimum_cover_crop,
    resolve_camera,
)
from app.schemas import Camera, CameraPose


def camera(
    *,
    start_x: float = 0.5,
    start_y: float = 0.5,
    start_zoom: float = 1.0,
    end_x: float = 0.5,
    end_y: float = 0.5,
    end_zoom: float = 1.0,
) -> Camera:
    return Camera(
        start=CameraPose(focus_x=start_x, focus_y=start_y, zoom=start_zoom),
        end=CameraPose(focus_x=end_x, focus_y=end_y, zoom=end_zoom),
    )


class RendererCameraTests(unittest.TestCase):
    def assert_bounded(self, crop) -> None:
        self.assertGreaterEqual(crop.x, 0.0)
        self.assertGreaterEqual(crop.y, 0.0)
        self.assertLessEqual(crop.right, crop.image_width + 1e-9)
        self.assertLessEqual(crop.bottom, crop.image_height + 1e-9)
        self.assertGreater(crop.width, 0.0)
        self.assertGreater(crop.height, 0.0)

    def test_shot_camera_has_precedence_over_scene_camera(self):
        scene_camera = camera(start_x=0.2, end_x=0.3)
        shot_camera = camera(start_x=0.7, end_x=0.8)

        self.assertIs(resolve_camera(shot_camera, scene_camera), shot_camera)
        self.assertIs(resolve_camera(None, scene_camera), scene_camera)
        self.assertIsNone(resolve_camera(None, None))

    def test_exif_orientation_changes_coordinate_dimensions_before_cropping(self):
        self.assertEqual(exif_oriented_dimensions(400, 800, 1), (400.0, 800.0))
        self.assertEqual(exif_oriented_dimensions(400, 800, 6), (800.0, 400.0))
        with self.assertRaises(ValueError):
            exif_oriented_dimensions(400, 800, 9)

        crop = camera_crop_rect(
            400,
            800,
            1080,
            1920,
            CameraPose(focus_x=0.5, focus_y=0.5, zoom=1.0),
            exif_orientation=6,
        )
        self.assertEqual((crop.image_width, crop.image_height), (800.0, 400.0))
        self.assert_bounded(crop)

    def test_zoom_one_uses_the_cover_crop_and_corner_focus_stays_inside_image(self):
        # A wide source needs horizontal cover-cropping for a vertical target.
        cover_width, cover_height = minimum_cover_crop(1600, 900, 1080, 1920)
        self.assertAlmostEqual(cover_width / cover_height, 1080 / 1920)
        self.assertAlmostEqual(cover_height, 900.0)

        left = camera_crop_rect(
            1600,
            900,
            1080,
            1920,
            CameraPose(focus_x=0.0, focus_y=0.0, zoom=1.0),
        )
        right = camera_crop_rect(
            1600,
            900,
            1080,
            1920,
            CameraPose(focus_x=1.0, focus_y=1.0, zoom=1.0),
        )
        self.assertAlmostEqual(left.x, 0.0)
        self.assertAlmostEqual(left.y, 0.0)
        self.assertAlmostEqual(right.right, 1600.0)
        self.assertAlmostEqual(right.bottom, 900.0)
        self.assert_bounded(left)
        self.assert_bounded(right)

    def test_interpolation_uses_exact_endpoints_and_clamps_every_frame_at_edges(self):
        path = camera(
            start_x=0.0,
            start_y=0.0,
            start_zoom=1.0,
            end_x=1.0,
            end_y=1.0,
            end_zoom=1.35,
        )
        first_pose = interpolate_camera_pose(path, 0.0)
        last_pose = interpolate_camera_pose(path, 1.0)
        self.assertEqual(first_pose, path.start)
        self.assertEqual(last_pose, path.end)

        crops = [
            camera_crop_for_frame(900, 1600, 1080, 1920, path, frame, 17)
            for frame in range(17)
        ]
        for crop in crops:
            self.assert_bounded(crop)
            self.assertAlmostEqual(crop.width / crop.height, 1080 / 1920)
        self.assertAlmostEqual(crops[0].x, 0.0)
        self.assertAlmostEqual(crops[0].y, 0.0)
        self.assertAlmostEqual(crops[-1].right, 900.0)
        self.assertAlmostEqual(crops[-1].bottom, 1600.0)

    def test_identical_keyframes_produce_a_static_crop(self):
        static_camera = camera(start_x=0.78, start_y=0.22, start_zoom=1.22, end_x=0.78, end_y=0.22, end_zoom=1.22)
        first = camera_crop_for_frame(1500, 1000, 1080, 1920, static_camera, 0, 9)
        middle = camera_crop_for_frame(1500, 1000, 1080, 1920, static_camera, 4, 9)
        last = camera_crop_for_frame(1500, 1000, 1080, 1920, static_camera, 8, 9)

        self.assertEqual(first, middle)
        self.assertEqual(middle, last)


if __name__ == "__main__":
    unittest.main()
