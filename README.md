# PT-Test-Task

## Архитектура решения
- **FastAPI API (`app/main.py`)** — точка входа серверной части. Собирает маршруты из модулей `app/api/*` и инициализирует подключение к базе через `app.db.database.init_db`, создавая схемы `users` и `rag` в PostgreSQL.
- **Сервис диалога (`app/services/agent.py`)** — обёртка вокруг LangGraph. Агент строит граф с узлом LLM (`chatbot`) и узлом инструментов (`ToolNode`) и автоматически решает, когда вызывать инструменты. Он работает поверх обобщённого клиента LLM из `app/services/model.py`, который поддерживает OpenAI-совместимые API и Ollama.
- **Инструменты агента (`app/services/tools/*.py`)** — расширяют возможности модели: `rag.py` делает релевантный поиск по корпоративным данным через pgvector и SentenceTransformers; `sql.py` выполняет только SELECT-запросы к локальной SQLite с данными команды; `web.py` обращается к DuckDuckGo и парсит страницы для свежей информации.
- **Слой данных (`app/db`)** — описывает ORM-модели SQLAlchemy для пользовательских данных (`models.py`) и для хранилища RAG-документов (`rag_models.py`). `database.py` поднимает синхронный и асинхронный engines, даёт FastAPI зависимость `get_db` (возвращает `AsyncSession`) и процедуры bootstrap’а эмбеддингов из `data/` через скрипты `scripts/embed_documents.py` и `scripts/upload_embeddings.py`.
- **Frontend (`streamlit_app.py`)** — лёгкая админка на Streamlit. Управляет пользователями и сессиями, показывает историю сообщений и отправляет новые сообщения в API.
- **Конфигурация (`app/core/config.py`)** — единая точка чтения настроек (имя приложения, параметры БД, модели, LangSmith) через `pydantic-settings`. Значения берутся из `.env`, что упрощает запуск в разных средах.

## Ключевые технологии и выбор
- **FastAPI + Uvicorn** — быстрый серверный фреймворк с удобной типизацией и зависимостями; используется в полностью асинхронном режиме для CRUD и интеграции с LangChain.
- **LangGraph / LangChain** — позволяет описывать управляемый граф состояний агента и гибко подключать инструменты, не ограничиваясь линейными цепочками.
- **PostgreSQL с pgvector** — хранилище для пользовательских данных и семантического поиска; pgvector является легким и удобным расширением для векторного поиска.
- **Sentence-Transformers** — даёт готовые мультиязычные модели (у меня по умолчанию `BAAI/bge-m3`) для генерации эмбеддингов документов.
- **Streamlit** — быстрый способ собрать UI без сложного фронтенда; ориентирован на внутренние инструменты и демо.
- **Docker Compose** — единый способ поднять БД, API и фронтенд. Даёт повторяемость окружения и избавляет от локальной установки PostgreSQL/pgvector.

## Запуск приложения
### Подготовка окружения
1. Скопируйте файл `.env.example` (или создайте его заново), указав ключевые параметры:
   - `DATABASE_URL` (по умолчанию `postgresql+psycopg://postgres:postgres@db:5432/db`).
   - Параметры модели: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`.
   - Настройки LangSmith (опционально): `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`.
   - Эмбеддер: `EMBEDDING_MODEL`, `EMBEDDING_DIM`.
2. При первом запуске убедитесь, что в каталоге `data/` есть исходные документы (`docs/`) или заранее подготовленные эмбеддинги (`embeddings/`). Если эмбеддингов нет, то скрипт `scripts/embed_documents.py` сгенерирует их из исходных документов:
```bash
python scripts/embed_documents.py
```

### Docker Compose
1. Соберите и поднимите сервисы:
   ```bash
   docker compose up --build
   ```
2. FastAPI будет доступен на `http://localhost:8000`, интерактивная документация — на `/docs`.
3. Streamlit UI откроется на `http://localhost:8080`. В настройках приложения уже прописан адрес API (`http://api:8000` внутри сети docker-compose).

### Полезные команды
- Запуск тестов: `pytest`.
- Обновление embeddings вручную: `python scripts/embed_documents.py` (создаёт CSV в `data/embeddings/`), затем `python scripts/upload_embeddings.py`.

## Примеры API-запросов

Все команды предполагают, что сервис запущен локально и доступен по адресу `http://localhost:8000`.

### Базовые маршруты

#### GET /
```bash
curl http://localhost:8000/ | jq
```
Пример ответа:
```json
{
  "app": "PT Test Task",
  "message": "PT-LLM-Assistant API running"
}
```

#### GET /health
```bash
curl http://localhost:8000/health | jq
```
Пример ответа:
```json
{
  "status": "ok"
}
```

### Быстрый чат без сессий

#### POST /chat
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет! Что ты умеешь?"}' | jq
```
Пример ответа:
```json
{
  "reply": "Здравствуйте! Готов помочь с вопросами по данным и документам.",
  "tools": ["rag"],
  "meta": {
    "session_id": null
  }
}
```

### Управление чат-сессиями

#### POST /chat/sessions
```bash
curl -X POST http://localhost:8000/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "title": "Обсуждение отчета"}' | jq
```
Пример ответа:
```json
{
  "id": "4d5f6a94-7c13-4f49-a873-b7d80d7c6f46",
  "user_id": 1,
  "title": "Обсуждение отчета",
  "created_at": "2024-05-01T10:15:04.123456"
}
```

#### GET /chat/sessions/{user_id}
```bash
curl http://localhost:8000/chat/sessions/1 | jq
```
Пример ответа:
```json
{
  "sessions": [
    {
      "id": "4d5f6a94-7c13-4f49-a873-b7d80d7c6f46",
      "title": "Обсуждение отчета",
      "created_at": "2024-05-01T10:15:04.123456",
      "updated_at": "2024-05-01T10:17:11.000000",
      "last_message_at": "2024-05-01T10:17:11.000000",
      "message_count": 3
    }
  ]
}
```

#### POST /chat/sessions/{session_id}/messages
```bash
curl -X POST http://localhost:8000/chat/sessions/4d5f6a94-7c13-4f49-a873-b7d80d7c6f46/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "Какие итоги по проекту?", "use_tools": true}' | jq
```
Пример ответа:
```json
{
  "reply": "Проект завершен, ключевые метрики достигнуты. Готов предоставить детали.",
  "tools": ["rag", "sql"],
  "meta": {
    "session_id": "4d5f6a94-7c13-4f49-a873-b7d80d7c6f46"
  }
}
```

#### GET /chat/sessions/{session_id}/messages
```bash
curl http://localhost:8000/chat/sessions/4d5f6a94-7c13-4f49-a873-b7d80d7c6f46/messages | jq
```
Пример ответа:
```json
{
  "session_id": "4d5f6a94-7c13-4f49-a873-b7d80d7c6f46",
  "messages": [
    {
      "id": 10,
      "role": "user",
      "content": "Какие итоги по проекту?",
      "created_at": "2024-05-01T10:17:05.000000"
    },
    {
      "id": 11,
      "role": "assistant",
      "content": "Проект завершен, ключевые метрики достигнуты. Готов предоставить детали.",
      "created_at": "2024-05-01T10:17:11.000000"
    }
  ]
}
```

#### DELETE /chat/sessions/{session_id}
```bash
curl -X DELETE http://localhost:8000/chat/sessions/4d5f6a94-7c13-4f49-a873-b7d80d7c6f46 | jq
```
Пример ответа:
```json
{
  "ok": true
}
```

### Управление пользователями

#### POST /users
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"external_id": "slack_u_123"}' | jq
```
Пример ответа:
```json
{
  "id": 1,
  "external_id": "slack_u_123",
  "created_at": "2024-05-01T09:00:00.000000",
  "updated_at": "2024-05-01T09:00:00.000000"
}
```

#### GET /users
```bash
curl "http://localhost:8000/users?skip=0&limit=20" | jq
```
Пример ответа:
```json
[
  {
    "id": 1,
    "external_id": "slack_u_123",
    "created_at": "2024-05-01T09:00:00.000000",
    "updated_at": "2024-05-01T09:05:32.000000"
  }
]
```

#### GET /users/{user_id}
```bash
curl http://localhost:8000/users/1 | jq
```
Пример ответа:
```json
{
  "id": 1,
  "external_id": "slack_u_123",
  "created_at": "2024-05-01T09:00:00.000000",
  "updated_at": "2024-05-01T09:05:32.000000"
}
```

#### PUT /users/{user_id}
```bash
curl -X PUT http://localhost:8000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"external_id": "slack_u_123_updated"}' | jq
```
Пример ответа:
```json
{
  "id": 1,
  "external_id": "slack_u_123_updated",
  "created_at": "2024-05-01T09:00:00.000000",
  "updated_at": "2024-05-01T09:05:32.000000"
}
```

#### DELETE /users/{user_id}
```bash
curl -X DELETE http://localhost:8000/users/1 | jq
```
Пример ответа:
```json
{
  "ok": true
}
```
