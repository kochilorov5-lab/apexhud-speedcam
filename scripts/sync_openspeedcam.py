import os
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://openspeedcam.net"
LOGIN_PAGE_URL = "https://openspeedcam.net/?_modal=login"
EXPORT_PAGE_URL = "https://openspeedcam.net/export"  # Проверь вкладку «Экспорт» на сайте, если путь отличается

OSC_LOGIN = os.environ.get("OSC_LOGIN", "").strip()
OSC_PASSWORD = os.environ.get("OSC_PASSWORD", "").strip()

OUTPUT_PATH = "data/speedcam_ru_kz.txt"


def create_authenticated_session() -> requests.Session:
    if not OSC_LOGIN or not OSC_PASSWORD:
        raise RuntimeError("Не заданы секреты OSC_LOGIN или OSC_PASSWORD в GitHub Secrets.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": BASE_URL + "/",
    })

    # 1. Загружаем страницу с модальным окном входа, чтобы получить cookies и реальный URL формы
    resp = session.get(LOGIN_PAGE_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Ищем форму авторизации (по полю password)
    password_input = soup.find("input", {"type": "password"})
    if not password_input:
        raise RuntimeError("Не удалось найти форму авторизации на странице OpenSpeedcam.")

    form = password_input.find_parent("form")
    action = form.get("action") if form and form.get("action") else LOGIN_PAGE_URL
    post_url = urljoin(BASE_URL, action)

    # Собираем все скрытые поля формы (CSRF-токены и т.д.)
    payload = {}
    if form:
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            inp_type = (inp.get("type") or "text").lower()
            if inp_type == "password":
                payload[name] = OSC_PASSWORD
            elif inp_type in ("text", "email") or "login" in name.lower() or "user" in name.lower() or "mail" in name.lower():
                payload[name] = OSC_LOGIN
            elif inp_type == "hidden":
                payload[name] = inp.get("value", "")
            elif inp_type == "checkbox" and inp.get("checked") is not None:
                payload[name] = inp.get("value", "1")

    # 2. Отправляем POST-запрос на реальный endpoint формы
    auth_resp = session.post(post_url, data=payload, timeout=30, allow_redirects=True)
    auth_resp.raise_for_status()

    # Проверяем, что авторизация прошла (на странице появилась кнопка выхода)
    if "logout" not in auth_resp.text.lower() and "выход" not in auth_resp.text.lower():
        raise RuntimeError(f"Авторизация не подтверждена (POST {post_url}). Проверь OSC_LOGIN и OSC_PASSWORD.")

    print(f"Успешный вход через {post_url}")
    return session
