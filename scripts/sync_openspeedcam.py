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


def check_vuetify_checkbox_dom(page, label_text):
    """Отмечает чекбокс Vuetify напрямую через DOM-событие, даже если аккордеон свёрнут."""
    result = page.evaluate("""(targetText) => {
        const labels = Array.from(document.querySelectorAll('label'));
        const label = labels.find(l => (l.innerText || '').includes(targetText));
        if (!label) return { found: false };

        const container = label.closest('.v-input--checkbox') || label.parentElement;
        const input = container ? container.querySelector('input[type="checkbox"]') : null;

        if (input) {
            if (!input.checked) {
                input.click();
            }
            return { found: true, checked: input.checked, text: label.innerText.trim() };
        }
        label.click();
        return { found: true, checked: true, text: label.innerText.trim() };
    }""", label_text)

    if not result.get("found"):
        print(f"   [Предупреждение] Чекбокс '{label_text}' не найден в DOM.")
        return False

    page.wait_for_timeout(400)
    print(f"   [Ок] Чекбокс '{result.get('text')}': checked={result.get('checked')}")
    return True


def run_export():
    ambush_date = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

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

        # 1. Отмечаем страны: Россия (RUS) и Казахстан (KAZ) напрямую в DOM
        print("4. Выбираем страны: Россия и Казахстан...")
        check_vuetify_checkbox_dom(page, "Россия (RUS)")
        check_vuetify_checkbox_dom(page, "Казахстан (KAZ)")

        # 2. Проверяем, что "Выбрать всё" отмечено
        check_vuetify_checkbox_dom(page, "Выбрать всё")

        # 3. Устанавливаем дату "Мобильные засады подтвержденные после" (1 год назад)
        date_input = page.locator("input[type='date'], input[value*='202']").first
        if date_input.count() > 0:
            try:
                date_input.fill(ambush_date)
                print(f"   [Ок] Установлена дата засад: {ambush_date}")
            except Exception:
                pass

        # 4. Ждём, пока кнопка ЭКСПОРТ разблокируется, и скачиваем файл
        print("5. Нажимаем ЭКСПОРТ и ждём файл...")
        page.wait_for_function("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => /ЭКСПОРТ/i.test(b.innerText || ''));
            return btn && !btn.disabled;
        }""", timeout=15000)

        export_btn = page.locator("button:has-text('ЭКСПОРТ'), button:has-text('Экспорт')").locator("visible=true").first
        with page.expect_download(timeout=90000) as download_info:
            export_btn.click()

        download = download_info.value
        temp_path = "/tmp/osc_ru_kz.dat"
        download.save_as(temp_path)
        all_lines = parse_downloaded_file(temp_path)
        print(f"   Скачано всего строк из файла ({download.suggested_filename}): {len(all_lines)}")

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
