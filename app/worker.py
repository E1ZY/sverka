import logging

from .pipeline import loop

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop()
