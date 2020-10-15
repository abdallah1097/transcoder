import unittest

from lib.ffmpeg import restricted_file
from lib.formatting import seconds_to_hms


class TestFormatting(unittest.TestCase):

    def test_secs_only(self):
        self.assertEqual(seconds_to_hms(75), '01:15')

    def test_hours(self):
        self.assertEqual(seconds_to_hms(3600), '01:00:00')

    def test_always_include_hours(self):
        self.assertEqual(seconds_to_hms(75, always_include_hours=True), '00:01:15')

    def test_secs_decimals(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=1), '01:12.5')

    def test_secs_decimals_2(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=2), '01:12.50')

    def test_frames(self):
        self.assertEqual(seconds_to_hms(72.5, output_frames=True), '01:12:12')

    def test_frames_2(self):
        self.assertEqual(seconds_to_hms(72.5, output_frames=True, framerate=30), '01:12:15')

    def test_ignore_decimals(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=2, output_frames=True), '01:12:12')

    def test_hours_and_frames(self):
        self.assertEqual(seconds_to_hms(72.5, always_include_hours=True, output_frames=True, framerate=30), '00:01:12:15')

    def test_frames_rounding(self):
        self.assertEqual(seconds_to_hms(65.16, output_frames=True, framerate=25), '01:05:04')

    def test_frames_rounding_2(self):
        self.assertEqual(seconds_to_hms(65.99, output_frames=True), '01:06:00')


class TestFileHandling(unittest.TestCase):

    def test_restricted_file(self):
        self.assertTrue(restricted_file('B2004203_mo01_RESTRICTED_CyberthonIV.mov'))


if __name__ == '__main__':
    unittest.main()
