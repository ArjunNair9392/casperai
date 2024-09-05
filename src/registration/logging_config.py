# logging_config.py
import logging


def setup_logger():
    # Configure the logging system
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])

    # Create and return a logger named 'app'
    return logging.getLogger('app')


# Initialize the logger
logger = setup_logger()