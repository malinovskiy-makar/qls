"""Одноразовый скрипт: список имён CSS-переменных из templates/_tokens.html."""
import re
from pathlib import Path

TOKENS_FILE = Path(__file__).resolve().parent.parent / "templates" / "_tokens.html"
NAME_RE = re.compile(r"--[a-z0-9-]+")


def main():
    text = TOKENS_FILE.read_text(encoding="utf-8")
    names = sorted(set(NAME_RE.findall(text)))
    for name in names:
        print(name)


if __name__ == "__main__":
    main()
