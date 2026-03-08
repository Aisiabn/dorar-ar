"""
dorar_arabia_epub.py
يجلب موسوعة اللغة العربية من dorar.net ويحفظها مباشرةً كـ EPUB.
المتطلبات: pip install requests beautifulsoup4 ebooklib
"""


import requests
from bs4 import BeautifulSoup
from ebooklib import epub
import re
import time
import traceback
import os
import html as html_mod


BASE      = "https://dorar.net"
INDEX     = "https://dorar.net/arabia"
MAIN_PAGE = "https://dorar.net/arabia/5197"
DELAY     = 1.0
OUT_FILE  = "موسوعة_اللغة_العربية.epub"
BC_BASE   = 2   # عدد عناصر breadcrumb الثابتة (الرئيسية + موسوعة اللغة العربية)


# ══════════════════════════════════════════════
# Session
# ══════════════════════════════════════════════

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent"               : "Mozilla/5.0 (Windows NT 6.1; WOW64) "
                                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                                     "Chrome/109.0.0.0 Safari/537.36",
        "Accept"                   : "text/html,application/xhtml+xml,application/xml;"
                                     "q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language"          : "ar,en-US;q=0.9,en;q=0.8",
        "Connection"               : "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def get_page(session, url, referer=INDEX):
    session.headers["Referer"] = referer
    try:
        r = session.get(url, timeout=20)
        print(f"  [{r.status_code}] {url}")
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        print(f"  [ERR] {e}")
        return ""


# ══════════════════════════════════════════════
# Breadcrumb → level
# ══════════════════════════════════════════════

def get_breadcrumb_level(soup):
    bc = soup.find("ol", class_="breadcrumb")
    if not bc:
        return 2
    items = [li.get_text(strip=True) for li in bc.find_all("li") if li.get_text(strip=True)]
    return max(len(items) - BC_BASE, 1)


# ══════════════════════════════════════════════
# مساعدات الحواشي
# ══════════════════════════════════════════════

def convert_inner_soup(tag):
    for s in tag.find_all("span", class_="aaya"):
        s.replace_with(f"﴿{s.get_text(strip=True)}﴾")
    for s in tag.find_all("span", class_="hadith"):
        s.replace_with(f"«{s.get_text(strip=True)}»")
    for s in tag.find_all("span", class_="sora"):
        t = s.get_text(strip=True)
        if t:
            s.replace_with(f" {t} ")


def get_tip_text(tip):
    for attr in ("data-original-title", "title", "data-content", "data-tippy-content"):
        val = tip.get(attr, "").strip()
        if val:
            inner = BeautifulSoup(val, "html.parser")
            convert_inner_soup(inner)
            return re.sub(r'\s+', ' ', inner.get_text()).strip()
    convert_inner_soup(tip)
    return re.sub(r'\s+', ' ', tip.get_text(strip=True)).strip()


# ══════════════════════════════════════════════
# روابط
# ══════════════════════════════════════════════

def get_pane_links(soup, base_num=None):
    panes = soup.find_all("div", class_="tab-pane")
    links = []
    seen  = set()
    for pane in panes:
        if "active" not in pane.get("class", []):
            continue
        for a in pane.find_all("a", href=True):
            href  = a["href"]
            title = a.get_text(strip=True)
            m     = re.match(r"^/arabia/(\d+)$", href)
            if not m or not title:
                continue
            num = int(m.group(1))
            if base_num and num <= base_num:
                continue
            if href in seen:
                continue
            seen.add(href)
            links.append({"url": BASE + href, "title": title, "num": num})
        break
    return links


def get_all_branches(html):
    soup       = BeautifulSoup(html, "html.parser")
    panes      = soup.find_all("div", class_="tab-pane")
    branches   = []
    seen_first = set()
    for pane in panes:
        links = []
        for a in pane.find_all("a", href=True):
            href  = a["href"]
            title = a.get_text(strip=True)
            m     = re.match(r"^/arabia/(\d+)$", href)
            if not m or not title:
                continue
            links.append({"url": BASE + href, "title": title, "num": int(m.group(1))})
        if not links:
            continue
        first_url = links[0]["url"]
        if first_url in seen_first:
            continue
        seen_first.add(first_url)
        raw_text     = pane.get_text(strip=True)
        branch_title = re.split(r'تَمهيد|تمهيد|البابُ|الباب|مُقَدِّمة', raw_text)[0].strip()
        if not branch_title:
            branch_title = links[0]["title"]
        branches.append({"title": branch_title, "links": links})
    return branches


# ══════════════════════════════════════════════
# استخراج المحتوى → HTML نظيف للـ EPUB
# ══════════════════════════════════════════════

def extract_content_html(soup, fn_start=1):
    """
    يستخرج المحتوى ويعيده كـ HTML مناسب للـ EPUB،
    مع قائمة حواشٍ كـ (رقم، نص).
    """
    # تنظيف
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()
    for pattern in [
        re.compile(r"\bmodal\b"), re.compile(r"\breadMore\b"),
        re.compile(r"\balert-dorar\b"), re.compile(r"\btitle-manhag\b"),
        re.compile(r"\bdorar_custom_accordion\b"), re.compile(r"\bdefault-gradient\b"),
        re.compile(r"\bfooter-copyright\b"),
    ]:
        for tag in soup.find_all(True, class_=pattern):
            tag.decompose()

    block = None
    card  = soup.find("div", class_="card-body")
    if card:
        for pane in card.find_all("div", class_="tab-pane"):
            if "active" in pane.get("class", []):
                text  = pane.get_text(strip=True)
                links = pane.find_all("a", href=re.compile(r"^/arabia/\d+$"))
                if len(text) > 200 and len(links) <= 2:
                    block = pane
                    break
    if not block:
        block = soup.find("body") or soup

    for tag in block.find_all(True, class_=re.compile(
            r"\balert-dorar\b|\breadMore\b|\bfixed-bottom\b|\bside-nav\b")):
        tag.decompose()
    for a in block.find_all("a"):
        if re.search(r"السابق|التالي|الصفحة|المراجع المعتمدة|اعتماد المنهجية", a.get_text()):
            a.decompose()

    # استخراج الحواشي
    footnotes  = []
    fn_counter = fn_start
    for fn_tag in block.find_all(
            ["span", "div", "sup"],
            class_=re.compile(r"foot|note|hawashi|fn|tip", re.I)):
        fn_text = get_tip_text(fn_tag)
        if fn_text:
            footnotes.append((fn_counter, fn_text))
            fn_tag.replace_with(
                f'<sup><a id="ref{fn_counter}" href="#fn{fn_counter}">[{fn_counter}]</a></sup>'
            )
            fn_counter += 1

    # تحويل العناوين
    for i in range(1, 7):
        for h in block.find_all(f"h{i}"):
            lvl   = min(i + 2, 6)
            h_new = BeautifulSoup(f"<h{lvl}>{html_mod.escape(h.get_text(strip=True))}</h{lvl}>",
                                  "html.parser").find()
            h.replace_with(h_new)

    # بناء HTML نهائي
    paragraphs = []
    for p in block.find_all("p"):
        txt = p.decode_contents().strip()
        if txt:
            paragraphs.append(f"<p>{txt}</p>")

    if not paragraphs:
        raw = block.get_text(separator="\n")
        raw = re.sub(r'\n{2,}', '\n', raw).strip()
        paragraphs = [f"<p>{html_mod.escape(line.strip())}</p>"
                      for line in raw.splitlines() if line.strip()]

    body_html = "\n".join(paragraphs)

    # تحويل span.aaya و span.hadith داخل HTML
    body_html = re.sub(
        r'<span[^>]*class="[^"]*aaya[^"]*"[^>]*>(.*?)</span>',
        r'﴿\1﴾', body_html, flags=re.S)
    body_html = re.sub(
        r'<span[^>]*class="[^"]*hadith[^"]*"[^>]*>(.*?)</span>',
        r'«\1»', body_html, flags=re.S)

    return {"html": body_html, "footnotes": footnotes, "fn_next": fn_counter}


# ══════════════════════════════════════════════
# الزحف
# ══════════════════════════════════════════════

def crawl(session, url, title, visited, referer=MAIN_PAGE, fn_counter=None):
    if fn_counter is None:
        fn_counter = [1]
    if url in visited:
        return []
    visited.add(url)

    num  = int(url.split("/")[-1])
    html = get_page(session, url, referer=referer)
    time.sleep(DELAY)

    if not html:
        return [{"url": url, "title": title, "level": 2,
                 "html": "<p>(failed)</p>", "footnotes": []}]

    soup  = BeautifulSoup(html, "html.parser")
    level = get_breadcrumb_level(soup)
    print(f"  [L{level}] {title}")

    sublinks = get_pane_links(soup, base_num=num)

    if sublinks:
        results = [{"url": url, "title": title, "level": level,
                    "html": "", "footnotes": []}]
        for sub in sublinks:
            results += crawl(session, sub["url"], sub["title"],
                             visited, referer=url, fn_counter=fn_counter)
        return results
    else:
        parsed = extract_content_html(soup, fn_start=fn_counter[0])
        fn_counter[0] = parsed["fn_next"]
        print(f"    → {len(parsed['html'])} chars | fn up to {fn_counter[0]-1}")
        return [{"url": url, "title": title, "level": level,
                 "html": parsed["html"], "footnotes": parsed["footnotes"]}]


# ══════════════════════════════════════════════
# بناء الـ EPUB
# ══════════════════════════════════════════════

CSS = """
@charset "UTF-8";
body { font-family: "Amiri", "Arial", serif; direction: rtl; text-align: right;
       line-height: 1.8; margin: 1em 2em; }
h1 { font-size: 1.8em; border-bottom: 2px solid #333; padding-bottom: .3em; }
h2 { font-size: 1.5em; color: #444; }
h3 { font-size: 1.3em; color: #555; }
h4, h5, h6 { font-size: 1.1em; color: #666; }
p  { margin: .5em 0; }
sup a { font-size: .75em; color: #0055aa; text-decoration: none; }
ol.footnotes { font-size: .85em; color: #444; border-top: 1px solid #ccc;
               margin-top: 2em; padding-top: 1em; }
ol.footnotes li { margin: .3em 0; }
"""


def build_chapter_html(title, results):
    """يبني HTML فصل كامل من قائمة النتائج."""
    body_parts = [f'<h1>{html_mod.escape(title)}</h1>\n']
    all_fns    = []

    for r in results:
        lvl   = min(max(r["level"], 1), 6)
        body_parts.append(f"<h{lvl}>{html_mod.escape(r['title'])}</h{lvl}>\n")
        if r.get("html"):
            body_parts.append(r["html"] + "\n")
        if r.get("footnotes"):
            all_fns.extend(r["footnotes"])

    if all_fns:
        fn_html = ['<ol class="footnotes">']
        for num, text in all_fns:
            fn_html.append(
                f'<li id="fn{num}"><a href="#ref{num}">[{num}]</a> '
                f'{html_mod.escape(text)}</li>'
            )
        fn_html.append("</ol>")
        body_parts.append("\n".join(fn_html))

    inner = "\n".join(body_parts)
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" dir="rtl" lang="ar" xml:lang="ar">
<head><meta charset="utf-8"/><title>{html_mod.escape(title)}</title></head>
<body>{inner}</body>
</html>"""


def build_epub(all_branches):
    book = epub.EpubBook()
    book.set_identifier("dorar-arabia-001")
    book.set_title("موسوعة اللغة العربية")
    book.set_language("ar")
    book.add_author("الدرر السنية")

    # CSS
    style = epub.EpubItem(
        uid="style", file_name="style/main.css",
        media_type="text/css", content=CSS.encode()
    )
    book.add_item(style)

    chapters = []
    toc      = []

    for idx, (branch_title, results) in enumerate(all_branches, 1):
        ch_html  = build_chapter_html(branch_title, results)
        ch_fname = f"chapter_{idx:03d}.xhtml"
        chapter  = epub.EpubHtml(
            title=branch_title,
            file_name=ch_fname,
            lang="ar",
            content=ch_html.encode("utf-8")
        )
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)
        toc.append(epub.Link(ch_fname, branch_title, f"ch{idx}"))

    book.toc   = toc
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(OUT_FILE, book)
    print(f"\n✓ Saved: {OUT_FILE}")


# ══════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════

if __name__ == "__main__":
    try:
        session = make_session()
        print("Initializing session...")
        get_page(session, INDEX)
        time.sleep(1)

        html_main = get_page(session, MAIN_PAGE)
        time.sleep(2)

        branches = get_all_branches(html_main)
        print(f"\n[OK] Found {len(branches)} branches:\n")
        for i, b in enumerate(branches, 1):
            print(f"  {i}. {b['title']} ({len(b['links'])} top links)")

        print()
        visited     = {MAIN_PAGE}
        all_branches = []

        for b in branches:
            print(f"\n{'='*50}")
            print(f"Branch: {b['title']}")
            print('='*50)

            fn_counter = [1]
            results    = []
            for entry in b["links"]:
                results += crawl(session, entry["url"], entry["title"],
                                 visited, fn_counter=fn_counter)

            all_branches.append((b["title"], results))

        print("\nBuilding EPUB...")
        build_epub(all_branches)

        print("\nAll done!")

    except Exception:
        print("=== ERROR ===")
        traceback.print_exc()
