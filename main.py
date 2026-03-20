#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Редактор исторических карт ВОВ
Главный файл запуска приложения
"""

import sys
import os
import json
import uuid

from PyQt6.QtWidgets import (
		QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
		QPushButton, QLabel, QSlider, QColorDialog, QFileDialog,
		QInputDialog, QMessageBox, QSplitter, QTreeWidget, QTreeWidgetItem,
		QToolButton, QStatusBar, QComboBox, QSpinBox, QCheckBox, QDialog,
		QDialogButtonBox, QLineEdit, QFormLayout, QGroupBox, QSizePolicy,
		QAbstractItemView, QStyledItemDelegate, QSplashScreen, QStyle
)
from PyQt6.QtCore import (
		Qt, QUrl, QObject, pyqtSlot, pyqtSignal, QSize, QTimer, QRect, QEvent
)
from PyQt6.QtGui import QIcon, QColor, QKeySequence, QShortcut, QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel

from bridge import Bridge

CONFIG_FILE = "config.json"
MAP_HTML    = os.path.join(os.path.dirname(__file__), "map.html")


def load_config():
		if os.path.exists(CONFIG_FILE):
				with open(CONFIG_FILE, "r", encoding="utf-8") as f:
						return json.load(f)
		return {}


def save_config(cfg: dict):
		with open(CONFIG_FILE, "w", encoding="utf-8") as f:
				json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── Диалог ввода API-ключа ──────────────────────
class ApiKeyDialog(QDialog):
		def __init__(self, parent=None, current_key=""):
				super().__init__(parent)
				self.setWindowTitle("Яндекс Maps API-ключ")
				self.setMinimumWidth(480)
				layout = QVBoxLayout(self)

				info = QLabel(
						"Для отображения тайлов Яндекса введите API-ключ.\n"
						"Получить ключ: https://developer.tech.yandex.ru/\n"
						"Тип: «Карты JS API и HTTP Геокодер»"
				)
				info.setWordWrap(True)
				layout.addWidget(info)

				form = QFormLayout()
				self.key_edit = QLineEdit(current_key)
				self.key_edit.setPlaceholderText("Вставьте API-ключ сюда")
				form.addRow("API-ключ:", self.key_edit)
				layout.addLayout(form)

				btns = QDialogButtonBox(
						QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
				)
				btns.accepted.connect(self.accept)
				btns.rejected.connect(self.reject)
				layout.addWidget(btns)

		def get_key(self):
				return self.key_edit.text().strip()


# ── FIX #7: Диалог редактирования текстового объекта ────────
class TextEditDialog(QDialog):
		def __init__(self, parent=None, obj_data: dict = None):
				super().__init__(parent)
				self.setWindowTitle("Редактировать текст")
				self.setMinimumWidth(400)
				obj_data = obj_data or {}

				layout = QVBoxLayout(self)
				form = QFormLayout()

				self.text_edit = QLineEdit(obj_data.get("text", ""))
				form.addRow("Текст:", self.text_edit)

				self.size_spin = QSpinBox()
				self.size_spin.setRange(8, 120)
				self.size_spin.setValue(int(obj_data.get("fontSize", 14)))
				form.addRow("Размер шрифта:", self.size_spin)

				self._color = obj_data.get("fontColor", "#000000")
				self.color_btn = QPushButton()
				self.color_btn.setFixedHeight(28)
				self._update_color_btn()
				self.color_btn.clicked.connect(self._pick_color)
				form.addRow("Цвет:", self.color_btn)

				style_row = QHBoxLayout()
				self.bold_cb   = QCheckBox("Жирный")
				self.italic_cb = QCheckBox("Курсив")
				self.bold_cb.setChecked(bool(obj_data.get("fontBold", True)))
				self.italic_cb.setChecked(bool(obj_data.get("fontItalic", False)))
				style_row.addWidget(self.bold_cb)
				style_row.addWidget(self.italic_cb)
				style_row.addStretch()
				form.addRow("Начертание:", style_row)

				layout.addLayout(form)

				btns = QDialogButtonBox(
						QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
				)
				btns.accepted.connect(self.accept)
				btns.rejected.connect(self.reject)
				layout.addWidget(btns)

		def _pick_color(self):
				c = QColorDialog.getColor(QColor(self._color), self, "Цвет текста")
				if c.isValid():
						self._color = c.name()
						self._update_color_btn()

		def _update_color_btn(self):
				lightness = QColor(self._color).lightness()
				fg = "#000" if lightness > 128 else "#fff"
				self.color_btn.setText(self._color)
				self.color_btn.setStyleSheet(
						f"background:{self._color};color:{fg};border-radius:4px;padding:2px 8px;"
				)

		def get_values(self):
				return {
						"text":      self.text_edit.text(),
						"fontSize":  self.size_spin.value(),
						"fontColor": self._color,
						"fontBold":  self.bold_cb.isChecked(),
						"fontItalic": self.italic_cb.isChecked(),
				}


# ── Панель инструментов ───────────────────────────
class ToolButton(QToolButton):
		def __init__(self, text, tooltip, shortcut="", parent=None):
				super().__init__(parent)
				self.setText(text)
				self.setToolTip(f"{tooltip}" + (f"  [{shortcut}]" if shortcut else ""))
				self.setCheckable(True)
				self.setFixedSize(48, 48)
				self.setFont(QFont("Segoe UI Emoji", 14))


# ── Элемент дерева слоёв ──────────────────────────
class LayerItem(QTreeWidgetItem):
		def __init__(self, layer_id: str, name: str, is_group=False, object_type: str = ""):
				super().__init__()
				self.layer_id    = layer_id
				self.is_group    = is_group
				self.object_type = object_type
				self.visible     = True
				self.opacity     = 100
				self.setText(0, name)
				self._update_icon()

		def _update_icon(self):
				if self.visible:
						self.setText(1, "👁")
						self.setBackground(1, QColor("transparent"))
				else:
						self.setText(1, "  ")
						self.setBackground(1, QColor("#3a3a3a"))
				tree = self.treeWidget()
				if tree:
						tree.viewport().update()

		def toggle_visibility(self):
				self.visible = not self.visible
				self._update_icon()
				bg = self.background(1).color()



# ── QTreeWidget с перехватом dropEvent ────────────────────
class LayerTree(QTreeWidget):
		"""Сигнал об изменении порядка слоёв после drag-and-drop."""
		orderChanged = pyqtSignal()

		def dropEvent(self, event):
				super().dropEvent(event)
				self.orderChanged.emit()

class EyeColumnDelegate(QStyledItemDelegate):
		def paint(self, painter, option, index):
				if index.column() == 1:
						# Берём цвет фона который мы установили через setBackground
						bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
						if bg_brush is not None:
								color = bg_brush if isinstance(bg_brush, QColor) else bg_brush.color()
								if color.alpha() > 0:
									r = option.rect
									size = min(r.width(), r.height()) - 6  # квадрат, отступ 3px
									x = r.x() + (r.width() - size) // 2
									y = r.y() + (r.height() - size) // 2
									from PyQt6.QtCore import QRect
									sq = QRect(x, y, size, size)

									painter.fillRect(sq, color)
									painter.setPen(QColor("#1a1a1a"))
									painter.drawLine(sq.topLeft(), sq.topRight())
									painter.drawLine(sq.topLeft(), sq.bottomLeft())
									painter.setPen(QColor("#5a5a5a"))
									painter.drawLine(sq.bottomLeft(), sq.bottomRight())
									painter.drawLine(sq.topRight(), sq.bottomRight())
						# Рисуем текст (глазок) поверх фона
						text = index.data(Qt.ItemDataRole.DisplayRole)
						if text:
								painter.setPen(QColor("#e0e0e0"))
								painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)
				else:
						super().paint(painter, option, index)

class VovLoadingOverlay(QWidget):
		def __init__(self, parent):
				super().__init__(parent)
				self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
				self.setAutoFillBackground(False)
				self._status_text = "Инициализация..."
				self._dot_count = 0
				self._dot_timer = QTimer(self)
				self._dot_timer.timeout.connect(self._tick_dots)
				self._dot_timer.start(400)

		def _tick_dots(self):
				self._dot_count = (self._dot_count + 1) % 4
				self.update()

		def set_status(self, msg: str):
				self._status_text = msg
				self.update()

		def show_over(self):
				self.setGeometry(self.parent().rect())
				self.raise_()
				self.show()

		def resizeEvent(self, event):
				if self.parent():
						self.setGeometry(self.parent().rect())

		def finish(self):
				self._dot_timer.stop()
				self.hide()
				self.deleteLater()

		def paintEvent(self, event):
				from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QLinearGradient, QPixmap
				from PyQt6.QtCore import QRect, QPoint
				p = QPainter(self)
				p.setRenderHint(QPainter.RenderHint.Antialiasing)
				W, H = self.width(), self.height()

				# Фон
				p.fillRect(0, 0, W, H, QColor("#1a1a2e"))

				# Картографическая сетка
				grid_pen = QPen(QColor("#1e2240"), 1)
				p.setPen(grid_pen)
				STEP = 48
				for x in range(0, W, STEP):
						p.drawLine(x, 0, x, H)
				for y in range(0, H, STEP):
						p.drawLine(0, y, W, y)

				# Watermark "1941–1945"
				wm_font = QFont("Segoe UI", 96, QFont.Weight.Bold)
				p.setFont(wm_font)
				p.setPen(QColor(255, 255, 255, 14))
				p.drawText(QRect(0, H//2 - 140, W, 180), Qt.AlignmentFlag.AlignCenter, "1941–1945")

				# Декоративная линия фронта
				front_pen = QPen(QColor("#8B0000"), 3)
				front_pen.setStyle(Qt.PenStyle.DashLine)
				p.setPen(front_pen)
				step_x = W / 9
				pts = [QPoint(int(i * step_x), int(H // 2 + ((-1)**i) * 30)) for i in range(10)]
				pts[0] = QPoint(0, H//2 - 10)
				pts[-1] = QPoint(W, H//2 + 10)
				for i in range(len(pts) - 1):
						p.drawLine(pts[i], pts[i+1])
				cross_pen = QPen(QColor("#cc0000"), 2)
				p.setPen(cross_pen)
				for pt in pts[::2]:
						p.drawLine(pt.x()-6, pt.y(), pt.x()+6, pt.y())
						p.drawLine(pt.x(), pt.y()-6, pt.x(), pt.y()+6)

				# Верхняя красная полоска
				p.fillRect(QRect(0, 0, W, 5), QColor("#8B0000"))

				# Нижняя тёмная полоса
				p.fillRect(QRect(0, H - 80, W, 80), QColor("#12122a"))

				# Иконка
				icon_font = QFont("Segoe UI Emoji", 52)
				p.setFont(icon_font)
				p.setPen(QColor("#c0c0c0"))
				p.drawText(QRect(0, H//2 - 200, W, 100), Qt.AlignmentFlag.AlignCenter, "🗺")

				# Заголовок
				title_font = QFont("Segoe UI", 28, QFont.Weight.Bold)
				p.setFont(title_font)
				p.setPen(QColor("#e8e8e8"))
				p.drawText(QRect(0, H//2 - 110, W, 52), Qt.AlignmentFlag.AlignCenter, "Редактор карт ВОВ")

				# Подзаголовок
				sub_font = QFont("Segoe UI", 14)
				p.setFont(sub_font)
				p.setPen(QColor("#7a8a9a"))
				p.drawText(QRect(0, H//2 - 58, W, 32), Qt.AlignmentFlag.AlignCenter,
									 "Великая Отечественная война  •  1941–1945")

				# Разделитель
				sep_pen = QPen(QColor("#8B0000"), 1)
				p.setPen(sep_pen)
				p.drawLine(W//4, H//2 - 18, W*3//4, H//2 - 18)

				# Статус + анимированные точки
				status_font = QFont("Segoe UI", 12)
				p.setFont(status_font)
				p.setPen(QColor("#4a9aba"))
				dots = "." * self._dot_count
				p.drawText(QRect(0, H - 62, W, 30),
									 Qt.AlignmentFlag.AlignCenter,
									 "⚙  " + self._status_text + dots)

				# Версия
				ver_font = QFont("Segoe UI", 10)
				p.setFont(ver_font)
				p.setPen(QColor("#3a4a5a"))
				p.drawText(QRect(0, H - 30, W - 16, 22),
									 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
									 "v1.0")
				p.end()

class OpacitySlider(QSlider):
		def __init__(self, parent=None):
				super().__init__(Qt.Orientation.Horizontal, parent)

		def mousePressEvent(self, event):
				if event.button() == Qt.MouseButton.LeftButton:
						val = QStyle.sliderValueFromPosition(
								self.minimum(), self.maximum(),
								event.position().toPoint().x(),
								self.width()
						)
						self.setValue(val)
				super().mousePressEvent(event)

# ── Главное окно ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
		def __init__(self):
				super().__init__()
				self.setWindowTitle("Редактор карт ВОВ")
				self.resize(1400, 900)

				self.config = load_config()
				self._current_project_path = None
				self._active_layer_id      = None
				self._current_tool         = "select"
				self._brush_color          = "#ff0000"
				self._brush_size           = 4
				self._eraser_size          = 20
				self._font_size            = 14
				self._font_color           = "#000000"
				self._font_bold            = True
				self._font_italic          = False
				self._export_path          = None
				self._selected_obj_id      = None  # FIX BUG-10: инициализация

				self._setup_ui()
				self._setup_shortcuts()

				if not self.config.get("yandex_api_key"):
						QTimer.singleShot(500, self._ask_api_key)

		def _setup_ui(self):
				self.setStyleSheet(DARK_STYLE)
				central = QWidget()
				self.setCentralWidget(central)
				root_layout = QVBoxLayout(central)
				root_layout.setContentsMargins(0, 0, 0, 0)
				root_layout.setSpacing(0)
				root_layout.addWidget(self._build_topbar())

				work = QHBoxLayout()
				work.setContentsMargins(0, 0, 0, 0)
				work.setSpacing(0)

				work.addWidget(self._build_tools_panel())
				work.addWidget(self._build_webview(), stretch=1)

				right_panel = QWidget()
				right_panel.setObjectName("rightPanel")
				right_lay = QVBoxLayout(right_panel)
				right_lay.setContentsMargins(0, 0, 0, 0)
				right_lay.setSpacing(0)
				right_lay.addWidget(self._build_statusbar())
				right_lay.addWidget(self._build_layers_panel(), stretch=1)
				work.addWidget(right_panel)

				root_layout.addLayout(work, stretch=1)

		def _build_topbar(self):
				bar = QWidget()
				bar.setFixedHeight(42)
				bar.setObjectName("topbar")
				lay = QHBoxLayout(bar)
				lay.setContentsMargins(8, 4, 8, 4)
				self.project_label = QLabel("Новый проект")
				self.project_label.setStyleSheet("font-size:14px;font-weight:bold;color:#e0e0e0;")
				lay.addWidget(self.project_label)
				lay.addStretch()
				for txt, tip, slot in [
						("📂 Открыть",  "Ctrl+O",  self._open_project),
						("💾 Сохранить", "Ctrl+S",  self._save_project),
						("📤 Экспорт",  "Ctrl+E",  self._export_png),
						("🔑 API-ключ", "Настроить ключ Яндекса", self._ask_api_key),
				]:
						btn = QPushButton(txt)
						btn.setToolTip(tip)
						btn.clicked.connect(slot)
						btn.setFixedHeight(30)
						lay.addWidget(btn)
				lay.addSpacing(12)
				lay.addWidget(QLabel("Слой:"))
				self.tile_combo = QComboBox()
				self.tile_combo.addItems(["Схема", "Спутник", "Гибрид"])
				self.tile_combo.currentIndexChanged.connect(self._change_tile_layer)
				self.tile_combo.setFixedWidth(100)
				lay.addWidget(self.tile_combo)
				return bar

		def _build_layers_panel(self):
				panel = QWidget()
				panel.setFixedWidth(250)
				panel.setObjectName("layersPanel")
				lay = QVBoxLayout(panel)
				lay.setContentsMargins(4, 4, 4, 4)
				lay.setSpacing(4)
				lbl = QLabel("СЛОИ")
				lbl.setStyleSheet("color:#aaa;font-size:11px;font-weight:bold;")
				lay.addWidget(lbl)

				opacity_row = QHBoxLayout()
				opacity_row.addWidget(QLabel("Непрозрачность:"))
				self.opacity_slider = OpacitySlider()
				self.opacity_slider.setRange(0, 100)
				self.opacity_slider.setValue(100)
				self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
				opacity_row.addWidget(self.opacity_slider)
				self.opacity_lbl = QLabel("100%")
				self.opacity_lbl.setFixedWidth(36)
				opacity_row.addWidget(self.opacity_lbl)
				lay.addLayout(opacity_row)

				btn_row = QHBoxLayout()
				for txt, tip, slot in [
						("📁", "Добавить группу",  self._add_group),
						("➕", "Добавить слой",    self._add_layer),
						("🗑", "Удалить выбранный",self._delete_layer),
				]:
						b = QPushButton(txt)
						b.setToolTip(tip)
						b.setFixedHeight(28)
						b.clicked.connect(slot)
						btn_row.addWidget(b)
				lay.addLayout(btn_row)

				self.layer_tree = LayerTree()
				self.layer_tree.setColumnCount(2)
				self.layer_tree.setHeaderHidden(True)
				self.layer_tree.setColumnWidth(0, 190)  # имя — колонка 0 (иерархия)
				self.layer_tree.setColumnWidth(1, 28)   # глаз — колонка 1
				# Визуально переставить колонку 1 (глаз) на позицию 0:
				self.layer_tree.header().moveSection(1, 0)
				self.layer_tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
				self.layer_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
				self.layer_tree.itemClicked.connect(self._on_layer_clicked)
				self.layer_tree.itemDoubleClicked.connect(self._on_layer_double_clicked)
				self.layer_tree.orderChanged.connect(self._on_layer_order_changed)
				self.layer_tree.setStyleSheet("""
						QTreeWidget { background:#1e1e1e; border:none; color:#e0e0e0; }
						QTreeWidget::item { border-bottom: 1px solid #2a2a2a; padding: 2px 0px; }
						QTreeWidget::item:hover    { background:#2a3a4a; }
						QTreeWidget::item:selected { background:#1a5276; }
				""")
				lay.addWidget(self.layer_tree)
				self.layer_tree.setItemDelegate(EyeColumnDelegate(self.layer_tree))
				return panel

		def _build_webview(self):
				self.webview = QWebEngineView()
				settings = self.webview.settings()
				settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
				settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
				self.channel = QWebChannel()
				self.bridge  = Bridge(self)
				self.channel.registerObject("bridge", self.bridge)
				self.webview.page().setWebChannel(self.channel)
				self.webview.load(QUrl.fromLocalFile(MAP_HTML))
				self.webview.loadFinished.connect(self._on_map_loaded)
				self.webview.installEventFilter(self)
				return self.webview

		def _build_tools_panel(self):
				panel = QWidget()
				panel.setFixedWidth(56)
				panel.setObjectName("toolsPanel")
				lay = QVBoxLayout(panel)
				lay.setContentsMargins(4, 8, 4, 8)
				lay.setAlignment(Qt.AlignmentFlag.AlignTop)
				self.tool_buttons = {}
				tools = [
						("select",  "🖱",  "Выбор",   "V"),
						("brush",   "🖌",  "Кисть",   "B"),
						("eraser",  "⬜",  "Ластик",  "E"),
						("text",    "T",   "Текст",   "T"),
						("import",  "🖼",  "Импорт",  ""),
				]
				for tid, icon, tip, sc in tools:
						btn = ToolButton(icon, tip, sc)
						btn.clicked.connect(lambda checked, t=tid: self._set_tool(t))
						lay.addWidget(btn)
						self.tool_buttons[tid] = btn
				self.tool_buttons["select"].setChecked(True)
				return panel

		def _build_statusbar(self):
				bar = QWidget()
				bar.setFixedWidth(250)
				bar.setObjectName("statusBar")
				lay = QVBoxLayout(bar)
				lay.setContentsMargins(8, 6, 8, 6)
				lay.setSpacing(6)

				lbl = QLabel("НАСТРОЙКИ")
				lbl.setStyleSheet("color:#aaa;font-size:11px;font-weight:bold;")
				lay.addWidget(lbl)

				self.color_btn = QPushButton("  🎨 Цвет кисти  ")
				self.color_btn.setFixedHeight(28)
				self.color_btn.clicked.connect(self._pick_brush_color)
				self._update_color_button()
				lay.addWidget(self.color_btn)

				row1 = QHBoxLayout()
				row1.addWidget(QLabel("Толщина:"))
				self.brush_slider = QSlider(Qt.Orientation.Horizontal)
				self.brush_slider.setRange(1, 20)
				self.brush_slider.setValue(self._brush_size)
				self.brush_slider.valueChanged.connect(self._on_brush_size_changed)
				row1.addWidget(self.brush_slider)
				self.brush_size_lbl = QLabel(str(self._brush_size))
				self.brush_size_lbl.setFixedWidth(20)
				row1.addWidget(self.brush_size_lbl)
				lay.addLayout(row1)

				row2 = QHBoxLayout()
				row2.addWidget(QLabel("Ластик:"))
				self.eraser_slider = QSlider(Qt.Orientation.Horizontal)
				self.eraser_slider.setRange(5, 100)
				self.eraser_slider.setValue(self._eraser_size)
				self.eraser_slider.valueChanged.connect(self._on_eraser_size_changed)
				row2.addWidget(self.eraser_slider)
				self.eraser_size_lbl = QLabel(str(self._eraser_size))
				self.eraser_size_lbl.setFixedWidth(24)
				row2.addWidget(self.eraser_size_lbl)
				lay.addLayout(row2)

				row3 = QHBoxLayout()
				row3.addWidget(QLabel("Шрифт:"))
				self.font_size_spin = QSpinBox()
				self.font_size_spin.setRange(8, 72)
				self.font_size_spin.setValue(self._font_size)
				self.font_size_spin.setFixedWidth(56)
				self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
				row3.addWidget(self.font_size_spin)
				self.font_color_btn = QPushButton("🔤 Цвет")
				self.font_color_btn.setFixedHeight(26)
				self.font_color_btn.clicked.connect(self._pick_font_color)
				row3.addWidget(self.font_color_btn)
				lay.addLayout(row3)

				row4 = QHBoxLayout()
				self.bold_cb = QCheckBox("Ж")
				self.bold_cb.setChecked(True)
				self.bold_cb.stateChanged.connect(self._on_font_bold_changed)
				row4.addWidget(self.bold_cb)
				self.italic_cb = QCheckBox("К")
				self.italic_cb.stateChanged.connect(self._on_font_italic_changed)
				row4.addWidget(self.italic_cb)
				row4.addStretch()
				lay.addLayout(row4)

				lay.addStretch()

				self.status_lbl = QLabel("Готово")
				self.status_lbl.setStyleSheet("color:#888;font-size:11px;")
				self.status_lbl.setWordWrap(True)
				lay.addWidget(self.status_lbl)

				return bar

		def _setup_shortcuts(self):
				QShortcut(QKeySequence("V"),      self, lambda: self._set_tool("select"))
				QShortcut(QKeySequence("B"),      self, lambda: self._set_tool("brush"))
				QShortcut(QKeySequence("E"),      self, lambda: self._set_tool("eraser"))
				QShortcut(QKeySequence("T"),      self, lambda: self._set_tool("text"))
				QShortcut(QKeySequence("Ctrl+O"), self, self._open_project)
				QShortcut(QKeySequence("Ctrl+E"), self, self._export_png)
				QShortcut(QKeySequence("Ctrl+S"), self, self._save_project)
				QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)
				QShortcut(QKeySequence("Delete"), self, self._delete_selected)

		def _js_log(self, msg: str):
				safe = msg.replace("\\", "\\\\").replace("'", "\\'")
				self._js(f"log('[PY] {safe}');")

		def _on_map_loaded(self, ok):
				if not ok:
						self.status_lbl.setText("Ошибка загрузки карты!")
						return
				api_key = self.config.get("yandex_api_key", "")
				self._js(f'initMap({json.dumps(api_key)});')
				self.status_lbl.setText("Карта загружена")
				self._js_log("App started, map loaded")
				last = self.config.get("last_project", "")
				if last and os.path.exists(last):
					self._js_log(f"Auto-opening last project: {os.path.basename(last)} (timer=800ms)")
					QTimer.singleShot(800, lambda: self._load_project_from_path(last))

		def _set_tool(self, tool: str):
				self._current_tool = tool
				for tid, btn in self.tool_buttons.items():
						btn.setChecked(tid == tool)
				if tool == "import":
						self._import_image()
						self._set_tool("select")
						return
				params = json.dumps({
						"tool":       tool,
						"color":      self._brush_color,
						"size":       self._brush_size,
						"eraserSize": self._eraser_size,
						"fontSize":   self._font_size,
						"fontColor":  self._font_color,
						"fontBold":   self._font_bold,
						"fontItalic": self._font_italic,
				})
				self._js(f"setTool({params});")
				self.status_lbl.setText(f"Инструмент: {tool}")
				self._js_log(f"Tool selected: {tool}")

		def _add_group(self):
				name, ok = QInputDialog.getText(self, "Новая группа", "Название группы:")
				if not ok or not name: return
				lid = f"group_{uuid.uuid4().hex[:8]}"
				# FIX BUG-11: не строим дерево вручную — JS является источником правды
				self._js(f'addLayerGroup("{lid}", {json.dumps(name)});')
				self._js("sendLayersToQt();")
				self._js_log(f"Group added: '{name}' id={lid}")

		def _add_layer(self):
				name, ok = QInputDialog.getText(self, "Новый слой", "Название слоя:")
				if not ok or not name: return
				lid = f"layer_{uuid.uuid4().hex[:8]}"
				selected = self.layer_tree.currentItem()
				parent_id = ""
				if selected and isinstance(selected, LayerItem) and selected.is_group:
						parent_id = selected.layer_id
				# FIX BUG-11: не строим дерево вручную — JS является источником правды
				self._js(f'addLayer("{lid}", {json.dumps(name)}, "{parent_id}");')
				self._js("sendLayersToQt();")
				self._js_log(f"Layer added: '{name}' id={lid} parent={parent_id}")

		def _delete_layer(self):
				item = self.layer_tree.currentItem()
				if not item or not isinstance(item, LayerItem): return
				# Не удаляем объекты-листья — только слои и группы
				if item.object_type:
						return
				lid = item.layer_id
				name = item.text(0)
				# FIX BUG-11: не трогаем дерево вручную — JS пересоберёт через sendLayersToQt
				self._js(f'removeLayer("{lid}");')
				self._js("sendLayersToQt();")
				self._active_layer_id = None
				self._js_log(f"Layer deleted: '{name}' id={lid}")

		def _on_layer_clicked(self, item, col):
				if not isinstance(item, LayerItem): return
				if col == 1:
						item.toggle_visibility()
						vis = item.visible
						if item.object_type:
								self._js(f'setObjectVisible("{item.layer_id}", {str(vis).lower()});')
								self._js_log(f"Object visibility: '{item.text(0)}' -> {vis}")
						else:
								self._js(f'setLayerVisible("{item.layer_id}", {str(vis).lower()});')
								self._js_log(f"Layer visibility: '{item.text(0)}' -> {vis}")
								if item.is_group:
										self._set_children_visibility(item, vis)
				else:
						if not item.is_group and not item.object_type:
								self._activate_layer(item)
						elif item.object_type:
								self._js(f'selectObjectById("{item.layer_id}")')
								self._clear_highlight(self.layer_tree.invisibleRootItem())
								item.setBackground(0, QColor("#1a5276"))
								item.setBackground(1, QColor("#1a5276"))
						self._sync_opacity_slider(item)


		def _set_children_visibility(self, parent_item: LayerItem, visible: bool):
				"""Рекурсивно применяет видимость ко всем дочерним LayerItem (слоям, не объектам)."""
				for i in range(parent_item.childCount()):
						child = parent_item.child(i)
						if not isinstance(child, LayerItem):
								continue
						if child.object_type:
								continue  # пропускаем объекты-листья
						child.visible = visible
						child._update_icon()
						bg = child.background(1).color()
						self._js(f'setLayerVisible("{child.layer_id}", {str(visible).lower()});')
						self._js_log(f"Child visibility: '{child.text(0)}' -> {visible}")
						if child.is_group:
								self._set_children_visibility(child, visible)

		def _on_layer_double_clicked(self, item, col):
				if not isinstance(item, LayerItem): return
				if item.object_type:
						return  # двойной клик по объекту-листу — не переименовываем
				raw_name = item.text(0)
				old_name = raw_name.replace("📁 ", "", 1) if item.is_group else raw_name
				name, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=old_name)
				if ok and name:
						display = ("📁 " + name) if item.is_group else name
						item.setText(0, display)
						self._js(f'renameLayer("{item.layer_id}", {json.dumps(name)});')
						self._js_log(f"Layer renamed: '{old_name}' -> '{name}'")

		def _activate_layer(self, item: LayerItem):
				self._active_layer_id = item.layer_id
				for i in range(self.layer_tree.topLevelItemCount()):
						self._clear_highlight(self.layer_tree.topLevelItem(i))
				item.setBackground(0, QColor("#1a5276"))
				item.setBackground(1, QColor("#1a5276"))
				self._js(f'setActiveLayer("{item.layer_id}");')
				self.status_lbl.setText(f"Активный слой: {item.text(0)}")
				self._js_log(f"Active layer: '{item.text(0)}' id={item.layer_id}")
				self._sync_opacity_slider(item)

		def _clear_highlight(self, item):
				item.setBackground(0, QColor("transparent"))
				item.setBackground(1, QColor("transparent"))
				for i in range(item.childCount()):
						self._clear_highlight(item.child(i))

		def _highlight_tree_item(self, obj_id: str | None):
				if not obj_id:
						self.layer_tree.setCurrentItem(None)
						return
				def find(item):
						if isinstance(item, LayerItem) and item.layer_id == obj_id:
								self.layer_tree.setCurrentItem(item)
								self.layer_tree.scrollToItem(item)
								return True
						for i in range(item.childCount()):
								if find(item.child(i)):
										return True
						return False
				find(self.layer_tree.invisibleRootItem())

		def _on_layer_order_changed(self):
				order = []
				root = self.layer_tree.invisibleRootItem()
				for i in range(root.childCount()):
						top = root.child(i)
						if isinstance(top, LayerItem) and not top.object_type:
								order.append(top.layer_id)
								for j in range(top.childCount()):
										child = top.child(j)
										if isinstance(child, LayerItem) and not child.object_type:
												order.append(child.layer_id)
				self._js(f'reorderLayers({json.dumps(order)});')
				self._js_log(f"Layer order changed: {order}")

		def _on_opacity_changed(self, value: int):
				self.opacity_lbl.setText(f"{value}%")
				item = self.layer_tree.currentItem()
				if not isinstance(item, LayerItem):
						return
				item.opacity = value
				if item.object_type:
						self._js(f"setObjectOpacity(\"{item.layer_id}\", {value});")
						self._js_log(f"Opacity: object={item.layer_id} -> {value}%")
				elif item.is_group:
						self._js(f"setGroupOpacity(\"{item.layer_id}\", {value});")
						self._js_log(f"Opacity: group={item.layer_id} -> {value}%")
				else:
						self._js(f"setLayerOpacity(\"{item.layer_id}\", {value});")
						self._js_log(f"Opacity: layer={item.layer_id} -> {value}%")

		def _sync_opacity_slider(self, item):
				if not isinstance(item, LayerItem):
						return
				opacity = getattr(item, 'opacity', 100)
				self.opacity_slider.blockSignals(True)
				self.opacity_slider.setValue(opacity)
				self.opacity_lbl.setText(f"{opacity}%")
				self.opacity_slider.blockSignals(False)

		def _pick_brush_color(self):
				c = QColorDialog.getColor(QColor(self._brush_color), self, "Цвет кисти")
				if c.isValid():
						self._brush_color = c.name()
						self._update_color_button()
						self._js(f'setBrushColor("{self._brush_color}");')
						self._js_log(f"Brush color: {self._brush_color}")

		def _update_color_button(self):
				self.color_btn.setStyleSheet(
						f"background:{self._brush_color};color:{'#000' if QColor(self._brush_color).lightness()>128 else '#fff'};"
						"border-radius:4px;padding:2px 8px;"
				)

		def _on_brush_size_changed(self, v):
				self._brush_size = v
				self.brush_size_lbl.setText(str(v))
				self._js(f"setBrushSize({v});")
				self._js_log(f"Brush size: {v}")

		def _on_eraser_size_changed(self, v):
				self._eraser_size = v
				self.eraser_size_lbl.setText(str(v))
				self._js(f"setEraserSize({v});")
				self._js_log(f"Eraser size: {v}")

		def _on_font_size_changed(self, v):
				self._font_size = v
				self._js(f"setFontSize({v});")
				self._js_log(f"Font size: {v}")

		def _pick_font_color(self):
				c = QColorDialog.getColor(QColor(self._font_color), self, "Цвет текста")
				if c.isValid():
						self._font_color = c.name()
						self._js(f'setFontColor("{self._font_color}");')
						self._js_log(f"Font color: {self._font_color}")

		def _on_font_bold_changed(self, state):
				self._font_bold = bool(state)
				self._js(f"setFontBold({str(self._font_bold).lower()});")
				self._js_log(f"Font bold: {self._font_bold}")

		def _on_font_italic_changed(self, state):
				self._font_italic = bool(state)
				self._js(f"setFontItalic({str(self._font_italic).lower()});")
				self._js_log(f"Font italic: {self._font_italic}")

		def _change_tile_layer(self, idx):
				types = ["map", "sat", "skl"]
				names = ["Схема", "Спутник", "Гибрид"]
				key = self.config.get("yandex_api_key", "")
				self._js(f'changeTileLayer("{types[idx]}", {json.dumps(key)});')
				self._js_log(f"Tile layer: {names[idx]}")

		def _import_image(self):
				path, _ = QFileDialog.getOpenFileName(
						self, "Выбрать изображение", "", "Images (*.png *.jpg *.jpeg *.bmp)"
				)
				if not path: return
				path_js = path.replace("\\", "/")
				self._js(f'importImage("file:///{path_js}");')
				self._js_log(f"Image imported: {os.path.basename(path)}")

		def _load_project_from_path(self, path: str):
				try:
						with open(path, "r", encoding="utf-8") as f:
								data = f.read()
				except Exception as e:
						self.status_lbl.setText(f"Ошибка открытия: {e}")
						return
				self._current_project_path = path
				safe_path = path.replace("\\", "/")
				self._js(f'setProjectPath("{safe_path}");')
				self._js(f"loadProject({json.dumps(data)});")
				self.project_label.setText(os.path.basename(path))
				self._js("sendLayersToQt();")
				self._js_log(f"Project loaded: {os.path.basename(path)}")

		def _save_project(self):
				if not self._current_project_path:
						path, _ = QFileDialog.getSaveFileName(
								self, "Сохранить проект", "projects/project.json", "JSON (*.json)"
						)
						if not path: return
						self._current_project_path = path
						safe_path = self._current_project_path.replace("\\", "/")
						self._js(f'setProjectPath("{safe_path}");')
				safe_path = self._current_project_path.replace("\\", "/")
				self._js(f'saveProject("{safe_path}");')
				self.project_label.setText(os.path.basename(self._current_project_path))
				self.config["last_project"] = self._current_project_path
				save_config(self.config)
				self._js_log(f"Project save requested: {os.path.basename(self._current_project_path)}")

		def _open_project(self):
				path, _ = QFileDialog.getOpenFileName(
						self, "Открыть проект", "projects/", "JSON (*.json)"
				)
				if not path: return
				self.config["last_project"] = path
				save_config(self.config)
				self._load_project_from_path(path)

		def _export_png(self):
				path, _ = QFileDialog.getSaveFileName(
						self, "Экспорт PNG", "export.png", "PNG (*.png)"
				)
				if not path:
						return
				self._export_path = path
				self.status_lbl.setText("Подготовка экспорта...")
				self._js_log(f"Export PNG started: {os.path.basename(path)}")
				self._js("hideMapUI();")
				QTimer.singleShot(150, self._do_grab)

		def _do_grab(self):
				path = self._export_path
				try:
						pixmap = self.webview.grab()
						os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
						saved = pixmap.save(path, "PNG")
						if saved:
								self.status_lbl.setText(f"Экспорт сохранён: {os.path.basename(path)}")
								self._js_log(f"Export PNG saved OK: {path}")
						else:
								self.status_lbl.setText("Ошибка сохранения PNG")
								self._js_log(f"Export PNG FAILED: pixmap.save() returned False")
				except Exception as e:
						self.status_lbl.setText(f"Ошибка экспорта: {e}")
						self._js_log(f"Export PNG ERROR: {e}")
				finally:
						self._js("showMapUI();")
						self._export_path = None

		def _undo(self):
				self._js("undoAction();")
				self._js_log("Undo requested")

		def _delete_selected(self):
				# Сначала проверяем — выделен ли слой/группа в дереве
				item = self.layer_tree.currentItem()
				if isinstance(item, LayerItem) and not item.object_type:
						self._delete_layer()
						return
				# Иначе — удаляем выбранный объект на карте
				if not self._selected_obj_id:
						self._js_log("Delete: nothing selected")
						return
				obj_id = json.dumps(self._selected_obj_id)
				self._js(f"deleteSelected({obj_id});")
				self._selected_obj_id = None
				self._js_log("Delete selected requested")

		def _ask_api_key(self):
				dlg = ApiKeyDialog(self, self.config.get("yandex_api_key", ""))
				if dlg.exec() == QDialog.DialogCode.Accepted:
						key = dlg.get_key()
						self.config["yandex_api_key"] = key
						save_config(self.config)
						self._js(f'initMap({json.dumps(key)});')
						self._js_log(f"API key updated (len={len(key)})")

		def _js(self, code: str):
				self.webview.page().runJavaScript(code)

		def eventFilter(self, obj, event):
			if obj is self.webview:
					if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
							self._js("startSpacePan();")
							return True
					if event.type() == QEvent.Type.KeyRelease and event.key() == Qt.Key.Key_Space:
							self._js("stopSpacePan();")
							return True
			return super().eventFilter(obj, event)

		def receive_layers(self, layers_json: str):
				try:
						self._js_log(f"receive_layers CALLED, json len={len(layers_json)}")
						layers = json.loads(layers_json)
						active_id = self._active_layer_id
						self.layer_tree.clear()

						for node in layers:
								if node.get("isGroup"):
										g_item = LayerItem(node["id"], "📁 " + node["name"], is_group=True)
										g_item.visible = node.get("visible", True)
										g_item.opacity = node.get("localOpacity", 100)
										g_item._update_icon()
										self.layer_tree.addTopLevelItem(g_item)
										for lyr in node.get("children", []):
												l_item = LayerItem(lyr["id"], lyr["name"])
												l_item.visible = lyr.get("visible", True)
												l_item.opacity = lyr.get("localOpacity", 100)
												l_item._update_icon()
												g_item.addChild(l_item)
												self._add_object_items(l_item, lyr.get("objects", []))
												if lyr["id"] == active_id:
														self._activate_layer(l_item)
										g_item.setExpanded(True)
								else:
										l_item = LayerItem(node["id"], node["name"])
										l_item.visible = node.get("visible", True)
										l_item.opacity = node.get("localOpacity", 100)   # ← добавить!
										l_item._update_icon()
										self.layer_tree.addTopLevelItem(l_item)
										self._add_object_items(l_item, node.get("objects", []))
										if node["id"] == active_id:
												self._activate_layer(l_item)

						total_objects = sum(
								sum(len(lyr.get("objects", [])) for lyr in node.get("children", []))
								if node.get("isGroup") else len(node.get("objects", []))
								for node in layers
						)
						self._js_log(
								f"receive_layers OK: {len(layers)} top-level nodes, "
								f"{total_objects} total objects"
						)
						current = self.layer_tree.currentItem()
						if current:
								self._sync_opacity_slider(current)
				except Exception as e:
						self.status_lbl.setText(f"Ошибка загрузки слоёв: {e}")
						self._js_log(f"ERROR receive_layers: {e}")

		def _add_object_items(self, layer_item: LayerItem, objects: list):
				TYPE_ICONS = {"text": "T", "polyline": "✏", "image": "🖼"}
				for obj in objects:
						obj_type  = obj.get("type", "")
						label     = obj.get("label", obj_type)
						icon_char = TYPE_ICONS.get(obj_type, "•")
						o_item = LayerItem(obj["id"], f"{icon_char}  {label}", object_type=obj_type)
						o_item.visible = obj.get("visible", True)
						o_item.opacity = obj.get("localOpacity", 100)
						o_item._update_icon()
						o_item.setFlags(o_item.flags() | Qt.ItemFlag.ItemIsSelectable)
						layer_item.addChild(o_item)
				if objects:
						layer_item.setExpanded(True)

		def on_js_status(self, msg: str):
				if msg == "__MAP_READY__":
						if hasattr(self, '_splash') and self._splash:
								# Минимум 4 секунды показа заставки
								QTimer.singleShot(5000, lambda: (
										self._splash.finish() or setattr(self, '_splash', None)
										if self._splash else None
								))
						return
				if msg == "__SAVE_DIALOG__":
						self._save_project()
						return
				if msg == "__SWITCH_SELECT__":
						self._set_tool("select")
						return
				if msg.startswith("__EDIT_TEXT__:"):
						try:
								payload = json.loads(msg[len("__EDIT_TEXT__:"):])
								dlg = TextEditDialog(self, payload)
								if dlg.exec() == QDialog.DialogCode.Accepted:
										v = dlg.get_values()
										text_js   = json.dumps(v["text"])
										color_js  = json.dumps(v["fontColor"])
										bold_js   = str(v["fontBold"]).lower()
										italic_js = str(v["fontItalic"]).lower()
										obj_id    = json.dumps(payload["id"])
										self._js(
												f"applyTextEdit({obj_id}, {text_js}, "
												f"{v['fontSize']}, {color_js}, {bold_js}, {italic_js});"
										)
										self._js_log(
												f"Text edit applied: id={payload['id']} "
												f"text={v['text']} size={v['fontSize']} "
												f"color={v['fontColor']} bold={v['fontBold']} italic={v['fontItalic']}"
										)
						except Exception as e:
								self.status_lbl.setText(f"Ошибка редактирования текста: {e}")
								self._js_log(f"ERROR __EDIT_TEXT__: {e}")
						return
				# FIX BUG-10: исправлен отступ (были пробелы вместо табов — блок не выполнялся)
				if msg.startswith("__SELECTED__:"):
						self._selected_obj_id = msg[len("__SELECTED__:"):] or None
						self._highlight_tree_item(self._selected_obj_id)
						current = self.layer_tree.currentItem()
						if current:
								self._sync_opacity_slider(current)
						return

				self.status_lbl.setText(msg)


# ── Тёмная тема ───────────────────────────────────────────────────────────────────────────
DARK_STYLE = """
QWidget { background:#1e1e1e; color:#e0e0e0; font-family:'Segoe UI'; font-size:12px; }
QMainWindow { background:#1e1e1e; }
#topbar   { background:#2d2d2d; border-bottom:1px solid #444; }
#layersPanel { background:#252525; border-top:1px solid #444; }
#toolsPanel  { background:#252525; border-right:1px solid #444; }
#statusBar   { background:#2d2d2d; border-left:1px solid #444; border-bottom:1px solid #444; }
#rightPanel  { background:#252525; border-left:1px solid #444; }
QPushButton  { background:#3a3a3a; color:#e0e0e0; border:1px solid #555;
							 border-radius:4px; padding:3px 10px; }
QPushButton:hover   { background:#4a4a4a; }
QPushButton:pressed { background:#2a5298; }
QToolButton { background:#2d2d2d; border:none; border-radius:6px; color:#e0e0e0; }
QToolButton:hover   { background:#3a3a3a; }
QToolButton:checked { background:#1a5276; border:1px solid #2e86c1; }
QSlider::groove:horizontal { background:#444; height:4px; border-radius:2px; }
QSlider::handle:horizontal { background:#2e86c1; width:12px; height:12px;
														border-radius:6px; margin:-4px 0; }
QComboBox   { background:#3a3a3a; border:1px solid #555; border-radius:4px; padding:2px 6px; }
QComboBox::drop-down { border:none; }
QSpinBox    { background:#3a3a3a; border:1px solid #555; border-radius:4px; padding:2px; }
QLabel      { color:#e0e0e0; }
QCheckBox   { color:#e0e0e0; }
QInputDialog { background:#2d2d2d; }
QLineEdit   { background:#3a3a3a; border:1px solid #555; border-radius:4px;
						color:#e0e0e0; padding:3px; }
"""


if __name__ == "__main__":
		app = QApplication(sys.argv)
		app.setStyle("Fusion")
		os.makedirs("projects", exist_ok=True)

		win = MainWindow()
		win.showMaximized()
		win.raise_()
		win.activateWindow()
		app.processEvents()

		overlay = VovLoadingOverlay(win)
		overlay.set_status("Инициализация...")
		overlay.show_over()
		win._splash = overlay
		app.processEvents()

		# Подстраховка: закрыть через 15 сек если __MAP_READY__ не пришёл
		QTimer.singleShot(15000, lambda: (
				overlay.finish() or setattr(win, '_splash', None)
				if win._splash else None
		))

		sys.exit(app.exec())

