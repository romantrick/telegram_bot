import logging
import os
import requests
import decimal # Для точной работы с большими числами APY
import json
import asyncio
from web3 import Web3
from dotenv import load_dotenv # Добавляем импорт
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из файла .env
# Явно указываем путь к файлу .env
load_dotenv(dotenv_path='.env')

# ID криптовалют на CoinGecko
COIN_IDS = ["bitcoin", "ethereum", "curve-dao-token"]
VS_CURRENCY = "usd"  # Валюта для сравнения (доллары США)

# --- Aave V3 PoolDataProvider Configuration ---
AAVE_POOL_DATA_PROVIDER_ADDRESS = "0x7B4EB56E7CD4b454BA8ff71E4518426369a138a3"
# Minimal ABI for getReserveData function
# Corrected ABI for PoolDataProvider's getReserveData function
AAVE_POOL_DATA_PROVIDER_ABI = json.loads("""
[
  {
    "inputs": [
      {
        "internalType": "address",
        "name": "asset",
        "type": "address"
      }
    ],
    "name": "getReserveData",
    "outputs": [
      { "internalType": "uint256", "name": "output1", "type": "uint256" },
      { "internalType": "uint256", "name": "output2", "type": "uint256" },
      { "internalType": "uint256", "name": "output3", "type": "uint256" },
      { "internalType": "uint256", "name": "output4", "type": "uint256" },
      { "internalType": "uint256", "name": "output5", "type": "uint256" },
      { "internalType": "uint256", "name": "liquidityRate", "type": "uint256" },
      { "internalType": "uint256", "name": "output7", "type": "uint256" },
      { "internalType": "uint256", "name": "output8", "type": "uint256" },
      { "internalType": "uint256", "name": "output9", "type": "uint256" },
      { "internalType": "uint128", "name": "liquidityIndex", "type": "uint128" },
      { "internalType": "uint128", "name": "variableBorrowIndex", "type": "uint128" },
      { "internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40" }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]
""")
# Asset Addresses (Ethereum Mainnet)
WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Web3 Setup - Store RPC URL globally, initialize instance on demand
ETH_RPC_URL = os.getenv("ETH_RPC_URL")
if not ETH_RPC_URL:
    logger.warning("ETH_RPC_URL environment variable not set. Aave APY fetching will be disabled.")

# Константа для конвертации из RAY (27 знаков)
RAY = decimal.Decimal(10**27)

# Функция для получения цен с CoinGecko
def get_crypto_prices():
    """Получает текущие цены для BTC, ETH, CRV с CoinGecko."""
    ids = ",".join(COIN_IDS)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies={VS_CURRENCY}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверка на ошибки HTTP
        prices = response.json()
        return prices
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к CoinGecko: {e}")
        return None

# Функция для получения APY из Aave V3 PoolDataProvider
# Note: This is a synchronous function, call it with asyncio.to_thread from async handlers
def get_aave_asset_apy(w3_instance: Web3, asset_address: str, asset_symbol: str):
    """Получает текущий Supply APY для указанного актива из Aave V3 PoolDataProvider."""
    if not w3_instance:
        logger.error("Экземпляр Web3 не передан в get_aave_asset_apy.")
        return None

    try:
        # Создаем объект контракта
        pool_data_provider_contract = w3_instance.eth.contract( # Use w3_instance here
            address=AAVE_POOL_DATA_PROVIDER_ADDRESS,
            abi=AAVE_POOL_DATA_PROVIDER_ABI
        )

        # Вызываем функцию getReserveData
        # Адрес должен быть Checksum Address
        checksum_asset_address = w3_instance.to_checksum_address(asset_address) # Use w3_instance here
        reserve_data = pool_data_provider_contract.functions.getReserveData(checksum_asset_address).call()

        # Индексы нужных значений в кортеже результата:
        # liquidityRate = 5 (индекс)
        liquidity_rate_ray = reserve_data[5]

        # Конвертируем из RAY в проценты
        supply_apy_percent = (decimal.Decimal(liquidity_rate_ray) / RAY) * 100
        logger.info(f"Successfully fetched Aave APY for {asset_symbol}: {supply_apy_percent:.4f}% (RAY: {liquidity_rate_ray})")
        return supply_apy_percent

    except Exception as e:
        logger.error(f"Ошибка при запросе к Aave PoolDataProvider для {asset_symbol} ({asset_address}): {e}")
        return None
# Обработчик команды /prices
async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с текущими ценами криптовалют с CoinGecko."""
    prices = get_crypto_prices()
    if prices:
        message_lines = ["Текущие курсы (CoinGecko):\n"]
        # Форматируем вывод цен
        for coin_id in COIN_IDS:
            coin_data = prices.get(coin_id)
            if coin_data and VS_CURRENCY in coin_data:
                price = coin_data[VS_CURRENCY]
                # Получаем символ монеты для красивого отображения
                symbol = ""
                if coin_id == "bitcoin": symbol = "BTC"
                elif coin_id == "ethereum": symbol = "ETH"
                elif coin_id == "curve-dao-token": symbol = "CRV"
                message_lines.append(f"{symbol}: ${price:,.2f}") # Форматируем цену
            else:
                 message_lines.append(f"Не удалось получить цену для {coin_id.upper()}")

        message = "\n".join(message_lines)
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Не удалось получить курсы с CoinGecko. Попробуйте позже.")

# Обработчик команды /apy
async def apy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с текущими Aave V3 Supply APY."""
    if not ETH_RPC_URL:
        await update.message.reply_text("Ошибка: ETH_RPC_URL не установлен в переменных окружения.")
        return

    message_lines = ["Aave v3 Supply APY (Ethereum):\n"]
    apy_fetched = False

    # Получаем APY для WETH асинхронно
    try:
        logger.info("Попытка подключения к Ethereum RPC...")
        w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
        if not await asyncio.to_thread(w3.is_connected): # Проверяем соединение асинхронно
             logger.error(f"Не удалось подключиться к Ethereum node по адресу {ETH_RPC_URL}")
             await update.message.reply_text(f"Ошибка: Не удалось подключиться к Ethereum node.")
             return

        logger.info("Успешно подключено к Ethereum RPC. Запрос APY для WETH...")
        # Запускаем синхронную функцию в отдельном потоке, передавая w3
        weth_apy = await asyncio.to_thread(get_aave_asset_apy, w3, WETH_ADDRESS, "WETH")
        if weth_apy is not None:
            message_lines.append(f"  WETH: {weth_apy:.2f}%")
            apy_fetched = True
        else:
            message_lines.append("  WETH: Ошибка получения")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении WETH APY: {e}", exc_info=True)
        message_lines.append("  WETH: Ошибка получения (внутренняя)")


    # Получаем APY для USDC асинхронно
    try:
        # Используем тот же экземпляр w3, если он был успешно создан
        if not w3: # Дополнительная проверка на всякий случай
             logger.error("Экземпляр w3 не был создан ранее.")
             await update.message.reply_text("Внутренняя ошибка: экземпляр Web3 не создан.")
             return

        logger.info("Запрос APY для USDC...")
        # Запускаем синхронную функцию в отдельном потоке, передавая w3
        usdc_apy = await asyncio.to_thread(get_aave_asset_apy, w3, USDC_ADDRESS, "USDC")
        if usdc_apy is not None:
            message_lines.append(f"  USDC: {usdc_apy:.2f}%")
            apy_fetched = True
        else:
            message_lines.append("  USDC: Ошибка получения")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении USDC APY: {e}", exc_info=True)
        message_lines.append("  USDC: Ошибка получения (внутренняя)")


    if apy_fetched:
        await update.message.reply_text("\n".join(message_lines))
    else:
         await update.message.reply_text("Не удалось получить данные Aave APY. Проверьте логи или попробуйте позже.")

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я бот для отображения курсов криптовалют.",
        reply_markup=None, # Можно добавить клавиатуру, если нужно
    )
    await update.message.reply_text("Используйте команду /prices для курсов CoinGecko или /apy для Aave APY.")

def main() -> None:
    """Запускает бота."""
    # Получаем токен из переменной окружения
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Токен TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        return

    # Создаем приложение и передаем ему токен бота.
    # Увеличиваем таймауты для подключения и чтения до 30 секунд
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = Application.builder().token(token).request(request).build()

    # Регистрируем обработчик команды /prices
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("prices", prices_command))
    application.add_handler(CommandHandler("apy", apy_command)) # Добавляем новый обработчик

    # Запускаем бота до принудительной остановки
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()