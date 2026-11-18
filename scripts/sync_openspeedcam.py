import os
import re
import datetime
import requests
from bs4 import BeautifulSoup

LOGIN = os.environ["OSC_LOGIN"]
PASSWORD = os.environ["OSC_PASSWORD"]

BASE_URL = "https://openspeedcam.net"
LOGIN_URL = f"{BASE_URL}/login"
EXPORT_URL = f"{BASE_URL}/export"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
})


def login():
    resp = session.get(LOGIN_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    payload = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name:
            payload[name] = inp.get("value", "")

    # Подставляем логин и пароль в поля формы авторизации
    for key in list(payload.keys()):
        low = key.lower()
        if "mail" in low or "login" in low or "user" in low:
            payload[key] = LOGIN
        elif "pass" in low:
            payload[key] = PASSWORD

    if not any("pass" in k.lower() for k in payload):
        payload["email"] = LOGIN
        payload["password"] = PASSWORD

    auth_resp = session.post(LOGIN_URL, data=payload, timeout=30)
    auth_resp.raise_for_status()


def fetch_country_export(country_keywords):
    resp = session.get(EXPORT_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    form = soup.find("form")
    if not form:
        raise RuntimeError("Форма экспорта на странице /export не найдена (проверьте авторизацию).")

    data = []
    ambush_after = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    # 1. Собираем скрытые поля (CSRF и служебные токены)
    for inp in form.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        if name:
            data.append((name, inp.get("value", "")))

    # 2. Выбираем формат "Навител" и рейтинг "0 (не опасная)"
    for select in form.find_all("select"):
        name = select.get("name")
        if not name:
            continue
        options = select.find_all("option")
        selected_val = None

        for opt in options:
            text = opt.get_text(strip=True).lower()
            val = opt.get("value", "")
            if "навител" in text or "navitel" in text:
                selected_val = val
                break
            if text.startswith("0") and ("не опасн" in text or val == "0"):
                selected_val = val
                break
            if any(kw in text for kw in country_keywords):
                selected_val = val
                break

        if selected_val is None and options:
            selected_val = options[0].get("value", "")
        if selected_val is not None:
            data.append((name, selected_val))

    # 3. Отмечаем чекбоксы: все типы объектов + мобильные засады, исключая КСС и историю экспортов
    for cb in form.find_all("input", {"type": "checkbox"}):
        name = cb.get("name")
        val = cb.get("value", "1")
        if not name:
            continue
        low_name = name.lower()
        # Исключаем промежуточные точки КСС и добавление в историю экспортов
        if "history" in low_name or "inter" in low_name or "kss" in low_name or "average_point" in low_name:
            continue
        # Фильтр по странам, если страны представлены чекбоксами
        if "country" in low_name:
            label = form.find("label", {"for": cb.get("id")})
            label_text = label.get_text(strip=True).lower() if label else ""
            if any(kw in label_text for kw in country_keywords):
                data.append((name, val))
            continue
        data.append((name, val))

    # 4. Дата для "Мобильные засады подтвержденные после" (1 год назад)
    for inp in form.find_all("input"):
        inp_type = (inp.get("type") or "").lower()
        name = inp.get("name")
        if name and (inp_type == "date" or "date" in name.lower() or "ambush" in name.lower()):
            if inp_type not in ("checkbox", "radio", "hidden", "submit"):
                data.append((name, ambush_after))

    action = form.get("action") or EXPORT_URL
    target_url = action if action.startswith("http") else f"{BASE_URL}{action}"

    export_resp = session.post(target_url, data=data, timeout=60)
    export_resp.raise_for_status()
    return export_resp.text


def main():
    login()
    ru_text = fetch_country_export(["россия", "russia"])
    kz_text = fetch_country_export(["казахстан", "kazakhstan"])

    header = "IDX,X,Y,TYPE,SPEED,DIRTYPE,DIRECTION"
    lines = [header]

    for block in (ru_text, kz_text):
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.upper().startswith("IDX,"):
                continue
            lines.append(line)

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "speedcam_ru_kz.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Экспорт завершён: сохранено {len(lines) - 1} объектов в {output_path}")


if __name__ == "__main__":
    main()
