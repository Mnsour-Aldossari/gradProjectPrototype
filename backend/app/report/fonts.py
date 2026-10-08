"""A font with Arabic letters for the PDF report, found on the server's machine.

No font is shipped with the project: Windows has Arial (with Arabic), a Linux server or the Docker image gets
DejaVu Sans from its fonts-dejavu-core package. REPORT_FONT (and REPORT_FONT_BOLD) name another .ttf file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

# Alif, ba, lam, ya, the em dash and the middle dot the report uses.
NEEDED = (0x0627, 0x0628, 0x0644, 0x064A, 0x2014, 0x00B7)

_WINDOWS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
# (regular, bold) in order of preference.
CANDIDATES: tuple[tuple[Path, Path], ...] = (
    (_WINDOWS / "arial.ttf", _WINDOWS / "arialbd.ttf"),
    (_WINDOWS / "segoeui.ttf", _WINDOWS / "segoeuib.ttf"),
    (_WINDOWS / "tahoma.ttf", _WINDOWS / "tahomabd.ttf"),
    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
)


@dataclass(frozen=True)
class ReportFont:
    regular: Path
    bold: Path  # the regular file when there is no bold one


class NoArabicFont(RuntimeError):
    pass


def has_arabic(path: Path) -> bool:
    try:
        with TTFont(path, fontNumber=0, lazy=True) as font:
            cmap = font.getBestCmap() or {}
    except Exception:
        return False
    return all(c in cmap for c in NEEDED)


@lru_cache(maxsize=8)
def find_font(regular: str = "", bold: str = "") -> ReportFont:
    """regular, bold: REPORT_FONT and REPORT_FONT_BOLD, if set; otherwise the first system font that has Arabic."""
    candidates = ((Path(regular), Path(bold or regular)),) if regular else CANDIDATES
    for reg, bld in candidates:
        if reg.is_file() and has_arabic(reg):
            return ReportFont(reg, bld if bld.is_file() and has_arabic(bld) else reg)
    where = f"REPORT_FONT ({regular})" if regular else "the usual places (Arial on Windows, DejaVu Sans on Linux)"
    raise NoArabicFont(
        f"No font with Arabic letters was found in {where}; set REPORT_FONT to a .ttf file that has them"
    )
