Отлично, картина полная. Готовлю обновлённые .md файлы. 📝

doc/BUGS.md — обновлённая версия
text
# 🐛 Трекер багов vov_editor

> Этот файл читается AI в начале каждой сессии для контекста текущих задач.
> Обновляется после каждого фикса или нового обнаружения.

---

## 🔴 Открытые баги

### BUG-9 — Пробел не работает как временный pan
**Статус**: ❌ Не исправлен  
**Описание**: Зажатие Space не переключает в режим перетаскивания карты. В логе нет никаких записей о нажатии.  
**Root cause**: `QWebEngineView` наследует от `QAbstractScrollArea`, которая **перехватывает Space** на уровне Qt до того, как событие достигает JS. JS-слушатель `document.addEventListener('keydown')` никогда не получает это событие.  
**Правильный fix**: Реализовать через Python: добавить `eventFilter` на `QWebEngineView` (или его viewport), перехватывать `QEvent.Type.KeyPress` с `Qt.Key.Key_Space`, и при нажатии вызывать `_js("startSpacePan()")`, при отпускании — `_js("stopSpacePan()")`.

---

## ✅ Закрытые баги

| ID | Описание | Коммит |
|---|---|---|
| BUG-10 | Объекты не появляются/не исчезают в панели слоёв после создания/удаления | локально |
| BUG-4 | Курсор палец исправлен | `` |
| BUG-3 | Переименование слоя | `1f74cbd` |
| BUG-8 | Двойной Ctrl+Z | `1f74cbd` |
| BUG-6 | Тень у текстовых меток | `cf1aaa4` |
| BUG-7 | Редактирование текста (двойной клик) | `81802ee` |
| BUG-2 | Объект не появляется в панели слоёв | `3f7d47f` |
| BUG-LOG | Копирование лога (кнопка 📋) | `3f7d47f` |
| BUG-1 | Автооткрытие последнего проекта + showMaximized | `7969736` |

---

## 🔬 BUG-10 — Разбор (архив для AI)

### Симптом
Объекты (текст, линии) создавались на карте и сохранялись в JSON, но **не появлялись в панели слоёв** в реальном времени. После перезапуска проекта — появлялись. Удаление объектов тоже не отражалось в панели.

### Путь диагностики (хронология)

**Шаг 1 — ложные гипотезы:**
- Предположение: `bridge = null` в момент вызова `sendLayersToQt` → добавили ретри через `setTimeout`
- Предположение: гонка таймеров при автооткрытии → увеличили таймер с 300мс до 800мс
- Предположение: `placeText` вызывает `__SWITCH_SELECT__` до `sendLayersToQt` и перебивает очередь bridge

**Шаг 2 — добавили детальный лог:**
```js
// В sendLayersToQt:
log('[sendLayersToQt] sending N top-level nodes, M total objects');
try {
    bridge.onLayersData(JSON.stringify(result));
    log('[sendLayersToQt] onLayersData call OK');
} catch(e) {
    log('[sendLayersToQt] ERROR: ' + e);
}

// В deleteSelected:
log('[deleteSelected] removing...');
log('[deleteSelected] layer objects remaining: ...');
log('[deleteSelected] calling pushHistory...');
// ...
log('[deleteSelected] pushHistory OK, calling sendLayersToQt...');

// В receive_layers (Python):
self._js_log(f"receive_layers CALLED, json len={len(layers_json)}")
Шаг 3 — лог выявил точку падения:

text
[deleteSelected] layer objects remaining: 0
[deleteSelected] calling pushHistory...
[deleteSelected] EXCEPTION: TypeError: history.push is not a function
Шаг 4 — root cause найден:

Root Cause — конфликт имён с window.history
js
var history = [];  // ← ПРОБЛЕМА
history — зарезервированное имя в браузерном JS. var history в глобальном скопе (window) конфликтует с встроенным window.history (браузерный History API). Qt WebEngine (Chromium) не позволяет перезаписать window.history, поэтому переменная оставалась объектом History, у которого нет метода .push(). Каждый вызов pushHistory() → history.push(record) падал с TypeError — молча, без вывода в консоль — и весь код после него (включая sendLayersToQt()) никогда не выполнялся.

Фикс
Переименовать history → undoHistory во всём map.html:

var history = [] → var undoHistory = []

history.push( → undoHistory.push(

history.pop( → undoHistory.pop(

history.length → undoHistory.length

history = [] внутри loadProject → undoHistory = []

Урок для AI
⚠️ В глобальном скопе JS (map.html загружен в браузере) нельзя использовать зарезервированные имена браузерного API как переменные:
history, location, navigator, screen, status, name, event, frames, self, top, parent, opener, closed
Все они являются свойствами window и могут вести себя непредсказуемо при попытке переопределения.
При любом странном TypeError: X is not a function — первым делом проверять конфликт имён с window.*.

