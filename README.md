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
