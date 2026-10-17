"""Real Qt widgets and signals, with external file launches intercepted."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from docidentity.core import Registry,new_id
from docidentity.gui import LookupWindow
with tempfile.TemporaryDirectory(prefix='identity-qt-') as temp:
    directory=Path(temp);registry=Registry(directory/'db')
    parent,child=new_id(),new_id();one=directory/'Document.odt';two=directory/'Copy.odt'
    # No document artifacts generated: empty files are availability-only fixtures.
    one.touch();two.touch()
    # Non-ODF extensions keep these fixtures outside ODF parsing.
    one=one.rename(one.with_suffix('.fixture'));two=two.rename(two.with_suffix('.fixture'))
    registry.commit(parent,one);registry.commit(parent,two);registry.commit(child,one,parent=parent,event='MODIFIED')
    app=QApplication(['docidentity-test']);window=LookupWindow(registry,parent);errors=[]
    def inspect():
        try:
            assert window.locations.rowCount()==2
            assert not opener.called
            window.locations.selectRow(0)
            assert window.open_folder.isEnabled()
            # Historical rows cannot accidentally open the newer document.
            for row in range(2):
                window.locations.selectRow(row)
                loc=window.selected()
                if not loc['current_at_path']:assert not window.open_file.isEnabled()
            image=Path('dist/qa/lookup.png');image.parent.mkdir(exist_ok=True)
            assert window.grab().save(str(image))
            window.lineage.itemActivated.emit(window.lineage.topLevelItem(0),0)
            assert window.search.text()==child and window.locations.rowCount()==1
            window.locations.selectRow(0);window.open_file.click()
            opener.assert_called_once();assert opener.call_args.args[0]==['xdg-open',str(one)]
            window.search.setText(new_id());window.load()
            assert 'not in the local registry' in window.summary.text()
            assert not window.open_file.isEnabled()
        except Exception as exc:errors.append(exc)
        finally:window.close();app.quit()
    with patch('docidentity.gui.subprocess.Popen') as opener:
        window.show();QTimer.singleShot(500,inspect);app.exec()
    registry.close()
    if errors:raise errors[0]
    print('PASS: native Qt lookup, paths, history tabs, lineage, explicit opening, unknown-ID state')
