import logging
import os
import requests
import json # Оставляем для загрузки конфига
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode # Для форматирования

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из файла .env
load_dotenv(dotenv_path='.env')

# --- Конфигурация ---
POOLS_CONFIG_PATH = "pools_config.json"
DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools" # Исправленный URL

# ID криптовалют на CoinGecko (для команды /prices)
COIN_IDS = ["bitcoin", "ethereum", "curve-dao-token"]
VS_CURRENCY = "usd"

# --- Вспомогательные функции ---

def load_pools_config(path: str = POOLS_CONFIG_PATH) -> list[dict]:
    """Загружает конфигурацию отслеживаемых пулов из JSON файла."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if not isinstance(config, list):
            logger.error(f"Ошибка: Файл конфигурации {path} должен содержать список JSON объектов.")
            return []
        logger.info(f"Успешно загружено {len(config)} пулов из {path}")
        return config
    except FileNotFoundError:
        logger.error(f"Ошибка: Файл конфигурации {path} не найден.")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON в файле {path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при чтении файла {path}: {e}")
        return []

def get_defilama_pools_data_sync() -> dict | None:
    """Синхронно получает данные о всех пулах с DefiLlama API."""
    try:
        response = requests.get(DEFILLAMA_POOLS_URL, timeout=20) # Увеличим таймаут
        response.raise_for_status()
        data = response.json()
        if 'data' in data and isinstance(data['data'], list):
            logger.info(f"Успешно получено {len(data['data'])} пулов с DefiLlama.")
            # Создаем словарь для быстрого доступа по ключу 'pool', пропуская пулы без него
            pools_dict_by_pool_key = {pool.get('pool'): pool for pool in data['data'] if pool.get('pool')}
            logger.info(f"Создан словарь для {len(pools_dict_by_pool_key)} пулов с ключом 'pool'.")
            return pools_dict_by_pool_key
        else:
            logger.error("Ошибка: Неожиданный формат ответа от DefiLlama API. Ключ 'data' отсутствует или не является списком.")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Ошибка: Таймаут при запросе к {DEFILLAMA_POOLS_URL}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к DefiLlama API: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"Ошибка декодирования JSON ответа от DefiLlama: {e}")
         return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении данных от DefiLlama: {e}")
        return None

def format_number(number) -> str:
    """Форматирует число для вывода (добавляет запятые, округляет)."""
    if number is None:
        return "N/A"
    try:
        num = float(number)
        if num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B"
        if num >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        if num >= 1_000:
            return f"{num / 1_000:.2f}K"
        if 0 < abs(num) < 0.01:
             return f"{num:.4f}" # Для очень маленьких APY
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return "N/A"

# --- Обработчики команд ---

# Функция для получения цен с CoinGecko (остается без изменений)
def get_crypto_prices():
    """Получает текущие цены для BTC, ETH, CRV с CoinGecko."""
    ids = ",".join(COIN_IDS)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies={VS_CURRENCY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        prices = response.json()
        return prices
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к CoinGecko: {e}")
        return None

async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с текущими ценами криптовалют с CoinGecko."""
    prices = await asyncio.to_thread(get_crypto_prices) # Выполняем синхронный запрос в потоке
    if prices:
        message_lines = ["*Текущие курсы (CoinGecko):*\n"]
        for coin_id in COIN_IDS:
            coin_data = prices.get(coin_id)
            if coin_data and VS_CURRENCY in coin_data:
                price = coin_data[VS_CURRENCY]
                symbol = ""
                if coin_id == "bitcoin": symbol = "BTC"
                elif coin_id == "ethereum": symbol = "ETH"
                elif coin_id == "curve-dao-token": symbol = "CRV"
                # Используем MarkdownV2 для форматирования
                message_lines.append(f"`{symbol}`: `${format_number(price)}`")
            else:
                 message_lines.append(f"Не удалось получить цену для `{coin_id.upper()}`")

        message = "\n".join(message_lines)
        # Указываем parse_mode=ParseMode.MARKDOWN_V2
        # Экранируем символы, которые могут конфликтовать с Markdown V2, если нужно
        # В данном случае format_number уже возвращает строки, безопасные для Markdown
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text("Не удалось получить курсы с CoinGecko. Попробуйте позже.")


async def pools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с APY и TVL для отслеживаемых пулов из DefiLlama."""
    await update.message.reply_text("Запрашиваю данные из DefiLlama, это может занять некоторое время...")

    # 1. Загружаем конфигурацию
    tracked_pools = load_pools_config()
    if not tracked_pools:
        await update.message.reply_text("Ошибка: Не удалось загрузить конфигурацию пулов.")
        return

    # 2. Получаем данные от DefiLlama (выполняем синхронную функцию в потоке)
    defilama_data_dict = await asyncio.to_thread(get_defilama_pools_data_sync)
    if defilama_data_dict is None:
        await update.message.reply_text("Ошибка: Не удалось получить данные от DefiLlama API.")
        return

    # 3. Сопоставляем и форматируем результат
    message_lines = ["*Данные по пулам (DefiLlama):*\n"]
    found_count = 0

    for pool_config in tracked_pools:
        pool_id = pool_config.get("defilama_id")
        user_comment = pool_config.get("user_comment", "N/A")
        found_pool_data = None
        # Используем 'defilama_id' из конфига как ключ 'pool' для поиска в словаре
        pool_key_from_config = pool_id # pool_id из конфига теперь ищем как ключ 'pool'

        # Поиск по ключу 'pool' (бывший 'id')
        if pool_key_from_config and pool_key_from_config in defilama_data_dict:
            found_pool_data = defilama_data_dict[pool_key_from_config]
            found_count += 1
        else:
            # Поиск по chain/project/symbol (оставляем как запасной вариант, если ID/pool не найден)
            # Этот поиск может быть неточным и медленным, если пулов много
            conf_chain = pool_config.get("chain", "").lower()
            conf_project = pool_config.get("project", "").lower()
            conf_symbol = pool_config.get("symbol", "").lower()

            # Простая проверка на пустые значения перед поиском
            if conf_chain and conf_project and conf_symbol:
                for llama_pool in defilama_data_dict.values():
                    llama_chain = llama_pool.get("chain", "").lower()
                    llama_project = llama_pool.get("project", "").lower()
                    llama_symbol = llama_pool.get("symbol", "").lower()

                    # Сравнение (можно улучшить, например, убрав пробелы)
                    if (llama_chain == conf_chain and
                        llama_project == conf_project and
                        llama_symbol == conf_symbol):
                        found_pool_data = llama_pool
                        found_count += 1
                        logger.info(f"Найден пул по совпадению chain/project/symbol: {user_comment}")
                        break # Нашли первое совпадение

        # Формируем строку для сообщения
        if found_pool_data:
            apy = found_pool_data.get('apy') # Попробуем сначала 'apy'
            if apy is None:
                 apy = found_pool_data.get('apyBase') # Если нет 'apy', попробуем 'apyBase'
            # Можно добавить логику для apyReward, если нужно
            tvl = found_pool_data.get('tvlUsd')
            # Используем MarkdownV2
            message_lines.append(
                f"`{user_comment}`: APY `{format_number(apy)}%`, TVL `${format_number(tvl)}`"
            )
        else:
            message_lines.append(f"`{user_comment}`: Не найден")

    if found_count == 0 and len(tracked_pools) > 0:
         message_lines.append("\n_Не удалось найти данные ни для одного из отслеживаемых пулов._")
    elif found_count < len(tracked_pools):
         message_lines.append(f"\n_Найдено данных для {found_count} из {len(tracked_pools)} пулов._")

    # Отправляем сообщение (может быть длинным, Telegram обрежет, если нужно)
    # Разбивка на части, если сообщение слишком длинное
    full_message = "\n".join(message_lines)
    max_length = 4096 # Макс. длина сообщения Telegram
    if len(full_message) <= max_length:
        await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        logger.warning("Сообщение слишком длинное, отправляю по частям.")
        for i in range(0, len(full_message), max_length):
            part = full_message[i:i + max_length]
            # Добавляем уведомление о продолжении, если это не последняя часть
            is_last_part = (i + max_length) >= len(full_message)
            if not is_last_part:
                 # Ищем последний перенос строки, чтобы не резать слово/форматирование
                 last_newline = part.rfind('\n')
                 if last_newline != -1:
                     part = part[:last_newline]
                 part += "\n_(продолжение следует...)_"

            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN_V2)
            await asyncio.sleep(0.5) # Небольшая задержка между частями


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я бот для мониторинга пулов DefiLlama.",
        reply_markup=None,
    )
    await update.message.reply_text(
        "Используйте команду /pools для получения данных APY и TVL по настроенным пулам.\n"
        "Используйте команду /prices для получения курсов BTC, ETH, CRV с CoinGecko."
    )

def main() -> None:
    """Запускает бота."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Токен TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        return

    # Увеличиваем таймауты
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, pool_timeout=30.0) # Добавим pool_timeout
    application = Application.builder().token(token).request(request).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("prices", prices_command))
    application.add_handler(CommandHandler("pools", pools_command)) # Заменили /apy на /pools

    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()