import os
import datetime
import zipfile
import io
from playwright.sync_api import sync_playwright

LOGIN = os.environ["OSC_LOGIN"]
PASSWORD = os.environ["OSC_PASSWORD"]
EXPORT_URL = "https://openspeedcam.net/export"


def parse_downloaded_file(file_path):
    """Читает скачанный .txt или .zip (если сайт отдаёт архив) и возвращает строки базы."""
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


def run_export():
    ambush_date = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    all_lines = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, locale="ru-RU")
        page = context.new_page()

        print("1. Открываем страницу экспорта OpenSpeedcam...")
        page.goto(EXPORT_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        # Проверяем, требуется ли авторизация
        if page.locator("input[type='password']").count() == 0:
            login_btn = page.locator("text=/Войти|Вход|Login|Sign in/i").first
            if login_btn.count() > 0:
                login_btn.click()
                page.wait_for_timeout(1500)

        if page.locator("input[type='password']").count() > 0:
            print("2. Выполняем вход в аккаунт...")
            user_input = page.locator("input[type='text'], input[type='email']").first
            pass_input = page.locator("input[type='password']").first
            user_input.fill(LOGIN)
            pass_input.fill(PASSWORD)

            submit_btn = page.locator("button[type='submit'], button:has-text('Войти'), button:has-text('Login')").first
            submit_btn.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(2000)

        if "/export" not in page.url:
            page.goto(EXPORT_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

        print("3. Настраиваем параметры экспорта...")

        # Формат: Навител
        format_field = page.locator("label:has-text('Формат')").locator("..").locator("input, [role='combobox'], select").first
        if format_field.count() > 0:
            format_field.click()
            page.wait_for_timeout(500)
            navitel_opt = page.locator("text=/Навител|Navitel/i").first
            if navitel_opt.count() > 0:
                navitel_opt.click()
                page.wait_for_timeout(500)

        # Объекты с рейтингом от: 0 (не опасная)
        rating_field = page.locator("label:has-text('рейтингом')").locator("..").locator("input, [role='combobox'], select").first
        if rating_field.count() > 0:
            rating_field.click()
            page.wait_for_timeout(500)
            zero_opt = page.locator("text=/0 \\(не опасная\\)/i").first
            if zero_opt.count() > 0:
                zero_opt.click()
                page.wait_for_timeout(500)

        # Чекбокс "Выбрать всё"
        select_all = page.locator("text=/Выбрать всё/i").first
        if select_all.count() > 0:
            select_all.click()
            page.wait_for_timeout(500)

        # Дата "Мобильные засады подтвержденные после"
        date_input = page.locator("input[type='date'], input[placeholder*='202']").first
        if date_input.count() > 0:
            date_input.fill(ambush_date)

        # Экспортируем поочерёдно Россию и Казахстан
        for country in ["Россия", "Казахстан"]:
            print(f"4. Экспортируем страну: {country}...")
            country_input = page.locator("label:has-text('Страна')").locator("..").locator("input, [role='combobox'], select").first
            if country_input.count() > 0:
                country_input.click()
                page.wait_for_timeout(500)
                if country_input.evaluate("el => el.tagName.toLowerCase() === 'input'"):
                    country_input.fill(country)
                    page.wait_for_timeout(800)
                country_opt = page.locator(f"text=/{country}/i").last
                if country_opt.count() > 0:
                    country_opt.click()
                    page.wait_for_timeout(800)

            export_btn = page.locator("button:has-text('ЭКСПОРТ'), button:has-text('Экспорт')").first
            with page.expect_download(timeout=60000) as download_info:
                export_btn.click()

            download = download_info.value
            temp_path = f"/tmp/osc_{country}.dat"
            download.save_as(temp_path)
            lines = parse_downloaded_file(temp_path)
            print(f"   Получено строк для {country}: {len(lines)}")
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
