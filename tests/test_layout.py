import unittest
from gametrans.overlay_layout import translated_rect


class LayoutTest(unittest.TestCase):
    def test_translation_must_stay_inside_game_at_different_resolutions(self):
        source = (1090, 700, 140, 36)
        for width, height in [(1360, 768), (1024, 576), (1920, 1080)]:
            scaled = tuple(round(x * (width/1360 if i % 2 == 0 else height/768))
                           for i, x in enumerate(source))
            x, y, w, h = translated_rect(scaled, (width, height), 'Lưu cài đặt tiếng Việt dài')
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, width)
            self.assertLessEqual(y + h, height)

    def test_invalid_viewport_safe(self):
        self.assertEqual(translated_rect((0,0,10,10), (0,0), 'abc'), (0,0,0,0))


if __name__ == '__main__':
    unittest.main()
