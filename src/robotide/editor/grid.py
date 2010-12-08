#  Copyright 2008-2009 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from wx import grid

from robotide.widgets import PopupCreator, PopupMenuItems
from robotide.context import IS_WINDOWS
from clipboard import ClipboardHandler


class GridEditor(grid.Grid):
    _col_add_threshold = 1
    _popup_items = ['Insert Cells', 'Delete Cells',
                    '---', 'Select All\tCtrl-A',
                    '---', 'Cut\tCtrl-X', 'Copy\tCtrl-C', 'Paste\tCtrl-V',
                    '---', 'Delete\tDel']

    def __init__(self, parent, num_rows, num_cols, popup_creator=None):
        grid.Grid.__init__(self, parent)
        self._bind_to_events()
        self.selection = _GridSelection(self)
        self.SetDefaultRenderer(grid.GridCellAutoWrapStringRenderer())
        self._clipboard_handler = ClipboardHandler(self)
        self._history = _GridState()
        self.CreateGrid(num_rows, num_cols)
        self._popup_creator = popup_creator or PopupCreator()

    def register_context_menu_hook(self, callable):
        self._popup_creator.add_hook(callable)

    def unregister_context_menu_hook(self, callable):
        self._popup_creator.remove_hook(callable)

    def _bind_to_events(self):
        self.Bind(grid.EVT_GRID_SELECT_CELL, self.OnSelectCell)
        self.Bind(grid.EVT_GRID_RANGE_SELECT, self.OnRangeSelect)
        self.Bind(grid.EVT_GRID_CELL_RIGHT_CLICK, self.OnCellRightClick)

    def write_cell(self, row, col, value, update_history=True):
        if update_history:
            self._update_history()
        self._expand_if_necessary(row, col)
        self.SetCellValue(row, col, value)

    def _expand_if_necessary(self, row, col):
        while row >= self.NumberRows - 1:
            self.AppendRows(1)
        while col >= self.NumberCols - self._col_add_threshold:
            self.AppendCols(1)

    def set_dirty(self):
        pass

    def _update_history(self):
        self._history.change(self._get_block_content(range(self.NumberRows),
                                                     range(self.NumberCols)))

    def select(self, row, column):
        self.SelectBlock(row, column, row, column)
        self.SetGridCursor(row, column)
        self.MakeCellVisible(row, column)

    def copy(self):
        self._clipboard_handler.copy()

    def cut(self):
        self._update_history()
        self._clipboard_handler.cut()
        self._clear_selected_cells()

    def _clear_selected_cells(self):
        for row, col in self.selection.cells():
            self.write_cell(row, col, '', update_history=False)

    def paste(self):
        self._update_history()
        self._clipboard_handler.paste()

    def delete(self):
        self._update_history()
        if self.IsCellEditControlShown():
            if IS_WINDOWS:
                self._delete_from_cell_editor()
        else:
            self._clear_selected_cells()

    def _delete_from_cell_editor(self):
        editor = self.get_cell_edit_control()
        start, end = editor.Selection
        if start == end:
            end += 1
        editor.Remove(start, end)

    def _is_whole_row_selection(self):
        return self.SelectedRows

    def get_cell_edit_control(self):
        return self.GetCellEditor(*self.selection.cell).GetControl()

    def get_selected_content(self):
        return self._get_block_content(self.selection.rows(),
                                       self.selection.cols())

    def _current_cell_value(self):
        return self.GetCellValue(*self.selection.cell)

    def _get_block_content(self, row_range, col_range):
        return [[self.GetCellValue(row, col) for col in col_range]
                 for row in row_range]

    def _strip_trailing_empty_cells(self, rowdata):
        while rowdata and not rowdata[-1]:
            rowdata.pop()
        return rowdata

    def undo(self):
        prev_data = self._history.back()
        if prev_data:
            self.ClearGrid()
            self._write_data(prev_data, update_history=False)

    def _write_data(self, data, update_history=True):
        for row_index, row_data in enumerate(data):
            for col_index, cell_value in enumerate(row_data):
                self.write_cell(row_index, col_index, cell_value, update_history)
        self.AutoSizeColumns()
        self.AutoSizeRows()

    def OnSelectCell(self, event):
        self.selection.set_from_single_selection(event)
        self.AutoSizeRows()
        event.Skip()

    def OnRangeSelect(self, event):
        if event.Selecting():
            self.selection.set_from_range_selection(self, event)
            self._ensure_selected_row_is_visible(event.BottomRow)

    def _ensure_selected_row_is_visible(self, bottom_row):
        if not self.IsVisible(bottom_row , 0) and bottom_row < self.NumberRows and self._is_whole_row_selection():
            self.MakeCellVisible(bottom_row, 0)
            self.SelectRow(bottom_row + 1, True)
            self.selection._set((self.selection.topleft.row, self.selection.topleft.col),
                                (self.selection.bottomright.row + 1, self.selection.bottomright.col))

    def OnCellRightClick(self, event):
        if hasattr(event, 'Row') and hasattr(event, 'Col'):
            self.selection.cell_right_clicked(event.Row, event.Col)
        self._popup_creator.show(self, PopupMenuItems(self, self._popup_items), 
                                 self.get_selected_content())

    def OnInsertCells(self, event):
        self._insert_or_delete_cells(self._insert_cells, event)

    def OnDeleteCells(self, event):
        self._insert_or_delete_cells(self._delete_cells, event)

    def _insert_or_delete_cells(self, action, event):
        self._update_history()
        for index in self.selection.rows():
            data = action(self._row_data(index))
            self._write_row(index, data)
        self.set_dirty()
        self._refresh_layout()
        event.Skip()

    def _insert_cells(self, data):
        cols = self.selection.cols()
        left = right = cols[0]
        data[left:right] = [''] * len(cols)
        return self._strip_trailing_empty_cells(data)

    def _delete_cells(self, data):
        cols = self.selection.cols()
        left, right = cols[0], cols[-1] + 1
        data[left:right] = []
        return data + [''] * len(cols)

    def _row_data(self, row):
        return [self.GetCellValue(row, col) for col in range(self.NumberCols)]

    def _write_row(self, row, data):
        for col, value in enumerate(data):
            self.write_cell(row, col, value, update_history=False)

    def _refresh_layout(self):
        self.SetFocus()
        self.SetGridCursor(*self.selection.cell)
        self.GetParent().Sizer.Layout()


class _GridSelection(object):
    cell = property(lambda self: (self.topleft.row, self.topleft.col))

    def __init__(self, grid):
        self._set((0, 0))
        self._grid = grid

    def _set(self, topleft, bottomright=None):
        self.topleft = _Cell(topleft[0], topleft[1])
        self.bottomright = self._count_bottomright(topleft, bottomright)

    def _count_bottomright(self, topleft, bottomright):
        if not bottomright:
            return _Cell(topleft[0], topleft[1])
        return _Cell(min(self._grid.NumberRows - 1, bottomright[0]),
                     min(self._grid.NumberCols - 1, bottomright[1]))

    def set_from_single_selection(self, event):
        self._set((event.Row, event.Col))

    def set_from_range_selection(self, grid, event):
        self._set(*self._get_bounding_coordinates(grid, event))

    def _get_bounding_coordinates(self, grid, event):
        whole_row_selection = grid.SelectedRows
        if whole_row_selection:
            return (whole_row_selection[0], 0), \
                   (whole_row_selection[-1], grid.NumberCols - 1)
        return (event.TopLeftCoords.Row, event.TopLeftCoords.Col), \
               (event.BottomRightCoords.Row, event.BottomRightCoords.Col)

    def cell_right_clicked(self, row, col):
        if not (row, col) in self.cells():
            self._set((row, col))

    def rows(self):
        """Returns a list containing indices of rows currently selected."""
        return range(self.topleft.row, self.bottomright.row + 1)

    def cols(self):
        """Returns a list containing indices of columns currently selected."""
        return range(self.topleft.col, self.bottomright.col + 1)

    def cells(self):
        """Return selected cells as a list of tuples (row, column)."""
        return [(row, col) for col in self.cols()
                           for row in self.rows()]


class _Cell(object):

    def __init__(self, row, col):
        self.row = row
        self.col = col

    def __iter__(self):
        for item in self.row, self.col:
            yield item


class _GridState(object):

    def __init__(self):
        self._back = []
        self._forward = []

    def change(self, state):
        if not self._back or state != self._back[-1]:
            self._back.append(state)
            self._forward = []

    def back(self):
        if not self._back:
            return None
        self._forward.append(self._back.pop())
        return self._forward[-1]

    def forward(self):
        if not self._forward:
            return None
        state = self._forward.pop()
        self._back.append(state)
        return state
