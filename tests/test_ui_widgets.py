import inspect
import unittest

from blogpost.ui.theme import COLORS
from blogpost.ui.widgets import (
    RoundedPanel,
    RoundedProgressBar,
    button_palette,
)


class UiWidgetStyleTests(unittest.TestCase):
    def test_panel_has_no_contrasting_default_border(self):
        default = inspect.signature(RoundedPanel.__init__).parameters["border"].default
        self.assertIsNone(default)

    def test_secondary_button_uses_fill_instead_of_outline(self):
        fill, outline, foreground = button_palette(
            variant="secondary",
            state="normal",
            hovered=False,
            pressed=False,
            focused=False,
            outer=COLORS["page"],
        )
        self.assertEqual(fill, COLORS["control"])
        self.assertEqual(outline, fill)
        self.assertEqual(foreground, COLORS["text"])

    def test_selected_toggle_uses_soft_fill_without_orange_outline(self):
        fill, outline, foreground = button_palette(
            variant="toggle",
            state="normal",
            hovered=False,
            pressed=False,
            focused=False,
            outer=COLORS["surface"],
            selected=True,
        )
        self.assertEqual(fill, COLORS["primary_soft"])
        self.assertEqual(outline, fill)
        self.assertEqual(foreground, COLORS["primary"])

    def test_disabled_button_has_no_contrasting_outline(self):
        fill, outline, foreground = button_palette(
            variant="secondary",
            state="disabled",
            hovered=False,
            pressed=False,
            focused=False,
            outer=COLORS["page"],
        )
        self.assertEqual(outline, fill)
        self.assertEqual(foreground, COLORS["subtle"])

    def test_progress_bar_default_is_four_pixels(self):
        default = inspect.signature(RoundedProgressBar.__init__).parameters["height"].default
        self.assertEqual(default, 4)


if __name__ == "__main__":
    unittest.main()
