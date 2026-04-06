"""
Vector entry point.

The splash screen must appear before the heavy import chain
(yfinance, numpy, all page/widget modules) runs.  We achieve this by:

  1. _bootstrap() — creates QApplication and paints the splash using only
     PyQt6 (already linked, fast) and nothing else from the vector package.
  2. Only after the splash is visible do we import vector.app (which pulls in
     yfinance, numpy, DataStore, all pages, etc.).
  3. main() receives the already-created app, splash, and start-time so the
     2-second minimum is measured from when the splash first appeared.
"""

import sys


def _bootstrap():
    """
    Create QApplication and show the splash as the very first visible action.
    Imports only PyQt6 — no vector package modules.
    """
    import time
    from pathlib import Path

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication, QSplashScreen

    app = QApplication(sys.argv)

    # Replicate resource_path() logic without importing vector.paths
    if hasattr(sys, '_MEIPASS'):            # PyInstaller
        base = Path(sys._MEIPASS)
    elif getattr(sys, 'frozen', False):     # Nuitka standalone
        base = Path(sys.executable).parent
    else:                                   # dev
        base = Path(__file__).resolve().parent

    px = QPixmap(str(base / 'assets' / 'splashboard.png'))
    if not px.isNull():
        px = px.scaled(
            700, 400,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)
    splash.setFixedSize(700, 400)
    geo = app.primaryScreen().geometry()
    splash.move(geo.center().x() - 350, geo.center().y() - 200)
    splash.show()
    app.processEvents()   # force OS to paint before any heavy work starts

    t_start = time.monotonic()
    return app, splash, t_start


if __name__ == '__main__':
    _app, _splash, _t_start = _bootstrap()   # splash is visible here

    from vector.app import main              # heavy imports happen now,
                                             # splash already on screen

    raise SystemExit(main(_app, _splash, _t_start))
