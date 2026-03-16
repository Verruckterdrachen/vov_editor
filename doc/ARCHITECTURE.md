# 🏗️ Архитектура vov_editor

## Схема взаимодействия компонентов

```
┌─────────────────────────────────────────────┐
│               MainWindow (PyQt6)             │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │LayerPanel│  │WebView   │  │ToolsPanel │  │
│  │(QTree)   │  │(Chromium)│  │(buttons)  │  │
│  └────┬─────┘  └────┬─────┘  └───────────┘  │
│       │              │                        │
│       └──────────────┴──── _js(code) ────────►│
│                      │◄─── bridge.onStatus ───┤
└──────────────────────┼─────────────────────── ┘
                       │
              ┌────────┴────────┐
              │    map.html     │
              │  (Leaflet.js)   │
              │                 │
              │  layers{}       │
              │  history[]      │
              │  activeTool     │
              └─────────────────┘
```

## Форматы данных

### Проект (JSON)
```json
{
  "version": "1.0",
  "center": [55.0, 32.0],
  "zoom": 5,
  "tileType": "map",
  "activeLayerId": "layer_abc123",
  "layers": [
    {
      "id": "group_xyz",
      "name": "Группа 1",
      "isGroup": true,
      "visible": true,
      "objects": []
    },
    {
      "id": "layer_abc123",
      "name": "Слой 1",
      "visible": true,
      "objects": [
        {
          "id": "obj_...",
          "type": "polyline",
          "latlngs": [[55.1, 32.1], [55.2, 32.3]],
          "color": "#ff0000",
          "weight": 4
        },
        {
          "id": "obj_...",
          "type": "text",
          "text": "Минск",
          "latlng": [53.9, 27.5],
          "fontSize": 16,
          "fontColor": "#000000",
          "fontBold": true,
          "fontItalic": false
        }
      ]
    }
  ]
}
```

## Инструменты

| ID | Клавиша | dragging | Курсор |
|---|---|---|---|
| `select` | V | enabled | pointer (палец) |
| `brush` | B | disabled | crosshair |
| `eraser` | E | disabled | none (кастомный круг) |
| `text` | T | disabled | text |
| `import` | — | — | — |

## Горячие клавиши

| Клавиша | Обработчик | Действие |
|---|---|---|
| `V/B/E/T` | Python QShortcut | Переключить инструмент |
| `Ctrl+Z` | Python QShortcut | Undo (вызывает `undoAction()` в JS) |
| `Ctrl+S` | Python QShortcut + JS keydown | Сохранить |
| `Ctrl+E` | Python QShortcut | Экспорт PNG |
| `Delete` | Python QShortcut + JS keydown | Удалить выбранный объект |
| `Space` | **Python eventFilter** (Qt перехватывает раньше JS) | Временный pan |
| `Ctrl+\`` | JS keydown | Показать/скрыть debug-лог |

## Состояние JS (глобальные переменные map.html)

| Переменная | Тип | Описание |
|---|---|---|
| `map` | L.Map | Leaflet-карта |
| `bridge` | QWebChannel object | Мост к Python |
| `activeTool` | string | Текущий инструмент |
| `activeLayerId` | string | ID активного слоя |
| `layers` | object | Словарь слоёв: id → {name, group, objects[]} |
| `layerOrder` | array | Порядок слоёв |
| `history` | array | Стек undo (max 50) |
| `selectedObj` | object | Выбранный объект |
| `spaceDown` | bool | Флаг зажатого пробела |
