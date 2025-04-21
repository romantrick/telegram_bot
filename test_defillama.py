# test_defillama.py
import requests
import json
import logging

# Настройка логирования (для вывода в консоль)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация (копируем из bot.py)
POOLS_CONFIG_PATH = "pools_config.json"
DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"

# Функции (копируем из bot.py)
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
            # Выведем первые 2 объекта для анализа структуры
            if len(data['data']) > 0:
                logger.info("--- Пример данных пула (первые 2): ---")
                for i, pool_sample in enumerate(data['data'][:2]):
                    logger.info(f"Пул {i+1}: {json.dumps(pool_sample, indent=2)}")
                logger.info("------------------------------------")

            # Создаем словарь для быстрого доступа по ID, пропуская пулы без 'id'
            # Используем 'pool' в качестве ключа, так как 'id' отсутствует или ненадежен
            pools_dict_by_pool_key = {pool.get('pool'): pool for pool in data['data'] if pool.get('pool')}
            logger.info(f"Создан словарь для {len(pools_dict_by_pool_key)} пулов с ключом 'pool'.")
            # Возвращаем словарь, используя 'pool' как ключ
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

# Основной блок для тестирования
if __name__ == "__main__":
    logger.info("--- Запуск теста DefiLlama API ---")

    # 1. Загружаем конфигурацию
    tracked_pools = load_pools_config()
    if not tracked_pools:
        logger.error("Тест прерван: не удалось загрузить конфигурацию.")
        exit()

    # 2. Получаем данные от DefiLlama
    defilama_data_dict = get_defilama_pools_data_sync()
    if defilama_data_dict is None:
        logger.error("Тест прерван: не удалось получить данные от DefiLlama.")
        exit()

    # 3. Сопоставляем и выводим результат для первых 5 пулов
    logger.info("\n--- Результаты сопоставления (первые 5 пулов): ---")
    found_count = 0
    for i, pool_config in enumerate(tracked_pools[:5]): # Берем только первые 5 для теста
        pool_id = pool_config.get("defilama_id")
        user_comment = pool_config.get("user_comment", "N/A")
        found_pool_data = None
        result_line = f"Пул '{user_comment}': "
        # Используем 'defilama_id' из конфига как ключ 'pool' для поиска в словаре
        pool_key_from_config = pool_id # pool_id из конфига теперь ищем как ключ 'pool'

        # Поиск по ключу 'pool' (бывший 'id')
        if pool_key_from_config and pool_key_from_config in defilama_data_dict:
            found_pool_data = defilama_data_dict[pool_key_from_config]
            found_count += 1
        else:
            # Поиск по chain/project/symbol (оставляем как запасной вариант)
            conf_chain = pool_config.get("chain", "").lower()
            conf_project = pool_config.get("project", "").lower()
            conf_symbol = pool_config.get("symbol", "").lower()

            if conf_chain and conf_project and conf_symbol:
                for llama_pool in defilama_data_dict.values():
                    llama_chain = llama_pool.get("chain", "").lower()
                    llama_project = llama_pool.get("project", "").lower()
                    llama_symbol = llama_pool.get("symbol", "").lower()

                    if (llama_chain == conf_chain and
                        llama_project == conf_project and
                        llama_symbol == conf_symbol):
                        found_pool_data = llama_pool
                        found_count += 1
                        logger.info(f"(Найден по совпадению для '{user_comment}')")
                        break

        # Формируем строку для вывода
        if found_pool_data:
            apy = found_pool_data.get('apy')
            if apy is None:
                 apy = found_pool_data.get('apyBase')
            tvl = found_pool_data.get('tvlUsd')
            result_line += f"Найден -> APY: {format_number(apy)}%, TVL: ${format_number(tvl)}"
            # Дополнительно выведем сам найденный объект для отладки
            # logger.debug(f"Данные для '{user_comment}': {found_pool_data}")
        else:
            result_line += "Не найден"

        logger.info(result_line)

    logger.info(f"\n--- Тест завершен. Найдено данных для {found_count} из 5 проверенных пулов. ---")