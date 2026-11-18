import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document

from contracts import load_catalog, render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("template_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    catalog, _ = load_catalog()
    if args.template_id not in catalog:
        parser.error("Неизвестный id шаблона.")
    if args.output.suffix.lower() != ".docx":
        parser.error("Выходной файл должен иметь расширение .docx.")
    contract = catalog[args.template_id]
    values = {field.key: field.example for field in contract.fields}
    content = render(contract, values)
    with ZipFile(BytesIO(content)) as package:
        if package.testzip() is not None:
            raise ValueError("Повреждённый пакет DOCX.")
    Document(BytesIO(content))
    with args.output.open("xb") as file:
        file.write(content)
    print(f"Договор сохранён: {args.output}")


if __name__ == "__main__":
    main()
