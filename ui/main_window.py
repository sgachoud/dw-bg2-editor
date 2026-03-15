"""
Main window for the BG2 Schematic Editor.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QStandardItemModel, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from schematic import Schematic

_UNDO_LIMIT = 50


# ---------------------------------------------------------------------------
# Block list model
# ---------------------------------------------------------------------------

class BlockModel(QStandardItemModel):
    COL_NAME = 0
    COL_COUNT = 1

    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Block ID", "Count"])

    def load_counts(self, counts: dict[str, int]):
        self.removeRows(0, self.rowCount())
        for name, count in counts.items():
            name_item = QStandardItem(name)
            name_item.setEditable(False)
            count_item = QStandardItem()
            count_item.setData(count, Qt.DisplayRole)
            count_item.setEditable(False)
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.appendRow([name_item, count_item])


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.schematic: Schematic | None = None
        self._dirty = False

        # undo/redo stacks: each entry is (description: str, snapshot: dict)
        self._undo_stack: list[tuple[str, dict]] = []
        self._redo_stack: list[tuple[str, dict]] = []

        self.setWindowTitle("BG2 Schematic Editor")
        self.resize(900, 600)

        self._build_menu()
        self._build_ui()
        self._build_status_bar()
        self._refresh_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")

        open_act = QAction("&Open…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._on_open)
        file_menu.addAction(open_act)

        self.save_act = QAction("&Save", self)
        self.save_act.setShortcut(QKeySequence.StandardKey.Save)
        self.save_act.triggered.connect(self._on_save)
        file_menu.addAction(self.save_act)

        self.save_as_act = QAction("Save &As…", self)
        self.save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_act.triggered.connect(self._on_save_as)
        file_menu.addAction(self.save_as_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        edit_menu = menu.addMenu("&Edit")

        self.undo_act = QAction("&Undo\tCtrl+Z", self)
        self.undo_act.triggered.connect(self._on_undo)
        edit_menu.addAction(self.undo_act)

        self.redo_act = QAction("&Redo\tCtrl+Y", self)
        self.redo_act.triggered.connect(self._on_redo)
        edit_menu.addAction(self.redo_act)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # --- file info bar ---
        self.file_label = QLabel("No file loaded.")
        self.file_label.setStyleSheet("color: gray;")
        root.addWidget(self.file_label)

        # --- splitter ---
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # Left: block list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter blocks…")
        self.search_edit.textChanged.connect(self._on_filter_changed)
        left_layout.addWidget(self.search_edit)

        self.block_model = BlockModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.block_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(BlockModel.COL_NAME)
        self.proxy_model.setSortRole(Qt.DisplayRole)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            BlockModel.COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            BlockModel.COL_COUNT, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # All three shortcuts fire only when the table has focus,
        # so QLineEdit keeps its own native Ctrl+Z text-undo.
        for key, slot in [
            (QKeySequence(Qt.Key.Key_Delete),          self._on_remove),
            (QKeySequence.StandardKey.Undo,            self._on_undo),
            (QKeySequence.StandardKey.Redo,            self._on_redo),
        ]:
            sc = QShortcut(QKeySequence(key), self.table)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(slot)

        left_layout.addWidget(self.table)

        splitter.addWidget(left)

        # Right: operations panel
        right = QWidget()
        right.setFixedWidth(280)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        # Info group
        info_group = QGroupBox("Selected Block")
        info_layout = QVBoxLayout(info_group)
        self.selected_label = QLabel("—")
        self.selected_label.setWordWrap(True)
        self.selected_count_label = QLabel("")
        self.selected_count_label.setStyleSheet("color: gray;")
        info_layout.addWidget(self.selected_label)
        info_layout.addWidget(self.selected_count_label)
        right_layout.addWidget(info_group)

        # Replace group
        replace_group = QGroupBox("Replace With")
        replace_layout = QVBoxLayout(replace_group)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("mod:block_name")
        self.replace_edit.returnPressed.connect(self._on_replace)
        replace_layout.addWidget(self.replace_edit)
        note = QLabel("<small>Properties (shape, axis…) are preserved.</small>")
        note.setTextFormat(Qt.RichText)
        replace_layout.addWidget(note)
        self.replace_btn = QPushButton("Apply Replace")
        self.replace_btn.clicked.connect(self._on_replace)
        replace_layout.addWidget(self.replace_btn)
        right_layout.addWidget(replace_group)

        # Remove button
        self.remove_btn = QPushButton("Remove Block (→ Air)")
        self.remove_btn.setToolTip("Replace every occurrence of this block with air  [Del]")
        self.remove_btn.clicked.connect(self._on_remove)
        right_layout.addWidget(self.remove_btn)

        right_layout.addStretch()

        # Schematic summary
        summary_group = QGroupBox("Schematic Info")
        summary_layout = QFormLayout(summary_group)
        self.dim_label = QLabel("—")
        self.total_label = QLabel("—")
        self.unique_label = QLabel("—")
        summary_layout.addRow("Dimensions:", self.dim_label)
        summary_layout.addRow("Total blocks:", self.total_label)
        summary_layout.addRow("Unique types:", self.unique_label)
        right_layout.addWidget(summary_group)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _refresh_ui(self):
        has_file = self.schematic is not None
        self.save_act.setEnabled(has_file)
        self.save_as_act.setEnabled(has_file)
        self.replace_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)

        can_undo = has_file and bool(self._undo_stack)
        can_redo = has_file and bool(self._redo_stack)
        self.undo_act.setEnabled(can_undo)
        self.redo_act.setEnabled(can_redo)
        self.undo_act.setText(
            f"&Undo  {self._undo_stack[-1][0]}" if can_undo else "&Undo"
        )
        self.redo_act.setText(
            f"&Redo  {self._redo_stack[-1][0]}" if can_redo else "&Redo"
        )

        if not has_file:
            self.file_label.setText("No file loaded.")
            self.file_label.setStyleSheet("color: gray;")
            self.block_model.load_counts({})
            self.dim_label.setText("—")
            self.total_label.setText("—")
            self.unique_label.setText("—")
            return

        s = self.schematic
        fname = os.path.basename(s.path) if s.path else "untitled"
        dirty_marker = " *" if self._dirty else ""
        self.file_label.setText(f"File: <b>{fname}</b>{dirty_marker}  |  {s.path}")
        self.file_label.setStyleSheet("")

        counts = s.get_block_counts()
        self.block_model.load_counts(counts)
        self.table.sortByColumn(BlockModel.COL_COUNT, Qt.DescendingOrder)

        dims = s.dimensions
        self.dim_label.setText(f"{dims[0]} × {dims[1]} × {dims[2]}")
        total = sum(counts.values())
        self.total_label.setText(f"{total:,}")
        self.unique_label.setText(str(len(counts)))

        self.selected_label.setText("—")
        self.selected_count_label.setText("")

    def _selected_block_name(self) -> str | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        src_idx = self.proxy_model.mapToSource(indexes[0])
        item = self.block_model.item(src_idx.row(), BlockModel.COL_NAME)
        return item.text() if item else None

    def _mark_dirty(self):
        self._dirty = True
        self._refresh_ui()

    # ------------------------------------------------------------------
    # Undo / redo helpers
    # ------------------------------------------------------------------

    def _push_undo(self, description: str):
        """Snapshot current schematic state onto the undo stack."""
        snap = self.schematic.snapshot()
        self._undo_stack.append((description, snap))
        if len(self._undo_stack) > _UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _on_undo(self):
        if not self.schematic or not self._undo_stack:
            return
        desc, before_snap = self._undo_stack.pop()
        after_snap = self.schematic.snapshot()
        self._redo_stack.append((desc, after_snap))
        self.schematic.restore(before_snap)
        self._dirty = True
        self._refresh_ui()
        self.status_bar.showMessage(f"Undid: {desc}", 3000)

    def _on_redo(self):
        if not self.schematic or not self._redo_stack:
            return
        desc, after_snap = self._redo_stack.pop()
        before_snap = self.schematic.snapshot()
        self._undo_stack.append((desc, before_snap))
        self.schematic.restore(after_snap)
        self._dirty = True
        self._refresh_ui()
        self.status_bar.showMessage(f"Redid: {desc}", 3000)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BG2 Schematic", "", "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            self.schematic = Schematic.load(path)
            self._dirty = False
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._refresh_ui()
            self.status_bar.showMessage(f"Loaded: {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _on_save(self):
        if not self.schematic:
            return
        if not self.schematic.path:
            self._on_save_as()
            return
        try:
            self.schematic.save(self.schematic.path)
            self._dirty = False
            self._refresh_ui()
            self.status_bar.showMessage("Saved.", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _on_save_as(self):
        if not self.schematic:
            return
        default = self.schematic.path or ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save BG2 Schematic", default, "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            self.schematic.save(path)
            self._dirty = False
            self._refresh_ui()
            self.status_bar.showMessage(f"Saved to: {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _on_selection_changed(self):
        name = self._selected_block_name()
        if name and self.schematic:
            counts = self.schematic.get_block_counts()
            count = counts.get(name, 0)
            self.selected_label.setText(name)
            self.selected_count_label.setText(f"{count:,} block(s)")
            self.replace_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
        else:
            self.selected_label.setText("—")
            self.selected_count_label.setText("")
            self.replace_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)

    def _on_filter_changed(self, text: str):
        self.proxy_model.setFilterFixedString(text)

    def _on_replace(self):
        name = self._selected_block_name()
        if not name or not self.schematic:
            return

        new_name = self.replace_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Replace", "Please enter a new block ID.")
            return

        if ':' not in new_name:
            QMessageBox.warning(
                self, "Replace",
                "Block ID must include a namespace (e.g. minecraft:stone)."
            )
            return

        if new_name == name:
            self.status_bar.showMessage("Old and new names are identical – nothing to do.", 3000)
            return

        self._push_undo(f"Replace '{name}'")
        self.schematic.replace_block(name, new_name)
        self.replace_edit.clear()
        self._mark_dirty()
        self.status_bar.showMessage(f"Replaced '{name}' → '{new_name}'.", 4000)

    def _on_remove(self):
        name = self._selected_block_name()
        if not name or not self.schematic:
            return

        counts = self.schematic.get_block_counts()
        count = counts.get(name, 0)

        reply = QMessageBox.question(
            self,
            "Remove Block",
            f"Remove all {count:,} occurrence(s) of\n'{name}'\nand replace with air?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._push_undo(f"Remove '{name}'")
        self.schematic.remove_block(name)
        self._mark_dirty()
        self.status_bar.showMessage(f"Removed '{name}' ({count:,} blocks → air).", 4000)

    # ------------------------------------------------------------------
    # Close guard
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Quit anyway?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Save:
                self._on_save()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
