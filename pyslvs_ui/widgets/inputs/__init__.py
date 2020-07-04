# -*- coding: utf-8 -*-

"""The widget of 'Inputs' tab."""

from __future__ import annotations

__all__ = ['InputsWidget', 'QRotatableView']
__author__ = "Yuan Chang"
__copyright__ = "Copyright (C) 2016-2020"
__license__ = "AGPL"
__email__ = "pyslvs@gmail.com"

from typing import (
    TYPE_CHECKING, Tuple, Dict, Mapping, Sequence, Iterator, Optional, Callable,
)
from csv import writer
from copy import copy
from numpy import array, hypot, arctan2
from qtpy.QtCore import Signal, Slot, QTimer
from qtpy.QtWidgets import (
    QWidget, QMessageBox, QInputDialog, QListWidgetItem, QApplication,
    QCheckBox,
)
from qtpy.QtGui import QIcon, QPixmap
from pyslvs import VJoint, curvature, derivative, path_signature
from pyslvs_ui.info import logger
from pyslvs_ui.graphics import DataChartDialog
from pyslvs_ui.widgets.undo_redo import (
    AddInput, DeleteInput, AddPath, DeletePath,
)
from .rotatable import QRotatableView
from .preview import AnimateDialog
from .inputs_ui import Ui_Form

if TYPE_CHECKING:
    from pyslvs_ui.widgets import MainWindowBase

_Coord = Tuple[float, float]
_Vars = Sequence[Tuple[int, int]]
_Paths = Sequence[Sequence[_Coord]]
_SliderPaths = Mapping[int, Sequence[_Coord]]
_AUTO_PATH = "Auto preview"  # Unified name


def _variable_int(text: str) -> int:
    """Change variable text to index."""
    return int(text.split()[-1].replace("Point", ""))


class InputsWidget(QWidget, Ui_Form):
    """There has following functions:

    + Function of mechanism variables settings.
    + Path recording.
    """
    __paths: Dict[str, _Paths]
    __slider_paths: Dict[str, _SliderPaths]

    about_to_resolve = Signal()

    def __init__(self, parent: MainWindowBase):
        super(InputsWidget, self).__init__(parent)
        self.setupUi(self)
        # parent's function pointer
        self.free_move_button = parent.free_move_button
        self.entities_point = parent.entities_point
        self.entities_link = parent.entities_link
        self.vpoints = parent.vpoint_list
        self.vlinks = parent.vlink_list
        self.main_canvas = parent.main_canvas
        self.solve = parent.solve
        self.reload_canvas = parent.reload_canvas
        self.output_to = parent.output_to
        self.conflict = parent.conflict
        self.dof = parent.dof
        self.right_input = parent.right_input
        self.command_stack = parent.command_stack
        self.set_coords_as_current = parent.set_coords_as_current
        self.get_back_position = parent.get_back_position
        # Angle panel
        self.dial = QRotatableView(self)
        self.dial.setStatusTip("Input widget of rotatable joint.")
        self.dial.setEnabled(False)
        self.dial.value_changed.connect(self.__update_var)
        self.dial_spinbox.valueChanged.connect(self.__set_var)
        self.inputs_dial_layout.insertWidget(0, self.dial)
        # Play button
        self.variable_stop.clicked.connect(self.variable_value_reset)
        # Timer for play button
        self.inputs_play_shaft = QTimer()
        self.inputs_play_shaft.setInterval(10)
        self.inputs_play_shaft.timeout.connect(self.__change_index)
        # Change the point coordinates with current position
        self.update_pos.clicked.connect(self.set_coords_as_current)
        # Record list
        self.record_list.blockSignals(True)
        self.record_list.addItem(_AUTO_PATH)
        self.record_list.setCurrentRow(0)
        self.record_list.blockSignals(False)
        self.__paths = {_AUTO_PATH: self.main_canvas.path_preview}
        self.__slider_paths = {_AUTO_PATH: self.main_canvas.slider_path_preview}

        def slot(widget: QCheckBox) -> Callable[[int], None]:
            @Slot(int)
            def func(ind: int) -> None:
                widget.setEnabled(ind >= 0
                                  and self.vpoints[ind].type != VJoint.R)

            return func

        # Slot option
        self.plot_joint.currentIndexChanged.connect(slot(self.plot_joint_slot))
        self.wrt_joint.currentIndexChanged.connect(slot(self.wrt_joint_slot))

    def clear(self) -> None:
        """Clear function to reset widget status."""
        self.__paths = {_AUTO_PATH: self.__paths[_AUTO_PATH]}
        for _ in range(self.record_list.count() - 1):
            self.record_list.takeItem(1)
        self.variable_list.clear()

    def __set_angle_mode(self) -> None:
        """Change to angle input."""
        self.dial.set_minimum(0)
        self.dial.set_maximum(360)
        self.dial_spinbox.setMinimum(0)
        self.dial_spinbox.setMaximum(360)

    def __set_unit_mode(self) -> None:
        """Change to unit input."""
        self.dial.set_minimum(-500)
        self.dial.set_maximum(500)
        self.dial_spinbox.setMinimum(-500)
        self.dial_spinbox.setMaximum(500)

    def paths(self) -> Dict[str, _Paths]:
        """Return current path data."""
        return self.__paths

    def slider_paths(self) -> Dict[str, _SliderPaths]:
        """Return current path data."""
        return self.__slider_paths

    @Slot(tuple)
    def set_selection(self, selections: Sequence[int]) -> None:
        """Set one selection from canvas."""
        self.joint_list.setCurrentRow(selections[0])

    @Slot()
    def clear_selection(self) -> None:
        """Clear the points selection."""
        self.driver_list.clear()
        self.joint_list.setCurrentRow(-1)

    @Slot(int, name='on_joint_list_currentRowChanged')
    def __update_relate_points(self, _=None) -> None:
        """Change the point row from input widget."""
        self.driver_list.clear()
        item: Optional[QListWidgetItem] = self.joint_list.currentItem()
        if item is None:
            return
        p0 = _variable_int(item.text())
        base_point = self.vpoints[p0]
        type_int = base_point.type
        if type_int == VJoint.R:
            for i, vpoint in enumerate(self.vpoints):
                if i == p0:
                    continue
                if base_point.same_link(vpoint):
                    if base_point.grounded() and vpoint.grounded():
                        continue
                    self.driver_list.addItem(f"[{vpoint.type_str}] Point{i}")
        elif type_int in {VJoint.P, VJoint.RP}:
            self.driver_list.addItem(f"[{base_point.type_str}] Point{p0}")

    @Slot(int, name='on_driver_list_currentRowChanged')
    def __set_add_var_enabled(self, _=None) -> None:
        """Set enable of 'add variable' button."""
        driver = self.driver_list.currentIndex()
        self.variable_add.setEnabled(driver != -1)

    @Slot(name='on_variable_add_clicked')
    def __add_inputs_variable(
        self,
        p0: Optional[int] = None,
        p1: Optional[int] = None
    ) -> None:
        """Add variable with '->' sign."""
        if p0 is None:
            item: Optional[QListWidgetItem] = self.joint_list.currentItem()
            if item is None:
                return
            p0 = _variable_int(item.text())
        if p1 is None:
            item = self.driver_list.currentItem()
            if item is None:
                return
            p1 = _variable_int(item.text())
        # Check DOF
        if self.dof() <= self.input_count():
            QMessageBox.warning(
                self,
                "Wrong DOF",
                "The number of variable must no more than degrees of freedom."
            )
            return
        # Check same link
        if not self.vpoints[p0].same_link(self.vpoints[p1]):
            QMessageBox.warning(
                self,
                "Wrong pair",
                "The base point and driver point should at the same link."
            )
            return
        # Check repeated pairs
        for p0_, p1_, a in self.input_pairs():
            if {p0, p1} == {p0_, p1_} and self.vpoints[p0].type == VJoint.R:
                QMessageBox.warning(
                    self,
                    "Wrong pair",
                    "There already have a same pair."
                )
                return
        if p0 == p1:
            # One joint by offset
            value = self.vpoints[p0].true_offset()
        else:
            # Two joints by angle
            value = self.vpoints[p0].slope_angle(self.vpoints[p1])
        self.command_stack.push(AddInput('->'.join((
            f'Point{p0}',
            f"Point{p1}",
            f"{value:.02f}",
        )), self.variable_list))

    def add_inputs_variables(self, variables: _Vars) -> None:
        """Add from database."""
        for p0, p1 in variables:
            self.__add_inputs_variable(p0, p1)

    @Slot(QListWidgetItem, name='on_variable_list_itemClicked')
    def __dial_ok(self, _=None) -> None:
        """Set the angle of base link and drive link."""
        if self.inputs_play_shaft.isActive():
            return
        row = self.variable_list.currentRow()
        enabled = row > -1
        is_rotatable = (
            enabled
            and not self.free_move_button.isChecked()
            and self.right_input()
        )
        self.dial.setEnabled(is_rotatable)
        self.dial_spinbox.setEnabled(is_rotatable)
        self.oldVar = self.dial.value()
        self.variable_play.setEnabled(is_rotatable)
        self.variable_speed.setEnabled(is_rotatable)
        item: Optional[QListWidgetItem] = self.variable_list.currentItem()
        if item is None:
            return
        expr = item.text().split('->')
        p0 = int(expr[0].replace('Point', ''))
        p1 = int(expr[1].replace('Point', ''))
        value = float(expr[2])
        if p0 == p1:
            self.__set_unit_mode()
        else:
            self.__set_angle_mode()
        self.dial.set_value(value if enabled else 0)

    def variable_excluding(self, row: Optional[int] = None) -> None:
        """Remove variable if the point was been deleted. Default: all."""
        one_row: bool = row is not None
        for i, (b, d, a) in enumerate(self.input_pairs()):
            # If this is not origin point any more
            if one_row and row != b:
                continue
            self.command_stack.push(DeleteInput(i, self.variable_list))

    @Slot(name='on_variable_remove_clicked')
    def remove_var(self, row: int = -1) -> None:
        """Remove and reset angle."""
        if row == -1:
            row = self.variable_list.currentRow()
        if not row > -1:
            return
        self.variable_stop.click()
        self.command_stack.push(DeleteInput(row, self.variable_list))
        self.get_back_position()
        self.solve()

    def interval(self) -> float:
        """Return interval value."""
        return self.record_interval.value()

    def input_count(self) -> int:
        """Use to show input variable count."""
        return self.variable_list.count()

    def input_pairs(self) -> Iterator[Tuple[int, int, float]]:
        """Back as point number code."""
        for row in range(self.variable_list.count()):
            var = self.variable_list.item(row).text().split('->')
            p0 = int(var[0].replace('Point', ''))
            p1 = int(var[1].replace('Point', ''))
            angle = float(var[2])
            yield p0, p1, angle

    def variable_reload(self) -> None:
        """Auto check the points and type."""
        self.joint_list.clear()
        self.plot_joint.clear()
        self.wrt_joint.clear()
        for i in range(self.entities_point.rowCount()):
            type_text = self.entities_point.item(i, 2).text()
            for w in [self.joint_list, self.plot_joint, self.wrt_joint]:
                w.addItem(f"[{type_text}] Point{i}")
        self.variable_value_reset()

    @Slot(float)
    def __set_var(self, value: float) -> None:
        self.dial.set_value(value)

    @Slot(float)
    def __update_var(self, value: float) -> None:
        """Update the value when rotating QDial."""
        item = self.variable_list.currentItem()
        self.dial_spinbox.blockSignals(True)
        self.dial_spinbox.setValue(value)
        self.dial_spinbox.blockSignals(False)
        if item:
            item_text = item.text().split('->')
            item_text[-1] = f"{value:.02f}"
            item.setText('->'.join(item_text))
            self.about_to_resolve.emit()
        if (
            self.record_start.isChecked()
            and abs(self.oldVar - value) > self.record_interval.value()
        ):
            self.main_canvas.record_path()
            self.oldVar = value

    def variable_value_reset(self) -> None:
        """Reset the value of QDial."""
        if self.inputs_play_shaft.isActive():
            self.variable_play.setChecked(False)
            self.inputs_play_shaft.stop()
        self.get_back_position()
        for i, (p0, p1, a) in enumerate(self.input_pairs()):
            self.variable_list.item(i).setText('->'.join([
                f'Point{p0}',
                f'Point{p1}',
                f"{self.vpoints[p0].slope_angle(self.vpoints[p1]):.02f}",
            ]))
        self.__dial_ok()
        self.solve()

    @Slot(bool, name='on_variable_play_toggled')
    def __play(self, toggled: bool) -> None:
        """Triggered when play button was changed."""
        self.dial.setEnabled(not toggled)
        self.dial_spinbox.setEnabled(not toggled)
        if toggled:
            self.inputs_play_shaft.start()
        else:
            self.inputs_play_shaft.stop()

    @Slot()
    def __change_index(self) -> None:
        """QTimer change index."""
        index = self.dial.value()
        speed = self.variable_speed.value()
        extreme_rebound = (
            self.conflict.isVisible()
            and self.extremeRebound.isChecked()
        )
        if extreme_rebound:
            speed = -speed
            self.variable_speed.setValue(speed)
        index += speed * 0.06 * (3 if extreme_rebound else 1)
        self.dial.set_value(index)

    @Slot(bool, name='on_record_start_toggled')
    def __start_record(self, toggled: bool) -> None:
        """Save to file path data."""
        if toggled:
            self.main_canvas.record_start(int(
                self.dial_spinbox.maximum() / self.record_interval.value()
            ))
            return
        path, path_slider = self.main_canvas.get_record_path()
        name, ok = QInputDialog.getText(
            self,
            "Recording completed!",
            "Please input name tag:"
        )
        i = 0
        name = name or f"Record_{i}"
        while name in self.__paths:
            name = f"Record_{i}"
            i += 1
        QMessageBox.information(self, "Record",
                                "The name tag is being used or empty.")
        self.add_path(name, path, path_slider)

    def add_path(self, name: str, path: _Paths, slider: _SliderPaths) -> None:
        """Add path function."""
        self.command_stack.push(AddPath(
            self.record_list,
            name,
            self.__paths,
            self.__slider_paths,
            path,
            slider
        ))
        self.record_list.setCurrentRow(self.record_list.count() - 1)

    def load_paths(self, paths: Mapping[str, _Paths],
                   slider_paths: Mapping[str, _SliderPaths]) -> None:
        """Add multiple paths."""
        for name, path in paths.items():
            self.add_path(name, path, slider_paths.get(name, {}))

    @Slot(name='on_record_remove_clicked')
    def __remove_path(self) -> None:
        """Remove path data."""
        row = self.record_list.currentRow()
        if not row > 0:
            return
        self.command_stack.push(DeletePath(
            row,
            self.record_list,
            self.__paths,
            self.__slider_paths
        ))
        self.record_list.setCurrentRow(self.record_list.count() - 1)
        self.reload_canvas()

    @Slot(QListWidgetItem, name='on_record_list_itemDoubleClicked')
    def __path_dlg(self, item: QListWidgetItem) -> None:
        """View path data."""
        name = item.text().split(":", maxsplit=1)[0]
        try:
            paths = self.__paths[name]
        except KeyError:
            return
        points_text = ", ".join(f"Point{i}" for i in range(len(paths)))
        if QMessageBox.question(
            self,
            "Path data",
            f"This path data including {points_text}.",
            (QMessageBox.Save | QMessageBox.Close),
            QMessageBox.Close
        ) != QMessageBox.Save:
            return
        file_name = self.output_to(
            "path data",
            ["Comma-Separated Values (*.csv)", "Text file (*.txt)"]
        )
        if not file_name:
            return
        with open(file_name, 'w+', encoding='utf-8', newline='') as stream:
            w = writer(stream)
            for path in paths:
                for point in path:
                    w.writerow(point)
                w.writerow(())
        logger.info(f"Output path data: {file_name}")

    def __current_path_name(self) -> str:
        """Return the current path name."""
        return self.record_list.currentItem().text().split(':', maxsplit=1)[0]

    @Slot(name='on_copy_path_clicked')
    def __copy_path(self):
        """Copy path from record list."""
        name = self.__current_path_name()
        num = 0
        name_copy = f"{name}_{num}"
        while name_copy in self.__paths:
            name_copy = f"{name}_{num}"
            num += 1
        self.add_path(name_copy, copy(self.__paths[name]), {})

    @Slot(name='on_cp_data_button_clicked')
    def __copy_path_data(self) -> None:
        """Copy current path data to clipboard."""
        data = self.__paths[self.__current_path_name()]
        if not data:
            return
        QApplication.clipboard().setText('\n'.join(
            f"[{x}, {y}]," for x, y in data[self.plot_joint.currentIndex()]
        ))

    @Slot(name='on_show_button_clicked')
    def __show_path(self) -> None:
        """Show specified path."""
        self.main_canvas.set_path_show(self.plot_joint.currentIndex())

    @Slot(name='on_show_all_button_clicked')
    def __show_all_path(self) -> None:
        """Show all paths."""
        self.record_show.setChecked(True)
        self.main_canvas.set_path_show(-1)

    @Slot(bool, name='on_record_show_toggled')
    def __set_path_show(self, toggled: bool) -> None:
        """Show all paths or hide."""
        self.main_canvas.set_path_show(-1 if toggled else -2)

    @Slot(int, name='on_record_list_currentRowChanged')
    def __set_path(self, _=None) -> None:
        """Reload the canvas when switch the path."""
        if not self.record_show.isChecked():
            self.record_show.setChecked(True)
        self.reload_canvas()

    def current_path(self) -> _Paths:
        """Return current path data to main canvas.

        + No path.
        + Show path data.
        + Auto preview.
        """
        row = self.record_list.currentRow()
        if row in {0, -1}:
            return ()
        path_name = self.record_list.item(row).text().split(':')[0]
        return self.__paths.get(path_name, ())

    @Slot(name='on_variable_up_clicked')
    @Slot(name='on_variable_down_clicked')
    def __set_variable_priority(self) -> None:
        row = self.variable_list.currentRow()
        if not row > -1:
            return
        item = self.variable_list.currentItem()
        self.variable_list.insertItem(
            row + (-1 if self.sender() == self.variable_up else 1),
            self.variable_list.takeItem(row)
        )
        self.variable_list.setCurrentItem(item)

    @Slot(name='on_animate_button_clicked')
    def __animate(self) -> None:
        """Make a motion animation."""
        data = self.__paths[self.__current_path_name()]
        if not data:
            return
        dlg = AnimateDialog(self.vpoints, data,
                            self.main_canvas.monochrome, self)
        dlg.show()
        dlg.exec_()
        dlg.deleteLater()

    @Slot(name='on_plot_button_clicked')
    def __plot(self) -> None:
        """Plot the data. Show the X and Y axises as two line."""
        joint = self.plot_joint.currentIndex()
        data = self.__paths[self.__current_path_name()]
        if not data:
            return
        pos = array(data[joint])
        if self.wrt_label.isChecked():
            pos[:] -= array(data[self.wrt_joint.currentIndex()])
        vel = derivative(pos)
        acc = derivative(vel)
        cur = curvature(data[joint])
        plot = {}
        plot_count = 0
        if self.plot_pos.isChecked():
            plot_count += 1
            plot["Position"] = pos
        if self.plot_vel.isChecked():
            plot_count += 1
            plot["Velocity"] = vel
        if self.plot_acc.isChecked():
            plot_count += 1
            plot["Acceleration"] = acc
        if self.plot_jerk.isChecked():
            plot_count += 1
            plot["Jerk"] = derivative(acc)
        if self.plot_curvature.isChecked():
            plot_count += 1
            plot["Curvature"] = cur
        if self.plot_signature.isChecked():
            plot_count += 1
            plot["Path Signature"] = path_signature(cur)
        if plot_count < 1:
            QMessageBox.warning(self, "No target", "No any plotting target.")
            return
        polar = self.p_coord_sys.isChecked()
        row = plot_count
        col = 1
        if polar:
            row, col = col, row
        dlg = DataChartDialog(self, "Analysis", row, col, polar)
        dlg.setWindowIcon(QIcon(QPixmap(":/icons/formula.png")))
        ax = dlg.ax()
        for p, (title, xy) in enumerate(plot.items()):
            ax_i = ax[p]
            ax_i.set_title(title)
            if title == "Path Signature":
                ax_i.plot(xy[:, 0], xy[:, 1])
                ax_i.set_ylabel(r"$\kappa$")
                ax_i.set_xlabel(r"$\int|\kappa|dt$")
            elif xy.ndim == 2:
                x = xy[:, 0]
                y = xy[:, 1]
                if self.c_coord_sys.isChecked():
                    ax_i.plot(x, label='x')
                    ax_i.plot(y, label='y')
                    ax_i.legend()
                else:
                    r = hypot(x, y)
                    theta = arctan2(y, x)
                    ax_i.plot(theta, r, linewidth=5)
            else:
                ax_i.plot(xy)
        dlg.set_margin(0.2)
        dlg.show()
        dlg.exec_()
        dlg.deleteLater()