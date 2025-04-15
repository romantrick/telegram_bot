import logging
import os
import requests
import decimal # Для точной работы с большими числами APY
import json
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
load_dotenv()

# ID криптовалют на CoinGecko
COIN_IDS = ["bitcoin", "ethereum", "curve-dao-token"]
VS_CURRENCY = "usd"  # Валюта для сравнения (доллары США)

# --- Aave V3 PoolDataProvider Configuration ---
AAVE_POOL_DATA_PROVIDER_ADDRESS = "0x7B4EB56E7CD4b454BA8ff71E4518426369a138a3"
# Minimal ABI for getReserveData function
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
      { "internalType": "uint256", "name": "unbacked", "type": "uint256" },
      { "internalType": "uint256", "name": "accruedToTreasuryScaled", "type": "uint256" },
      { "internalType": "uint256", "name": "totalAToken", "type": "uint256" },
      { "internalType": "uint256", "name": "totalStableDebt", "type": "uint256" },
      { "internalType": "uint256", "name": "totalVariableDebt", "type": "uint256" },
      { "internalType": "uint256", "name": "liquidityRate", "type": "uint256" },
      { "internalType": "uint256", "name": "variableBorrowRate", "type": "uint256" },
      { "internalType": "uint256", "name": "stableBorrowRate", "type": "uint256" },
      { "internalType": "uint256", "name": "averageStableBorrowRate", "type": "uint256" },
      { "internalType": "uint40", "name": "liquidityIndex", "type": "uint40" },
      { "internalType": "uint40", "name": "variableBorrowIndex", "type": "uint40" },
      { "internalType": "uint128", "name": "lastUpdateTimestamp", "type": "uint128" }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]
""")
# Asset Addresses (Ethereum Mainnet)
WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Web3 Setup
ETH_RPC_URL = os.getenv("ETH_RPC_URL")
if not ETH_RPC_URL:
    logger.warning("ETH_RPC_URL environment variable not set. Aave APY fetching will be disabled.")
    w3 = None
else:
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        logger.error(f"Failed to connect to Ethereum node at {ETH_RPC_URL}")
        w3 = None # Disable if connection fails

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
def get_aave_asset_apy(asset_address: str, asset_symbol: str):
    """Получает текущий Supply APY для указанного актива из Aave V3 PoolDataProvider."""
    if not w3:
        logger.warning("Web3 connection not available. Skipping Aave APY fetch.")
        return None

    try:
        # Создаем объект контракта
        pool_data_provider_contract = w3.eth.contract(
            address=AAVE_POOL_DATA_PROVIDER_ADDRESS,
            abi=AAVE_POOL_DATA_PROVIDER_ABI
        )

        # Вызываем функцию getReserveData
        # Адрес должен быть Checksum Address
        checksum_asset_address = w3.to_checksum_address(asset_address)
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
    """Отправляет сообщение с текущими ценами криптовалют."""
    prices = get_crypto_prices()
    if prices:
        message_lines = ["Текущие курсы:\n"]
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

        # --- Добавляем Aave APY ---
        message_lines.append("\nAave v3 Supply APY (Ethereum):")

        # Получаем APY для WETH
        weth_apy = get_aave_asset_apy(WETH_ADDRESS, "WETH")
        if weth_apy is not None:
            message_lines.append(f"  WETH: {weth_apy:.2f}%")
        else:
            message_lines.append("  WETH: Ошибка получения")

        # Получаем APY для USDC
        usdc_apy = get_aave_asset_apy(USDC_ADDRESS, "USDC")
        if usdc_apy is not None:
            message_lines.append(f"  USDC: {usdc_apy:.2f}%")
        else:
            message_lines.append("  USDC: Ошибка получения")
        # --- Конец блока Aave APY ---

        message = "\n".join(message_lines)
        await update.message.reply_text(message)
    else:
        # Если не удалось получить цены CoinGecko, все равно попробуем получить APY
        message_lines = ["Не удалось получить курсы CoinGecko."]
        message_lines.append("\nAave v3 Supply APY (Ethereum):")
        weth_apy = get_aave_asset_apy(WETH_ADDRESS, "WETH")
        usdc_apy = get_aave_asset_apy(USDC_ADDRESS, "USDC")

        apy_fetched = False
        if weth_apy is not None:
            message_lines.append(f"  WETH: {weth_apy:.2f}%")
            apy_fetched = True
        else:
            message_lines.append("  WETH: Ошибка получения")

        if usdc_apy is not None:
            message_lines.append(f"  USDC: {usdc_apy:.2f}%")
            apy_fetched = True
        else:
            message_lines.append("  USDC: Ошибка получения")

        if apy_fetched:
            await update.message.reply_text("\n".join(message_lines))
        else:
             await update.message.reply_text("Не удалось получить данные ни о курсах CoinGecko, ни об Aave APY. Попробуйте позже.")

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я бот для отображения курсов криптовалют.",
        reply_markup=None, # Можно добавить клавиатуру, если нужно
    )
    await update.message.reply_text("Используйте команду /prices, чтобы узнать текущие курсы BTC, ETH и CRV.")

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

    # Запускаем бота до принудительной остановки
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()