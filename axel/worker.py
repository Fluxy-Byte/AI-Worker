import os

from dotenv import load_dotenv

load_dotenv()

from src.infra.health.server import start_health_server
from src.services.queue.consumer import start_consumer

if __name__ == "__main__":
    start_health_server(port=int(os.getenv("PORT", "7074")))
    start_consumer()
