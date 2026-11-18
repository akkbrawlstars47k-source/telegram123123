"""Extract labelled details without assuming a fixed line order."""
import re
from collections import defaultdict

# Generic company labels apply only to the contracting user's fields.
ALIASES = {
    "organization": ["наименование", "название организации", "полное наименование", "полное наименование организации", "полное наименование компании", "организация", "компания"],
    "inn": ["ИНН"],
    "ogrn": ["ОГРН", "ОГРНИП"],
    "kpp": ["КПП"],
    "user_legal_address": ["юридический адрес", "юр. адрес", "юрадрес", "адрес местонахождения", "адрес регистрации"],
    "user_actual_address": ["фактический адрес", "факт. адрес", "адрес фактического нахождения"],
    "user_postal_address": ["почтовый адрес", "адрес для корреспонденции"],
    "user_account": ["расчетный счет", "р/с", "р.с.", "расч. счет", "номер расчетного счета"],
    "user_correspondent_account": ["корреспондентский счет", "корр. счет", "к/с", "к.с."],
    "user_bic": ["БИК", "БИК банка"],
    "user_bank": ["банк", "банк получателя", "наименование банка"],
    "user_phone": ["телефон", "тел.", "телефон/факс"],
    "user_email": ["email", "e-mail", "электронная почта", "эл. почта"],
}
NUMERIC_KEYS = {"inn", "ogrn", "kpp", "user_account", "user_correspondent_account", "user_bic"}


def normalized(text):
    return text.casefold().replace("ё", "е").replace("\u00a0", " ")


def label_pattern(label):
    return re.escape(normalized(label)).replace(r"\ ", r"[ \t]+")


def extract_fields(fields, message):
    labels = {}
    # Include unused address labels as boundaries so factual and postal addresses stay distinct.
    for key, aliases in ALIASES.items():
        for alias in aliases:
            labels[normalized(alias)] = key
    for field in fields:
        for label in (field.key, *field.aliases, field.label):
            labels[normalized(label)] = field.key
    # Unknown headings terminate a multiline value rather than becoming part of an address.
    heading = re.compile(r"(?m)^([^\n:=\t]{1,100})\s*[:=]")
    for match in heading.finditer(message):
        label = normalized(match[1].strip())
        labels.setdefault(label, None)

    alternatives = "|".join(label_pattern(label) for label in sorted(labels, key=len, reverse=True))
    matcher = re.compile(
        r"(?<![\w])(?P<label>" + alternatives + r")"
        r"(?:[ \t]*[:=\t][ \t]*|[ ]+(?=\S))",
        re.I,
    )
    source = normalized(message)
    matches = list(matcher.finditer(source))
    result = defaultdict(list)
    for index, match in enumerate(matches):
        key = labels[normalized(match["label"])]
        if key is None:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(message)
        value = message[match.end():end].strip(" \t\r\n;,|")
        value = re.sub(r"\s*\n\s*", " ", value)
        if key in NUMERIC_KEYS:
            value = re.sub(r"[ \t\u00a0]", "", value)
        if value and value not in result[key]:
            result[key].append(value)

    # Widely used compact form "ИНН/КПП 1234567890/123456789".
    combined = re.compile(r"ИНН\s*[/\\]\s*КПП\s*[:=]?\s*([0-9]{10}|[0-9]{12})\s*[/\\]\s*([0-9]{9})(?![0-9])", re.I)
    for match in combined.finditer(message):
        for key, value in zip(("inn", "kpp"), match.groups()):
            if value not in result[key]:
                result[key].append(value)
    if not result.get("organization"):
        for line in message.splitlines():
            if re.fullmatch(r'\s*(?:ООО|ПАО|АО|ЗАО|ОАО|ИП)\s+[^:=]{2,180}', line, re.I):
                name = line.strip()
                if name not in result["organization"]:
                    result["organization"].append(name)
    return result
