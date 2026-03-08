import requests
from bs4 import BeautifulSoup
import re
import time
import traceback
import os


BASE      = "https://dorar.net"
INDEX     = "https://dorar.net/arabia"
MAIN_PAGE = "https://dorar.net/arabia/5197"
DELAY     = 1.0
OUT_DIR   = "dorar_arabia_output"

# عدد عناصر breadcrumb الثابتة قبل بداية الهرمية الفعلية
# مثال: الرئيسية > موسوعة اللغة العربية  ← 2 عناصر ثابتة → level يبدأ من 1 بعدهما
BC_BASE = 2


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
    """
    يستخرج مستوى العنوان من ol.breadcrumb.

    مثال breadcrumb:
      الرئيسية > موسوعة اللغة العربية > علم النحو > الباب الأول > الفصل الأول
      ──────────────────── BC_BASE=2 ───────────── | ─── level 1 ─── | ─ level 2 ─ | level 3

    الناتج = عدد العناصر - BC_BASE، بحد أدنى 1.
    Fallback: 2 (مستوى افتراضي للفروع الرئيسية)
    """
    bc = soup.find("ol", class_="breadcrumb")
    if not bc:
        return 2
    items = [li.get_text(strip=True) for li in bc.find_all("li") if li.get_text(strip=True)]
    level = max(len(items) - BC_BASE, 1)
    return level


# ══════════════════════════════════════════════
# مساعد الحواشي
# ══════════════════════════════════════════════

def convert_inner_soup(soup_tag):
    for inner in soup_tag.find_all("span", class_="aaya"):
        inner.replace_with(f"﴿{inner.get_text(strip=True)}﴾")
    for inner in soup_tag.find_all("span", class_="hadith"):
        inner.replace_with(f"«{inner.get_text(strip=True)}»")
    for inner in soup_tag.find_all("span", class_="sora"):
        t = inner.get_text(strip=True)
        if t:
            inner.replace_with(f" {t} ")


def get_tip_text(tip):
    for attr in ("data-original-title", "title", "data-content", "data-tippy-content"):
        val = tip.get(attr, "").strip()
        if val:
            inner_soup = BeautifulSoup(val, "html.parser")
            convert_inner_soup(inner_soup)
            return re.sub(r'\s+', ' ', inner_soup.get_text()).strip()
    convert_inner_soup(tip)
    return re.sub(r'\s+', ' ', tip.get_text(strip=True)).strip()


def fix_multiline_footnotes(text):
    lines  = text.splitlines()
    result = []
    fn_def = re.compile(r'^\[\^\d+\]:')
    i = 0
    while i < len(lines):
        line = lines[i]
        if fn_def.match(line):
            parts = [line.rstrip()]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt == '' or fn_def.match(nxt):
                    break
                parts.append(nxt.strip())
                i += 1
            result.append(' '.join(p for p in parts if p))
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


# ══════════════════════════════════════════════
# روابط
# ══════════════════════════════════════════════

def get_pane_links(soup, base_num=None):
    """يستخرج روابط القائمة الجانبية من الـ tab-pane الـ active."""
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
# استخراج المحتوى — يقبل soup جاهزة
# ══════════════════════════════════════════════

def extract_content(soup, fn_start=1):
    """
    يستخرج المحتوى من soup جاهزة (بدل إعادة parse).
    يعيد: {"text": str, "footnotes": list, "fn_next": int}
    """
    # تنظيف العناصر غير المرغوبة
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()
    for pattern in [
        re.compile(r"\bmodal\b"),
        re.compile(r"\breadMore\b"),
        re.compile(r"\balert-dorar\b"),
        re.compile(r"\btitle-manhag\b"),
        re.compile(r"\bdorar_custom_accordion\b"),
        re.compile(r"\bdefault-gradient\b"),
        re.compile(r"\bfooter-copyright\b"),
    ]:
        for tag in soup.find_all(True, class_=pattern):
            tag.decompose()

    # تحديد الـ block الرئيسي
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

    for i in range(1, 7):
        for h in block.find_all(f"h{i}"):
            h.replace_with(f"\n{'#' * (i + 2)} {h.get_text(strip=True)}\n")

    # استخراج الحواشي
    footnotes  = []
    fn_counter = fn_start
    for fn_tag in block.find_all(
            ["span", "div", "sup"],
            class_=re.compile(r"foot|note|hawashi|fn|tip", re.I)):
        fn_text = get_tip_text(fn_tag)
        if fn_text:
            footnotes.append(f"[^{fn_counter}]: {fn_text}")
            fn_tag.replace_with(f" [^{fn_counter}] ")
            fn_counter += 1

    raw = block.get_text(separator="\n", strip=False)
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'(?<!\n)\n(?![\n#>﴿«\[])', ' ', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)

    inline = re.compile(
        r'\[(\d+)\]\s*(يُنظَر[^\n]*|انظر[^\n]*|\(\([^)]+\)\)[^\n]*)',
        re.UNICODE
    )
    found = {m.group(1): m.group(0).strip() for m in inline.finditer(raw)}
    if found:
        for num, body in found.items():
            footnotes.append(f"[^{num}]: {body}")
        clean = inline.sub(lambda m: f" [^{m.group(1)}] ", raw)
    else:
        clean = raw

    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    return {"text": clean, "footnotes": footnotes, "fn_next": fn_counter}


# ══════════════════════════════════════════════
# الزحف — المستوى من breadcrumb
# ══════════════════════════════════════════════

def crawl(session, url, title, visited, referer=MAIN_PAGE, fn_counter=None):
    """
    يزحف تعاودياً.
    المستوى يُشتق من ol.breadcrumb في كل صفحة — لا يُمرَّر من الخارج.
    """
    if fn_counter is None:
        fn_counter = [1]
    if url in visited:
        return []
    visited.add(url)

    num      = int(url.split("/")[-1])
    html     = get_page(session, url, referer=referer)
    time.sleep(DELAY)

    if not html:
        return [{"url": url, "title": title, "level": 2,
                 "text": "(failed)", "footnotes": [], "fn_next": fn_counter[0]}]

    # parse مرة واحدة — نستخدمها لكل شيء
    soup  = BeautifulSoup(html, "html.parser")
    level = get_breadcrumb_level(soup)

    print(f"  [L{level}] {title}")

    sublinks = get_pane_links(soup, base_num=num)

    if sublinks:
        results = [{"url": url, "title": title, "level": level,
                    "text": "", "footnotes": [], "fn_next": fn_counter[0]}]
        for sub in sublinks:
            results += crawl(session, sub["url"], sub["title"],
                             visited, referer=url, fn_counter=fn_counter)
        return results
    else:
        parsed = extract_content(soup, fn_start=fn_counter[0])
        fn_counter[0] = parsed["fn_next"]
        print(f"    → {len(parsed['text'])} chars | fn up to {fn_counter[0]-1}")
        return [{"url": url, "title": title, "level": level, **parsed}]


# ══════════════════════════════════════════════
# الحفظ — ملف فرع واحد
# ══════════════════════════════════════════════

def save_markdown(results, branch_title):
    safe_name = re.sub(r'[^\w\u0600-\u06FF]', '_', branch_title)[:40]
    filepath  = os.path.join(OUT_DIR, f"{safe_name}.md")

    lines = [
        f"# {branch_title}\n\n",
        "> المصدر: موسوعة اللغة العربية — الدرر السنية\n\n",
        "---\n\n",
    ]
    all_footnotes = []

    for r in results:
        hashes = "#" * min(max(r["level"], 1), 6)
        lines.append(f"{hashes} {r['title']}\n\n")
        if r.get("text"):
            lines.append(f"{r['text']}\n\n")
        if r.get("footnotes"):
            all_footnotes.extend(r["footnotes"])
        if r["level"] >= 3:
            lines.append("---\n\n")

    if all_footnotes:
        lines.append("\n")
        for fn in all_footnotes:
            lines.append(f"{fn}\n")

    content = fix_multiline_footnotes("".join(lines))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    total_chars = sum(len(r.get("text", "")) for r in results)
    print(f"  → Saved: {filepath} | {len(results)} pages | "
          f"~{total_chars // 1024} KB | {len(all_footnotes)} حاشية")
    return filepath


# ══════════════════════════════════════════════
# الحفظ — ملف مجمّع للـ EPUB
# ══════════════════════════════════════════════

def save_combined_markdown(all_branches_results):
    """
    يكتب ملفاً واحداً يجمع كل الفروع بترقيم حواشٍ عالمي متسلسل.
    مناسب لتحويله إلى EPUB بـ Pandoc.
    """
    filepath      = os.path.join(OUT_DIR, "موسوعة_اللغة_العربية.md")
    global_fn     = 1          # عداد عالمي
    global_fn_map = {}         # (branch_idx, old_fn_num) → new_fn_num

    lines         = [
        "# موسوعة اللغة العربية\n\n",
        "> المصدر: الدرر السنية\n\n",
        "---\n\n",
    ]
    all_footnotes = []

    for b_idx, (branch_title, results) in enumerate(all_branches_results):
        lines.append(f"# {branch_title}\n\n")

        for r in results:
            hashes = "#" * min(max(r["level"] + 1, 2), 6)  # +1 لأن # الرئيسية مأخوذة
            lines.append(f"{hashes} {r['title']}\n\n")

            text = r.get("text", "")
            fns  = r.get("footnotes", [])

            # إعادة ترقيم الحواشي لهذه الصفحة
            if fns:
                remap = {}
                for fn_def in fns:
                    m = re.match(r'^\[\^(\d+)\]:', fn_def)
                    if m:
                        old_n = int(m.group(1))
                        remap[old_n] = global_fn
                        new_def = re.sub(r'^\[\^\d+\]:', f'[^{global_fn}]:', fn_def)
                        all_footnotes.append(new_def)
                        global_fn += 1

                # إعادة ترقيم الإشارات في النص
                def replace_ref(m):
                    old = int(m.group(1))
                    return f" [^{remap.get(old, old)}] "

                text = re.sub(r'\[\^(\d+)\]', replace_ref, text)

            if text:
                lines.append(f"{text}\n\n")
            if r["level"] >= 3:
                lines.append("---\n\n")

        lines.append("\n\n")

    # كتابة تعريفات الحواشي في النهاية
    if all_footnotes:
        lines.append("\n")
        for fn in all_footnotes:
            lines.append(f"{fn}\n")

    content = fix_multiline_footnotes("".join(lines))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n  → Combined: {filepath} | {len(all_footnotes)} حاشية إجمالية")
    return filepath


# ══════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════

if __name__ == "__main__":
    try:
        os.makedirs(OUT_DIR, exist_ok=True)

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
        visited             = {MAIN_PAGE}
        all_branches_results = []   # لتجميع الـ EPUB

        for b in branches:
            print(f"\n{'='*50}")
            print(f"Branch: {b['title']}")
            print('='*50)

            fn_counter = [1]
            results    = []
            for entry in b["links"]:
                results += crawl(session, entry["url"], entry["title"],
                                 visited, fn_counter=fn_counter)

            save_markdown(results, b["title"])
            all_branches_results.append((b["title"], results))

        # كتابة الملف المجمّع للـ EPUB
        if all_branches_results:
            save_combined_markdown(all_branches_results)

        print("\nAll done!")

    except Exception:
        print("=== ERROR ===")
        traceback.print_exc()