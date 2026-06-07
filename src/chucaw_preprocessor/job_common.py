from datetime import datetime
from pathlib import Path


def normalize_run(run: str) -> str:
    """
    Normaliza el formato de la hora de ejecución (run), asegurando el sufijo 'z'.

    Parameters
    ----------
    run : str
        Hora de ejecución (ej. "06", "18z").

    Returns
    -------
    str
        Hora normalizada (ej. "06z").
    """
    run = run.strip().lower()
    if run.endswith("z"):
        return run
    return f"{run}z"


def parse_date(date_value: str) -> datetime:
    """
    Analiza una cadena de fecha en formato YYYYMMDD.

    Parameters
    ----------
    date_value : str
        Fecha en formato string.

    Returns
    -------
    datetime
        Objeto datetime correspondiente.
    """
    return datetime.strptime(date_value, "%Y%m%d")


def partition_prefix(base_prefix: str, date_str: str, run: str) -> str:
    """
    Construye el prefijo de partición de S3 basado en fecha y hora.

    Formatea la ruta siguiendo la convención year=YYYY/month=MM/day=DD/hour=HHz.

    Parameters
    ----------
    base_prefix : str
        Prefijo base en el bucket.
    date_str : str
        Fecha en formato YYYYMMDD.
    run : str
        Hora de ejecución.

    Returns
    -------
    str
        Ruta de prefijo de partición completa y normalizada.
    """
    parsed = parse_date(date_str)
    base = Path(base_prefix.strip("/"))
    return str(
        base
        / f"year={parsed.year:04d}"
        / f"month={parsed.month:02d}"
        / f"day={parsed.day:02d}"
        / f"hour={normalize_run(run)}"
    ).replace("\\", "/")
