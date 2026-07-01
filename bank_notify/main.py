import os
import sys
import signal
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from bank_notify.worker import run_worker_loop

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

def handle_worker_result(task: asyncio.Task):
    try:
        task.result()
    except Exception as exc:
        logging.critical(f"Worker task failed catastrophically: {exc}. Requesting shutdown.")
        os.kill(os.getpid(), signal.SIGTERM)

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(run_worker_loop())
    worker_task.add_done_callback(handle_worker_result)
    logging.info("Background notification worker started successfully.")

    yield

    logging.info("Stopping notification worker...")
    if not worker_task.done():
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logging.info("Background notification worker stopped gracefully.")
    else:
        try:
            exc = worker_task.exception()
            if exc:
                logging.error(f"Worker had already crashed before shutdown sequence: {exc}")
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)