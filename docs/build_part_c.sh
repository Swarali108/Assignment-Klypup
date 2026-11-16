#!/usr/bin/env bash
# Rebuild docs/part_c.pdf from docs/part_c.md: markdown -> styled HTML -> Chromium print (A4, must stay <= 2 pages).
# Needs Node (npx fetches `marked` and `playwright` on first use). Usage: docs/build_part_c.sh
set -euo pipefail
cd "$(dirname "$0")"
TMP="$(mktemp -d)"
npx -y marked --gfm -i part_c.md -o "$TMP/body.html"
{
cat <<'HTML'
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Part C: Win the client</title>
<style>
  @page { size: A4; margin: 11mm 12mm 11mm 12mm; }
  * { box-sizing: border-box; }
  body { font: 9.3pt/1.36 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1c2321; margin: 0; }
  h1 { font-size: 15pt; margin: 0 0 2pt; color: #0f3d2e; letter-spacing: -0.2pt; }
  h2 { font-size: 10.5pt; margin: 7pt 0 3pt; color: #0f3d2e; border-bottom: 1.2pt solid #cfe0d8; padding-bottom: 1.5pt; }
  p { margin: 2.5pt 0; }
  ul, ol { margin: 2pt 0 2pt 13pt; padding: 0; }
  li { margin: 1pt 0; }
  table { width: 100%; border-collapse: collapse; margin: 3pt 0 4pt; font-size: 8.7pt; page-break-inside: auto; }
  tr { page-break-inside: avoid; }
  th { background: #eef5f1; text-align: left; font-weight: 600; color: #0f3d2e; }
  th, td { border: 0.6pt solid #d5ddd9; padding: 1.8pt 3.5pt; vertical-align: top; }
  td:first-child { white-space: nowrap; }
  blockquote { margin: 3pt 0; padding: 3pt 7pt; background: #fbf6e9; border-left: 2.5pt solid #c9a24a; }
  blockquote p { margin: 1.5pt 0; }
  em { color: #33403b; }
  strong { color: #10241c; }
</style></head><body>
HTML
cat "$TMP/body.html"
echo '</body></html>'
} > "$TMP/part_c.html"
npx -y playwright pdf --paper-format=A4 "file://$TMP/part_c.html" part_c.pdf
command -v pdfinfo >/dev/null && pdfinfo part_c.pdf | grep Pages || true
rm -rf "$TMP"
