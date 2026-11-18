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
    """Открывает модальное окно входа Vuetify и авторизуется."""
    page.goto(EXPORT_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)

    triggers = [
        "button:has-text('Вход')",
        "button:has-text('Войти')",
        "header button:has(i)",
        ".v-toolbar button",
    ]

    for selector in triggers:
        if page.locator("input[type='password']:visible").count() > 0:
            break
        loc = page.locator(selector)
        for i in range(loc.count()):
            el = loc.nth(i)
            if el.is_visible():
                try:
                    el.click(timeout=1500)
                    page.wait_for_timeout(800)
                    if page.locator("input[type='password']:visible").count() > 0:
                        break
                    menu_login = page.locator("text=/Вход|Войти|Login/i").locator("visible=true").first
                    if menu_login.count() > 0:
                        menu_login.click(timeout=1500)
                        page.wait_for_timeout(800)
                        if page.locator("input[type='password']:visible").count() > 0:
                            break
                except Exception:
                    pass

    if page.locator("input[type='password']:visible").count() == 0:
        hidden_login = page.locator("text=/Вход|Войти|Login/i").first
        if hidden_login.count() > 0:
            hidden_login.evaluate("el => el.click()")
            page.wait_for_timeout(1200)

    if page.locator("input[type='password']:visible").count() == 0:
        raise RuntimeError(f"Не удалось открыть окно входа. Текущий URL: {page.url}")

    print("2. Вводим логин и пароль...")
    dialog = page.locator(".v-dialog--active, .v-dialog:visible").first
    scope = dialog if dialog.count() > 0 else page

    user_input = scope.locator("input:not([type='password']):not([type='hidden']):not([type='checkbox']):visible").first
    pass_input = scope.locator("input[type='password']:visible").first

    user_input.fill(LOGIN)
    pass_input.fill(PASSWORD)

    submit_btn = scope.locator("button[type='submit']:visible, button:has-text('Войти'):visible, button:has-text('Вход'):visible").first
    submit_btn.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(2000)


def select_vuetify_option(page, label_regex, option_regex):
    """Выбирает значение в выпадающем списке Vuetify 1.x (.menuable__content__active)."""
    label = page.locator(f"label:has-text('{label_regex}')").first
    if label.count() == 0:
        print(f"   [Инфо] Поле '{label_regex}' не найдено.")
        return False

    slot = label.locator("xpath=ancestor::div[contains(@class,'v-input__slot')][1]")
    # Проверяем, не выбрано ли уже нужное значение
    current_val = slot.locator(".v-select__selection").first
    if current_val.count() > 0:
        txt = current_val.inner_text().strip()
        if option_regex.split("|")[0].replace("\\", "") in txt:
            print(f"   [Ок] В поле '{label_regex}' уже выбрано: {txt}")
            return True

    if slot.count() > 0:
        slot.click()
    else:
        label.click(force=True)

    page.wait_for_timeout(800)

    # Если это автокомплит с полем ввода — вводим текст для фильтрации
    active_input = slot.locator("input[type='text']:visible").first
    if active_input.count() > 0 and not active_input.is_disabled():
        try:
            active_input.fill(option_regex.split("|")[0].replace("\\", ""))
            page.wait_for_timeout(800)
        except Exception:
            pass

    # Ищем пункт строго внутри открытого меню Vuetify 1.x (.menuable__content__active)
    menu = page.locator(".menuable__content__active").first
    option = menu.locator(f".v-list__tile__title:has-text('{option_regex.split('|')[0].replace(chr(92), '')}')").first
    if option.count() == 0:
        option = menu.locator(f"text=/{option_regex}/i").first

    if option.count() > 0:
        option.click()
        page.wait_for_timeout(800)
        return True

    # Закрываем меню клавишей Escape, если пункт не найден
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print(f"   [Предупреждение] Пункт '{option_regex}' не найден в '{label_regex}'.")
    return False


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
        if "/export" not in page.url:
            page.goto(EXPORT_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

        # Формат: Навител
        select_vuetify_option(page, "Формат", "Навител|Navitel")

        # Объекты с рейтингом от: 0 (не опасная)
        select_vuetify_option(page, "рейтингом", "0 (не опасная)|0")

        # Чекбокс "Выбрать всё" (нажимаем, только если он не отмечен)
        select_all_label = page.locator("label:has-text('Выбрать всё')").first
        if select_all_label.count() > 0:
            cb_container = select_all_label.locator("xpath=ancestor::div[contains(@class,'v-input--checkbox')][1]")
            cb_input = cb_container.locator("input[type='checkbox']").first
            if cb_input.count() > 0 and not cb_input.is_checked():
                select_all_label.click()
                page.wait_for_timeout(500)

        # Дата "Мобильные засады подтвержденные после"
        date_input = page.locator("input[type='date'], input[value*='202']").first
        if date_input.count() > 0:
            try:
                date_input.fill(ambush_date)
            except Exception:
                pass

        # Выводим все доступные поля на странице экспорта для точного понимания выбора страны
        labels_list = page.evaluate("""() => Array.from(document.querySelectorAll('label')).map(l => l.innerText.trim()).filter(Boolean)""")
        print("   Доступные поля на странице:", labels_list[:15])

        # Экспортируем поочерёдно Россию и Казахстан
        for country in ["Россия", "Казахстан"]:
            print(f"4. Выбираем страну и скачиваем: {country}...")
            selected = select_vuetify_option(page, "Страна", country)
            if not selected:
                # Если выбор страны сделан через чипы/кнопки или дерево регионов
                country_el = page.locator(f"text=/{country}/i").locator("visible=true").first
                if country_el.count() > 0:
                    country_el.click()
                    page.wait_for_timeout(800)

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
