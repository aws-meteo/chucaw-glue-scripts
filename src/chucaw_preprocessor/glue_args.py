import argparse
import sys


def resolve_args(required: list[str], optional: list[str] | None = None) -> dict[str, str]:
    optional = optional or []
    expected = list(dict.fromkeys(required + optional))

    try:
        from awsglue.utils import getResolvedOptions  # type: ignore

        values = getResolvedOptions(sys.argv, expected)
        return {k: values.get(k, "") for k in expected}
    except Exception:
        parser = argparse.ArgumentParser()
        for name in required:
            parser.add_argument(f"--{name}", required=True)
        for name in optional:
            parser.add_argument(f"--{name}", required=False, default="")
        args = parser.parse_args()
        return vars(args)
