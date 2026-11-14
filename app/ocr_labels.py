"""Recognize explicit stage labels with bounded OCR homoglyph substitutions."""
import re

_WORDS = re.compile(r'\b(?P<value>\d{1,3})[ \t]*(?P<word>[A-Za-zА-Яа-яЁё3]+)')
_GLYPHS = str.maketrans({'t': 'т', 'r': 'т', 'a': 'а', 'n': 'п', 'e': 'е', 'з': 'э', '3': 'э'})


def stage_candidates(text):
    for match in _WORDS.finditer(text):
        word = match['word'].casefold().translate(_GLYPHS)
        # Includes mixed-script этап/етап and the observed OCR rendering tran.
        if re.fullmatch(r'(?:[эе]?тап|ттап)(?:а|у|е|ом)?', word):
            value = int(match['value'])
            if 1 <= value <= 100:
                yield value, match.span('value')
