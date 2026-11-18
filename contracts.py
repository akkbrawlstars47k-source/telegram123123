import json
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

from company_card import extract_fields
from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str
    example: str
    aliases: tuple[str, ...] = ()

    def accepts(self, value: str) -> bool:
        if not value or len(value) > 500 or not re.fullmatch(
            r"[\x09\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]+", value
        ):
            return False
        if self.type == "inn":
            return re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", value) is not None
        lengths = {"ogrn": (13, 15), "kpp": (9,), "account": (20,), "bic": (9,)}
        if self.type in lengths:
            return value.isascii() and value.isdigit() and len(value) in lengths[self.type]
        if self.type == "date":
            match = re.fullmatch(r"([0-9]{2})\.([0-9]{2})\.([0-9]{4})", value)
            if not match:
                return False
            day, month, year = map(int, match.groups())
            try:
                date(year, month, day)
            except ValueError:
                return False
        return True


@dataclass(frozen=True)
class Contract:
    id: str
    group: str
    title: str
    file: Path
    fields: tuple[Field, ...]


def load_catalog() -> tuple[dict[str, Contract], int]:
    config = json.loads((ROOT / "contracts.json").read_text(encoding="utf-8"))
    catalog = {}
    threshold = config["group_menu_threshold"]
    if type(threshold) is not int or threshold < 1:
        raise ValueError("group_menu_threshold должен быть положительным целым числом.")
    for item in config["templates"]:
        contract = Contract(
            id=item["id"], group=item["group"], title=item["title"],
            file=ROOT / item["file"], fields=tuple(Field(**field) for field in item["fields"]),
        )
        if (not re.fullmatch(r"[a-z0-9_-]{1,40}", contract.id)
                or contract.id in catalog
                or contract.group not in {"РАО", "ВОИС"} or not contract.title.strip()):
            raise ValueError("Проверьте id, группу и название шаблона в contracts.json.")
        keys = {field.key for field in contract.fields}
        labels = {field.label.strip().casefold() for field in contract.fields}
        if (not keys or len(keys) != len(contract.fields) or len(labels) != len(contract.fields)
                or any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", field.key)
                       or not field.label.strip() or ":" in field.label
                       or len(field.label.splitlines()) != 1 or len(field.example.splitlines()) != 1
                       or field.type not in {"text", "date", "inn", "ogrn", "kpp", "account", "bic"} or not field.accepts(field.example)
                       for field in contract.fields)):
            raise ValueError(f"Проверьте поля шаблона {contract.id}.")
        if not contract.file.is_file() or contract.file.suffix.lower() != ".docx":
            raise ValueError(f"Файл DOCX шаблона {contract.id} недоступен.")
        variables = DocxTemplate(contract.file).get_undeclared_template_variables()
        if variables != keys:
            raise ValueError(
                f"Шаблон {contract.id}: отсутствуют {sorted(keys - variables)}, "
                f"не описаны {sorted(variables - keys)}."
            )
        catalog[contract.id] = contract
    if not catalog:
        raise ValueError("В contracts.json нет шаблонов.")
    return catalog, threshold


def merge_fields(contract: Contract, accepted: dict[str, str], message: str) -> dict[str, str]:
    pending = [field for field in contract.fields if field.key not in accepted]
    parsed = extract_fields(contract.fields, message)
    # A single requested field can still be answered with its value alone.
    if len(pending) == 1 and len(message.strip().splitlines()) == 1 and not parsed:
        parsed[pending[0].key] = [message.strip()]

    accepted = accepted.copy()
    for field in pending:
        values = parsed.get(field.key, [])
        if len(values) == 1 and field.accepts(values[0]):
            accepted[field.key] = values[0]
    return accepted


def render(contract: Contract, values: dict[str, str]) -> bytes:
    for field in contract.fields:
        if not field.accepts(values.get(field.key, "")):
            raise ValueError(f"Отсутствует или имеет неверный формат поле {field.key}.")
    document = DocxTemplate(contract.file)
    document.render(values, jinja_env=Environment(undefined=StrictUndefined), autoescape=True)
    with BytesIO() as stream:
        document.save(stream)
        return stream.getvalue()
