#!/usr/bin/env bash
# scaffold.sh -- creates the four Touchstone 2 page skeletons.
#
# It writes ONLY the standard HTML boilerplate (the part Unit 2 hands you) plus a
# TODO comment naming every required element that still has to go on that page.
# Everything that earns credit -- headings, copy, nav links, figure, picture,
# media, form -- you write yourself.
#
# Safe to re-run: it will not overwrite a page you have started working on.
set -euo pipefail
CLIENT="Riverbend Yoga Studio"

make_page() {
  file="$1"; title="$2"; todos="$3"
  if [ -s "$file" ]; then
    echo "skip   $file (already has content)"
    return
  fi
  {
    echo "<!DOCTYPE html>"
    echo "<html lang=\"en\">"
    echo "<head>"
    echo "  <meta charset=\"utf-8\">"
    echo "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    echo "  <title>${title} | ${CLIENT}</title>"
    echo "</head>"
    echo "<body>"
    echo "${todos}"
    echo "</body>"
    echo "</html>"
  } > "$file"
  echo "create $file"
}

COMMON='<!-- TODO nav: <nav><ul><li><a href="..."> for all four pages, relative paths -->
<!-- TODO footer: <footer> with something a real visitor would need -->'

make_page index.html "Home" \
"<!-- TODO header: logo or studio image, alt text describes the client -->
${COMMON}
<!-- TODO main: exactly ONE <h1>, then h2 sections (no skipped levels) -->
<!-- TODO   mission statement -->
<!-- TODO   beginner reassurance -->
<!-- TODO   featured class -->
<!-- TODO   schedule overview -->
<!-- TODO   one <img> with meaningful alt text -->"

make_page services.html "Services" \
"<!-- TODO header -->
${COMMON}
<!-- TODO main: one <h1>, then h2 sections -->
<!-- TODO   class types: gentle / vinyasa / restorative -->
<!-- TODO   private sessions -->
<!-- TODO   pricing model overview (no checkout) -->
<!-- TODO   ONE <figure> + <figcaption>  -> highlight a workshop -->
<!-- TODO   ONE responsive image: <picture> with <source media=...> x2 + fallback <img> -->
<!-- TODO   ONE <img> with meaningful alt text -->"

make_page about.html "About" \
"<!-- TODO header -->
${COMMON}
<!-- TODO main: one <h1>, then h2 sections -->
<!-- TODO   instructor bios (use yoga-instructor_c.png, meaningful alt) -->
<!-- TODO   accessibility accommodations -->
<!-- TODO   studio policies -->
<!-- TODO   ONE <audio controls> or <video controls> WITH fallback text between the tags -->"

make_page events.html "Events" \
"<!-- TODO header -->
${COMMON}
<!-- TODO main: one <h1>, then the monthly workshop list -->
<!-- TODO form: <form> > <fieldset> > <legend>, a <label for> per field, -->
<!-- TODO       name, email (type=email), class/event interest, experience level -->
<!-- TODO       (radio group inside its own fieldset), preferred contact method, -->
<!-- TODO       message, and required on the fields that must not be empty -->
<!-- TODO       then a submit button -->"

echo
echo "Now:  python3 ts2_check.py .     # this is your to-do list, one error at a time"
