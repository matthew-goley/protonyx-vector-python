from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    APP_NAME,
    APP_VERSION,
    COMPANY_NAME,
    MONTE_CARLO_HORIZON_DAYS,
    MONTE_CARLO_SIMULATIONS,
    VOLATILITY_LOOKBACK_PERIODS,
)
from ..widgets import CardFrame, LoadingButton
from .dashboard import _CONTENT_W

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


class _AnimatedChevron(QWidget):
    """Small chevron icon that rotates smoothly between 0° (›) and 90° (⌄)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self.setFixedSize(22, 22)
        self._anim = QPropertyAnimation(self, b'angle')
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = value
        self.update()

    angle = pyqtProperty(float, get_angle, set_angle)

    def animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._angle)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(11.0, 11.0)
        painter.rotate(self._angle)
        pen = QPen(QColor('#8d98af'), 2.0, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        # Draw a right-pointing chevron ›; rotated 90° it becomes ⌄
        painter.drawLine(QPointF(-3.0, -5.0), QPointF(3.5, 0.0))
        painter.drawLine(QPointF(3.5, 0.0), QPointF(-3.0, 5.0))


class _AccordionSection(CardFrame):
    """
    Collapsible settings card with an animated chevron and smooth height expansion.
    Collapsed by default; clicking the header toggles open/closed.
    """

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._open = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────
        # Use QFrame (not QPushButton) so child widgets render correctly.
        self._header = QFrame()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet('border: none; background: transparent;')
        self._header.mousePressEvent = self._header_clicked

        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(20, 18, 20, 18)
        header_row.setSpacing(12)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet('font-size: 16pt; font-weight: 700; background: transparent; border: none;')
        self._chevron = _AnimatedChevron()

        header_row.addWidget(title_lbl)
        header_row.addStretch(1)
        header_row.addWidget(self._chevron)
        root.addWidget(self._header)

        # ── Content wrapper (height-animated) ────────────────────────────
        self._content = QWidget()
        self._content.setMaximumHeight(0)
        self._content.setMinimumHeight(0)

        inner = QVBoxLayout(self._content)
        inner.setContentsMargins(20, 4, 20, 18)
        inner.setSpacing(0)
        self._form = QFormLayout()
        self._form.setSpacing(12)
        inner.addLayout(self._form)
        root.addWidget(self._content)

        # ── Height animation ──────────────────────────────────────────────
        self._anim = QPropertyAnimation(self._content, b'maximumHeight')
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.finished.connect(self._on_finished)

    def form(self) -> QFormLayout:
        return self._form

    def _header_clicked(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle()

    def _measure(self) -> int:
        self._content.setMaximumHeight(16_777_215)
        self._content.layout().activate()
        h = self._content.sizeHint().height()
        self._content.setMaximumHeight(0)
        return max(h, 40)

    def _toggle(self) -> None:
        if self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._open = not self._open
        if self._open:
            natural_h = self._measure()
            self._anim.setStartValue(0)
            self._anim.setEndValue(natural_h)
            self._chevron.animate_to(90.0)
        else:
            self._anim.setStartValue(self._content.height())
            self._anim.setEndValue(0)
            self._chevron.animate_to(0.0)
        self._anim.start()

    def _on_finished(self) -> None:
        if self._open:
            self._content.setMaximumHeight(16_777_215)
        # Notify the parent container so the scroll area recomputes its range
        p = self.parentWidget()
        if p:
            p.adjustSize()


class QDoubleSpinBoxCompat(QSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setSingleStep(1)
        self.setRange(-100, 100)
        self.setSuffix('%')
        self.setMinimumWidth(120)

    def value(self) -> float:  # type: ignore[override]
        return super().value() / 100

    def setValue(self, value: float) -> None:  # type: ignore[override]
        super().setValue(int(round(value * 100)))


_RISK_TIERS_SETTINGS = [
    {
        'key': 'low',
        'label': 'Conservative',
        'description': 'Tighter guardrails \u2014 flags smaller risks sooner',
        'color': '#2dd4bf',
    },
    {
        'key': 'regular',
        'label': 'Moderate',
        'description': 'Balanced \u2014 standard thresholds for most investors',
        'color': '#38bdf8',
    },
    {
        'key': 'high',
        'label': 'Aggressive',
        'description': 'Wider guardrails \u2014 tolerates bigger swings',
        'color': '#1e3a8a',
    },
]

_TIER_DISPLAY_NAME = {'low': 'Conservative', 'regular': 'Moderate', 'high': 'Aggressive'}


class _RiskTierOption(QFrame):
    """Compact clickable risk tier option for the settings page."""

    def __init__(self, tier: dict, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tier_key = tier['key']
        self._accent = tier['color']
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        label = QLabel(tier['label'])
        label.setStyleSheet('font-size: 13pt; font-weight: 700; background: transparent; border: none;')
        layout.addWidget(label)

        desc = QLabel(tier['description'])
        desc.setWordWrap(True)
        desc.setProperty('role', 'muted')
        desc.setStyleSheet('font-size: 10pt; background: transparent; border: none;')
        layout.addWidget(desc)

        if selected:
            self.set_selected(True)
        else:
            self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        bg = '#161b26' if is_dark else '#ffffff'
        border_idle = '#1e2535' if is_dark else '#d0d8e8'
        if self._selected:
            self.setStyleSheet(
                f'QFrame {{ background: {bg}; border: 2px solid {self._accent}; border-radius: 12px; }}'
            )
        else:
            self.setStyleSheet(
                f'QFrame {{ background: {bg}; border: 1px solid {border_idle}; border-radius: 12px; }}'
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            while parent and not isinstance(parent, SettingsPage):
                parent = parent.parentWidget()
            if parent:
                parent._select_risk_tier(self.tier_key)


class _DebugTestWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(object, object)  # output_path, error

    def __init__(self, store, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._settings = settings

    def run(self) -> None:  # noqa: D401
        try:
            from vector.lens.debug_runner import run_debug_tests

            def cb(current: int, total: int, message: str) -> None:
                self.progress.emit(current, total, message)

            output_path = run_debug_tests(self._store, self._settings, progress_callback=cb)
            self.done.emit(output_path, None)
        except Exception as e:  # noqa: BLE001
            self.done.emit(None, e)


class SettingsPage(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self.remove_list = QListWidget()
        self.remove_list.setMinimumHeight(200)
        self._build_ui()

    def _add_section(self, parent: QVBoxLayout, title: str) -> QFormLayout:
        card = CardFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        heading = QLabel(title)
        heading.setStyleSheet('font-size: 16pt; font-weight: 700;')
        layout.addWidget(heading)
        form = QFormLayout()
        form.setSpacing(12)
        layout.addLayout(form)
        parent.addWidget(card)
        return form

    def _add_accordion(self, parent: QVBoxLayout, title: str) -> QFormLayout:
        section = _AccordionSection(title)
        parent.addWidget(section)
        return section.form()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setFixedWidth(_CONTENT_W())
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 24)
        layout.setSpacing(16)

        general = self._add_section(layout, 'General')
        self.theme_combo = QComboBox(); self.theme_combo.addItems(['Dark', 'Light'])
        self.currency_combo = QComboBox(); self.currency_combo.addItems(['USD', 'EUR', 'GBP'])
        self.date_combo = QComboBox(); self.date_combo.addItems(['MM/DD/YYYY', 'DD/MM/YYYY'])
        general.addRow('Theme', self.theme_combo)
        general.addRow('Default Currency', self.currency_combo)
        general.addRow('Date Format', self.date_combo)

        # ── Investment Style ──
        style_card = CardFrame()
        style_layout = QVBoxLayout(style_card)
        style_layout.setContentsMargins(20, 20, 20, 20)
        style_layout.setSpacing(10)
        style_heading = QLabel('Investment Style')
        style_heading.setStyleSheet('font-size: 16pt; font-weight: 700;')
        style_layout.addWidget(style_heading)

        tier_row = QHBoxLayout()
        tier_row.setSpacing(10)
        self._tier_options: dict[str, _RiskTierOption] = {}
        for tier in _RISK_TIERS_SETTINGS:
            opt = _RiskTierOption(tier, selected=False)
            self._tier_options[tier['key']] = opt
            tier_row.addWidget(opt)
        style_layout.addLayout(tier_row)

        self._style_note = QLabel('Lens will update on the next refresh.')
        self._style_note.setProperty('role', 'muted')
        self._style_note.setStyleSheet('font-size: 10pt;')
        self._style_note.setVisible(False)
        style_layout.addWidget(self._style_note)
        layout.addWidget(style_card)

        refresh = self._add_accordion(layout, 'Data & Refresh')
        self.refresh_combo = QComboBox(); self.refresh_combo.addItems(['1 min', '5 min', '15 min', 'Manual only'])
        clear_cache_button = LoadingButton('Clear Cached Price Data')
        clear_cache_button.clicked.connect(self.window.clear_cache)
        self._export_csv_button = LoadingButton('Export Positions to CSV')
        self._export_csv_button.clicked.connect(self._export_to_csv)
        reset_button = LoadingButton('Reset All App Data / Re-run Onboarding')
        reset_button.clicked.connect(self.window.reset_all_data)
        refresh.addRow('Auto-refresh Interval', self.refresh_combo)
        refresh.addRow('', clear_cache_button)
        refresh.addRow('', self._export_csv_button)
        refresh.addRow('', reset_button)

        thresholds = self._add_accordion(layout, 'Portfolio Direction Thresholds')
        self.strong_spin = self._spin_box(); self.strong_spin.setRange(-100, 100)
        self.steady_spin = self._spin_box(); self.steady_spin.setRange(-100, 100)
        self.neutral_low_spin = self._spin_box(); self.neutral_low_spin.setRange(-100, 100)
        self.neutral_high_spin = self._spin_box(); self.neutral_high_spin.setRange(-100, 100)
        self.depreciating_spin = self._spin_box(); self.depreciating_spin.setRange(-100, 100)
        thresholds.addRow('Strong cutoff (%)', self.strong_spin)
        thresholds.addRow('Steady cutoff (%)', self.steady_spin)
        thresholds.addRow('Neutral low (%)', self.neutral_low_spin)
        thresholds.addRow('Neutral high (%)', self.neutral_high_spin)
        thresholds.addRow('Weak cutoff (%)', self.depreciating_spin)

        volatility = self._add_accordion(layout, 'Volatility')
        self.lookback_combo = QComboBox(); self.lookback_combo.addItems(['3 months', '6 months', '1 year'])
        self.low_vol_spin = QSpinBox(); self.low_vol_spin.setRange(1, 100); self.low_vol_spin.setMinimumWidth(120)
        self.high_vol_spin = QSpinBox(); self.high_vol_spin.setRange(1, 100); self.high_vol_spin.setMinimumWidth(120)
        volatility.addRow('Lookback Period', self.lookback_combo)
        volatility.addRow('Low cutoff', self.low_vol_spin)
        volatility.addRow('High cutoff', self.high_vol_spin)

        lens_signals = self._add_accordion(layout, 'Lens Signal Thresholds')
        self._lens_tier_note = QLabel('')
        self._lens_tier_note.setWordWrap(True)
        self._lens_tier_note.setProperty('role', 'muted')
        self._lens_tier_note.setStyleSheet('font-size: 10pt; margin-bottom: 8px;')
        lens_signals.addRow(self._lens_tier_note)
        self.stock_conc_spin = QSpinBox(); self.stock_conc_spin.setRange(1, 100); self.stock_conc_spin.setSuffix('%'); self.stock_conc_spin.setMinimumWidth(120)
        self.sector_conc_spin = QSpinBox(); self.sector_conc_spin.setRange(1, 100); self.sector_conc_spin.setSuffix('%'); self.sector_conc_spin.setMinimumWidth(120)
        self.steep_dt_spin = QSpinBox(); self.steep_dt_spin.setRange(-100, -1); self.steep_dt_spin.setSuffix('%'); self.steep_dt_spin.setMinimumWidth(120)
        self.high_beta_spin = QDoubleSpinBox(); self.high_beta_spin.setRange(0.5, 5.0); self.high_beta_spin.setSingleStep(0.1); self.high_beta_spin.setDecimals(1); self.high_beta_spin.setMinimumWidth(120)
        self.stock_vol_spin = QSpinBox(); self.stock_vol_spin.setRange(1, 100); self.stock_vol_spin.setSuffix('%'); self.stock_vol_spin.setMinimumWidth(120)
        self.dead_weight_spin = QSpinBox(); self.dead_weight_spin.setRange(1, 50); self.dead_weight_spin.setSuffix('%'); self.dead_weight_spin.setMinimumWidth(120)
        self.loss_threshold_spin = QSpinBox(); self.loss_threshold_spin.setRange(-100, -1); self.loss_threshold_spin.setSuffix('%'); self.loss_threshold_spin.setMinimumWidth(120)
        self.winner_drift_spin = QDoubleSpinBox(); self.winner_drift_spin.setRange(1.0, 10.0); self.winner_drift_spin.setSingleStep(0.5); self.winner_drift_spin.setDecimals(1); self.winner_drift_spin.setMinimumWidth(120); self.winner_drift_spin.setSuffix('×')
        lens_signals.addRow('Stock concentration threshold %', self.stock_conc_spin)
        lens_signals.addRow('Sector concentration threshold %', self.sector_conc_spin)
        lens_signals.addRow('Steep downtrend threshold %', self.steep_dt_spin)
        lens_signals.addRow('High beta threshold', self.high_beta_spin)
        lens_signals.addRow('High volatility threshold %', self.stock_vol_spin)
        lens_signals.addRow('Dead weight threshold %', self.dead_weight_spin)
        lens_signals.addRow('Unrealized loss alert %', self.loss_threshold_spin)
        lens_signals.addRow('Winner drift multiple', self.winner_drift_spin)

        monte_carlo = self._add_accordion(layout, 'Monte Carlo')
        self.mc_period_combo = QComboBox(); self.mc_period_combo.addItems(list(MONTE_CARLO_HORIZON_DAYS.keys()))
        self.mc_sims_combo = QComboBox(); self.mc_sims_combo.addItems([str(n) for n in MONTE_CARLO_SIMULATIONS])
        monte_carlo.addRow('Projection period', self.mc_period_combo)
        monte_carlo.addRow('Simulations', self.mc_sims_combo)

        developer = self._add_accordion(layout, 'Developer')
        dev_desc = QLabel(
            'Run the Lens engine across mock portfolios from <code>debug_test.json</code> '
            'and write the results to <code>output.md</code>. Useful for testing CTA '
            'behavior across all risk tiers without changing your real portfolio.'
        )
        dev_desc.setWordWrap(True)
        dev_desc.setProperty('role', 'muted')
        dev_desc.setStyleSheet('font-size: 10pt;')
        self.run_lens_test_button = LoadingButton('Run Lens Test')
        self.run_lens_test_button.clicked.connect(self._run_lens_test)
        self._lens_test_status = QLabel('')
        self._lens_test_status.setProperty('role', 'muted')
        self._lens_test_status.setStyleSheet('font-size: 10pt;')
        self._lens_test_status.setWordWrap(True)
        developer.addRow(dev_desc)
        developer.addRow('', self.run_lens_test_button)
        developer.addRow('', self._lens_test_status)
        self._lens_test_worker: _DebugTestWorker | None = None

        positions = self._add_section(layout, 'Positions')
        add_position = LoadingButton('Add New Position')
        add_position.clicked.connect(self.window.add_position_from_settings)
        remove_button = LoadingButton('Remove Selected Position')
        remove_button.clicked.connect(self.remove_selected_position)
        positions.addRow('', add_position)
        positions.addRow('Current Positions', self.remove_list)
        positions.addRow('', remove_button)

        about = self._add_section(layout, 'About')
        about.addRow('App Version', QLabel(APP_VERSION))
        about.addRow('Brand', QLabel(f'{COMPANY_NAME} / {APP_NAME}'))
        about.addRow('Credits', QLabel('PyQt6, Yahoo Finance (yfinance)'))

        layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

        # ── Sticky save footer (outside scroll, always visible) ───────────
        footer = QFrame()
        footer.setObjectName('settingsFooter')
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.addStretch(1)
        self.save_button = LoadingButton('Save Settings')
        self.save_button.setProperty('accent', True)
        self.save_button.setMinimumWidth(160)
        self.save_button.clicked.connect(self.save_settings)
        footer_layout.addWidget(self.save_button)
        outer.addWidget(footer)

    def _spin_box(self) -> QDoubleSpinBoxCompat:
        return QDoubleSpinBoxCompat()

    def load_from_settings(self, settings: dict[str, Any], positions: list[dict[str, Any]]) -> None:
        self.theme_combo.setCurrentText(settings['theme'])
        self.currency_combo.setCurrentText(settings['currency'])
        self.date_combo.setCurrentText(settings['date_format'])
        self.refresh_combo.setCurrentText(settings['refresh_interval'])
        # Risk tier
        tier = settings.get('risk_tier', 'regular')
        self._current_risk_tier = tier
        for key, opt in self._tier_options.items():
            opt.set_selected(key == tier)
        tier_name = _TIER_DISPLAY_NAME.get(tier, 'Moderate')
        self._lens_tier_note.setText(
            f'Your investment style is set to <b>{tier_name}</b>. '
            f'The defaults below reflect that profile. Changing any value '
            f'overrides the default for that specific threshold.'
        )
        thresholds = settings['direction_thresholds']
        self.strong_spin.setValue(float(thresholds['strong']))
        self.steady_spin.setValue(float(thresholds['steady']))
        self.neutral_low_spin.setValue(float(thresholds['neutral_low']))
        self.neutral_high_spin.setValue(float(thresholds['neutral_high']))
        self.depreciating_spin.setValue(float(thresholds['depreciating']))
        vol = settings['volatility']
        self.lookback_combo.setCurrentText(vol['lookback'])
        self.low_vol_spin.setValue(int(vol['low_cutoff']))
        self.high_vol_spin.setValue(int(vol['high_cutoff']))
        ls = settings.get('lens_signals', {})
        self.stock_conc_spin.setValue(int(ls.get('stock_concentration_pct', 35)))
        self.sector_conc_spin.setValue(int(ls.get('sector_concentration_pct', 50)))
        self.steep_dt_spin.setValue(int(ls.get('steep_downtrend_pct', -20)))
        self.high_beta_spin.setValue(float(ls.get('high_beta_threshold', 1.3)))
        self.stock_vol_spin.setValue(int(ls.get('stock_vol_threshold_pct', 45)))
        self.dead_weight_spin.setValue(int(ls.get('dead_weight_pct', 2)))
        self.loss_threshold_spin.setValue(int(ls.get('loss_threshold', -15)))
        self.winner_drift_spin.setValue(float(ls.get('winner_drift_multiple', 2.0)))
        mc = settings.get('monte_carlo', {})
        self.mc_period_combo.setCurrentText(mc.get('projection_period', '1 year'))
        self.mc_sims_combo.setCurrentText(str(mc.get('simulations', 500)))
        self.remove_list.clear()
        for position in positions:
            item = QListWidgetItem(f"{position['ticker']} — {position['shares']:.4f}".rstrip('0').rstrip('.'))
            item.setData(Qt.ItemDataRole.UserRole, position['ticker'])
            self.remove_list.addItem(item)

    def _select_risk_tier(self, tier_key: str) -> None:
        self._current_risk_tier = tier_key
        for key, opt in self._tier_options.items():
            opt.set_selected(key == tier_key)
        # Update the lens tier note — no save yet, waits for Save Settings
        tier_name = _TIER_DISPLAY_NAME.get(tier_key, 'Moderate')
        self._lens_tier_note.setText(
            f'Your investment style is set to <b>{tier_name}</b>. '
            f'The defaults below reflect that profile. Changing any value '
            f'overrides the default for that specific threshold.'
        )
        self._style_note.setVisible(False)

    def save_settings(self) -> None:
        self.save_button.start_loading('Saving...')
        QApplication.processEvents()
        settings = self.window.settings
        settings['theme'] = self.theme_combo.currentText()
        settings['currency'] = self.currency_combo.currentText()
        settings['date_format'] = self.date_combo.currentText()
        settings['refresh_interval'] = self.refresh_combo.currentText()
        settings['risk_tier'] = getattr(self, '_current_risk_tier', 'regular')
        settings['direction_thresholds'] = {
            'strong': self.strong_spin.value(),
            'steady': self.steady_spin.value(),
            'neutral_low': self.neutral_low_spin.value(),
            'neutral_high': self.neutral_high_spin.value(),
            'depreciating': self.depreciating_spin.value(),
        }
        settings['volatility'] = {
            'lookback': self.lookback_combo.currentText(),
            'lookback_period': VOLATILITY_LOOKBACK_PERIODS[self.lookback_combo.currentText()],
            'low_cutoff': self.low_vol_spin.value(),
            'high_cutoff': self.high_vol_spin.value(),
        }
        settings['lens_signals'] = {
            'stock_concentration_pct': self.stock_conc_spin.value(),
            'sector_concentration_pct': self.sector_conc_spin.value(),
            'steep_downtrend_pct': self.steep_dt_spin.value(),
            'high_beta_threshold': round(self.high_beta_spin.value(), 1),
            'stock_vol_threshold_pct': self.stock_vol_spin.value(),
            'dead_weight_pct': self.dead_weight_spin.value(),
            'loss_threshold': self.loss_threshold_spin.value(),
            'winner_drift_multiple': round(self.winner_drift_spin.value(), 1),
        }
        settings['monte_carlo'] = {
            'projection_period': self.mc_period_combo.currentText(),
            'simulations': int(self.mc_sims_combo.currentText()),
        }
        self.window.settings = settings
        self.window.store.save_settings(settings)
        self.window.apply_theme()
        self.window.refresh_data()
        self._style_note.setVisible(False)
        self.save_button.stop_loading('Save Settings')

    def _run_lens_test(self) -> None:
        if self._lens_test_worker is not None and self._lens_test_worker.isRunning():
            return
        self.run_lens_test_button.start_loading('Running...')
        self._lens_test_status.setText('Starting...')
        worker = _DebugTestWorker(self.window.store, dict(self.window.settings), self)
        worker.progress.connect(self._on_lens_test_progress)
        worker.done.connect(self._on_lens_test_done)
        self._lens_test_worker = worker
        worker.start()

    def _on_lens_test_progress(self, current: int, total: int, message: str) -> None:
        self._lens_test_status.setText(f'[{current}/{total}] {message}')

    def _on_lens_test_done(self, output_path, error) -> None:
        self.run_lens_test_button.stop_loading('Run Lens Test')
        if error is not None:
            self._lens_test_status.setText(f'Failed: {error}')
        else:
            self._lens_test_status.setText(f'Done — wrote {output_path}')
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path)))
            except Exception:
                pass
        if self._lens_test_worker is not None:
            self._lens_test_worker.deleteLater()
            self._lens_test_worker = None

    def _export_to_csv(self) -> None:
        import csv
        from datetime import datetime

        default_name = f'vector_positions_{datetime.now().strftime("%Y-%m-%d")}.csv'
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Positions', default_name, 'CSV Files (*.csv)',
        )
        if not path:
            return

        self._export_csv_button.start_loading('Exporting...')
        QApplication.processEvents()

        positions = self.window.positions or []
        store = self.window.store
        refresh = self.window.settings.get('refresh_interval', '5 min')

        rows: list[dict] = []
        for p in positions:
            ticker = p.get('ticker', '')
            shares = float(p.get('shares', 0) or 0)
            cost_basis = float(p.get('equity', 0) or 0)
            entry_price = cost_basis / shares if shares > 0 else 0.0
            current_price = 0.0
            try:
                snap = store.get_snapshot(ticker, refresh) or {}
                current_price = float(snap.get('price', 0) or 0)
            except Exception:
                current_price = float(p.get('price', 0) or 0)
            current_value = shares * current_price
            pnl_dollar = current_value - cost_basis
            pnl_pct = (current_value / cost_basis - 1) * 100 if cost_basis > 0 else 0.0
            rows.append({
                'ticker': ticker,
                'name': p.get('name', ''),
                'sector': p.get('sector', ''),
                'shares': shares,
                'entry_price': round(entry_price, 2),
                'current_price': round(current_price, 2),
                'cost_basis': round(cost_basis, 2),
                'current_value': round(current_value, 2),
                'unrealized_pnl_dollar': round(pnl_dollar, 2),
                'unrealized_pnl_pct': round(pnl_pct, 2),
                'added_at': p.get('added_at', ''),
            })

        error: str | None = None
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            error = str(e)

        self._export_csv_button.stop_loading('Export Positions to CSV')
        if error:
            QMessageBox.warning(self, 'Export Failed', f'Could not export: {error}')
        else:
            QMessageBox.information(
                self, 'Export Complete',
                f'Exported {len(rows)} position{"s" if len(rows) != 1 else ""} to\n{path}',
            )

    def remove_selected_position(self) -> None:
        item = self.remove_list.currentItem()
        if not item:
            return
        ticker = item.data(Qt.ItemDataRole.UserRole)
        confirm = QMessageBox.question(self, 'Remove Position', f'Remove {ticker} from the portfolio?')
        if confirm == QMessageBox.StandardButton.Yes:
            self.window.positions = [position for position in self.window.positions if position['ticker'] != ticker]
            self.window.store.save_positions(self.window.positions)
            self.window.refresh_data()
            self.load_from_settings(self.window.settings, self.window.positions)
