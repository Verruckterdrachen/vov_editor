# 📋 Инструкции для AI-ассистента (vov_editor)

> Этот файл **обязателен к прочтению** в начале каждой сессии.

---

## 🎯 Контекст проекта

`vov_editor` — десктопное PyQt6-приложение для рисования линий фронта ВОВ на интерактивной карте Leaflet.js.

### Стек
- Python 3.10–3.12, PyQt6, PyQt6-WebEngine
- Leaflet.js (рендер в `QWebEngineView`)
- `QWebChannel` для связи Python ↔ JS

### Структура файлов
| Файл | Роль |
|---|---|
| `main.py` | Главное окно, панели, инструменты, shortcuts |
| `map.html` | Вся логика карты: Leaflet, рисование, текст, слои |
| `bridge.py` | QWebChannel-мост: Python ↔ JS |
| `config.json` | API-ключ Яндекс.Карт и настройки (last_project и др.) |
| `projects/*.json` | Сохранённые проекты |

---

## 🔌 Архитектура взаимодействия Python ↔ JS

### Python → JS
```python
self.webview.page().runJavaScript("someJsFunction(args);")
Все вызовы идут через _js(code) в MainWindow.

JS → Python
Через bridge (объект Bridge из bridge.py), зарегистрированный в QWebChannel:

js
bridge.onStatus('сообщение');          // статус-строка
bridge.onLayersData(jsonString);       // дерево слоёв
bridge.saveProjectData(jsonString);    // сохранение на диск
bridge.onError('сообщение');           // ошибка JS
Специальные статус-сообщения (JS → Python через bridge.onStatus)
Строка	Действие в Python
__SAVE_DIALOG__	Открыть диалог сохранения
__SWITCH_SELECT__	Переключить инструмент на Select
__EDIT_TEXT__:{json}	Открыть диалог редактирования текста
⚠️ Критические особенности среды
QWebEngineView / Chromium
Space и другие системные клавиши перехватываются Qt (QAbstractScrollArea) до того, как доходят до JS. Для таких клавиш нужен QShortcut в Python или eventFilter на QWebEngineView.

user-select: text в CSS не работает для выделения мышью внутри WebEngine без явного разрешения через QWebEngineSettings.

JavascriptCanAccessClipboard по умолчанию отключён.

Leaflet.js
Leaflet принудительно выставляет cursor на .leaflet-container и .leaflet-interactive (SVG). CSS-правило #map { cursor: X } перебивается Leaflet. Правильный способ менять курсор — map.getContainer().style.cursor = 'X' через JS или CSS с !important на .leaflet-container.

L.divIcon с className: '' убирает классы с внешнего Leaflet-контейнера иконки, но HTML-строка внутри рендерится как есть. CSS-классы, применённые к внутреннему <div>, работают — но только если класс присутствует в DOM в момент рендера.

text-shadow в CSS-классе не применится, если стиль задан инлайн в style="..." строке buildTextIcon. Убирать нужно именно из инлайн-стиля.

Двойные обработчики событий
Ctrl+Z, Ctrl+S, Delete — обрабатываются и в Python (QShortcut), и в JS (keydown). Двойная обработка приводит к двойному срабатыванию. Правило: если есть QShortcut в Python — убираем из JS.

Зарезервированные имена window.* в JS
В глобальном скопе map.html нельзя использовать как переменные имена, являющиеся свойствами window:
history, location, navigator, screen, status, name, event, frames, self, top, parent, opener, closed

Qt WebEngine (Chromium) не позволяет перезаписать эти свойства через var. Переменная будет ссылаться на браузерный объект, а не на твоё значение.

Симптом: TypeError: X.push is not a function или аналогичный — код падает молча, JS не выбрасывает ошибку в лог, весь код после падения не выполняется.

Правило: при любом необъяснимом TypeError с базовыми методами (.push, .pop, .length) — первым делом проверить конфликт имён с window.*.

JS-исключения внутри обработчиков
Исключения в JS внутри колбэков и обработчиков событий не всегда видны в логе и не останавливают Python.

При отладке: оборачивать подозрительные функции в try/catch с явным log('[fn] EXCEPTION: ' + e + ' | stack: ' + (e.stack||'n/a')).

Это позволяет найти точную строку падения вместо поиска "почему sendLayersToQt молчит".

QWebChannel и асинхронность
bridge инициализируется асинхронно внутри new QWebChannel(qt.webChannelTransport, callback). До вызова callback bridge === null.

runJavaScript() из Python — асинхронный. Python не ждёт завершения JS. Лог-строки из Python могут появиться раньше или позже JS-логов.

Если sendLayersToQt() вызывается до готовности bridge — добавить ретри: if (!bridge) { setTimeout(sendLayersToQt, 200); return; }.

После инициализации bridge — вызывать sendLayersToQt() прямо внутри QWebChannel-callback, чтобы гарантировать актуальное состояние слоёв.

🛡️ Правила работы AI
Читать в начале каждой сессии: doc/AI_INSTRUCTIONS.md, doc/BUGS.md, doc/ARCHITECTURE.md.

Перед написанием кода — изучить все связанные файлы из репо.

Перед фиксом — объяснить механизм: почему текущий код не работает, и почему предложенный fix сработает с учётом особенностей среды.

Спрашивать согласие перед написанием кода.

Не объединять много несвязанных фиксов в один коммит без проверки логики каждого.

CSS-фиксы: проверять специфичность, наличие конкурирующих стилей (особенно Leaflet), инлайн vs класс.

JS-события: проверять, доходит ли событие до WebView (Qt может перехватить Space, F5 и др.).

Не допускать регрессии: при изменении функции проверять все места, где она вызывается.

Debug/log: при фиксе сложных багов добавлять log(...) для диагностики. После подтверждения фикса — убирать временные логи.

Использовать эмодзи в ответах пользователю.

Читать doc/BUGS.md в начале каждой сессии для контекста текущих задач.

📤 Порядок вывода кода
Код не коммитится на GitHub самостоятельно. Сначала AI презентует изменения пользователю в чате, дожидается подтверждение, затем коммитит.

Формат вывода:
Если изменений мало (точечные, несколько строк) — формат БЫЛО/СТАЛО:

text
Файл: map.html  (функция setTool)
БЫЛО:
  document.body.className = 'tool-' + activeTool;
СТАЛО:
  document.body.className = 'tool-' + activeTool;
  map.getContainer().style.cursor = cursorMap[activeTool] || '';
Если изменений много (несколько функций, новые классы) — полный новый файл целиком в код-блоке.

После подтверждения от пользователя:
AI коммитит изменения на GitHub

AI обновляет doc/BUGS.md (закрывает баг, добавляет коммит в таблицу)

AI сообщает что сделано и предлагает следующий баг