# План развертывания Telegram-бота (Render / Railway) с использованием Docker

## 1. Анализ

*   **Приложение:** Telegram-бот (`bot.py`), получающий курсы криптовалют с CoinGecko.
*   **Зависимости:** `python-telegram-bot`, `requests` (`requirements.txt`).
*   **Метод работы:** Long-polling (`application.run_polling()`).
*   **Конфигурация:** Требуется токен Telegram из переменной окружения `TELEGRAM_BOT_TOKEN`.
*   **Ненужные/Опасные файлы:** `config.py` содержит чувствительные данные (приватный ключ Ethereum) и не используется ботом. **Его нельзя включать в образ Docker.** Файлы `get_balance_bring.sh`, `get_balances.py`, `render.yaml` также не требуются для текущей задачи.

## 2. Способ развертывания

*   **Платформа:** Render.com
*   **Тип сервиса:** Background Worker (т.к. бот должен работать постоянно в фоне).
*   **Метод доставки кода:** Прямое подключение к GitHub-репозиторию (`https://github.com/romantrick/telegram_bot.git`). Render будет автоматически собирать Docker-образ из `Dockerfile` в репозитории.

## 3. Подготовка репозитория (Уже сделано)

### `Dockerfile` (Уже в репозитории)

Файл `Dockerfile` должен находиться в корне вашего репозитория со следующим содержимым:

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

### Файлы в репозитории

Убедитесь, что в вашем репозитории (`master` ветка) находятся как минимум:
*   `bot.py`
*   `requirements.txt`
*   `Dockerfile`
*   `.gitignore` (чтобы исключить секреты и ненужные файлы)
(Эти файлы уже были добавлены и отправлены на GitHub).

## 4. Настройка сервиса в Render

1.  Войдите в ваш аккаунт Render.
2.  Нажмите "New +" -> "Background Worker".
3.  Выберите "Build and deploy from a Git repository".
4.  Подключите ваш GitHub-аккаунт к Render, если еще не сделали этого.
5.  Выберите репозиторий `romantrick/telegram_bot`.
6.  **Name:** Дайте имя вашему сервису (например, `telegram-crypto-bot`).
7.  **Region:** Выберите регион.
8.  **Branch:** Убедитесь, что выбрана ветка `master`.
9.  **Runtime:** Выберите **Docker**. Render автоматически найдет и использует ваш `Dockerfile`.
10. **Instance Type:** Выберите тарифный план (можно начать с бесплатного "Free").
11. **Environment Variables:**
    *   Нажмите "+ Add Environment Variable".
    *   **Key:** `TELEGRAM_BOT_TOKEN`
    *   **Value:** Вставьте ваш секретный токен Telegram-бота.
    *   Убедитесь, что переменная помечена как "Secret".
12. Нажмите "Create Background Worker".

## 5. Запуск и мониторинг

*   Render автоматически скачает код из вашего GitHub-репозитория, соберет Docker-образ с помощью `Dockerfile` и запустит контейнер, выполнив команду `CMD`.
*   Следите за логами развертывания и работы бота во вкладке "Logs" вашего сервиса в Render.
*   Проверьте работу бота в Telegram.

## 6. Настройка сервиса в Railway (Альтернатива Render)

Railway также может автоматически собирать и развертывать Docker-образы из GitHub.

1.  Войдите в ваш аккаунт Railway ([railway.app](https://railway.app/)).
2.  Нажмите "New Project" -> "Deploy from GitHub repo".
3.  Подключите ваш GitHub-аккаунт к Railway, если еще не сделали этого, и разрешите доступ к репозиторию `romantrick/telegram_bot`.
4.  Выберите репозиторий `romantrick/telegram_bot`.
5.  Railway автоматически обнаружит `Dockerfile` и предложит развернуть его. Подтвердите.
6.  После создания сервиса перейдите в его настройки (вкладка "Settings").
7.  Перейдите в раздел "Variables".
8.  Нажмите "+ New Variable".
9.  **Variable Name:** `TELEGRAM_BOT_TOKEN`
10. **Variable Value:** Вставьте ваш секретный токен Telegram-бота.
11. Railway автоматически перезапустит сервис с новой переменной окружения.
12. Следите за логами развертывания и работы бота во вкладке "Deployments" -> выберите последнее развертывание -> "View Logs".
13. Проверьте работу бота в Telegram.