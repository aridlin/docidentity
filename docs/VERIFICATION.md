# Verification on the target system

2026-10-17; Arch Linux, Python 3.14, LibreOffice 26.8.1.1.

`python scripts/test.py`: **33 tests passed** in process-isolated suites:
14 core/registry tests, 3 CLI/PDF tests, 7 scanner parser tests and 9 actual headless UNO tests. Some tests
cover multiple applications and scenarios. `dist/test-results.txt` retains the
run output. The closed-database exceptions in that output are deliberately
injected failures; their recovery assertions pass.

Covered: random ID validation, initial registration, opening existing identities,
identical copies, multiple paths, first and subsequent edits, formatting,
cursor/selection exclusion, undo, unchanged Save As, save failure and retry,
discard, inferred rename, missing files, hash mismatch and metadata exclusion,
barcode repair/deduplication, restored coordinates and stable normalized hashes,
read-only loads, SQLite failure across consecutive saves with ancestry recovery,
Writer/Calc/Impress registration and PDF export, native PDF generation/recovery,
scanner CLI protocol validation and registry backup.

Every tested LibreOffice format was saved, reopened/copied, exported through its
own PDF filter, rasterized and independently decoded to the full expected ID.
A custom Calc print area excluding the barcode was rejected before PDF
registration. The normalized hash trims trailing empty Calc anchor rows while
retaining meaningful intervening rows and attributed cells.

`xvfb-run -a -s '-screen 0 1280x900x24' python scripts/test_extension.py`:
OXT installation, real Python loader, **automatic visible-document startup**,
automatic new documents, the actual Ctrl+N/AddDirect dispatch, first edit and committed lineage verified in Writer, Calc and Impress. No manual
job/listener bootstrap is used by this final test. Headless library tests drive
the controller directly; the installed CLI does not depend on a GUI startup hook.
`dist/extension-results.txt` contains the package integration output.

`xvfb-run -a -s '-screen 0 1280x900x24' python scripts/test_gui.py`:
real Qt widgets verified: multiple paths, lineage navigation, no automatic file
open on lookup and explicit open-button invocation. `xdg-open` is intercepted in
this test so no fixture is launched. `dist/gui-results.txt` records the result.

Rendered Writer, Calc, Impress pages and the complete lookup window were visually
inspected. PNGs remain in `dist/qa/`; temporary documents and databases are removed
by the tests. Native UNO exceptions are reported by a custom unittest result
class because Python 3.14's default traceback cleanup tries to mutate UNO proxy
exception fields. Drawing mutations use listener suppression without deferring
layout through controller locks; this avoids native headless drawing failures
observed during development. Graphics are imported through owned byte streams.

Not yet verified: a physical printer/laser scanner round trip, every pre-existing
custom document/template, extended manual interactive use, and every LibreOffice
release. In particular, complex page layouts still need inspection after first
registration. Concurrent editing of one path is unsupported. Arbitrary PDF
stamping and background filesystem monitoring are outside this implementation.

## 0.2.0 desktop integration
The lookup window uses installed PyQt6 native desktop widgets, structured tabs,
proper selection/actions, clipboard copying and an inline unknown-ID state.
The scanner tests cover full @$ ID dispatch exactly once, Enter/Tab/idle
termination, @#clipbin compatibility, unknown @# reservation, malformed IDs,
unchanged ordinary scan passthrough and shell-free lookup invocation.
The device-specific service receives an in-place extension, with a backup;
there is no competing global hook. Physical scanner confirmation still requires
an actual scan; parser event replay is explicitly synthetic verification.

The installed scanner service was restarted and confirmed active with its exclusive
Symbol device attachment. A synthetic @$ HID-key sequence was replayed through
the installed parser; it launched the installed Qt lookup in the service's actual
desktop environment. The GUI remained running and no document was opened. This
checks the complete software launch path; it is not a claim of a physical scan.
