name: Scraper AR

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 360
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install requests beautifulsoup4

      - name: Install Pandoc
        run: |
          wget -q https://github.com/jgm/pandoc/releases/download/3.6/pandoc-3.6-1-amd64.deb
          sudo dpkg -i pandoc-3.6-1-amd64.deb

      - name: Run scraper
        run: python Scraper_ar.py

      - name: Convert to EPUB
        run: |
          pandoc dorar_arabia_output/موسوعة_اللغة_العربية.md \
            --metadata-file=epub_metadata.yaml \
            --toc \
            --toc-depth=3 \
            -o dorar_arabia_output/موسوعة_اللغة_العربية.epub

      - name: Commit and push results
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add dorar_arabia_output/
          git diff --cached --quiet || (
            git commit -m "update: scraped content $(date +'%Y-%m-%d')"
            git pull --rebase origin main
            git push
          )
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}