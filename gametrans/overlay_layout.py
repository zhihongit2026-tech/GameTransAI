"""Pure layout math used by the game overlay; tested without Qt/Windows."""

def translated_rect(box, viewport_size, text):
    """Expand around a recognized line, but clip ALL output inside client bounds."""
    vx, vy = viewport_size
    x, y, w, h = box
    if vx < 1 or vy < 1:
        return (0, 0, 0, 0)
    font_size = max(12, min(22, int(h * 0.85)))
    width = min(vx, max(w + 12, min(int(len(text) * font_size * 0.59) + 18, max(180, w * 3))))
    approx_lines = max(1, (len(text) * font_size * 0.55) // max(1, width - 16) + 1)
    height = min(vy, max(h + 6, min(4, approx_lines) * (font_size + 3) + 8))
    x = max(0, min(x, vx - width))
    y = max(0, min(y, vy - height))
    return (x, y, width, height)
