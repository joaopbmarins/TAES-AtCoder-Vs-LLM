"""Operações de arquivo seguras para etapas reexecutáveis."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable


def atomic_replace(path: str | Path, writer: Callable[[Path], None]) -> None:
    """Escreve em arquivo temporário no mesmo diretório e substitui o destino."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        writer(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
