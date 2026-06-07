from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Static validation for FourCastNet Colab smoke notebook")
    p.add_argument("--NOTEBOOK", required=True)
    return p.parse_args()


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def main() -> int:
    args = _parse_args()
    nb_path = Path(args.NOTEBOOK)
    errors: list[str] = []

    if not nb_path.exists():
        _fail(errors, f"Notebook not found: {nb_path}")
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(errors, f"Invalid notebook JSON: {exc}")
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    cells = nb.get("cells", [])
    if not isinstance(cells, list) or not cells:
        _fail(errors, "Notebook has no cells")

    markdown = []
    code = []
    for cell in cells:
        src = "".join(cell.get("source", []))
        if cell.get("cell_type") == "markdown":
            markdown.append(src)
        elif cell.get("cell_type") == "code":
            code.append(src)

    all_markdown = "\n".join(markdown)
    all_code = "\n".join(code)
    all_text = all_markdown + "\n" + all_code

    lowered_text = all_text.lower()
    warning_phrases = ["does not prove scientific validity", "not meteorologically trustworthy"]
    if not all(phrase in lowered_text for phrase in warning_phrases):
        _fail(errors, "Top warning about scientific validity/trustworthiness is missing")

    required_sections = [
        "scientific_validity_warning",
        "tensor_schema_preflight",
        "normalization_preflight",
        "checkpoint_model_load_preflight",
        "direct_tensor_inference_attempt",
        "optional_hdf5_io_preflight",
    ]
    for section in required_sections:
        if section not in all_text:
            _fail(errors, f"Missing required section marker: {section}")

    if "colab_validation_report.json" not in all_text:
        _fail(errors, "Notebook does not mention colab_validation_report.json")

    if "INPUT_TENSOR" not in all_code and "input_tensor" not in all_code.lower():
        _fail(errors, "Notebook is missing explicit tensor input handling logic")

    if "tensor_schema_ok" not in all_code or "normalization_ok" not in all_code:
        _fail(errors, "Notebook is missing required tensor preflight report fields")

    if "inference_attempted" not in all_code or "inference_success" not in all_code:
        _fail(errors, "Notebook is missing model/inference attempt status flags")

    for idx, md in enumerate(markdown):
        if "````" in md:
            _fail(errors, f"Markdown cell {idx} contains nested backticks")
        if md.count("```") % 2 != 0:
            _fail(errors, f"Markdown cell {idx} has unbalanced triple backticks")

    out = {"ok": len(errors) == 0, "errors": errors, "notebook": str(nb_path)}
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
