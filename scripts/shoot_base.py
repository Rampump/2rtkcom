# -*- coding: utf-8 -*-
"""
从真机 192.168.1.71:5757 抓取 2RTK Server 界面截图（英文界面）。

设计要点：只截「卡片 / 区块」这类扁平元素，不截整页长图。
整页长图宽高比常在 0.6 左右，放进文章栏后会被压成看不清的细长条。

用法::

    python scripts/shoot_base.py              # 全部重抓
    python scripts/shoot_base.py config       # 只抓某一组
    python scripts/shoot_base.py --list       # 看有哪些组
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

HOST = "http://192.168.1.71:5757"
USER = "admin"
PASS = "admin"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "images" / "base"
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1400, "height": 1000}
SCALE = 2


def login(page):
    page.goto(HOST + "/login", wait_until="networkidle")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASS)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.setItem('2rtk_lang','en')")
    page.goto(HOST + "/", wait_until="networkidle")
    page.wait_for_timeout(1500)


def goto(page, path, ms=2500):
    page.goto(HOST + path, wait_until="networkidle")
    page.wait_for_timeout(ms)


def snap(page, name, selector):
    el = page.locator(selector).first
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    box = el.bounding_box()
    path = OUT / (name + ".png")
    el.screenshot(path=str(path))
    ratio = box["width"] / box["height"] if box["height"] else 0
    flag = "  <-- 偏竖长，考虑拆分" if ratio < 1.1 else ""
    print(f"  {name}.png  {int(box['width'])}x{int(box['height'])}  ({ratio:.2f}){flag}")


def snap_card(page, name, idx):
    """截取第 idx 个 section.card。"""
    snap(page, name, f"section.card >> nth={idx}")


# ---------------------------------------------------------------- 登录
def shoot_login(page):
    print("[login]")
    # /logout 只接受 POST，这里直接清空会话 cookie
    page.context.clear_cookies()
    page.goto(HOST + "/login", wait_until="networkidle")
    page.wait_for_timeout(1500)
    snap(page, "web-01-login", "body")
    login(page)


# ---------------------------------------------------------------- 状态页
def shoot_status(page):
    print("[status]")
    goto(page, "/", 5000)
    # 顶部整片：运行状态 + 卫星 + 基站信息（三卡一行）
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "web-03-status-overview.png"),
                    clip={"x": 0, "y": 0, "width": 1400, "height": 820})
    print("  web-03-status-overview.png  1400x820")

    snap_card(page, "web-02-run-status", 0)
    snap_card(page, "web-04-satellites", 1)
    snap_card(page, "web-05-caster-cards", 3)
    snap_card(page, "web-06-log", 6)
    snap_card(page, "web-07-map", 7)


# ---------------------------------------------------------------- 配置页
def clip_of(page, js_box, name):
    """按 JS 计算出的矩形截屏（跨元素组合时用）。"""
    box = page.evaluate(js_box)
    page.screenshot(path=str(OUT / (name + ".png")),
                    full_page=True,
                    clip={"x": box["x"], "y": box["y"],
                          "width": box["w"], "height": box["h"]})
    print(f"  {name}.png  {int(box['w'])}x{int(box['h'])}  ({box['w']/box['h']:.2f})")


def shoot_config(page):
    print("[config]")
    goto(page, "/config", 3000)
    page.select_option("#mode", "serial")
    page.wait_for_timeout(1500)

    # ① 模式 + 串口 + 波特率（Mode / Serial Port / Baud）
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[0].getBoundingClientRect();   // Mode
      const b=f.children[1].getBoundingClientRect();   // Serial Port
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-05-config-serial")

    # ② 扫描串口之后（真实结果：Found 1 serial port）
    page.click("#scan-serial-ports")
    page.wait_for_timeout(5000)
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[0].getBoundingClientRect();
      const b=f.children[1].getBoundingClientRect();
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-06-scan-ports")

    # ③ 填入串口与波特率
    page.fill("#serial_port", "/dev/ttyUSB0")
    page.fill("#baud_rate", "115200")
    page.wait_for_timeout(700)
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[0].getBoundingClientRect();
      const b=f.children[1].getBoundingClientRect();
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-07-serial-filled")

    # ④ 出口①：上游 Caster
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[9].getBoundingClientRect();    // ① switch-row
      const b=f.children[10].getBoundingClientRect();   // caster 字段组
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-08-output-caster")

    # ⑤ 出口②：本地 Caster
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[12].getBoundingClientRect();   // ② 标题
      const b=f.children[18].getBoundingClientRect();   // kv 表
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-09-output-local-caster")

    # ⑥ 出口③：数传电台
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[23].getBoundingClientRect();   // ③ 标题
      const b=f.children[27].getBoundingClientRect();   // Direction
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-10-output-radio")

    # ⑦ 底部保存按钮
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[29].getBoundingClientRect();
      return {x:a.x+window.scrollX-16, y:a.y+window.scrollY-8, w:a.width+32, h:a.height+16};
    }""", "web-11-save")

    # ⑧ 中继模式：Mode + 中继地址 + 挂载点 + 账号
    goto(page, "/config", 3000)
    page.select_option("#mode", "relay")
    page.wait_for_timeout(1500)
    clip_of(page, """() => {
      const f=document.querySelector('form.form');
      const a=f.children[0].getBoundingClientRect();
      const b=f.children[5].getBoundingClientRect();
      const top=a.y+window.scrollY, bot=b.y+b.height+window.scrollY;
      return {x:a.x+window.scrollX-16, y:top-16, w:a.width+32, h:bot-top+32};
    }""", "web-12-relay-mode")
    page.select_option("#mode", "serial")
    page.wait_for_timeout(1000)


# ---------------------------------------------------------------- 标定页
def shoot_calibrate(page):
    print("[calibrate]")
    goto(page, "/calibrate", 2500)

    # 1. 设备卡（串口 / 波特率 / 型号 / 识别按钮）
    snap(page, "cal-01-device", "section.card >> nth=0")

    # 2. 扫描：真机只有一个 GNSS 口，结果表会自动带出型号
    page.click("#cal-scan")
    page.wait_for_timeout(18000)
    snap(page, "cal-02-scan-done", "section.card >> nth=0")

    # 3. 读模块信息：固件 / 硬件 ID / 当前模式，几秒内出结果；
    #    但要等「方式」选项解锁（识别收尾约 25-30 秒）
    page.click("#cal-detect")
    page.wait_for_timeout(6000)
    snap(page, "cal-03-detected", "section.card >> nth=0")
    page.wait_for_function(
        "() => !document.querySelector('input[value=cors]').disabled",
        timeout=60000,
    )
    page.wait_for_timeout(600)
    snap(page, "cal-03b-detected-ready", "section.card >> nth=0")

    # 4. 四种方式
    snap(page, "cal-04-methods", "section.card >> nth=1")

    # 5. 各方式的参数卡
    page.check("input[value=cors]", force=True)
    page.wait_for_timeout(1500)
    if page.locator("#cal-cors-card").is_visible():
        snap(page, "cal-05-cors", "#cal-cors-card")

    page.check("input[value=survey_in]", force=True)
    page.wait_for_timeout(1500)
    if page.locator("#cal-svin-card").is_visible():
        snap(page, "cal-06-survey", "#cal-svin-card")

    page.check("input[value=manual]", force=True)
    page.wait_for_timeout(1500)
    if page.locator("#cal-coord-card").is_visible():
        snap(page, "cal-07-manual", "#cal-coord-card")

    # 6. 运行区
    snap(page, "cal-08-run", "section.card >> nth=-1")


# ---------------------------------------------------------------- 标定页


GROUPS = {
    "login": shoot_login,
    "status": shoot_status,
    "config": shoot_config,
    "calibrate": shoot_calibrate,
}


def main():
    if "--list" in sys.argv:
        print("\n".join(GROUPS))
        return
    want = [a for a in sys.argv[1:] if not a.startswith("--")] or list(GROUPS)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE,
                                  locale="en-US")
        page = ctx.new_page()
        login(page)
        print("登录完成:", page.url)
        for g in want:
            GROUPS[g](page)
        browser.close()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
