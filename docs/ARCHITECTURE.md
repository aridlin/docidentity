# Architecture and operational boundaries

- `docidentity/core.py`: IDs, sessions, XDG paths, version-1 SQLite migration,
  transactions, structured observations, conservative reconciliation, ODF hashes.
- `docidentity/barcode.py`: dependency-free subset-B Code 128 encoder and grayscale
  PNG generation with UNO byte-stream import. Complete 34-character payload, modulo-103 checksum, stop pattern,
  ten-module quiet zones. The 110 x 14 mm UNO graphic has approximately 0.256 mm
  modules and high-resolution raster bars. No barcode font dependency.
- `docidentity/office.py`: Writer page-anchored TextGraphicObject, Calc sheet
  GraphicObjectShape below used cells, Impress first-page GraphicObjectShape
  with collision checks. Controller coordinates listeners and suppression.
- `extension/Identity.py`: Python UNO XJob/XJobExecutor and global document listener,
  startup hooks, automatic new-document registration, accessible menu, position dialog and reconciliation choice.
- `extension/*.xcu`: startup job registration and the six menu actions.
- `docidentity/cli.py`, `gui.py`: reusable generator entry points, explicit lookup,
  native Qt location/history/lineage navigation; `xdg-open` only on button activation.
- `scripts/build.py`, `install.py`: deterministic file ordering in OXT packaging
  and user-only installation, plus optional global Codex generation policy.
- `tests/`: pure registry/state tests and real LibreOffice integration tests.

## State machine

New untitled document (including Ctrl+N) -> automatic provisional registration.
Existing unregistered file -> explicit provisional registration -> successful save -> clean ID A.
First user model modification -> provisional B, parent A -> more edits/undo keep B.
Successful save -> commit B + A->B in one SQLite transaction -> clean B.
Cancelled/failed save -> keep provisional B for retry. Discard/close -> no commit.
Unchanged Save As -> same ID, new observed location, confirmed SAVE_AS event.
Barcode and metadata actions execute under a reentrant suppression guard.
Save-time modification notifications are separately suppressed for the entire
OnSave/OnSaveAs through Done/Failed interval. isModified=false notifications
never create identities. Navigation/selection does not modify the UNO model.

The file and SQLite cannot share an atomic transaction. Store recovery identity, pending ancestry edges
and Parent in the ODF before saving; commit DB only after save success and a
saved embedded-ID check. Recovery uses the persisted Parent on next open. The
old path's file content is not backed up, and no filesystem event is fabricated.

SQLite connections accept UNO callbacks on different threads and all registry
methods serialize access with a reentrant lock. Different processes coordinate
through SQLite WAL/locking. A connection-per-document avoids a daemon.
Only local file URLs are supported. There is no network transmission.

## UNO integration risks addressed and remaining limits

Modification notifications have no reliable distinction between user formatting
and other user edits. The chosen policy counts every user model modification;
only extension operations and save internals are suppressed. Programmatic edits
by another extension count too. Direct user dragging of the barcode is also a
model modification; tracking-only placement uses the provided coordinate dialog.

Page anchoring differs between applications; a shared drawing implementation is
not used for Writer. Writer reserves margin space and can reflow the document;
existing headers/anchored user shapes still require review. Calc barcode shapes
below used data may lie outside a user's explicit print range. Impress refuses
to overwrite occupied corners. There is no arbitrary automatic layout engine.

UNO document event listeners cannot atomically veto all storage requests or make
a cross-resource file/SQLite transaction. Post-save validation and persisted
ancestry are the recovery boundary. A malformed/corrupt embedded ID is reported
rather than silently adopted. Version-1 schema is created transactionally; unknown
future schemas are refused rather than downgraded. No content snapshots are stored.

Known paths are historical observations, not guarantees that a path still contains
that identity: the GUI marks its latest observed identity and live availability.
It does not open files to verify every hash automatically. A copy can only be
identified conservatively by embedded ID and supporting hashes; an offline edit
with the same metadata needs a user's reconciliation decision.

`integration/scanner_adapter.py` extends the existing target-specific HID parser
with `@$` dispatch while retaining `@#` commands. It is deployed only with the
scanner-integration installer option; it does not create another input service.
