import argparse
import sys


def resolve_args(required: list[str], optional: list[str] | None = None) -> dict[str, str]:
    """
    Resuelve los argumentos para un trabajo de Glue, soportando parámetros obligatorios y opcionales.

    Debido a que 'getResolvedOptions' de Glue trata todas las claves como obligatorias,
    esta función solo le pasa los argumentos estrictamente necesarios. Los opcionales
    se manejan por separado mediante 'parse_known_args' para ignorar de forma segura
    los argumentos internos inyectados por Glue (ej. --JOB_ID).

    Parameters
    ----------
    required : list[str]
        Lista de nombres de argumentos obligatorios.
    optional : list[str] | None, opcional
        Lista de nombres de argumentos opcionales, por defecto None.

    Returns
    -------
    dict[str, str]
        Diccionario con todos los argumentos resueltos y sus valores.
    """
    optional = optional or []

    try:
        from awsglue.utils import getResolvedOptions  # type: ignore

        # getResolvedOptions marks every key it receives as REQUIRED.
        # Only pass the truly required subset; optional args are handled below.
        result: dict[str, str] = {}
        if required:
            values = getResolvedOptions(sys.argv, required)
            result = {k: values[k] for k in required}

        # Parse optional args with parse_known_args so Glue's injected internal
        # args (--JOB_ID, --enable-metrics, etc.) are silently ignored.
        if optional:
            opt_parser = argparse.ArgumentParser()
            for name in optional:
                opt_parser.add_argument(f"--{name}", required=False, default="")
            parsed_opt, _ = opt_parser.parse_known_args(sys.argv[1:])
            result.update(vars(parsed_opt))

        return result

    except Exception:
        # Fallback for local / non-Glue environments.
        # Use parse_known_args to tolerate any extra flags on the command line.
        parser = argparse.ArgumentParser()
        for name in required:
            parser.add_argument(f"--{name}", required=True)
        for name in optional:
            parser.add_argument(f"--{name}", required=False, default="")
        args, _ = parser.parse_known_args()
        return vars(args)
