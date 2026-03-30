import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, "/Users/imarchand/git/pirobot/server")

import handlers.lcd  # registers the handler
from handlers.base import BaseHandler


def _make_handler():
    handler = BaseHandler.get_handler("lcd")
    mock_lcd = MagicMock()
    mock_lcd.height = 320
    mock_lcd.width = 240
    mock_server = MagicMock()
    mock_server.lcd = mock_lcd
    handler.server = mock_server
    handler.eligible = True
    return handler, mock_lcd


class TestLcdDisplayFrame(unittest.TestCase):

    def test_display_frame_calls_show_image(self):
        handler, mock_lcd = _make_handler()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        handler.display_frame(frame)
        mock_lcd.ShowImage.assert_called_once()

    def test_display_frame_resizes_to_lcd_dimensions(self):
        handler, mock_lcd = _make_handler()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        handler.display_frame(frame)
        call_args = mock_lcd.ShowImage.call_args[0][0]
        # PIL Image size is (width, height)
        self.assertEqual(call_args.size, (mock_lcd.height, mock_lcd.width))

    def test_stop_video_calls_show_image(self):
        handler, mock_lcd = _make_handler()
        handler.stop_video()
        mock_lcd.ShowImage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
