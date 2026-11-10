"""Real Qt widgets and signals; intercept external launches, never user files."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PyQt6.QtCore import QTimer,Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from docidentity.core import Registry,new_id
from docidentity.gui import LookupWindow
with tempfile.TemporaryDirectory(prefix='identity-qt-') as temp:
    directory=Path(temp);registry=Registry(directory/'db')
    parent,child=new_id(),new_id();one=directory/'Document.fixture';two=directory/'Copy.fixture'
    one.touch();two.touch()
    registry.commit(parent,two);registry.commit(parent,one);registry.commit(child,one,parent=parent,event='MODIFIED')
    app=QApplication(['docidentity-test']);window=LookupWindow(registry,parent);errors=[]
    def inspect():
        try:
            assert window.locations.rowCount()==2 and not opener.called
            # Select the available current copy even when a historical path is newer.
            assert window.selected()['path']==str(two) and window.open_file.isEnabled()
            assert window.document_name.text()==two.name
            window.open_folder.click()
            assert opener.call_args.args[0].toLocalFile()==str(directory)
            QTest.keyClick(window,Qt.Key.Key_O,Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            assert opener.call_args.args[0].toLocalFile()==str(directory)
            QTest.keyClick(window,Qt.Key.Key_O,Qt.KeyboardModifier.ControlModifier)
            assert opener.call_args.args[0].toLocalFile()==str(two)
            window.copy_path.click();assert app.clipboard().text()==str(two)
            window.search.setText('unsubmitted search');window.copy.click()
            assert app.clipboard().text()==parent
            window.locations.itemActivated.emit(window.locations.item(0,0))
            assert opener.call_args.args[0].toLocalFile()==str(two)
            window.locations.selectRow(1);assert not window.open_file.isEnabled()
            before=opener.call_count
            window.locations.itemActivated.emit(window.locations.item(1,0))
            assert opener.call_count==before and window.open_folder.isEnabled()
            window.lineage.itemActivated.emit(window.lineage.topLevelItem(0),0)
            assert window.search.text()==child and window.open_file.isEnabled()
            with patch('docidentity.gui.QMessageBox.warning') as warning:
                opener.return_value=False;window.open_file.click();warning.assert_called_once()
            opener.return_value=True
            # Refresh availability, retain folder access when only the file is missing.
            one.unlink();window.load()
            assert not window.open_file.isEnabled() and window.open_folder.isEnabled()
            assert 'missing' in window.selection_hint.text().lower()
            one.touch();window.load()
            image=Path('dist/qa/lookup.png');image.parent.mkdir(parents=True,exist_ok=True)
            assert window.grab().save(str(image))
            window.resize(720,540);app.processEvents()
            assert window.open_file.isVisible() and window.open_folder.isVisible()
            assert window.grab().save('dist/qa/lookup-small.png')
            window.search.setText(new_id());window.load()
            assert 'not in the local registry' in window.summary.text()
            assert not window.open_file.isEnabled() and not window.copy.isEnabled()
            window.search.clear();window.load()
            assert 'Scan a barcode' in window.summary.text() and not window.open_folder.isEnabled()
            assert window.grab().save('dist/qa/lookup-empty.png')
            window.search.setText('invalid');window.load();assert not window.copy_path.isEnabled()
        except Exception as exc:errors.append(exc)
        finally:window.close();app.quit()
    with patch('docidentity.gui.QDesktopServices.openUrl',return_value=True) as opener:
        window.show();QTimer.singleShot(100,inspect);app.exec()
    registry.close()
    if errors:raise errors[0]
    print('PASS: automatic selection, opening, historical guard, clipboard, launch errors, missing paths, lineage, empty/error states and compact layout')
