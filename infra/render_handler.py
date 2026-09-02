"""FASE 6.8 - Handler RENDER_CONTENT.
Renderiza a arte (HTML -> PNG via Playwright). Texto na tela, anti-UGC."""
import os
import html as html_lib
import logging

from mongo_connection import get_client
from content_store import ContentStore

logger = logging.getLogger("render_handler")
OUT_DIR = os.path.join(os.path.dirname(__file__), "render_output")

TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1350px; font-family:'Helvetica Neue',Arial,sans-serif;
  background:linear-gradient(160deg,#0b0b0f 0%,#16161f 60%,#1f1a2a 100%);
  color:#fff; display:flex; flex-direction:column; justify-content:space-between;
  padding:90px 80px; }}
.brand {{ font-size:26px; letter-spacing:6px; text-transform:uppercase; color:#8f8fa8; }}
.style-tag {{ font-size:22px; letter-spacing:3px; color:#5e5e78; margin-top:10px; }}
.headline {{ font-size:62px; font-weight:800; line-height:1.15; margin-top:40px; }}
.body {{ font-size:38px; line-height:1.5; color:#e8e8f0; white-space:pre-line; margin-top:36px; }}
.cta {{ align-self:flex-start; background:#fff; color:#0b0b0f; font-size:30px;
  font-weight:700; padding:22px 44px; border-radius:60px; letter-spacing:1px; }}
</style></head><body>
<div><div class="brand">{brand}</div><div class="style-tag">{style}</div></div>
<div><div class="headline">{headline}</div><div class="body">{body}</div></div>
<div class="cta">{cta}</div>
</body></html>"""


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")

    decision = ((content.get("steps") or {}).get("DECISION") or {}).get("data") or {}
    if decision.get("decisao") != "APROVAR":
        store.save_step(content_id, "RENDER",
                        {"status": "skipped_by_decision", "decisao": decision.get("decisao")})
        return {"content_id": content_id, "rendered": False}

    copy_data = ((content.get("steps") or {}).get("COPY") or {}).get("data") or {}
    image_data = ((content.get("steps") or {}).get("IMAGE") or {}).get("data") or {}

    h = html_lib.escape
    html_out = TEMPLATE.format(
        brand=h((content.get("positioning_ref") or "AUTOMACAO SUPERIOR")[:40]),
        style=h((image_data.get("style") or "")[:40]),
        headline=h((copy_data.get("headline") or copy_data.get("body", "")[:60])[:140]),
        body=h((copy_data.get("body") or "")[:700]),
        cta=h(copy_data.get("cta") or "link na bio"),
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    html_path = os.path.join(OUT_DIR, f"{content_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    png_path = os.path.join(OUT_DIR, f"{content_id}.png")
    render_mode = "html_only"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.goto("file://" + html_path)
            page.screenshot(path=png_path)
            browser.close()
        render_mode = "png"
    except Exception as e:
        logger.warning("playwright_indisponivel err=%s", e)
        png_path = None

    render_data = {"html_path": html_path, "png_path": png_path,
                   "render_mode": render_mode, "style": image_data.get("style")}
    store.save_step(content_id, "RENDER", render_data)
    logger.info("render_done content_id=%s mode=%s", content_id, render_mode)
    return {"content_id": content_id, "render_mode": render_mode}
