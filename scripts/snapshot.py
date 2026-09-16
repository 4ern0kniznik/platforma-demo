"""Снимает HTML настоящего приложения (не макета) для витрины GitHub Pages.

Ходит по известным адресам локального стенда через httpx с сессионной кукой,
переписывает абсолютные ссылки на файлы снимка и на статику, вставляет плашку
про то, что это снимок с вымышленными данными и формы не работают.

Стенд и данные (пороги 10/30, два поставщика, два лота, наблюдатель) заводятся отдельно —
см. `Контора/деплои/app-snapshot-0.2.0.md`, раздел «Как повторить». Коротко:
    1. поднять стенд: scripts/dev.py --port 8098 --phone +79991110001 --data-dir <tmp>
       с FILES_DIR=<tmp>/files и DEV_SHOW_CODE=true;
    2. завести пороги 10/30 и наблюдателя: seed_db.py <tmp>/pgdata (правит базу напрямую —
       экрана порогов и скрипта для роли viewer на этапе 1 нет);
    3. завести поставщиков, лоты и документы через настоящие HTTP-формы: seed_http.py
       --base http://127.0.0.1:8098 --admin-phone +79991110001 — выводит JSON с UUID
       поставщиков и расчётов;
    4. снять снимок этим скриптом, подставив UUID из шага 3.

Запуск (после шагов 1–3):
    uv run --directory /Users/yaitskii/Claude/Platforma/код python \
        /Users/yaitskii/Claude/Platforma/демо/scripts/snapshot.py \
        --base http://127.0.0.1:8098 \
        --admin-phone +79991110001 --viewer-phone +79991110002 \
        --calc1 /calculations/<uuid участвуем> --calc2 /calculations/<uuid ниже порога> \
        --supplier-full <uuid поставщика с полным комплектом документов> \
        --supplier-partial <uuid поставщика с неполным комплектом документов>

Пишет файлы в /Users/yaitskii/Claude/Platforma/демо/app/.
"""

import argparse
import re
import shutil
from pathlib import Path

import httpx

DEMO_APP_DIR = Path("/Users/yaitskii/Claude/Platforma/демо/app")
STATIC_CSS = Path("/Users/yaitskii/Claude/Platforma/код/app/static/app.css")

DEV_CODE_RE = re.compile(r"Код из лога сервера: <strong>(\d{4})</strong>")

# Абсолютная ссылка на сервере → относительный файл в снимке. Записи под конкретные
# идентификаторы поставщиков дописываются в main() — их UUID известен только на старте.
LINK_MAP = {
    'href="/static/app.css"': 'href="app.css"',
    'href="/catalog"': 'href="02-postavshchik-tovar.html"',
    'href="/lots/new"': 'href="03-lot.html"',
    'href="/logout"': 'href="01-vhod.html"',
    'action="/catalog"': 'action="#"',
    'action="/lots/new"': 'action="#"',
    'action="/lots"': 'action="#"',
    'action="/auth/code"': 'action="#"',
    'action="/auth/verify"': 'action="#"',
}

# Ссылки, которые LINK_MAP не ловит буквальной строкой, потому что несут случайный UUID:
# скачивание файла документа. В снимке файлы не открываются вовсе — формы и так не работают,
# а сами PDF на витрину не публикуются.
FILE_LINK_RE = re.compile(r'href="/files/[0-9a-fA-F-]+"')

BANNER = (
    '<div style="background:#FEF3C7;color:#78350F;padding:12px 16px;'
    'font:14px/1.4 system-ui,sans-serif;text-align:center;border-bottom:1px solid #F5D98B">'
    "Снимок приложения v0.2.0 от 16.09.2026, данные вымышленные, формы не работают."
    "</div>"
)


def login(client: httpx.Client, base: str, phone: str) -> None:
    r = client.post(f"{base}/auth/code", data={"phone": phone})
    r.raise_for_status()
    m = DEV_CODE_RE.search(r.text)
    if not m:
        raise SystemExit(f"Не нашёл dev-код для {phone}")
    code = m.group(1)
    r = client.post(f"{base}/auth/verify", data={"phone": phone, "code": list(code)})
    if r.status_code != 303:
        raise SystemExit(f"Вход не удался для {phone}: {r.status_code}")


def rewrite(html: str) -> str:
    for old, new in LINK_MAP.items():
        html = html.replace(old, new)
    html = FILE_LINK_RE.sub('href="#"', html)
    html = html.replace("<body>", "<body>\n" + BANNER, 1)
    return html


def save(name: str, html: str) -> None:
    DEMO_APP_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_APP_DIR / name
    path.write_text(rewrite(html), encoding="utf-8")
    print("сохранено:", path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8090")
    parser.add_argument("--admin-phone", required=True)
    parser.add_argument("--viewer-phone", required=True)
    parser.add_argument("--calc1", required=True, help="путь вида /calculations/<uuid> — участвуем")
    parser.add_argument("--calc2", required=True, help="путь вида /calculations/<uuid> — ниже порога")
    parser.add_argument(
        "--supplier-full", required=True, help="UUID поставщика с полным комплектом документов"
    )
    parser.add_argument(
        "--supplier-partial", required=True, help="UUID поставщика с неполным комплектом документов"
    )
    args = parser.parse_args()

    # Ссылки на карточки документов известны только сейчас — UUID передан аргументом.
    LINK_MAP[f'href="/suppliers/{args.supplier_full}/documents"'] = (
        'href="05-dokumenty-postavshchika-polnyy.html"'
    )
    LINK_MAP[f'action="/suppliers/{args.supplier_full}/documents"'] = 'action="#"'
    LINK_MAP[f'href="/suppliers/{args.supplier_partial}/documents"'] = (
        'href="06-dokumenty-postavshchika-nepolnyy.html"'
    )
    LINK_MAP[f'action="/suppliers/{args.supplier_partial}/documents"'] = 'action="#"'

    # 1. Вход — без сессии вовсе.
    anon = httpx.Client(follow_redirects=False)
    r = anon.get(args.base + "/")
    r.raise_for_status()
    save("01-vhod.html", r.text)
    anon.close()

    # 2–4, документы и первый результат — под сессией оператора (в этой сборке —
    # администратор, у него те же права на каталог, лот и документы, что у operator).
    operator = httpx.Client(follow_redirects=False)
    login(operator, args.base, args.admin_phone)

    r = operator.get(args.base + "/catalog")
    r.raise_for_status()
    save("02-postavshchik-tovar.html", r.text)

    r = operator.get(args.base + "/lots/new")
    r.raise_for_status()
    save("03-lot.html", r.text)

    r = operator.get(args.base + args.calc1)
    r.raise_for_status()
    save("04-rezultat-uchastvuem.html", r.text)

    r = operator.get(args.base + args.calc2)
    r.raise_for_status()
    save("04-rezultat-nizhe-poroga.html", r.text)

    r = operator.get(f"{args.base}/suppliers/{args.supplier_full}/documents")
    r.raise_for_status()
    save("05-dokumenty-postavshchika-polnyy.html", r.text)

    r = operator.get(f"{args.base}/suppliers/{args.supplier_partial}/documents")
    r.raise_for_status()
    save("06-dokumenty-postavshchika-nepolnyy.html", r.text)
    operator.close()

    # 5. Тот же расчёт (calc1, «участвуем») глазами наблюдателя.
    viewer = httpx.Client(follow_redirects=False)
    login(viewer, args.base, args.viewer_phone)
    r = viewer.get(args.base + args.calc1)
    r.raise_for_status()
    save("04-rezultat-viewer.html", r.text)
    viewer.close()

    shutil.copy(STATIC_CSS, DEMO_APP_DIR / "app.css")
    print("статика скопирована:", DEMO_APP_DIR / "app.css")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
