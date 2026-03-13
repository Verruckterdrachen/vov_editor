# -*- coding: utf-8 -*-
"""
QWebChannel мост: Python ↔ JavaScript
"""

import json
import os

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal


class Bridge(QObject):
    """
    Объект, экспортируемый в JavaScript через QWebChannel.
    JS обращается к нему как: bridge.имяМетода(...)
    """

    # Сигнал → отправить сообщение в JS (не используем напрямую, через runJavaScript)
    js_message = pyqtSignal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window   # ссылка на MainWindow

    # ── Методы, вызываемые из JavaScript ──────────────────

    @pyqtSlot(str)
    def saveProjectData(self, json_str: str):
        """JS вызывает, когда нужно записать данные проекта на диск."""
        path = self.window._current_project_path
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(json_str)
            self.window.on_js_status(f"Сохранено: {os.path.basename(path)}")
        except Exception as e:
            self.window.on_js_status(f"Ошибка сохранения: {e}")

    @pyqtSlot(str)
    def onStatus(self, msg: str):
        """JS передаёт строку статуса для отображения в нижней строке."""
        self.window.on_js_status(msg)

    @pyqtSlot(str)
    def onLayersData(self, layers_json: str):
        """JS передаёт дерево слоёв (после loadProject) для обновления панели."""
        self.window.receive_layers(layers_json)

    @pyqtSlot(str, str)
    def onLayerAdded(self, layer_id: str, name: str):
        """JS уведомляет о добавлении нового слоя (для синхронизации панели)."""
        pass  # панель обновляется из Python

    @pyqtSlot(str)
    def onError(self, msg: str):
        """JS сообщает об ошибке."""
        self.window.on_js_status(f"JS ошибка: {msg}")

    @pyqtSlot(str, str)
    def saveImageFile(self, base64_data: str, path: str):
        """Сохранение PNG-экспорта карты на диск."""
        import base64
        try:
            # base64_data: "data:image/png;base64,iVBOR..."
            header, encoded = base64_data.split(",", 1)
            raw = base64.b64decode(encoded)
            with open(path, "wb") as f:
                f.write(raw)
            self.window.on_js_status(f"Экспорт сохранён: {os.path.basename(path)}")
        except Exception as e:
            self.window.on_js_status(f"Ошибка экспорта: {e}")
