import os
import datetime
import zipfile
from playwright.sync_api import sync_playwright

LOGIN = os.environ["OSC_LOGIN"]
PASSWORD = os.environ["OSC_PASSWORD"]
BASE_URL = "https://openspeedcam.net"
EXPORT_URL = f"{BASE_URL}/export"


def parse_downloaded_file(file_path):
    """Читает скачанный .txt или .zip и возвращает строки базы."""
    if zipfile.is_zipfile(file_path):
        lines = []
        with zipfile.ZipFile(file_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith((".txt", ".csv")):
                    content = zf.read(name).decode("utf-8", errors="ignore")
                    lines.extend(content.splitlines())
        return lines
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().splitlines()


def ensure_logged_in(page):
    """Переходит напрямую на страницу входа и авторизуется."""
    for login_path in ["/login", "/auth/login", "/signin"]:
        page.goto(f"{BASE_URL}{login_path}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        if page.locator("input[type='password']").count() > 0:
            break

    # Если прямая ссылка не открыла форму, пробуем открыть бургер-меню Vuetify
    if page.locator("input[type='password']").count() == 0:
        page.goto(EXPORT_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        burger = page.locator("button.v-toolbar__side-icon, .v-app-bar__nav-icon, header button").first
        if burger.count() > 0 and burger.is_visible():
            burger.click()
            page.wait_for_timeout(1000)
        login_item = page.locator("text=/Вход|Войти|Login/i").locator("visible=true").first
        if login_item.count() > 0:
            login_item.click()
            page.wait_for_timeout(1500)

    if page.locator("input[type='password']").count() == 0:
        raise RuntimeError(f"Не удалось найти форму входа. Текущий URL: {page.url}")

    print("2. Вводим логин и пароль...")
    user_input = page.locator("input[type='text']:visible, input[type='email']:visible, input:not([type='password']):not([type='hidden']):visible").first
    pass_input = page.locator("input[type='password']:visible").first

    user_input.fill(LOGIN)
    pass_input.fill(PASSWORD)

    submit_btn = page.locator("button[type='submit']:visible, button:has-text('Войти'):visible, button:has-text('Вход'):visible, button:has-text('Login'):visible").first
    submit_btn.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(2500)


def select_vuetify_option(page, label_regex, option_regex):
    """Выбирает значение в выпадающем списке Vuetify (v-select / v-autocomplete)."""
    label = page.locator(f"label:has-text('{label_regex}')").first
    if label.count() == 0:
        print(f"   [Предупреждение] Поле '{label_regex}' не найдено.")
        return

    # Кликаем по родительскому контейнеру поля Vuetify (.v-input__slot)
    slot = label.locator("xpath=ancestor::div[contains(@class,'v-input__slot')][1]")
    if slot.count() > 0:
        slot.click()
    else:
        label.click(force=True)

    page.wait_for_timeout(800)

    # Ищем видимый пункт в открывшемся выпадающем меню Vuetify
    option = page.locator(f".v-menu__content--active >> text=/{option_regex}/i").first
    if option.count() == 0:
        option = page.locator(f"text=/{option_regex}/i").locator("visible=true").last

    if option.count() > 0:
        option.click()
        page.wait_for_timeout(800)
    else:
        print(f"   [Предупреждение] Пункт '{option_regex}' не найден в списке '{label_regex}'.")


def run_export():
    ambush_date = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    all_lines = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            locale="ru-RU",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print("1. Авторизуемся на OpenSpeedcam...")
        ensure_logged_in(page)

        print("3. Переходим на страницу экспорта...")
        page.goto(EXPORT_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        # Формат: Навител
        select_vuetify_option(page, "Формат", "Навител|Navitel")

        # Объекты с рейтингом от: 0 (не опасная)
        select_vuetify_option(page, "рейтингом", "0 \\(не опасная\\)|0")

        # Чекбокс "Выбрать всё"
        select_all = page.locator("label:has-text('Выбрать всё')").first
        if select_all.count() > 0:
            select_all.click()
            page.wait_for_timeout(500)

        # Дата "Мобильные засады подтвержденные после"
        date_input = page.locator("input[type='date'], input[value*='202']").first
        if date_input.count() > 0:
            date_input.fill(ambush_date)

        # Экспортируем поочерёдно Россию и Казахстан
        for country in ["Россия", "Казахстан"]:
            print(f"4. Выбираем страну и скачиваем: {country}...")
            select_vuetify_option(page, "Страна", country)

            export_btn = page.locator("button:has-text('ЭКСПОРТ'), button:has-text('Экспорт')").locator("visible=true").first
            with page.expect_download(timeout=60000) as download_info:
                export_btn.click()

            download = download_info.value
            temp_path = f"/tmp/osc_{country}.dat"
            download.save_as(temp_path)
            lines = parse_downloaded_file(temp_path)
            print(f"   Скачано строк для {country}: {len(lines)}")
            all_lines.extend(lines)

        browser.close()

    header = "IDX,X,Y,TYPE,SPEED,DIRTYPE,DIRECTION"
    cleaned = [header]
    for raw in all_lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.upper().startswith("IDX,"):
            continue
        cleaned.append(line)

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "speedcam_ru_kz.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned) + "\n")

    print(f"Готово! Итого сохранено {len(cleaned) - 1} объектов в {output_path}")


if __name__ == "__main__":
    run_export()
