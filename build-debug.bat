@echo off
REM Vector v0.5.0 Nuitka DEBUG build (console enabled for tracebacks)
REM Run from project root with .venv activated.

if exist "Vector-v0.5.0-debug.dist" (
    echo Removing stale Vector-v0.5.0-debug.dist...
    rmdir /s /q "Vector-v0.5.0-debug.dist"
)

REM Nuitka standalone include flags (why each is required):
REM   certifi data        - cacert.pem SSL bundle for requests/urllib3/yfinance
REM   matplotlib + data   - Lens/ticker charts; mpl-data ships fonts/styles/matplotlibrc
REM   curl_cffi + data     - yfinance >=0.2.54 HTTP backend (compiled ext + bundled libcurl/cacert)
REM   websockets           - imported eagerly by yfinance.live at "import yfinance"
REM   google.protobuf      - yfinance.pricing_pb2 imports it eagerly at "import yfinance"
REM   multitasking/frozendict/peewee/platformdirs - yfinance runtime deps Nuitka can miss
REM   pytz/tzdata(+data)/dateutil - timezone data for pandas/yfinance tz-aware ops on Windows
REM   charset_normalizer   - requests transitive dep
python -m nuitka ^
  --standalone ^
  --enable-plugin=pyqt6 ^
  --output-filename="Vector-v0.5.0-debug.exe" ^
  --include-data-dir=assets=assets ^
  --include-data-dir=vector/lens/templates=vector/lens/templates ^
  --include-data-files=debug_test.json=debug_test.json ^
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
  --include-package-data=certifi ^
  --include-package=matplotlib ^
  --include-package-data=matplotlib ^
  --include-package=curl_cffi ^
  --include-package-data=curl_cffi ^
  --include-package=websockets ^
  --include-package=google.protobuf ^
  --include-package=multitasking ^
  --include-package=frozendict ^
  --include-package=peewee ^
  --include-package=platformdirs ^
  --include-package=pytz ^
  --include-package=tzdata ^
  --include-package-data=tzdata ^
  --include-package=dateutil ^
  --include-package=charset_normalizer ^
  main.py
