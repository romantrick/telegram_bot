import os
import decimal
import json
import logging
from web3 import Web3
from dotenv import load_dotenv

# Включаем базовое логирование для отладки web3
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Aave V3 PoolDataProvider Configuration ---
AAVE_POOL_DATA_PROVIDER_ADDRESS = "0x7B4EB56E7CD4b454BA8ff71E4518426369a138a3"
# ABI for PoolDataProvider's getReserveData function - matching error output types
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
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

# Константа для конвертации из RAY (27 знаков)
RAY = decimal.Decimal(10**27)

# Функция для получения APY из Aave V3 PoolDataProvider
def get_aave_asset_apy(w3_instance, asset_address: str, asset_symbol: str):
    """Получает текущий Supply APY для указанного актива из Aave V3 PoolDataProvider."""
    if not w3_instance:
        logger.error("Экземпляр Web3 не инициализирован.")
        return None

    try:
        # Создаем объект контракта PoolDataProvider
        pool_data_provider_contract = w3_instance.eth.contract(
            address=AAVE_POOL_DATA_PROVIDER_ADDRESS,
            abi=AAVE_POOL_DATA_PROVIDER_ABI
        )

        # Вызываем функцию getReserveData
        # Адрес должен быть Checksum Address
        checksum_asset_address = w3_instance.to_checksum_address(asset_address)
        logger.info(f"Вызов PoolDataProvider.getReserveData для {asset_symbol} ({checksum_asset_address})...")
        # Возвращает кортеж с 12 элементами согласно ABI
        reserve_data = pool_data_provider_contract.functions.getReserveData(checksum_asset_address).call()
        logger.info(f"Получены данные резерва для {asset_symbol}.")
        # Извлекаем liquidityRate (индекс 5 в кортеже)
        # Это uint256, выражено в RAY
        liquidity_rate_ray = reserve_data[5]

        # Конвертируем из RAY в проценты
        supply_apy_percent = (decimal.Decimal(liquidity_rate_ray) / RAY) * 100
        logger.info(f"Успешно рассчитан Aave APY для {asset_symbol}: {supply_apy_percent:.4f}% (RAY: {liquidity_rate_ray})")
        return supply_apy_percent

    except Exception as e:
        logger.error(f"Ошибка при запросе к Aave PoolDataProvider для {asset_symbol} ({asset_address}): {e}", exc_info=True)
        return None

if __name__ == "__main__":
    # Загружаем переменные окружения из файла .env
    load_dotenv()
    eth_rpc_url = os.getenv("ETH_RPC_URL")

    if not eth_rpc_url:
        print("Ошибка: Переменная окружения ETH_RPC_URL не найдена в файле .env")
        exit(1)

    print(f"Используется Ethereum RPC URL: {eth_rpc_url}")

    # Инициализация Web3
    w3 = Web3(Web3.HTTPProvider(eth_rpc_url))

    # Проверка соединения
    if not w3.is_connected():
        print(f"Ошибка: Не удалось подключиться к узлу Ethereum по адресу {eth_rpc_url}")
        exit(1)

    print("Успешно подключено к узлу Ethereum.")
    print(f"Получение Supply APY из Aave V3...")
    print("-" * 30)

    # --- Получаем APY для USDC ---
    print(f"Запрос APY для USDC ({USDC_ADDRESS})...")
    usdc_apy = get_aave_asset_apy(w3, USDC_ADDRESS, "USDC")
    if usdc_apy is not None:
        print(f"Текущий Aave V3 Supply APY для USDC: {usdc_apy:.4f}%")
    else:
        print("Не удалось получить APY для USDC.")
    print("-" * 30)

    # --- Получаем APY для WETH ---
    print(f"Запрос APY для WETH ({WETH_ADDRESS})...")
    weth_apy = get_aave_asset_apy(w3, WETH_ADDRESS, "WETH")
    if weth_apy is not None:
        print(f"Текущий Aave V3 Supply APY для WETH: {weth_apy:.4f}%")
    else:
        print("Не удалось получить APY для WETH.")
    print("-" * 30)