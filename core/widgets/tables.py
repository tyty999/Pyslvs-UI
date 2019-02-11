# -*- coding: utf-8 -*-

"""Custom table of Points and Links.
Also contains selection status label.
"""

__author__ = "Yuan Chang"
__copyright__ = "Copyright (C) 2016-2019"
__license__ = "AGPL"
__email__ = "pyslvs@gmail.com"

from abc import abstractmethod
from time import time
from typing import (
    TYPE_CHECKING,
    Tuple,
    List,
    Dict,
    Iterator,
    Sequence,
    Union,
    Optional,
    TypeVar,
)
from core.QtModules import (
    Signal,
    Qt,
    QTimer,
    QTableWidget,
    QSizePolicy,
    QAbstractItemView,
    QTableWidgetItem,
    Slot,
    QApplication,
    QTableWidgetSelectionRange,
    QHeaderView,
    QLabel,
    QWidget,
    QABCMeta,
)
from core.graphics import color_icon
from core.libs import VJoint, VPoint, VLink, color_rgb

if TYPE_CHECKING:
    from core.widgets import MainWindowBase

_Data = TypeVar('_Data', VPoint, VLink)
_Coord = Tuple[float, float]


class BaseTableWidget(QTableWidget, metaclass=QABCMeta):

    """Two tables has some shared function."""

    row_selection_changed = Signal(list)
    delete_request = Signal()

    def __init__(self, row: int, headers: Sequence[str], parent: QWidget):
        super(BaseTableWidget, self).__init__(parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setStatusTip("This table will show about the entities items in current view mode.")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.setRowCount(row)
        self.setColumnCount(len(headers))
        for i, e in enumerate(headers):
            self.setHorizontalHeaderItem(i, QTableWidgetItem(e))

        # Table widget column width.
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        @Slot()
        def __emit_selection_changed():
            self.row_selection_changed.emit(self.selected_rows())

        self.itemSelectionChanged.connect(__emit_selection_changed)

    def row_text(self, row: int, *, has_name: bool = False) -> List[str]:
        """Get the whole row of texts.

        + Edit point: has_name = False
        + Edit link: has_name = True
        """
        texts = []
        for column in self.effective_range(has_name):
            item = self.item(row, column)
            if item is None:
                texts.append('')
            else:
                texts.append(item.text())
        return texts

    @abstractmethod
    def effective_range(self, has_name: bool) -> Iterator[int]:
        """Return valid column range for row text."""
        ...

    @abstractmethod
    def item_data(self, row: int) -> _Data:
        """Return a table data by row index."""
        ...

    def data(self) -> Iterator[_Data]:
        """Return table data in subclass."""
        yield from (self.item_data(row) for row in range(self.rowCount()))

    def data_tuple(self) -> Tuple[_Data, ...]:
        """Return data set as a container."""
        return tuple(self.data())

    def selected_rows(self) -> List[int]:
        """Get what row is been selected."""
        return [row for row in range(self.rowCount()) if self.item(row, 0).isSelected()]

    def selectAll(self):
        """Override method of select all function."""
        self.setFocus(Qt.ShortcutFocusReason)
        super(BaseTableWidget, self).selectAll()

    def set_selections(self, selections: Sequence[int], key_detect: bool = False):
        """Auto select function, get the signal from canvas."""
        self.setFocus()
        keyboard_modifiers = QApplication.keyboardModifiers()
        if key_detect:
            continue_select, not_select = {
                Qt.ShiftModifier: (True, False),
                Qt.ControlModifier: (True, True),
            }.get(keyboard_modifiers, (False, False))
            self.__set_selected_ranges(
                selections,
                is_continue=continue_select,
                un_select=not_select
            )
        else:
            self.__set_selected_ranges(
                selections,
                is_continue=(keyboard_modifiers == Qt.ShiftModifier),
                un_select=False
            )

    def __set_selected_ranges(
        self,
        selections: Sequence[int],
        *,
        is_continue: bool,
        un_select: bool
    ):
        """Different mode of select function."""
        selected_rows = self.selected_rows()
        if not is_continue:
            self.clearSelection()
        self.setCurrentCell(selections[-1], 0)
        for row in selections:
            is_selected = (row not in selected_rows) if un_select else True
            self.setRangeSelected(
                QTableWidgetSelectionRange(row, 0, row, self.columnCount() - 1),
                is_selected
            )
            self.scrollToItem(self.item(row, 0))

    def keyPressEvent(self, event):
        """Hit the delete key,
        will emit delete signal from this table.
        """
        if event.key() == Qt.Key_Delete:
            self.delete_request.emit()

    def clear(self):
        """Overridden the clear function, just removed all items."""
        for row in range(self.rowCount()):
            self.removeRow(0)

    @Slot()
    def clearSelection(self):
        """Overridden the 'clear_selection' slot to emit 'row_selection_changed'"""
        super(BaseTableWidget, self).clearSelection()
        self.row_selection_changed.emit([])


class PointTableWidget(BaseTableWidget):

    """Custom table widget for points."""

    selectionLabelUpdate = Signal(list)

    def __init__(self, parent: QWidget):
        super(PointTableWidget, self).__init__(0, (
            'Number',
            'Links',
            'Type',
            'Color',
            'X',
            'Y',
            'Current',
        ), parent)

    def item_data(self, row: int) -> VPoint:
        """Return data of VPoint."""
        links = self.item(row, 1).text()
        color = self.item(row, 3).text()
        x = float(self.item(row, 4).text())
        y = float(self.item(row, 5).text())
        # p_type = (type: str, angle: float)
        p_type = self.item(row, 2).text().split(':')
        if p_type[0] == 'R':
            j_type = VJoint.R
            angle = 0.
        else:
            angle = float(p_type[1])
            j_type = VJoint.P if p_type[0] == 'P' else VJoint.RP
        vpoint = VPoint([
            link for link in links.replace(" ", '').split(',') if link
        ], j_type, angle, color, x, y, color_rgb)
        vpoint.move(*self.current_position(row))
        return vpoint

    def expression(self) -> str:
        """Return expression string."""
        exprs = ", ".join(vpoint.expr for vpoint in self.data())
        return f"M[{exprs}]"

    def edit_point(self, row: int, links: str, type_str: str, color: str, x: str, y: str):
        """Edit a point."""
        for i, e in enumerate([f'Point{row}', links, type_str, color, x, y, f"({x}, {y})"]):
            item = QTableWidgetItem(str(e))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if i == 3:
                item.setIcon(color_icon(e))
            self.setItem(row, i, item)

    def rename(self, row: int):
        """When index changed, the points need to rename."""
        for j in range(row, self.rowCount()):
            self.setItem(j, 0, QTableWidgetItem(f'Point{j}'))

    def current_position(self, row: int) -> List[_Coord]:
        """Get the current coordinate from a point."""
        type_str = self.item(row, 2).text().split(':')
        coords_text = self.item(row, 6).text().replace(';', ',')
        coords = eval(f"[{coords_text}]")
        if (type_str[0] in {'P', 'RP'}) and len(coords) == 1:
            x, y = coords[0]
            self.item(row, 6).setText("; ".join([f"({x:.06f}, {y:.06f})"] * 2))
            coords.append(coords[0])
        return coords

    def update_current_position(self, coords: Sequence[Union[_Coord, Tuple[_Coord, _Coord]]]):
        """Update the current coordinate for a point."""
        for i, c in enumerate(coords):
            if type(c[0]) == float:
                text = f"({c[0]:.06f}, {c[1]:.06f})"
            else:
                text = "; ".join(f"({x:.06f}, {y:.06f})" for x, y in c)
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.setItem(i, 6, item)

    def get_back_position(self):
        """Let all the points go back to origin coordinate."""
        self.update_current_position(tuple(
            (float(self.item(row, 4).text()), float(self.item(row, 5).text()))
            for row in range(self.rowCount())
        ))

    def get_links(self, row: int) -> List[str]:
        item = self.item(row, 1)
        if not item:
            return []
        return [s for s in item.text().split(',') if s]

    def set_selections(self, selections: Sequence[int], key_detect: bool = False):
        """Need to update selection label on status bar."""
        super(PointTableWidget, self).set_selections(selections, key_detect)
        self.selectionLabelUpdate.emit(self.selected_rows())

    def effective_range(self, has_name: bool) -> Iterator[int]:
        """Row range that can be delete."""
        if has_name:
            return range(self.columnCount())
        else:
            return range(1, self.columnCount() - 1)

    @Slot()
    def clearSelection(self):
        """Overridden the 'clear_selection' slot,
        so it will emit signal to clean the selection.
        """
        super(PointTableWidget, self).clearSelection()
        self.selectionLabelUpdate.emit([])


class LinkTableWidget(BaseTableWidget):

    """Custom table widget for link."""

    def __init__(self, parent: QWidget):
        super(LinkTableWidget, self).__init__(1, ('Name', 'Color', 'Points'), parent)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setAcceptDrops(True)
        self.edit_link(0, 'ground', 'White', '')

    def item_data(self, row: int) -> VLink:
        """Return data of VLink."""
        name = self.item(row, 0).text()
        color = self.item(row, 1).text()
        points = []
        for p in self.item(row, 2).text().split(','):
            if p:
                points.append(int(p.replace('Point', '')))
        return VLink(name, color, tuple(points), color_rgb)

    def colors(self) -> Dict[str, str]:
        """Return name and color as a dict."""
        return {vlink.name: vlink.color_str for vlink in self.data()}

    def edit_link(
        self,
        row: int,
        name: str,
        color: str,
        points: str
    ):
        """Edit a link."""
        for i, e in enumerate((name, color, points)):
            item = QTableWidgetItem(e)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if i == 1:
                item.setIcon(color_icon(e))
            self.setItem(row, i, item)

    def find_name(self, name: str) -> int:
        """Return row index by input name."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if not item:
                continue
            if name == item.text():
                return row

    def get_points(self, row: int) -> List[int]:
        """Get all point names."""
        item = self.item(row, 2)
        if not item:
            return []
        return [int(s.replace('Point', '')) for s in item.text().split(',') if s]

    def effective_range(self, has_name: bool) -> Iterator[int]:
        """Row range that can be delete."""
        return range(self.columnCount())

    def clear(self):
        """We should keep the 'ground' left."""
        super(LinkTableWidget, self).clear()
        self.setRowCount(1)
        self.edit_link(0, 'ground', 'White', '')


class ExprTableWidget(BaseTableWidget):

    """Expression table.

    + Free move request: link name, length
    """

    def __init__(self, parent: QWidget):
        super(ExprTableWidget, self).__init__(0, (
            'Function',
            'p0',
            'p1',
            'p2',
            'p3',
            'p4',
            'target',
        ), parent)
        self.expr = []

    def set_expr(
        self,
        expr: List[Tuple[str]],
        data_dict: Dict[str, Union[_Coord, float]],
        unsolved: Tuple[int]
    ):
        """Set the table items for new coming expression."""
        if expr != self.expr:
            self.clear()
            self.setRowCount(len(expr) + len(unsolved))
        row = 0
        for expr in expr:
            # Target
            self.setItem(row, self.columnCount() - 1, QTableWidgetItem(expr[-1]))
            # Parameters
            for column, e in enumerate(expr[:-1]):
                if e in data_dict:
                    if type(data_dict[e]) == float:
                        # Pure digit
                        text = f"{e}:{data_dict[e]:.02f}"
                    else:
                        # Coordinate
                        text = f"{e}:({data_dict[e][0]:.02f}, {data_dict[e][1]:.02f})"
                else:
                    # Function name
                    text = e
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.setItem(row, column, item)
            row += 1
        for p in unsolved:
            # Declaration
            self.setItem(row, 0, QTableWidgetItem("Unsolved"))
            # Target
            self.setItem(row, self.columnCount() - 1, QTableWidgetItem(f"P{p}"))
            row += 1
        self.expr = expr

    def item_data(self, _: int) -> None:
        """Not used generator."""
        return None

    def effective_range(self, has_name: bool) -> Iterator[int]:
        """Return column count."""
        return range(self.columnCount())

    def clear(self):
        """Emit to close the link free move widget."""
        super(ExprTableWidget, self).clear()


class SelectionLabel(QLabel):

    """This QLabel can show distance in status bar."""

    def __init__(self, parent: 'MainWindowBase'):
        super(SelectionLabel, self).__init__(parent)
        self.update_select_point()
        self.dataTuple = parent.entities_point.data_tuple

    @Slot()
    @Slot(list)
    def update_select_point(self, points: Optional[List[int]] = None):
        """Get points and distance from Point table widget."""
        if points is None:
            points = []
        p_count = len(points)
        if not p_count:
            self.setText("No selection.")
            return
        text = ""
        text += "Selected: "
        text += " - ".join(str(p) for p in points)
        vpoints = self.dataTuple()
        if p_count > 1:
            distances = []
            angles = []
            for i in range(min(p_count, 3)):
                if i != 0:
                    vpoint0 = vpoints[points[i - 1]]
                    vpoint1 = vpoints[points[i]]
                    distances.append(f"{vpoint1.distance(vpoint0):.04}")
                    angles.append(f"{vpoint0.slope_angle(vpoint1):.04}°")
            ds_t = ", ".join(distances)
            as_t = ", ".join(angles)
            text += f" | {ds_t} | {as_t}"
        self.setText(text)

    @Slot(float, float)
    def update_mouse_position(self, x: float, y: float):
        """Get the mouse position from canvas when press the middle button."""
        self.setText(f"Mouse at: ({x:.04f}, {y:.04f})")


class FPSLabel(QLabel):

    """This QLabel can show FPS of main canvas in status bar."""

    def __init__(self, parent: QWidget):
        super(FPSLabel, self).__init__(parent)
        self.__t0 = time() - 1
        self.__frame_timer = QTimer()
        self.__frame_timer.timeout.connect(self.__update_text)
        self.__frame_timer.start(500)

    @Slot()
    def __update_text(self):
        """Update FPS with timer."""
        t1 = time() - self.__t0
        fps = 1 / t1 if t1 else 1
        self.setText(f"FPS: {fps:6.02f}")

    @Slot()
    def update_text(self):
        """Update FPS with timer."""
        self.__update_text()
        self.__t0 = time()
