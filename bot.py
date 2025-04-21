import logging
import os
import requests
import json # Оставляем для загрузки конфига
import asyncio
import html # Для экранирования HTML символов
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # Добавляем импорты для Inline Keyboard
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler # Добавляем CallbackQueryHandler
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
    logger.info(f"Запрос данных с {DEFILLAMA_POOLS_URL}...")
    try:
        response = requests.get(DEFILLAMA_POOLS_URL, timeout=30) # Увеличим таймаут еще
        logger.info(f"Статус ответа: {response.status_code}")
        response.raise_for_status() # Вызовет исключение для 4xx/5xx
        data = response.json()
        if 'data' in data and isinstance(data['data'], list):
            logger.info(f"Успешно получено {len(data['data'])} пулов с DefiLlama.")
            # Создаем словарь для быстрого доступа по ключу 'pool', пропуская пулы без него
            pools_dict_by_pool_key = {pool.get('pool'): pool for pool in data['data'] if pool.get('pool')}
            logger.info(f"Создан словарь для {len(pools_dict_by_pool_key)} пулов с ключом 'pool'.")
            return pools_dict_by_pool_key
        else:
            logger.error("Ошибка: Неожиданный формат ответа от DefiLlama API. Ключ 'data' отсутствует или не является списком.")
            logger.debug(f"Содержимое ответа (первые 500 символов): {str(response.content)[:500]}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Ошибка: Таймаут при запросе к {DEFILLAMA_POOLS_URL}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"Ошибка HTTP при запросе к DefiLlama API: {e}")
        logger.debug(f"Содержимое ответа (первые 500 символов): {str(response.content)[:500]}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при запросе к DefiLlama API: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"Ошибка декодирования JSON ответа от DefiLlama: {e}")
         logger.debug(f"Содержимое ответа (первые 500 символов): {str(response.content)[:500]}")
         return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении данных от DefiLlama: {e}", exc_info=True)
        return None

# Обновляем format_number для HTML и без экранирования точек
def format_number(number) -> str:
    """Форматирует число для вывода (добавляет запятые, округляет)."""
    if number is None:
        return "N/A"
    try:
        num = float(number)
        formatted_num_str = ""
        if num >= 1_000_000_000:
            formatted_num_str = f"{num / 1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            formatted_num_str = f"{num / 1_000_000:.2f}M"
        elif num >= 1_000:
            formatted_num_str = f"{num / 1_000:.2f}K"
        elif 0 < abs(num) < 0.01:
             formatted_num_str = f"{num:.4f}" # Для очень маленьких APY
        else:
            formatted_num_str = f"{num:,.2f}"
        # Не экранируем точку для HTML
        return formatted_num_str
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
        # Используем HTML для форматирования
        message_lines = ["<b>Текущие курсы (CoinGecko):</b>\n"]
        for coin_id in COIN_IDS:
            coin_data = prices.get(coin_id)
            if coin_data and VS_CURRENCY in coin_data:
                price = coin_data[VS_CURRENCY]
                symbol = ""
                if coin_id == "bitcoin": symbol = "BTC"
                elif coin_id == "ethereum": symbol = "ETH"
                elif coin_id == "curve-dao-token": symbol = "CRV"
                message_lines.append(f"<code>{symbol}</code>: ${format_number(price)}")
            else:
                 message_lines.append(f"Не удалось получить цену для <code>{coin_id.upper()}</code>")

        message = "\n".join(message_lines)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Не удалось получить курсы с CoinGecko. Попробуйте позже.")

# Команда /pools теперь инициирует выбор сети
async def pools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает процесс выбора сети для фильтрации пулов."""
    tracked_pools = load_pools_config()
    if not tracked_pools:
        await update.message.reply_text("Ошибка: Не удалось загрузить конфигурацию пулов.")
        return

    # Получаем уникальные сети из конфига
    chains = sorted(list(set(pool.get("chain", "Unknown") for pool in tracked_pools)))

    keyboard = []
    # Создаем кнопки для каждой сети (2 в ряд)
    row = []
    for chain in chains:
        # callback_data будет содержать префикс и название сети
        row.append(InlineKeyboardButton(chain.capitalize(), callback_data=f"select_chain:{chain}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: # Добавляем оставшиеся кнопки, если их нечетное число
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите сеть:", reply_markup=reply_markup)

# Новый обработчик для кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на Inline кнопки."""
    query = update.callback_query
    await query.answer() # Отвечаем на callback, чтобы убрать "часики" у кнопки

    callback_data = query.data
    parts = callback_data.split(":", 2) # Разделяем callback_data
    action = parts[0]

    # --- Шаг 1: Выбрана сеть ---
    if action == "select_chain":
        selected_chain = parts[1]
        context.user_data['selected_chain'] = selected_chain # Сохраняем выбор

        tracked_pools = load_pools_config()
        # Получаем уникальные группы для выбранной сети
        groups = sorted(list(set(
            pool.get("ticker_group", "Unknown")
            for pool in tracked_pools
            if pool.get("chain", "").lower() == selected_chain.lower() and pool.get("ticker_group")
        )))

        keyboard = []
        row = []
        # Кнопка "Все группы"
        row.append(InlineKeyboardButton("Все группы", callback_data=f"select_group:{selected_chain}:all_groups"))
        # Кнопки для каждой группы (2 в ряд)
        for group in groups:
            row.append(InlineKeyboardButton(group.capitalize(), callback_data=f"select_group:{selected_chain}:{group}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"Сеть: <b>{html.escape(selected_chain.capitalize())}</b>\nВыберите группу тикеров:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

    # --- Шаг 2: Выбрана группа ---
    elif action == "select_group":
        if len(parts) < 3:
             logger.warning(f"Некорректный callback_data для select_group: {callback_data}")
             await query.edit_message_text(text="Произошла ошибка. Попробуйте снова /pools")
             return

        selected_chain = parts[1]
        selected_group = parts[2]

        # Проверяем, что сеть была сохранена
        if context.user_data.get('selected_chain') != selected_chain:
            logger.warning(f"Несовпадение сети в user_data и callback_data: {context.user_data.get('selected_chain')} vs {selected_chain}")
            await query.edit_message_text(text="Произошла ошибка состояния. Попробуйте снова /pools")
            return

        await query.edit_message_text(text=f"Сеть: <b>{html.escape(selected_chain.capitalize())}</b>\nГруппа: <b>{html.escape(selected_group.capitalize() if selected_group != 'all_groups' else 'Все')}</b>\n\nЗапрашиваю данные...", parse_mode=ParseMode.HTML)

        # Получаем данные от DefiLlama
        defilama_data_dict = await asyncio.to_thread(get_defilama_pools_data_sync)
        if defilama_data_dict is None:
            await query.edit_message_text(text="Ошибка: Не удалось получить данные от DefiLlama API.")
            return

        # Фильтруем пулы из конфига по выбранной сети и группе
        tracked_pools = load_pools_config()
        filtered_config_pools = [
            pool for pool in tracked_pools
            if pool.get("chain", "").lower() == selected_chain.lower() and
               (selected_group == "all_groups" or pool.get("ticker_group", "").lower() == selected_group.lower())
        ]

        if not filtered_config_pools:
             await query.edit_message_text(text=f"Не найдено настроенных пулов для сети <b>{html.escape(selected_chain.capitalize())}</b> и группы <b>{html.escape(selected_group.capitalize() if selected_group != 'all_groups' else 'Все')}</b>.", parse_mode=ParseMode.HTML)
             return

        # Сопоставляем и готовим данные для вывода
        results = []
        max_project_len = 0
        max_symbol_len = 0

        for pool_config in filtered_config_pools:
            pool_key_from_config = pool_config.get("defilama_id") # Ищем по ID/ключу 'pool'
            found_pool_data = None

            if pool_key_from_config and pool_key_from_config in defilama_data_dict:
                found_pool_data = defilama_data_dict[pool_key_from_config]
            else:
                # Поиск по chain/project/symbol (запасной вариант)
                conf_chain = pool_config.get("chain", "").lower()
                conf_project = pool_config.get("project", "").lower()
                conf_symbol = pool_config.get("symbol", "").lower()
                if conf_chain and conf_project and conf_symbol:
                    for llama_pool in defilama_data_dict.values():
                        # Сравнение должно быть более точным, возможно, с учетом регистра для project/symbol
                        if (llama_pool.get("chain", "").lower() == conf_chain and
                            llama_pool.get("project", "") == pool_config.get("project", "") and # Сверяем с оригиналом из конфига
                            llama_pool.get("symbol", "") == pool_config.get("symbol", "")):
                            found_pool_data = llama_pool
                            logger.info(f"Найден пул по совпадению chain/project/symbol: {pool_config.get('user_comment')}")
                            break

            if found_pool_data:
                project = found_pool_data.get('project', 'N/A')
                symbol = found_pool_data.get('symbol', 'N/A')
                apy = found_pool_data.get('apy')
                if apy is None:
                    apy = found_pool_data.get('apyBase')
                tvl = found_pool_data.get('tvlUsd')

                results.append({
                    "project": project,
                    "symbol": symbol,
                    "apy": apy,
                    "tvl": tvl
                })
                # Обновляем максимальную длину для выравнивания
                max_project_len = max(max_project_len, len(project))
                max_symbol_len = max(max_symbol_len, len(symbol))

        # Форматируем вывод
        if not results:
            message = f"Не найдено данных в DefiLlama для пулов сети <b>{html.escape(selected_chain.capitalize())}</b> и группы <b>{html.escape(selected_group.capitalize() if selected_group != 'all_groups' else 'Все')}</b>."
        else:
            message_lines = [f"<b>Пулы для сети {html.escape(selected_chain.capitalize())} / группа {html.escape(selected_group.capitalize() if selected_group != 'all_groups' else 'Все')}:</b>\n"]
            # Рассчитываем ширину для числовых полей (примерно)
            max_apy_len = 7 # Примерно: "123.45%"
            max_tvl_len = 10 # Примерно: "$123.45B"

            for res in results:
                # Экранируем HTML символы в данных перед вставкой в <code>
                project_str = html.escape(res['project']).ljust(max_project_len)
                symbol_str = html.escape(res['symbol']).ljust(max_symbol_len)
                apy_str = (format_number(res['apy']) + '%').rjust(max_apy_len)
                tvl_str = ('$' + format_number(res['tvl'])).rjust(max_tvl_len)
                message_lines.append(f"<code>{project_str} - {symbol_str} : {apy_str}, {tvl_str}</code>")

            message = "\n".join(message_lines)

        # Отправляем или редактируем сообщение
        # Разбивка на части, если нужно (логика аналогична предыдущей, но с HTML)
        max_length = 4096
        if len(message) <= max_length:
            await query.edit_message_text(text=message, parse_mode=ParseMode.HTML)
        else:
            # Отправляем первую часть через edit, остальные через send_message
            first_part = message[:max_length]
            # Обрезаем до последнего переноса строки
            last_newline = first_part.rfind('\n')
            if last_newline != -1:
                first_part = first_part[:last_newline]
            await query.edit_message_text(text=first_part, parse_mode=ParseMode.HTML)

            remaining_message = message[len(first_part):].strip()
            for i in range(0, len(remaining_message), max_length):
                 part = remaining_message[i:i + max_length]
                 await context.bot.send_message(chat_id=query.message.chat_id, text=part, parse_mode=ParseMode.HTML)
                 await asyncio.sleep(0.5)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я бот для мониторинга пулов DefiLlama.",
        reply_markup=None,
    )
    await update.message.reply_text(
        "Используйте команду /pools для выбора сети и группы тикеров.\n"
        "Используйте команду /prices для получения курсов BTC, ETH, CRV с CoinGecko."
    )

# Обновляем main для добавления CallbackQueryHandler
def main() -> None:
    """Запускает бота."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Токен TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        return

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, pool_timeout=30.0)
    application = Application.builder().token(token).request(request).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("prices", prices_command))
    application.add_handler(CommandHandler("pools", pools_command))
    # Добавляем обработчик для кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()