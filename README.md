# Prodigia

A register of anomalous sightings, kept from public reports, published as a static page.

The unit of the register is the event, not the post. Reports of one event from several sources are filed under a single entry, so an entry shows how many independent reports the event has gathered. Each entry carries a standing, which is a statement about the record and never about the phenomenon: UNRESOLVED means the filed reports hold no established ordinary explanation, RESOLVED - ORDINARY means an ordinary cause is established in the record and is named, and INSUFFICIENT RECORD means the filed reports lack the time, place or detail a check requires.

## Layout

index.html is the register page. It is generated, never edited by hand.

events.json is the register itself, the source of truth. Every entry carries its date, place, described form, summary, standing, and the list of reports filed under it, each report naming its source, its posting date and its address.

gather.py is the gatherer. It is stdlib-only Python with no accounts, no keys and no telemetry. It reads the public news wire for sighting coverage and ingests source snapshots from the sources directory when present, files each report under the event it describes, consolidates entries the filing rules would join, settles standings from the record, and re-renders index.html.

sources holds snapshots of source tables read from public indexes, saved verbatim as JSON rows. A snapshot row carries the fields its source published: the sighting date and time, the place, the described form, the witness summary and the address of the full report.

## Filing rules

A report is filed under an existing event when both describe the same form in the same region within seven days. Reports whose described form is rare in the record, such as a jellyfish form, are filed under that form's single active event within the same window when their own region is unstated. When in doubt a new entry is opened. Entries can be merged as the record grows; they are never split to fit a count, and no entry is ever removed for being resolved.

## Running the gatherer

python3 gather.py

The gatherer is idempotent: a report already in the register, known by its address, is not filed twice. Each run rewrites events.json and index.html in place.

## Publication

The repository is served as a static site from its main branch. A gather run that changes the register is committed like any other change, so the page's history is the register's history.
