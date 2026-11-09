"""The "Morning" design tokens: every colour in the dashboard comes from here, named by its role.

Coloured text uses the darker inks (CORAL_INK, SKY_INK) so it passes WCAG AA; the light fills (CORAL, SKY)
are for bars, dots and display numbers of 24 px or more. tests/dashboard/test_theme.py checks the ratios.
"""

SKY_TOP = "#E4EEF7"  # top of the page gradient
PAPER = "#F4F7FA"  # page background below the gradient
CARD = "#FFFFFF"
INK = "#1D2B3A"  # text, primary button
INK_SOFT = "#44525F"  # body copy inside cards
MUTED = "#5F6E7E"  # labels, captions, axis text
RULE = "#E2E8EF"  # dividers, empty tracks, grid
WASH = "#EDF2F7"  # inputs, slider and bar tracks
CORAL = "#DC756D"  # the one highlight per chart
CORAL_INK = "#B4463E"
SKY = "#4A90C2"  # the main data series
SKY_INK = "#2F6E9A"
SUN = "#F2C14E"  # logo and the plug-in peak only
PALE = "#C8D8E8"  # secondary bars
TINT_CORAL = "#FDF0EE"
TINT_SKY = "#EAF3FA"
TINT_SUN = "#FEF6E4"
TINT_GREEN = "#E8F4EC"

SERIF = "Young Serif"
SANS = "Hanken Grotesk"
SHADOW = "0 1px 2px rgba(29,43,58,0.04), 0 8px 24px rgba(29,43,58,0.05)"


def _luminance(colour: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio of two #RRGGBB colours."""
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
