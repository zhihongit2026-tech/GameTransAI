"""GameTrans AI V2 launcher and bundled-OCR integration test entrypoint."""
import sys


def ocr_self_test(fixture_b64: str) -> int:
    """Run *bundled* OCR against the submitted real-game screenshot (no Internet)."""
    import base64
    from pathlib import Path
    import cv2
    import numpy as np
    from rapidocr import RapidOCR

    data = base64.b64decode(Path(fixture_b64).read_text(encoding='ascii'))
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return 2
    result = RapidOCR()(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    texts = list(result.txts) if result.txts is not None else []
    from gametrans.scanner import has_chinese
    chinese = [s for s in texts if has_chinese(s)]
    # At least five Chinese fragments and one known settings header.
    return 0 if len(chinese) >= 5 and any('设置' in s or '分辨率' in s for s in chinese) else 3


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--ocr-self-test':
        sys.exit(ocr_self_test(sys.argv[2]))
    from gametrans.ui import launch_app
    sys.exit(launch_app())
