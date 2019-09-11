# -*- coding: utf-8 -*-

"""YAML format processing function."""

from __future__ import annotations

__author__ = "Yuan Chang"
__copyright__ = "Copyright (C) 2016-2019"
__license__ = "AGPL"
__email__ = "pyslvs@gmail.com"

from typing import (
    TYPE_CHECKING,
    Tuple,
    List,
    Sequence,
    Dict,
    Any,
)
import yaml
from pyslvs import __version__, VJoint
from core.QtModules import (
    QObject,
    QFileInfo,
    QProgressDialog,
    QCoreApplication,
)
from .overview import OverviewDialog
if TYPE_CHECKING:
    from core.widgets import MainWindowBase


class YamlEditor(QObject):

    """YAML reader and writer."""

    def __init__(self, parent: MainWindowBase) -> None:
        super(YamlEditor, self).__init__(parent)
        # Undo stack
        self.command_stack = parent.command_stack
        # Action group settings
        self.prefer = parent.prefer
        # Call to get point expressions
        self.vpoints = parent.vpoint_list
        # Call to get link data
        self.vlinks = parent.vlink_list
        # Call to get storage data
        self.get_storage = parent.get_storage
        # Call to get collections data
        self.collect_data = parent.collection_tab_page.collect_data
        # Call to get triangle data
        self.config_data = parent.collection_tab_page.config_data
        # Call to get inputs variables data
        self.input_pairs = parent.inputs_widget.input_pairs
        # Call to get algorithm data
        self.algorithm_data = parent.dimensional_synthesis.mechanism_data
        # Call to get path data
        self.path_data = parent.inputs_widget.path_data

        # Add empty links function
        self.add_empty_links = parent.add_empty_links
        # Add points function
        self.add_points = parent.add_points

        # Call to load inputs variables data
        self.load_inputs = parent.inputs_widget.add_inputs_variables
        # Add storage function
        self.load_storage = parent.add_multiple_storage
        # Call to load paths
        self.load_paths = parent.inputs_widget.load_paths
        # Call to load collections data
        self.load_collections = parent.collection_tab_page.structure_widget.add_collections
        # Call to load config data
        self.load_config = parent.collection_tab_page.configure_widget.add_collections
        # Call to load algorithm results
        self.load_algorithm = parent.dimensional_synthesis.load_results

        # Clear function for main window
        self.main_clear = parent.clear

    def save(self, file_name: str) -> None:
        """Save YAML file."""
        mechanism_data = []
        for vpoint in self.vpoints:
            attr = {
                'links': vpoint.links,
                'type': vpoint.type,
                'x': vpoint.x,
                'y': vpoint.y,
            }
            if vpoint.type in {VJoint.P, VJoint.RP}:
                attr['angle'] = vpoint.angle
            mechanism_data.append(attr)

        data = {
            'mechanism': mechanism_data,
            'links': {l.name: l.color_str for l in self.vlinks},
            'input': [{'base': b, 'drive': d} for b, d, _ in self.input_pairs()],
            'storage': list(self.get_storage().items()),
            'collection': self.collect_data(),
            'triangle': self.config_data(),
            'algorithm': eval(str(self.algorithm_data)),
            'path': self.path_data(),
        }
        if self.prefer.file_type_option == 0:
            flow_style = False
        elif self.prefer.file_type_option == 1:
            flow_style = True
        else:
            raise ValueError(f"unsupported option: {self.prefer.file_type_option}")
        yaml_script = yaml.dump(data, default_flow_style=flow_style)
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(f"# Generated by Pyslvs {__version__}\n\n" + yaml_script)

    def load(self, file_name: str) -> None:
        """Load YAML file."""
        self.main_clear()
        dlg = QProgressDialog("Loading project", "Cancel", 0, 8, self.parent())
        dlg.setLabelText("Reading file ...")
        dlg.show()
        with open(file_name, encoding='utf-8') as f:
            yaml_script = f.read()
        data: Dict[str, Any] = yaml.load(yaml_script, Loader=yaml.FullLoader)

        # Mechanism data
        dlg.setValue(1)
        dlg.setLabelText("Loading mechanism ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add mechanism")
        links_data: Dict[str, str] = data.get('links', {})
        self.add_empty_links(links_data)
        mechanism_data: List[Dict[str, Any]] = data.get('mechanism', [])
        p_attr = []
        nan = float("nan")
        for point_attr in mechanism_data:
            QCoreApplication.processEvents()
            p_x: float = point_attr.get('x', nan)
            p_y: float = point_attr.get('y', nan)
            p_links: Tuple[str] = point_attr.get('links', ())
            p_type: int = point_attr.get('type', 0)
            p_angle: float = point_attr.get('angle', 0.)
            p_attr.append((p_x, p_y, ','.join(p_links), 'Green', p_type, p_angle))
        self.add_points(p_attr)
        self.__end_group()

        # Input data
        dlg.setValue(2)
        dlg.setLabelText("Loading input data ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add input data")
        input_data: List[Dict[str, int]] = data.get('input', [])
        i_attr = []
        for input_attr in input_data:
            QCoreApplication.processEvents()
            if ('base' in input_attr) and ('drive' in input_attr):
                i_base = input_attr['base']
                i_drive = input_attr['drive']
                i_attr.append((i_base, i_drive))
        self.load_inputs(i_attr)
        self.__end_group()

        # Storage data
        dlg.setValue(3)
        dlg.setLabelText("Loading storage ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add storage")
        storage_data: List[Tuple[str, str]] = data.get('storage', [])
        self.load_storage(storage_data)
        self.__end_group()

        # Path data
        dlg.setValue(4)
        dlg.setLabelText("Loading paths ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add paths")
        path_data: Dict[str, Sequence[Tuple[float, float]]] = data.get('path', {})
        self.load_paths(path_data)
        self.__end_group()

        # Collection data
        dlg.setValue(5)
        dlg.setLabelText("Loading graph collections ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add graph collections")
        collection_data: List[Tuple[Tuple[int, int], ...]] = data.get('collection', [])
        self.load_collections(collection_data)
        self.__end_group()

        # Configuration data
        dlg.setValue(6)
        dlg.setLabelText("Loading synthesis configurations ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add synthesis configurations")
        config_data: Dict[str, Dict[str, Any]] = data.get('triangle', {})
        self.load_config(config_data)
        self.__end_group()

        # Algorithm data
        dlg.setValue(7)
        dlg.setLabelText("Loading synthesis results ...")
        if dlg.wasCanceled():
            dlg.deleteLater()
            return self.main_clear()
        self.__set_group("Add synthesis results")
        algorithm_data: List[Dict[str, Any]] = data.get('algorithm', [])
        self.load_algorithm(algorithm_data)
        self.__end_group()

        # Workbook loaded
        dlg.setValue(8)
        dlg.deleteLater()

        # Show overview dialog
        dlg = OverviewDialog(
            self.parent(),
            QFileInfo(file_name).baseName(),
            storage_data,
            i_attr,
            path_data,
            collection_data,
            config_data,
            algorithm_data
        )
        dlg.show()
        dlg.exec_()
        dlg.deleteLater()

    def __set_group(self, text: str) -> None:
        """Set group."""
        if self.prefer.open_project_actions_option == 1:
            self.command_stack.beginMacro(text)

    def __end_group(self) -> None:
        """End group."""
        if self.prefer.open_project_actions_option == 1:
            self.command_stack.endMacro()
