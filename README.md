# Document Identity and Lineage

Local-first Python UNO extension for LibreOffice on Arch Linux / KDE Plasma.
ODT, ODS and ODP files carry a random 128-bit `@$` identity, a printable Code 128
barcode on every printed page, and ODF custom properties. SQLite stores locations, lineage, observations
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
The build artifact is `dist/docidentity-0.3.0.oxt`. Alternatively install it with
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
and repeating barcodes. The registry entry is committed when you first save them as ODF.
Opening existing untracked files still leaves registration under your control.

The **Document Identity** menu offers:

1. **Register Document**: add barcode and custom properties; save a named ODF file
   to commit. New untitled documents remain provisional until saved as ODF.
2. **Document Information**: opens the native lookup window for a saved identity,
   with document/folder opening and copy actions, locations, history and lineage.
   Unsaved identities show a short explanation to save first.
3. **Reposition Barcode**: enter horizontal/vertical coordinates in millimetres
   from the page origin (inside the print header for Calc). This operation
   preserves identity. Save afterwards to persist the position.
4. **Restore Default Barcode Position**: place the managed barcode at its default.
5. **Repair Barcode**: replace its graphic and remove reserved-name duplicates.
6. **Reconcile Document Identity**: explicitly keep the embedded identity, or
   allocate a child identity (committed only on save). Cancel changes nothing.

Registration preserves existing text, cells and user drawings. The same ID is
printed on **every page**, using an adapter suited to each application:

- **Writer:** one paragraph-anchored graphic in each active header variant (including
  first/left/right variants and follow-on page styles). The headers repeat as
  pages are added. A 22 mm top margin reserves space above existing header text.
- **Calc:** one managed background canvas per page style used by the sheets. A
  repeating print header reserves a barcode band above existing header text, so
  every printed page includes it even with explicit print ranges. Cell values,
  formulas and existing header fields are preserved. The barcode is visible in
  Print Preview/PDF; it is not a floating drawing over the editable cell grid.
  Existing non-managed header backgrounds are not overwritten; move those
  backgrounds before registration. Placement coordinates for Calc are measured
  inside the print header. The header must be at least 110 mm wide.
- **Impress:** one managed graphic on every slide, with a bottom-right default
  and a collision-checked fallback corner. New slides are reconciled during
  editing and before saving, printing or PDF export.

Repeated instances share the document's ID; they are not separate identities.
Repair removes extra copies within a header/slide without deleting legitimate
instances on other pages. The `DocIdentity.ManagedBarcode` name prefix is reserved.
Review layout after initial registration: reserving space can change pagination.
Old first-page-only layouts migrate in memory when opened, under identity-change
suppression; save to persist the upgraded layout. **Repair Barcode** also upgrades
an existing document without creating a new ID. Read-only legacy documents need
an editable ODF copy before migration.

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
docidentity                 # open the search window
docidentity lookup          # same, without a scanned ID
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
exported PDF without modifying it. Exports are registered only after every rendered
page contains the matching decodable barcode; a missing barcode on any page fails safely.

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

The lookup validates the entire ID and opens a native Qt window. A document
summary and **Open document**, **Open folder**, and **Copy path** actions sit above
the locations table; history, lineage, hashes and warnings have separate tabs.
The best available current location is selected automatically. Opening the window
or scanning a barcode never opens the document itself. Double-click a current
location to open it, or right-click for open/copy actions. Historical locations
cannot open a newer document under an old identity; their folder and path remain
accessible. Missing files have clear explanations. Desktop launch failures are
shown in a dialog instead of being silently discarded.

**Ctrl+O** opens the selected document, **Ctrl+Shift+O** opens its folder,
**Ctrl+L** focuses the search, and **F5** refreshes availability. **Copy ID** copies
the displayed record, even if another search has been typed. Double-click a parent
or child in Lineage to navigate. Unknown IDs keep the window open with a clear
message. Run `docidentity` without arguments or launch **Document Identity** from
the desktop application menu to start an empty search.
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

Hashes use version `odf-v2`: canonical content/styles XML and remaining resources,
excluding metadata, settings, thumbnails, manifest, managed barcode frames,
their embedded images/styles and explicitly owned Calc header background images.
Observations made by the old `odf-v1` normalizer are retained but are not compared
against `odf-v2` hashes as though they used the same algorithm. It is a
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
For Calc barcodes: use Print Preview to see the repeating header. If registration
reports a narrow page, enlarge the usable page/header width to at least 110 mm
or use landscape orientation. Move any existing custom header background before
registration. Verify the exported PDF before printing.

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
registries are isolated and disposable. `dist/qa/**/*.png` are page renders retained
for inspection; all temporary ODF/PDF test files are removed afterwards.
Tests decode the exact `@$` payload using zbar from rendered PDF pages for all
three applications. This verifies rendering and machine decoding, not a physical
laser scanner/printer combination; physical scanning still needs a printed test.
See `docs/ARCHITECTURE.md` and `docs/VERIFICATION.md` for design and measured status.
