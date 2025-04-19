import logging
import os

import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)


logger = logging.getLogger('bot')

logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler('logs/bot.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.handlers = []
logger.addHandler(console_handler)
logger.addHandler(file_handler)

redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True
)
