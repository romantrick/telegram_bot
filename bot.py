import logging
import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ID криптовалют на CoinGecko
COIN_IDS = ["bitcoin", "ethereum", "curve-dao-token"]
VS_CURRENCY = "usd"  # Валюта для сравнения (доллары США)

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

        message = "\n".join(message_lines)
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Не удалось получить данные о курсах. Попробуйте позже.")

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
    application.add_handler(CommandHandler("prices", prices_command))

    # Запускаем бота до принудительной остановки
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()