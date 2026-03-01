def save_markdown(results, branch_title):
    safe_name = re.sub(r'[^\w\u0600-\u06FF]', '_', branch_title)[:40]
    filepath   = os.path.join(OUT_DIR, f"{safe_name}.md")

    lines = [
        f"# {branch_title}\n\n",
        "> المصدر: موسوعة اللغة العربية - الدرر السنية\n\n",
        "---\n\n",
    ]

    all_footnotes = []   # ← تُجمع هنا كل حواشي الملف

    for r in results:
        hashes = "#" * min(max(r["level"], 1), 6)
        lines.append(f"{hashes} {r['title']}\n\n")

        if r.get("text"):
            lines.append(f"{r['text']}\n\n")

        if r.get("footnotes"):
            all_footnotes.extend(r["footnotes"])   # ← تأجيل، لا كتابة فورية

        if r["level"] >= 3:
            lines.append("---\n\n")

    # ✅ كل الحواشي في نهاية الملف مرة واحدة
    if all_footnotes:
        lines.append("\n")
        for fn in all_footnotes:
            lines.append(f"{fn}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    total_chars = sum(len(r.get("text", "")) for r in results)
    print(f"  → Saved: {filepath} | {len(results)} pages | ~{total_chars // 1024} KB | {len(all_footnotes)} حاشية")
    return filepath