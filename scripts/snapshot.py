"""Снимает HTML настоящего приложения (не макета) для витрины GitHub Pages.

Ходит по известным адресам локального стенда через httpx с сессионной кукой,
переписывает абсолютные ссылки на файлы снимка и на статику, вставляет плашку
про то, что это снимок с вымышленными данными и формы не работают.

Запуск (после того как локальный стенд поднят и данные заведены — см. отчёт devops):
    uv run --directory /Users/yaitskii/Claude/Platforma/код python \
        /Users/yaitskii/Claude/Platforma/демо/scripts/snapshot.py \
        --base http://127.0.0.1:8090 \
        --admin-phone +79991110001 --viewer-phone +79991110002 \
        --calc1 /calculations/<uuid участвуем> --calc2 /calculations/<uuid ниже порога>

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

# Абсолютная ссылка на сервере → относительный файл в снимке.
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

BANNER = (
    '<div style="background:#FEF3C7;color:#78350F;padding:12px 16px;'
    'font:14px/1.4 system-ui,sans-serif;text-align:center;border-bottom:1px solid #F5D98B">'
    "Снимок приложения v0.1.0 от 15.09.2026, данные вымышленные, формы не работают."
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
    args = parser.parse_args()

    # 1. Вход — без сессии вовсе.
    anon = httpx.Client(follow_redirects=False)
    r = anon.get(args.base + "/")
    r.raise_for_status()
    save("01-vhod.html", r.text)
    anon.close()

    # 2–4 и первый результат — под сессией оператора (в этой сборке — администратор,
    # у него те же права на каталог и лот, что у operator).
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
