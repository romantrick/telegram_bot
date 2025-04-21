# Используем официальный образ Python 3.9 slim как базовый
FROM python:3.10-slim

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
COPY bot.py .
# Копируем файл конфигурации пулов
COPY pools_config.json .

# Указываем команду для запуска бота при старте контейнера
# Python запускается с флагом -u для небуферизованного вывода,
# что полезно для просмотра логов в Render
CMD ["python", "-u", "bot.py"]