
"""Extract role-focused text from Greenhouse job descriptions."""

from html import unescape
from bs4 import BeautifulSoup


BOILERPLATE_CLASSES = (".content-intro", ".content-conclusion")


def clean_description(description: str | None) -> str:
    """Remove HTML and common employer boilerplate."""
    if not description:
        return ""

    soup = BeautifulSoup(
        unescape(unescape(description)),
        "html.parser",
    )

    for element in soup.select(
        ", ".join((*BOILERPLATE_CLASSES, "script", "style"))
    ):
        element.decompose()

    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
    ]

    return "\n".join(line for line in lines if line)
