"""Native Qt desktop lookup. No global input listener and no implicit file open."""
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon,QFont,QKeySequence,QShortcut,QDesktopServices
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QLineEdit,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,
    QAbstractItemView,QTabWidget,QTreeWidget,QTreeWidgetItem,QSplitter,QMessageBox,QMenu,QFrame,QSizePolicy)

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
        top=QHBoxLayout();heading=QLabel('Document Identity')
        font=heading.font();font.setPointSize(font.pointSize()+3);font.setWeight(QFont.Weight.DemiBold);heading.setFont(font)
        top.addWidget(heading);top.addStretch()
        self.copy=QPushButton(QIcon.fromTheme('edit-copy'),'Copy ID');self.copy.clicked.connect(self.copy_identity)
        self.copy.setToolTip('Copy the displayed document identity')
        top.addWidget(self.copy);layout.addLayout(top)
        searchrow=QHBoxLayout();self.search=QLineEdit(identity)
        self.search.setPlaceholderText('Scan or paste a document ID  ·  @$…');self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Document identifier');self.search.returnPressed.connect(self.load)
        searchrow.addWidget(self.search)
        self.lookup=QPushButton(QIcon.fromTheme('edit-find'),'Look up');self.lookup.setDefault(True);self.lookup.clicked.connect(self.load)
        searchrow.addWidget(self.lookup);layout.addLayout(searchrow)
        card=QFrame();card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout=QVBoxLayout(card);card_layout.setContentsMargins(16,14,16,14);card_layout.setSpacing(10)
        self.document_name=QLabel('Find a document');self.document_name.setTextFormat(Qt.TextFormat.PlainText)
        font=self.document_name.font();font.setPointSize(font.pointSize()+5);font.setWeight(QFont.Weight.DemiBold);self.document_name.setFont(font)
        self.document_name.setWordWrap(True)
        self.document_name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        card_layout.addWidget(self.document_name)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText)
        card_layout.addWidget(self.summary)
        actions=QHBoxLayout()
        self.open_file=QPushButton(QIcon.fromTheme('document-open'),'Open document');self.open_file.clicked.connect(lambda:self.open_selected(False))
        self.open_file.setToolTip('Open the selected current document (Ctrl+O)')
        self.open_folder=QPushButton(QIcon.fromTheme('folder-open'),'Open folder');self.open_folder.clicked.connect(lambda:self.open_selected(True))
        self.open_folder.setToolTip('Open the containing folder (Ctrl+Shift+O)')
        self.copy_path=QPushButton(QIcon.fromTheme('edit-copy'),'Copy path');self.copy_path.clicked.connect(self.copy_selected_path)
        for button in (self.open_file,self.open_folder,self.copy_path):
            button.setMinimumHeight(34);actions.addWidget(button)
        actions.addStretch();card_layout.addLayout(actions)
        self.selection_hint=QLabel();self.selection_hint.setWordWrap(True);self.selection_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.selection_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.selection_hint.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        card_layout.addWidget(self.selection_hint);layout.addWidget(card)
        splitter=QSplitter(Qt.Orientation.Vertical);layout.addWidget(splitter,1)
        locations=QWidget();locations_layout=QVBoxLayout(locations);locations_layout.setContentsMargins(0,0,0,0)
        label=QLabel('Locations  ·  Double-click a current file to open it')
        font=label.font();font.setBold(True);label.setFont(font);locations_layout.addWidget(label)
        self.locations=table(['File','Status','Folder'])
        self.locations.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Interactive)
        self.locations.setColumnWidth(0,260)
        self.locations.itemSelectionChanged.connect(self.update_actions)
        self.locations.itemActivated.connect(lambda *_:self.open_selected(False))
        self.locations.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.locations.customContextMenuRequested.connect(self.location_menu)
        locations_layout.addWidget(self.locations);splitter.addWidget(locations)
        self.tabs=QTabWidget();splitter.addWidget(self.tabs);splitter.setSizes([270,320])
        self.history=table(['When','Event','Evidence','Location','Details']);self.tabs.addTab(self.history,'History')
        self.lineage=QTreeWidget();self.lineage.setHeaderLabels(['Relationship','Document ID']);self.lineage.header().setStretchLastSection(True)
        self.lineage.itemActivated.connect(self.navigate);self.tabs.addTab(self.lineage,'Lineage')
        self.hashes=table(['When','Algorithm','Content hash','File hash']);self.tabs.addTab(self.hashes,'Hashes')
        self.warnings=table(['When','Warning','Status','Details']);self.tabs.addTab(self.warnings,'Warnings')
        self.statusBar().showMessage('Scanning opens this window. Files open only when you choose Open file.')
        self.refresh_shortcut=QShortcut(QKeySequence.StandardKey.Refresh,self);self.refresh_shortcut.activated.connect(self.load)
        self.open_shortcut=QShortcut(QKeySequence('Ctrl+O'),self);self.open_shortcut.activated.connect(lambda:self.open_selected(False))
        self.folder_shortcut=QShortcut(QKeySequence('Ctrl+Shift+O'),self);self.folder_shortcut.activated.connect(lambda:self.open_selected(True))
        self.search_shortcut=QShortcut(QKeySequence('Ctrl+L'),self);self.search_shortcut.activated.connect(self.focus_search)
        self.load()

    def focus_search(self):
        self.search.setFocus();self.search.selectAll()

    def copy_identity(self):
        if self.info:
            QApplication.clipboard().setText(self.info['id'])
            self.statusBar().showMessage('Document ID copied',3000)

    def copy_selected_path(self):
        loc=self.selected()
        if loc:
            QApplication.clipboard().setText(loc['path'])
            self.statusBar().showMessage('Full file path copied',3000)

    def location_menu(self,position):
        item=self.locations.itemAt(position)
        if not item:return
        self.locations.selectRow(item.row())
        menu=QMenu(self)
        for button in (self.open_file,self.open_folder,self.copy_path):
            action=menu.addAction(button.icon(),button.text())
            action.setEnabled(button.isEnabled());action.triggered.connect(button.click)
        menu.exec(self.locations.viewport().mapToGlobal(position))

    def rows(self,widget,rows):
        widget.setRowCount(0)
        for row in rows:
            n=widget.rowCount();widget.insertRow(n)
            for col,value in enumerate(row):
                item=QTableWidgetItem(str(value or '—'));item.setToolTip(str(value or '—'));widget.setItem(n,col,item)

    def load(self):
        from .core import validate
        for widget in (self.locations,self.history,self.hashes,self.warnings):widget.setRowCount(0)
        self.lineage.clear();self.info=None;self.document_name.setText('Find a document');self.update_actions()
        self.tabs.setTabText(3,'Warnings')
        if not self.search.text().strip():
            self.summary.setText('Scan a barcode or paste its @$ identifier above to find the document and its folder.')
            self.statusBar().showMessage('Ctrl+L focuses search · F5 refreshes');return
        try:self.info=self.registry.info(validate(self.search.text().strip()))
        except KeyError:
            self.document_name.setText('Document not found')
            self.summary.setText('This document is not in the local registry. Open its digital file in LibreOffice to reconcile or register it.')
            self.statusBar().showMessage('No local record found');return
        except Exception as exc:
            self.summary.setText(str(exc));self.statusBar().showMessage('Lookup could not be completed');return
        info=self.info;self.search.setText(info['id'])
        info['locations']=sorted(info['locations'],key=lambda loc:(not (loc['available'] and loc['current_at_path']),not loc['current_at_path'],not loc['available']))
        count=len(info['locations']);unresolved=sum(not x['resolved'] for x in info['warnings'])
        self.summary.setText(f"{count} known location{'s' if count!=1 else ''}  ·  Created {date(info['created'])}  ·  Last saved {date(info['modified'])}"+(f'  ·  {unresolved} warning(s)' if unresolved else ''))
        self.rows(self.locations,[(Path(x['path']).name,('Current' if x['current_at_path'] else 'Historical')+(' · Missing' if not x['available'] else ''),str(Path(x['path']).parent)) for x in info['locations']])
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
        if self.locations.rowCount():self.locations.selectRow(0)
        else:self.document_name.setText('No known file location')
        self.statusBar().showMessage('Ctrl+O opens document · Ctrl+Shift+O opens folder · Ctrl+L searches · F5 refreshes')
        self.update_actions()

    def selected(self):
        row=self.locations.currentRow()
        return self.locations.item(row,0).data(ROLE) if row>=0 and self.locations.item(row,0) else None

    def update_actions(self):
        loc=self.selected();folder=Path(loc['path']).parent if loc else None
        self.copy.setEnabled(bool(self.info));self.copy_path.setEnabled(bool(loc))
        self.open_folder.setEnabled(bool(folder and folder.is_dir()))
        self.open_file.setEnabled(bool(loc and loc['available'] and loc['current_at_path']))
        if loc:
            self.document_name.setText(Path(loc['path']).name)
            if not loc['current_at_path']:
                hint='Historical location: a newer identity was recorded here. Open its folder to locate the current file.'
            elif not loc['available']:
                hint='File missing or inaccessible. You can still copy its path or open its folder if it exists.'
            else:hint=loc['path']
        else:hint='Select a location below.' if self.info and self.info['locations'] else ''
        self.selection_hint.setText(hint)

    def open_selected(self,directory):
        loc=self.selected()
        if not loc:return
        if not directory and (not loc['available'] or not loc['current_at_path']):return
        path=Path(loc['path']);target=path.parent if directory else path
        if not (target.is_dir() if directory else target.is_file()):
            QMessageBox.warning(self,'Location unavailable',f'This location is no longer available:\n{target}')
            self.load();return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            QMessageBox.warning(self,'Could not open location',f'The desktop could not open:\n{target}\nCheck the default application for this file type.' )
            return
        self.statusBar().showMessage(('Opened folder: ' if directory else 'Opened document: ')+str(target),5000)

    def navigate(self,item,column=0):
        identity=item.data(0,ROLE)
        if identity:self.search.setText(identity);self.load()

def show(registry,identity):
    app=QApplication.instance() or QApplication(['docidentity'])
    app.setApplicationName('Document Identity');app.setOrganizationName('DocIdentity')
    window=LookupWindow(registry,identity);window.show();window.raise_();window.activateWindow()
    return app.exec()
