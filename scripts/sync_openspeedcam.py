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


def dump_page_diagnostics(page, reason=""):
    """Печатает диагностику страницы при проблемах с поиском элементов или ожиданием."""
    try:
        print(f"   [Диагностика] {reason} | URL: {page.url} | TITLE: {page.title()}")
        body_text = (page.inner_text("body") or "").strip().replace("\r", "")
        print("   [Диагностика] TEXT (первые 1200 символов):")
        print(body_text[:1200])
        items = page.evaluate("""() => {
            const out = [];
            for (const lbl of document.querySelectorAll('label')) {
                const txt = (lbl.innerText || '').trim().replace(/\\s+/g, ' ');
                if (txt) out.push('LABEL: ' + txt);
            }
            for (const inp of document.querySelectorAll('input[type="checkbox"]')) {
                out.push('CB: id=' + (inp.id || '') + ' name=' + (inp.name || '') + ' checked=' + inp.checked);
            }
            return out.slice(0, 60);
        }""")
        if items:
            print("   [Диагностика] Элементы на странице:", " | ".join(items[:25]))
    except Exception as e:
        print(f"   [Диагностика] Ошибка при чтении состояния страницы: {e}")


def check_vuetify_checkbox_dom(page, keywords):
    """Отмечает чекбокс Vuetify по списку ключевых слов (регистронезависимо)."""
    kw_list = keywords if isinstance(keywords, (list, tuple)) else [keywords]
    result = page.evaluate("""(kwList) => {
        const lowerKw = kwList.map(k => (k || '').toLowerCase()).filter(Boolean);
        const matches = (txt) => {
            const low = (txt || '').toLowerCase();
            return lowerKw.some(k => low.includes(k));
        };

        const labels = Array.from(document.querySelectorAll('label'));
        let label = labels.find(l => matches(l.innerText || ''));

        if (!label) {
            const inputs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
            for (const inp of inputs) {
                const container = inp.closest('.v-input--checkbox, .v-checkbox, .v-selection-control') || inp.parentElement;
                const cText = container ? (container.innerText || '') : '';
                const attrs = [inp.id, inp.name, inp.value, inp.getAttribute('aria-label')].join(' ');
                if (matches(cText) || matches(attrs)) {
                    label = container ? container.querySelector('label') : null;
                    if (!inp.checked) {
                        inp.click();
                    }
                    if (!inp.checked && label) {
                        label.click();
                    }
                    return {
                        found: true,
                        checked: inp.checked,
                        text: (label ? label.innerText : cText || attrs).trim()
                    };
                }
            }
            return { found: false };
        }

        const container = label.closest('.v-input--checkbox, .v-checkbox, .v-selection-control') || label.parentElement;
        const input = container ? container.querySelector('input[type="checkbox"]') : null;

        if (input) {
            if (!input.checked) {
                input.click();
            }
            if (!input.checked) {
                label.click();
            }
            return { found: true, checked: input.checked, text: (label.innerText || '').trim() };
        }
        label.click();
        return { found: true, checked: true, text: (label.innerText || '').trim() };
    }""", kw_list)

    if not result.get("found"):
        print(f"   [Предупреждение] Чекбокс по ключам {kw_list} не найден в DOM.")
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

        print(f"   Текущий URL: {page.url} | Заголовок: {page.title()}")

        # 1. Отмечаем страны: Россия и Казахстан
        print("4. Выбираем страны: Россия и Казахстан...")
        rus_ok = check_vuetify_checkbox_dom(page, ["Россия (RUS)", "Россия", "Russia", "RUS"])
        kaz_ok = check_vuetify_checkbox_dom(page, ["Казахстан (KAZ)", "Казахстан", "Kazakhstan", "KAZ"])

        # 2. Проверяем "Выбрать всё"
        all_ok = check_vuetify_checkbox_dom(page, ["Выбрать всё", "Выбрать все", "Select all"])

        if not (rus_ok or kaz_ok or all_ok):
            dump_page_diagnostics(page, "Ни один нужный чекбокс не найден")

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
        try:
            page.wait_for_function("""() => {
                const btn = Array.from(document.querySelectorAll('button')).find(b => /ЭКСПОРТ|EXPORT/i.test(b.innerText || ''));
                return btn && !btn.disabled;
            }""", timeout=60000)
        except Exception as e:
            dump_page_diagnostics(page, f"Таймаут ожидания активной кнопки ЭКСПОРТ: {e}")
            raise

        export_btn = page.locator("button:has-text('ЭКСПОРТ'), button:has-text('Экспорт'), button:has-text('EXPORT')").locator("visible=true").first
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
