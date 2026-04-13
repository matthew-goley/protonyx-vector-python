@echo off
REM Vector v0.4.0 Nuitka build
REM Run from project root with .venv activated.

if exist "Vector-v0.4.0.dist" (
    echo Removing stale Vector-v0.4.0.dist...
    rmdir /s /q "Vector-v0.4.0.dist"
)

python -m nuitka ^
  --standalone ^
  --windows-console-mode=disable ^
  --enable-plugin=pyqt6 ^
  --output-filename="Vector-v0.4.0.exe" ^
  --include-data-dir=assets=assets ^
  --include-data-dir=vector/lens/templates=vector/lens/templates ^
  --include-package=vector.lens ^
  --include-package=vector.lens.analyzers ^
  --include-package=yfinance ^
  --include-package=pandas ^
  --include-package=numpy ^
  --include-package=lxml ^
  --include-package=bs4 ^
  --include-package=requests ^
  --include-package=urllib3 ^
  --include-package=certifi ^
  main.py
