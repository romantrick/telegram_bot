import logging
import os
import requests
import decimal # Для точной работы с большими числами APY
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest # Уже импортировано ниже, но убедимся

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ID криптовалют на CoinGecko
COIN_IDS = ["bitcoin", "ethereum", "curve-dao-token"]
VS_CURRENCY = "usd"  # Валюта для сравнения (доллары США)

# Константы для Aave V3 Subgraph (Ethereum Mainnet)
AAVE_SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/aave/protocol-v3"
# ID резерва USDC в Aave V3 Mainnet (underlyingAsset + poolAddress)
USDC_RESERVE_ID = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
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

# Функция для получения APY из Aave V3 Subgraph
def get_aave_usdc_apy():
   """Получает текущий Supply APY для USDC из Aave V3 Subgraph."""
   query = f"""
   {{
     reserve(id: "{USDC_RESERVE_ID}") {{
       symbol
       supplyAPY # Возвращается в формате RAY (10^27)
     }}
   }}
   """
   try:
       response = requests.post(AAVE_SUBGRAPH_URL, json={'query': query})
       response.raise_for_status()
       data = response.json()

       if "errors" in data:
           logger.error(f"Ошибка GraphQL: {data['errors']}")
           return None

       reserve_data = data.get("data", {}).get("reserve")
       if reserve_data and "supplyAPY" in reserve_data:
           # Конвертируем из RAY в проценты
           supply_apy_ray = decimal.Decimal(reserve_data["supplyAPY"])
           supply_apy_percent = (supply_apy_ray / RAY) * 100
           return supply_apy_percent
       else:
           logger.warning("Не удалось найти supplyAPY для USDC в ответе subgraph.")
           return None

   except requests.exceptions.RequestException as e:
       logger.error(f"Ошибка при запросе к Aave Subgraph: {e}")
       return None
   except (KeyError, TypeError, ValueError, decimal.InvalidOperation) as e:
       logger.error(f"Ошибка при обработке ответа от Aave Subgraph: {e}")
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
        # Добавляем Aave APY
        usdc_apy = get_aave_usdc_apy()
        if usdc_apy is not None:
            message_lines.append(f"\nAave v3 USDC Supply APY: {usdc_apy:.2f}%")
        else:
            message_lines.append("\nНе удалось получить Aave USDC APY.")

        message = "\n".join(message_lines)
        await update.message.reply_text(message)
    else:
        # Если не удалось получить цены CoinGecko, все равно попробуем получить APY
        usdc_apy = get_aave_usdc_apy()
        if usdc_apy is not None:
             await update.message.reply_text(f"Не удалось получить курсы CoinGecko.\nAave v3 USDC Supply APY: {usdc_apy:.2f}%")
        else:
             await update.message.reply_text("Не удалось получить данные ни о курсах CoinGecko, ни об Aave USDC APY. Попробуйте позже.")

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