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
    QDialogButtonBox, QLineEdit, QFormLayout, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QUrl, QObject, pyqtSlot, pyqtSignal, QSize, QTimer
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


# ── Диалог ввода API-ключа ──────────────────────────────
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


# ── Панель инструментов ───────────────────────────────
class ToolButton(QToolButton):
    def __init__(self, text, tooltip, shortcut="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(f"{tooltip}" + (f"  [{shortcut}]" if shortcut else ""))
        self.setCheckable(True)
        self.setFixedSize(48, 48)
        self.setFont(QFont("Segoe UI Emoji", 14))


# ── Элемент дерева слоёв ──────────────────────────────
class LayerItem(QTreeWidgetItem):
    def __init__(self, layer_id: str, name: str, is_group=False):
        super().__init__()
        self.layer_id  = layer_id
        self.is_group  = is_group
        self.visible   = True
        self.setText(0, name)
        self._update_icon()

    def _update_icon(self):
        self.setText(1, "👁" if self.visible else "  ")

    def toggle_visibility(self):
        self.visible = not self.visible
        self._update_icon()


# ── QTreeWidget с перехватом dropEvent ────────────────
class LayerTree(QTreeWidget):
    """QTreeWidget с сигналом об изменении порядка слоёв после drag-and-drop."""
    orderChanged = pyqtSignal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.orderChanged.emit()


# ── Главное окно ────────────────────────────────────────────────
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
        self._font_color           = "#ffffff"
        self._font_bold            = False
        self._font_italic          = False

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
        work.addWidget(self._build_layers_panel())
        work.addWidget(self._build_webview(), stretch=1)
        work.addWidget(self._build_tools_panel())
        root_layout.addLayout(work, stretch=1)
        root_layout.addWidget(self._build_statusbar())

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

        # FIX #3: используем подкласс LayerTree вместо QTreeWidget
        self.layer_tree = LayerTree()
        self.layer_tree.setColumnCount(2)
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setColumnWidth(0, 190)
        self.layer_tree.setColumnWidth(1, 28)
        self.layer_tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.layer_tree.itemClicked.connect(self._on_layer_clicked)
        self.layer_tree.itemDoubleClicked.connect(self._on_layer_double_clicked)
        # FIX #3: подписываемся на сигнал изменения порядка
        self.layer_tree.orderChanged.connect(self._on_layer_order_changed)
        lay.addWidget(self.layer_tree)
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
        bar.setFixedHeight(44)
        bar.setObjectName("statusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(12)
        self.color_btn = QPushButton("  🎨 Цвет  ")
        self.color_btn.setFixedHeight(32)
        self.color_btn.clicked.connect(self._pick_brush_color)
        self._update_color_button()
        lay.addWidget(self.color_btn)
        lay.addWidget(QLabel("Толщина:"))
        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setRange(1, 20)
        self.brush_slider.setValue(self._brush_size)
        self.brush_slider.setFixedWidth(100)
        self.brush_slider.valueChanged.connect(self._on_brush_size_changed)
        lay.addWidget(self.brush_slider)
        self.brush_size_lbl = QLabel(str(self._brush_size))
        lay.addWidget(self.brush_size_lbl)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Ластик:"))
        self.eraser_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_slider.setRange(5, 100)
        self.eraser_slider.setValue(self._eraser_size)
        self.eraser_slider.setFixedWidth(100)
        self.eraser_slider.valueChanged.connect(self._on_eraser_size_changed)
        lay.addWidget(self.eraser_slider)
        self.eraser_size_lbl = QLabel(str(self._eraser_size))
        lay.addWidget(self.eraser_size_lbl)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Шрифт:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(self._font_size)
        self.font_size_spin.setFixedWidth(60)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        lay.addWidget(self.font_size_spin)
        self.font_color_btn = QPushButton("🔤 Цвет")
        self.font_color_btn.setFixedHeight(30)
        self.font_color_btn.clicked.connect(self._pick_font_color)
        lay.addWidget(self.font_color_btn)
        self.bold_cb = QCheckBox("Ж")
        self.bold_cb.stateChanged.connect(self._on_font_bold_changed)
        lay.addWidget(self.bold_cb)
        self.italic_cb = QCheckBox("К")
        self.italic_cb.stateChanged.connect(self._on_font_italic_changed)
        lay.addWidget(self.italic_cb)
        lay.addStretch()
        self.status_lbl = QLabel("Готово")
        self.status_lbl.setStyleSheet("color:#888;")
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

    # ── Вспомогательный метод логирования в JS-панель ──────
    def _js_log(self, msg: str):
        """Пишет сообщение в debug-лог JS (Ctrl+` для показа)."""
        safe = msg.replace("\\", "\\\\").replace("'", "\\'")
        self._js(f"log('[PY] {safe}');")

    def _on_map_loaded(self, ok):
        if not ok:
            self.status_lbl.setText("Ошибка загрузки карты!")
            return
        api_key = self.config.get("yandex_api_key", "")
        # FIX #2: json.dumps безопасно экранирует спецсимволы в ключе
        self._js(f'initMap({json.dumps(api_key)});')
        self.status_lbl.setText("Карта загружена")
        self._js_log("App started, map loaded")

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
        # FIX #1: стабильный UUID вместо id(name)
        lid = f"group_{uuid.uuid4().hex[:8]}"
        item = LayerItem(lid, name, is_group=True)
        self.layer_tree.addTopLevelItem(item)
        self._js(f'addLayerGroup("{lid}", {json.dumps(name)});')
        self._js_log(f"Group added: '{name}' id={lid}")

    def _add_layer(self):
        name, ok = QInputDialog.getText(self, "Новый слой", "Название слоя:")
        if not ok or not name: return
        # FIX #1: стабильный UUID вместо id(name)
        lid = f"layer_{uuid.uuid4().hex[:8]}"
        item = LayerItem(lid, name)
        selected = self.layer_tree.currentItem()
        if selected and isinstance(selected, LayerItem) and selected.is_group:
            selected.addChild(item)
            selected.setExpanded(True)
        else:
            self.layer_tree.addTopLevelItem(item)
        self._activate_layer(item)
        self._js(f'addLayer("{lid}", {json.dumps(name)});')
        self._js_log(f"Layer added: '{name}' id={lid}")

    def _delete_layer(self):
        item = self.layer_tree.currentItem()
        if not item or not isinstance(item, LayerItem): return
        lid = item.layer_id
        name = item.text(0)
        root = self.layer_tree.invisibleRootItem()
        parent = item.parent() or root
        parent.removeChild(item)
        self._js(f'removeLayer("{lid}");')
        self._active_layer_id = None
        self._js_log(f"Layer deleted: '{name}' id={lid}")

    def _on_layer_clicked(self, item, col):
        if not isinstance(item, LayerItem): return
        if col == 1:
            item.toggle_visibility()
            vis = item.visible
            self._js(f'setLayerVisible("{item.layer_id}", {str(vis).lower()});')
            self._js_log(f"Layer visibility: '{item.text(0)}' -> {vis}")
        else:
            if not item.is_group: self._activate_layer(item)

    def _on_layer_double_clicked(self, item, col):
        if not isinstance(item, LayerItem): return
        old_name = item.text(0)
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=old_name)
        if ok and name:
            item.setText(0, name)
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

    def _clear_highlight(self, item):
        item.setBackground(0, QColor("transparent"))
        item.setBackground(1, QColor("transparent"))
        for i in range(item.childCount()):
            self._clear_highlight(item.child(i))

    # FIX #3: синхронизация порядка слоёв после drag-and-drop
    def _on_layer_order_changed(self):
        """Собирает плоский список ID слоёв из дерева и отправляет в JS."""
        order = []
        root = self.layer_tree.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            if isinstance(top, LayerItem):
                order.append(top.layer_id)
                for j in range(top.childCount()):
                    child = top.child(j)
                    if isinstance(child, LayerItem):
                        order.append(child.layer_id)
        order_json = json.dumps(order)
        self._js(f'reorderLayers({order_json});')
        self._js_log(f"Layer order changed: {order}")

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
        # FIX #2: json.dumps безопасно экранирует спецсимволы в ключе
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
        self._js_log(f"Project save requested: {os.path.basename(self._current_project_path)}")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть проект", "projects/", "JSON (*.json)"
        )
        if not path: return
        self._current_project_path = path
        safe_path = path.replace("\\", "/")
        self._js(f'setProjectPath("{safe_path}");')
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        self._js(f"loadProject({json.dumps(data)});")
        self.project_label.setText(os.path.basename(path))
        self._js("sendLayersToQt();")
        self._js_log(f"Project opened: {os.path.basename(path)}")

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт PNG", "export.png", "PNG (*.png)")
        if path:
            self._js(f'exportPNG("{path.replace(chr(92), "/")}");')
            self._js_log(f"Export PNG: {os.path.basename(path)}")

    def _undo(self):
        self._js("undoAction();")
        self._js_log("Undo requested")

    def _delete_selected(self):
        self._js("deleteSelected();")
        self._js_log("Delete selected requested")

    def _ask_api_key(self):
        dlg = ApiKeyDialog(self, self.config.get("yandex_api_key", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = dlg.get_key()
            self.config["yandex_api_key"] = key
            save_config(self.config)
            # FIX #2: json.dumps безопасно экранирует спецсимволы в ключе
            self._js(f'initMap({json.dumps(key)});')
            self._js_log(f"API key updated (len={len(key)})")

    def _js(self, code: str):
        self.webview.page().runJavaScript(code)

    def receive_layers(self, layers_json: str):
        try:
            layers = json.loads(layers_json)
            self.layer_tree.clear()
            for grp in layers:
                g_item = LayerItem(grp["id"], grp["name"], is_group=True)
                self.layer_tree.addTopLevelItem(g_item)
                for lyr in grp.get("children", []):
                    l_item = LayerItem(lyr["id"], lyr["name"])
                    g_item.addChild(l_item)
                g_item.setExpanded(True)
            self._js_log(f"Layers tree rebuilt: {len(layers)} top-level items")
        except Exception as e:
            self.status_lbl.setText(f"Ошибка загрузки слоёв: {e}")
            self._js_log(f"ERROR receive_layers: {e}")

    def on_js_status(self, msg: str):
        # JS шлёт спецсигналы:
        if msg == "__SAVE_DIALOG__":
            self._save_project()
            return
        # Авто-переключение на Select после текста
        if msg == "__SWITCH_SELECT__":
            self._set_tool("select")
            return
        self.status_lbl.setText(msg)


# ── Тёмная тема ─────────────────────────────────────────────────────────────
DARK_STYLE = """
QWidget { background:#1e1e1e; color:#e0e0e0; font-family:'Segoe UI'; font-size:12px; }
QMainWindow { background:#1e1e1e; }
#topbar   { background:#2d2d2d; border-bottom:1px solid #444; }
#layersPanel { background:#252525; border-right:1px solid #444; }
#toolsPanel  { background:#252525; border-left:1px solid #444; }
#statusBar   { background:#2d2d2d; border-top:1px solid #444; }
QPushButton  { background:#3a3a3a; color:#e0e0e0; border:1px solid #555;
               border-radius:4px; padding:3px 10px; }
QPushButton:hover   { background:#4a4a4a; }
QPushButton:pressed { background:#2a5298; }
QToolButton { background:#2d2d2d; border:none; border-radius:6px; color:#e0e0e0; }
QToolButton:hover   { background:#3a3a3a; }
QToolButton:checked { background:#1a5276; border:1px solid #2e86c1; }
QTreeWidget { background:#1e1e1e; border:none; color:#e0e0e0; }
QTreeWidget::item:hover    { background:#2a3a4a; }
QTreeWidget::item:selected { background:#1a5276; }
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
    win.show()
    sys.exit(app.exec())
