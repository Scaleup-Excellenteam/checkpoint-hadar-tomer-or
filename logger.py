import os
import logging

"""
usage

from logger import setup_logger
import logging

setup_logger("CLIENT") / setup_logger("SERVER")

logger = logging.getLogger(__name__)

logger.info("User %s joined room %s", username, room)
logger.debug("debug: User %s joined room %s", username, room)
"""      

def setup_logger(role: str):
    os.makedirs("Log", exist_ok=True)
    log_file = os.path.join("Log", f"app_{role.lower()}.log")
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s | {role} | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),          # console
            logging.FileHandler(log_file)     # file
        ]
    )