"""Native Qt desktop lookup. No global input listener and no implicit file open."""
from pathlib import Path
import subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon,QFont,QKeySequence,QShortcut
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QLineEdit,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,
    QAbstractItemView,QTabWidget,QTreeWidget,QTreeWidgetItem,QSplitter,QMessageBox)

ROLE=Qt.ItemDataRole.UserRole

def date(value):
    from datetime import datetime
    try:return datetime.fromisoformat(value).astimezone().strftime('%d %b %Y, %H:%M')
    except (ValueError,TypeError):return value or '—'

def table(headers):
    widget=QTableWidget(0,len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide();widget.setShowGrid(False)
    widget.setAlternatingRowColors(True);widget.setWordWrap(False)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget

class LookupWindow(QMainWindow):
    def __init__(self,registry,identity):
        super().__init__();self.registry=registry;self.info=None
        self.setWindowTitle('Document Identity');self.setWindowIcon(QIcon.fromTheme('document-properties'))
        self.resize(1080,780);self.setMinimumSize(720,540)
        body=QWidget();self.setCentralWidget(body);layout=QVBoxLayout(body)
        layout.setContentsMargins(24,20,24,16);layout.setSpacing(14)
        top=QHBoxLayout();heading=QLabel('Document lookup')
        font=heading.font();font.setPointSize(font.pointSize()+6);font.setWeight(QFont.Weight.DemiBold);heading.setFont(font)
        top.addWidget(heading);top.addStretch()
        self.copy=QPushButton(QIcon.fromTheme('edit-copy'),'Copy ID');self.copy.clicked.connect(lambda:QApplication.clipboard().setText(self.search.text()))
        top.addWidget(self.copy);layout.addLayout(top)
        searchrow=QHBoxLayout();self.search=QLineEdit(identity)
        self.search.setPlaceholderText('Scan or paste a document ID  ·  @$…');self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Document identifier');self.search.returnPressed.connect(self.load)
        searchrow.addWidget(self.search)
        self.lookup=QPushButton(QIcon.fromTheme('edit-find'),'Look up');self.lookup.setDefault(True);self.lookup.clicked.connect(self.load)
        searchrow.addWidget(self.lookup);layout.addLayout(searchrow)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        splitter=QSplitter(Qt.Orientation.Vertical);layout.addWidget(splitter,1)
        locations=QWidget();locations_layout=QVBoxLayout(locations);locations_layout.setContentsMargins(0,0,0,0)
        label=QLabel('Known locations');font=label.font();font.setBold(True);label.setFont(font);locations_layout.addWidget(label)
        self.locations=table(['File','Availability','Identity at path','Folder'])
        self.locations.itemSelectionChanged.connect(self.update_actions);locations_layout.addWidget(self.locations)
        actions=QHBoxLayout()
        self.open_file=QPushButton(QIcon.fromTheme('document-open'),'Open file');self.open_file.clicked.connect(lambda:self.open_selected(False))
        self.open_folder=QPushButton(QIcon.fromTheme('folder-open'),'Show in folder');self.open_folder.clicked.connect(lambda:self.open_selected(True))
        actions.addWidget(self.open_file);actions.addWidget(self.open_folder);actions.addStretch()
        self.selection_hint=QLabel('Select a location to open it');self.selection_hint.setWordWrap(True);self.selection_hint.setMaximumWidth(440);actions.addWidget(self.selection_hint)
        locations_layout.addLayout(actions);splitter.addWidget(locations)
        self.tabs=QTabWidget();splitter.addWidget(self.tabs);splitter.setSizes([270,320])
        self.history=table(['When','Event','Evidence','Location','Details']);self.tabs.addTab(self.history,'History')
        self.lineage=QTreeWidget();self.lineage.setHeaderLabels(['Relationship','Document ID']);self.lineage.header().setStretchLastSection(True)
        self.lineage.itemActivated.connect(self.navigate);self.tabs.addTab(self.lineage,'Lineage')
        self.hashes=table(['When','Algorithm','Content hash','File hash']);self.tabs.addTab(self.hashes,'Hashes')
        self.warnings=table(['When','Warning','Status','Details']);self.tabs.addTab(self.warnings,'Warnings')
        self.statusBar().showMessage('Scanning opens this window. Files open only when you choose Open file.')
        self.refresh_shortcut=QShortcut(QKeySequence.StandardKey.Refresh,self);self.refresh_shortcut.activated.connect(self.load)
        self.load()

    def rows(self,widget,rows):
        widget.setRowCount(0)
        for row in rows:
            n=widget.rowCount();widget.insertRow(n)
            for col,value in enumerate(row):
                item=QTableWidgetItem(str(value or '—'));item.setToolTip(str(value or '—'));widget.setItem(n,col,item)

    def load(self):
        from .core import validate
        for widget in (self.locations,self.history,self.hashes,self.warnings):widget.setRowCount(0)
        self.lineage.clear();self.info=None;self.update_actions()
        try:self.info=self.registry.info(validate(self.search.text().strip()))
        except KeyError:
            self.summary.setText('This document is not in the local registry. Open its digital file in LibreOffice to reconcile or register it.')
            self.statusBar().showMessage('No local record found');return
        except Exception as exc:
            self.summary.setText(str(exc));self.statusBar().showMessage('Lookup could not be completed');return
        info=self.info;self.search.setText(info['id'])
        count=len(info['locations']);unresolved=sum(not x['resolved'] for x in info['warnings'])
        self.summary.setText(f"{count} known location{'s' if count!=1 else ''}  ·  Created {date(info['created'])}  ·  Last saved {date(info['modified'])}"+(f'  ·  {unresolved} warning(s)' if unresolved else ''))
        self.rows(self.locations,[(Path(x['path']).name,'Available' if x['available'] else 'Missing / inaccessible','Current' if x['current_at_path'] else 'Historical',str(Path(x['path']).parent)) for x in info['locations']])
        for n,loc in enumerate(info['locations']):
            self.locations.item(n,0).setData(ROLE,loc);self.locations.item(n,0).setToolTip(loc['path'])
            self.locations.item(n,0).setIcon(QIcon.fromTheme('document-open' if loc['available'] else 'dialog-warning'))
        self.rows(self.history,[(date(e['created']),e['type'].replace('_',' ').title(),e['certainty'].title(),e['path'],e['detail']) for e in info['events']])
        for rel,label in (('parents','Parent'),('children','Child')):
            for record in info[rel]:
                item=QTreeWidgetItem([label,record['id']]);item.setData(0,ROLE,record['id']);self.lineage.addTopLevelItem(item)
        if not self.lineage.topLevelItemCount():self.lineage.addTopLevelItem(QTreeWidgetItem(['No recorded ancestry','']))
        self.rows(self.hashes,[(date(h['created']),h['algorithm'],h['normalized'],h['full_hash']) for h in info['hashes']])
        self.rows(self.warnings,[(date(w['created']),w['code'].replace('_',' ').title(),'Resolved' if w['resolved'] else 'Needs review',w['detail']) for w in info['warnings']])
        self.tabs.setTabText(3,f'Warnings ({unresolved})' if unresolved else 'Warnings')
        self.statusBar().showMessage('Double-click an identity in Lineage to navigate. F5 refreshes this record.')
        self.update_actions()

    def selected(self):
        row=self.locations.currentRow()
        return self.locations.item(row,0).data(ROLE) if row>=0 and self.locations.item(row,0) else None

    def update_actions(self):
        loc=self.selected();self.open_folder.setEnabled(bool(loc))
        self.open_file.setEnabled(bool(loc and loc['available'] and loc['current_at_path']))
        self.selection_hint.setText('Historical path: the file now has another known identity' if loc and not loc['current_at_path'] else ('Select a location to open it' if not loc else ''))

    def open_selected(self,directory):
        loc=self.selected()
        if not loc:return
        if not directory and (not loc['available'] or not loc['current_at_path']):return
        path=Path(loc['path']);target=path.parent if directory else path
        if not target.exists():QMessageBox.warning(self,'Location unavailable','This location is no longer available.');return
        subprocess.Popen(['xdg-open',str(target)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def navigate(self,item,column=0):
        identity=item.data(0,ROLE)
        if identity:self.search.setText(identity);self.load()

def show(registry,identity):
    app=QApplication.instance() or QApplication(['docidentity'])
    app.setApplicationName('Document Identity');app.setOrganizationName('DocIdentity')
    window=LookupWindow(registry,identity);window.show();window.raise_();window.activateWindow()
    return app.exec()
