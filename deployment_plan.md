# План развертывания Telegram-бота на Render с использованием Docker

## 1. Анализ

*   **Приложение:** Telegram-бот (`bot.py`), получающий курсы криптовалют с CoinGecko.
*   **Зависимости:** `python-telegram-bot`, `requests` (`requirements.txt`).
*   **Метод работы:** Long-polling (`application.run_polling()`).
*   **Конфигурация:** Требуется токен Telegram из переменной окружения `TELEGRAM_BOT_TOKEN`.
*   **Ненужные/Опасные файлы:** `config.py` содержит чувствительные данные (приватный ключ Ethereum) и не используется ботом. **Его нельзя включать в образ Docker.** Файлы `get_balance_bring.sh`, `get_balances.py`, `render.yaml` также не требуются для текущей задачи.

## 2. Способ развертывания

*   **Платформа:** Render.com
*   **Тип сервиса:** Background Worker (т.к. бот должен работать постоянно в фоне).
*   **Метод доставки кода:** Docker-образ, загруженный в публичный или приватный реестр контейнеров (например, Docker Hub, GitHub Container Registry).

## 3. Подготовка Docker-образа

### `Dockerfile`

Создайте файл `Dockerfile` в корне проекта (рядом с `bot.py` и `requirements.txt`) со следующим содержимым:

```dockerfile
# Используем официальный образ Python 3.9 slim как базовый
FROM python:3.9-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями в рабочую директорию
COPY requirements.txt .

# Устанавливаем зависимости
# --no-cache-dir чтобы не хранить кеш pip и уменьшить размер образа
# --upgrade pip обновляем pip до последней версии
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем основной код бота в рабочую директорию
# Важно: НЕ копируйте config.py или другие ненужные/секретные файлы!
COPY bot.py .

# Указываем команду для запуска бота при старте контейнера
# Python запускается с флагом -u для небуферизованного вывода,
# что полезно для просмотра логов в Render
CMD ["python", "-u", "bot.py"]
```

### Сборка и отправка образа

Выполните следующие команды в терминале в папке с `Dockerfile`:

1.  **Сборка образа:**
    ```bash
    docker build -t ваш_логин_в_реестре/имя_бота:latest .
    ```
    *Замените `ваш_логин_в_реестре/имя_бота` на актуальный путь к вашему образу (например, `ваш_dockerhub_логин/my-telegram-bot`).*

2.  **Вход в реестр:**
    ```bash
    docker login # Для Docker Hub
    # или команды для вашего реестра (e.g., ghcr.io, Gitlab)
    ```

3.  **Отправка образа:**
    ```bash
    docker push ваш_логин_в_реестре/имя_бота:latest
    ```

## 4. Настройка сервиса в Render

1.  Войдите в ваш аккаунт Render.
2.  Нажмите "New +" -> "Background Worker".
3.  Выберите "Deploy an existing image from a registry".
4.  **Image Path:** Укажите полный путь к вашему образу, который вы отправили в реестр (например, `docker.io/ваш_dockerhub_логин/my-telegram-bot:latest` или `ghcr.io/ваш_github_логин/my-telegram-bot:latest`).
5.  **Name:** Дайте имя вашему сервису (например, `telegram-crypto-bot`).
6.  **Region:** Выберите регион.
7.  **Instance Type:** Выберите тарифный план (можно начать с бесплатного "Free", если доступен для Background Workers и подходит по ресурсам).
8.  **Environment Variables:**
    *   Нажмите "+ Add Environment Variable".
    *   **Key:** `TELEGRAM_BOT_TOKEN`
    *   **Value:** Вставьте ваш секретный токен Telegram-бота.
    *   Убедитесь, что переменная помечена как "Secret".
9.  Нажмите "Create Background Worker".

## 5. Запуск и мониторинг

*   Render автоматически скачает ваш Docker-образ и запустит контейнер, выполнив команду `CMD` из `Dockerfile`.
*   Следите за логами развертывания и работы бота во вкладке "Logs" вашего сервиса в Render.
*   Проверьте работу бота в Telegram.