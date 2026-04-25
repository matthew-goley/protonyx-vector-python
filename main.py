"""
Vector entry point.

Startup ordering (matches CLAUDE.md):

  1. _create_app() — creates QApplication using only PyQt6 (already linked,
     fast). Does NOT yet import the vector package.
  2. _run_auth_gate() — verifies a saved token via auth.auth.get_me, or shows
     the LoginWindow until the user signs in. If the user dismisses the
     dialog without authenticating we exit cleanly.
  3. _show_splash() — paints the splash so it appears BEFORE the heavy import
     chain (yfinance, numpy, all page/widget modules) runs.
  4. Only then is vector.app imported, and main() proceeds with the existing
     splash → window construction → 2-second minimum → splash.finish() flow.
"""



import sys


def _create_app():
    """Create the QApplication with no UI yet — auth comes before splash."""
    from PyQt6.QtWidgets import QApplication
    return QApplication(sys.argv)


def _run_auth_gate(app):
    """Resolve (token, user_data) before the splash and main app load.

    Tries the saved session first; falls back to LoginWindow.exec(). Exits the
    process with status 0 if the user closes the login dialog without
    authenticating.
    """
    from auth.auth import clear_token, get_me, load_token
    from auth.login_window import LoginWindow

    saved = load_token()
    if saved:
        try:
            user_data = get_me(saved)
            return saved, user_data
        except Exception:
            clear_token()

    dialog = LoginWindow()
    dialog.exec()
    if not dialog.token or not dialog.user_data:
        sys.exit(0)
    return dialog.token, dialog.user_data


def _show_splash(app):
    """Paint the splash screen and return (splash, t_start)."""
    import time
    from pathlib import Path

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QSplashScreen

    # Replicate resource_path() logic without importing vector.paths
    if hasattr(sys, '_MEIPASS'):            # PyInstaller
        base = Path(sys._MEIPASS)
    elif getattr(sys, 'frozen', False):     # Nuitka standalone
        base = Path(sys.executable).parent
    else:                                   # dev
        base = Path(__file__).resolve().parent

    sw = app.primaryScreen().size().width()
    splash_w = min(int(sw * 0.55), 900)
    splash_h = splash_w * 800 // 1400

    px = QPixmap(str(base / 'assets' / 'splashboard.png'))
    if not px.isNull():
        px = px.scaled(
            splash_w, splash_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)
    splash.setFixedSize(splash_w, splash_h)
    geo = app.primaryScreen().geometry()
    splash.move(geo.center().x() - splash_w // 2, geo.center().y() - splash_h // 2)
    splash.show()
    app.processEvents()   # force OS to paint before any heavy work starts

    return splash, time.monotonic()


if __name__ == '__main__':
    _app = _create_app()

    _token, _user_data = _run_auth_gate(_app)

    _splash, _t_start = _show_splash(_app)        # splash visible here

    from vector.app import main                   # heavy imports happen now,
                                                  # splash already on screen

    raise SystemExit(main(_app, _splash, _t_start, token=_token, user_data=_user_data))
