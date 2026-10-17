# Document Identity and Lineage

Local-first Python UNO extension for LibreOffice on Arch Linux / KDE Plasma.
ODT, ODS and ODP files carry a random 128-bit `@$` identity, one printable Code 128
barcode, and ODF custom properties. SQLite stores locations, lineage, observations
and history. No content backup, version-control system, filesystem watcher,
keyboard hook, network listener or permanent service is installed.

## Get the source

```sh
git clone https://github.com/aridlin/docidentity.git
cd docidentity
```

The scanner integration is optional and adapts an existing scanner-specific
handler locally. Device identifiers, private command implementations and registry
data are not included in this repository. Build artifacts are generated locally.

## Install on Arch Linux

Requirements: LibreOffice with Python UNO, Python >= 3.11, native Qt widgets (`python-pyqt6` on Arch),
`python-cairo` for the new-PDF helper. SQLite and the barcode PNG generator use
Python's standard library. PDF verification requires Poppler and `zbar` (also used by the tests).

```sh
python -c 'import uno, PyQt6.QtWidgets, cairo'
python scripts/build.py
python scripts/install.py --global-policy
```

Close all LibreOffice windows before installation/upgrade; restart LibreOffice
fully afterwards. The installer uses user `unopkg`, never root. An already running
LibreOffice can prevent `unopkg` installation; close it and run the command again.
The build artifact is `dist/docidentity-0.2.0.oxt`. Alternatively install it with
LibreOffice Tools > Extensions > Add, and install just the CLI with
`python scripts/install.py --skip-extension --global-policy`.

`~/.local/bin/docidentity` launches system Python. Add `~/.local/bin` to PATH if
needed. The installer copies the Python package to
`$XDG_DATA_HOME/docidentity/app` (default `~/.local/share/docidentity/app`).
The OXT bundles the same core; rebuild and reinstall both when upgrading.
No pip installation is required on Arch and no system Python packages are changed.

Upgrade: run the same build/install commands. Do not delete the registry.
Removal: `python scripts/install.py --remove`. This restores the scanner handler
from its matching pre-integration backup when applicable, then removes the extension and CLI,
but retains the registry, embedded document metadata and global document policy.
To remove the global policy too, remove its `Registered document generation`
section from `~/.codex/AGENTS.md` yourself; unrelated instructions are preserved.

## Use in LibreOffice

New documents, including Ctrl+N, automatically receive one provisional identity
and barcode. The registry entry is committed when you first save them as ODF.
Opening existing untracked files still leaves registration under your control.

The **Document Identity** menu offers:

1. **Register Document**: add barcode and custom properties; save a named ODF file
   to commit. New untitled documents remain provisional until saved as ODF.
2. **Document Information**: current/provisional ID, current path and registry
   details, including all locations, parents, children, timestamps, events,
   hashes and warnings.
3. **Reposition Barcode**: enter horizontal/vertical coordinates in millimetres
   from the page origin. This is the supported manual placement operation and
   preserves identity. Save afterwards to persist the position.
4. **Restore Default Barcode Position**: place the managed barcode at its default.
5. **Repair Barcode**: replace its graphic and remove reserved-name duplicates.
6. **Reconcile Document Identity**: explicitly keep the embedded identity, or
   allocate a child identity (committed only on save). Cancel changes nothing.

Registration preserves existing text/cells/shapes. Writer reserves a 22 mm top
margin and uses a page-anchored barcode near the upper-right of page one; this can
reflow an existing document. Calc places the shape two rows below first-sheet
used data. Impress tries the bottom-right first, then other vacant corners;
it refuses registration if no corner is vacant. Nothing replaces user cells or
user drawings. Review layout after initial registration, especially complex
Writer headers and custom Calc print ranges. Reposition through the menu when
needed. Managed object names reserve the `DocIdentity.ManagedBarcode` prefix;
do not assign this prefix to your own drawings.

The first **user modification, including formatting**, allocates one new
provisional child ID and updates its barcode in memory. Subsequent modifications
in that dirty session keep it. Cursor movement and selection do not count.
Undo retains the allocated identity. Saving commits it; closing and discarding
leaves the original file/registry identity intact. Extension-controlled changes
are suppressed. Ordinary dragging/deleting the barcode outside the menu is a
user modification and therefore creates an ID; use the placement/repair actions
when the intent is a tracking-only change.

An unchanged Save or Save As retains the ID. Saving edits to one copy changes
only that file's state. Old identities remain as history, with the old path
marked historical when a newer identity has been observed there. This system
does **not** retain old file contents or promise that an ancestor can be reopened.

## CLI and Codex document generation

Run from source as `python -m docidentity.cli`, or use the installed command:

```sh
docidentity register /absolute/path/document.odt
docidentity register /absolute/path/workbook.ods
docidentity register /absolute/path/slides.odp
docidentity info '@$A7F92C103B8D4E569012AB34CD56EF78'
docidentity lookup '@$A7F92C103B8D4E569012AB34CD56EF78'
docidentity reconcile /absolute/path/moved-document.odt
docidentity register-pdf /absolute/path/created-by-docidentity.pdf
docidentity export /absolute/path/document.odt /absolute/path/output.pdf
docidentity register-export /absolute/path/document.odt /absolute/path/already-exported.pdf
docidentity pdf /absolute/path/new.pdf --text 'A new document created by this tooling'
docidentity check
docidentity backup /absolute/path/registry-backup.sqlite3
```

ODF registration and export start one disposable headless LibreOffice process
with an isolated temporary profile and a random **local named pipe**, then stop
it. They do not alter your interactive LibreOffice profile. Do not operate on a
file currently open for editing; read-only loads are rejected. `--pipe NAME`
can instead connect to a deliberately launched existing UNO pipe.
`DOCIDENTITY_SOFFICE` overrides the system `/usr/bin/soffice` executable.
The PDF helper only creates new one-page PDFs (up to 52 lines); output paths must
not already exist. Use the library/barcode module in a richer generator or make
an ODF and export it for longer documents.

Library entry points: `Registry`, `Session`, `new_id`, `barcode.png`,
`Office.register`, `Office.export`, and `cli.make_pdf`.
Do not register an arbitrary PDF under an ID without a visible barcode.
`register-pdf` can recover registration of this tool's own generated PDFs after a
database failure: it verifies the Creator/Subject metadata and decodes the visible
barcode using Poppler/zbar before registering, without changing the PDF.
Arbitrary PDF stamping, signed-PDF editing, encryption and destructive PDF
rewrites are intentionally not implemented. PDF export from the tooling records
the same ID and a source-to-PDF relationship. Exporting through LibreOffice's
stock PDF dialog does include the visible barcode, but does **not** automatically
register that output path: use `docidentity export` for registered exports, or
`docidentity register-export SOURCE OUTPUT.pdf` to verify and register an already
exported PDF without modifying it. Exports are registered only after a rendered
page contains the matching decodable barcode; excluded print areas fail safely.

`AGENTS.md` applies this project's generation policy locally.
`docs/GLOBAL-AGENTS-snippet.md` provides the reusable global instruction;
`install.py --global-policy` appends it to `$CODEX_HOME/AGENTS.md` (normally
`~/.codex/AGENTS.md`) without replacing existing instructions. Project-local
instructions alone do not affect other repositories. The global rule directs
future Codex sessions to this installed CLI, and permits an explicit user exception.

## Scanner integration

On this target system `python scripts/install.py --scanner-integration` updates
and restarts the **existing** `scanner-commands.service`. Its `@#clipbin` command
and normal barcode passthrough remain intact. `@$` IDs are consumed by that same
scanner-specific parser and launch the lookup GUI, so they are not typed into
the focused application. No second device grab or global hook is added. The
installer saves a timestamped backup beside the handler and refuses to overwrite
an unexpected handler version. It does not upload anything during installation.

For another handler: when its completed input starts with `@$`,
pass the complete value as a **single argument** to `docidentity lookup ID`.
Use a subprocess argument list; avoid shell interpolation. For example:

```python
if barcode.startswith('@$'):
    subprocess.Popen(['docidentity', 'lookup', barcode])
# Leave the separate @# command protocol with its current handler.
```

The lookup validates the entire ID and opens a native Qt window with separate
locations, history, lineage, hashes and warnings views; it never
opens a document just because a barcode was scanned. Select a location and use
**Open selected file** or **Open containing directory** explicitly. All known
locations are listed, with availability and whether the last observed identity
at that path is current. Double-click a parent or child in the Lineage tab to navigate. Unknown IDs
show a clear inline message while keeping the lookup window open.
There is no competing global keyboard hook or daemon.

## Storage, recovery and troubleshooting

Registry: `$XDG_DATA_HOME/docidentity/registry.sqlite3`; extension warnings/errors:
`$XDG_DATA_HOME/docidentity/extension.log`. `DOCIDENTITY_DATA_HOME` overrides the
whole data directory, particularly for tests. Directory creation uses mode 0700.
No cache/config files are needed. SQLite uses WAL, FULL synchronous writes,
foreign keys, a busy timeout, versioned migration and serialized thread access.
Back up SQLite with `docidentity backup`, not by copying its open database alone.

ODF custom properties: `DocIdentity.ID`, `RegisteredURI`, `Schema`, `Created`,
`Parent`, and `RecoveryEdges`. RecoveryEdges retains explicit unsynchronized
lineage across consecutive successful saves while SQLite is unavailable. Parent is deliberately retained after saving: if the file save
succeeds but SQLite fails, opening/reconciling the file can recreate the identity
and its pending ancestry edges. This cannot recover a whole lost registry's earlier
history or locations. Keep registry backups. SQLite corruption is reported;
it is never silently overwritten. Restore a backup or choose a separate new
registry (`--database FILE`), then reconcile saved documents.

Hashes use version `odf-v1`: canonical content/styles XML and remaining resources,
excluding metadata, settings, thumbnails, manifest, managed barcode frames,
their embedded image and styles used exclusively by those frames. It is a
conservative structural normalization, not a proof of semantic equivalence.
LibreOffice may rename generated styles, rewrite formulas or reorder structures
between releases; these can produce diagnostics for visually unchanged files.
User metadata is excluded with meta.xml. Full-file SHA-256 is recorded separately.
Neither hash is the identity or proof of ancestry. A mismatch records a warning
and diagnostic event, never an automatic fork. Use Reconcile to make the choice.

Reconciliation checks local paths on open/save or explicit CLI invocation.
Confirmed save/register events are distinguished from observed discoveries and
inferred copies/moves/renames. A missing old path alone never proves a move.
Matching inode/device plus normalized hash allows an explicitly **inferred**
move/rename event; all old locations remain. No inode is used as an identity.
The embedded RegisteredURI may still refer to the pre-Save-As path because UNO
announces the new URL only after saving; SQLite records the actual saved path,
and the next open reconciles this safely without assigning a new ID.

Read-only files must first be saved to an editable ODF copy. Unsupported formats
must be converted explicitly to ODT/ODS/ODP. Digital signatures can be invalidated
by any edit; the extension does not preserve signatures. Remote document URLs
are not supported; choose a local file.

An extension callback cannot veto all saves through UNO document-event listeners.
If barcode/metadata updating fails, errors are logged and the post-save callback
verifies that the saved ID matches the in-memory ID before committing. Repair
and save again; inspect the log if a saved document's tracking looks wrong.
Forced process termination before a successful save never commits provisional
lineage. Concurrent editing of the same path is outside supported operation;
LibreOffice's lock must be respected. External editors that do not run this
extension can change content while retaining an embedded ID; hash warnings and
explicit reconciliation handle that case.

For missing menu: fully restart LibreOffice; check `unopkg list` and the log.
For `No module named uno`: use Arch's `/usr/bin/python` paired with installed
LibreOffice; a private venv may lack UNO. For `NoConnectException`: ensure
LibreOffice starts and the CLI uses the right pipe/executable. Avoid running
headless tests inside restrictive sandboxes that block LibreOffice IPC.
For invisible Calc barcode: check print ranges; a custom range may exclude the
area below used cells. Enlarge the print range or reposition within a free
printed area before export. Verify the exported PDF before printing.

## Tests and verification

```sh
python -m unittest discover -s tests -p test_core.py -v
python scripts/test.py
xvfb-run -a -s '-screen 0 1280x900x24' python scripts/test_extension.py
xvfb-run -a -s '-screen 0 1280x900x24' python scripts/test_gui.py
```

The test runner launches **actual installed LibreOffice** in a disposable profile.
The OXT test installs the package into another disposable profile and exercises
its real Python component loader, automatic startup attachment, edit detection
and save callbacks. It does not rely on mocked UNO objects. Test document
registries are isolated and disposable. `dist/qa/*.png` are page renders retained
for inspection; all temporary ODF/PDF test files are removed afterwards.
Tests decode the exact `@$` payload using zbar from rendered PDF pages for all
three applications. This verifies rendering and machine decoding, not a physical
laser scanner/printer combination; physical scanning still needs a printed test.
See `docs/ARCHITECTURE.md` and `docs/VERIFICATION.md` for design and measured status.
