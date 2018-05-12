# -*- coding: utf-8 -*-

"""SQL database output function."""

__author__ = "Yuan Chang"
__copyright__ = "Copyright (C) 2016-2018"
__license__ = "AGPL"
__email__ = "pyslvs@gmail.com"

import zlib
import os
import datetime
from peewee import (
    SqliteDatabase,
    Model,
    CharField,
    BlobField,
    ForeignKeyField,
    DateTimeField,
)
from core.QtModules import (
    QPushButton,
    pyqtSignal,
    QIcon,
    QPixmap,
    QFileInfo,
    QWidget,
    pyqtSlot,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
)
from .workbook_overview import WorkbookOverview
from .example import example_list
from .Ui_peeweeIO import Ui_Form


"""Use to encode the Python script."""
_compress = lambda obj: zlib.compress(bytes(repr(obj), encoding="utf8"), 5)
_decompress = lambda obj: eval(zlib.decompress(obj).decode())

"""We need a not-a-number symbol for eval function."""
nan = float('nan')

"""Create a empty Sqlite database object."""
_db = SqliteDatabase(None)


class UserModel(Model):
    
    """Show who commited the workbook."""
    
    name = CharField(unique=True)
    
    class Meta:
        database = _db


class BranchModel(Model):
    
    """The branch in this workbook."""
    
    name = CharField(unique=True)
    
    class Meta:
        database = _db


class CommitModel(Model):
    
    """Commit data: Mechanism and Workbook information.
    
    + Previous and branch commit.
    + Commit time.
    + Workbook information.
    + Expression using Lark parser.
    + Storage data.
    + Path data.
    + Collection data.
    + Triangle collection data.
    + Input variables data.
    + Algorithm data.
    """
    
    previous = ForeignKeyField('self', related_name='next', null=True)
    branch = ForeignKeyField(BranchModel, null=True)
    
    date = DateTimeField(default=datetime.datetime.now)
    
    author = ForeignKeyField(UserModel, null=True)
    description = CharField()
    
    mechanism = BlobField()
    linkcolor = BlobField()
    
    storage = BlobField()
    
    pathdata = BlobField()
    
    collectiondata = BlobField()
    
    triangledata = BlobField()
    
    inputsdata = BlobField()
    
    algorithmdata = BlobField()
    
    class Meta:
        database = _db


class LoadCommitButton(QPushButton):
    
    """The button of load commit."""
    
    loaded = pyqtSignal(int)
    
    def __init__(self, id, parent):
        super(LoadCommitButton, self).__init__(
            QIcon(QPixmap(":icons/dataupdate.png")),
            " #{}".format(id),
            parent
        )
        self.setToolTip("Reset to commit #{}.".format(id))
        self.id = id
    
    def mouseReleaseEvent(self, event):
        """Load the commit when release button."""
        super(LoadCommitButton, self).mouseReleaseEvent(event)
        self.loaded.emit(self.id)
    
    def isLoaded(self, id: int):
        """Set enable if this commit is been loaded."""
        self.setEnabled(id != self.id)


class FileWidget(QWidget, Ui_Form):
    
    """The table that stored workbook data,
    including IO functions.
    """
    
    load_id = pyqtSignal(int)
    
    def __init__(self, parent):
        """Set attributes.
        
        + UI part
        + The main window functions
        + Functions to get and set data
        + External functions.
        """
        super(FileWidget, self).__init__(parent)
        self.setupUi(self)
        """UI part
        
        + ID
        + Date
        + Description
        + Author
        + Previous
        + Branch
        """
        self.CommitTable.setColumnWidth(0, 70)
        self.CommitTable.setColumnWidth(1, 70)
        self.CommitTable.setColumnWidth(2, 130)
        self.CommitTable.setColumnWidth(3, 70)
        self.CommitTable.setColumnWidth(4, 70)
        self.CommitTable.setColumnWidth(5, 70)
        """The main window functions.
        
        + Get current point data.
        + Get current link data.
        """
        self.pointDataFunc = parent.EntitiesPoint.data
        self.linkDataFunc = parent.EntitiesLink.data
        self.storageDataFunc = lambda: tuple((
            parent.mechanism_storage.item(row).text(),
            parent.mechanism_storage.item(row).expr
        ) for row in range(parent.mechanism_storage.count()))
        """Functions to get and set data.
        
        + Call it to get main window be shown as saved.
        + Add empty link with color.
        + Main window will load the entered expression.
        + Reset the main window.
        + Call to load storages.
        + Call after loaded paths.
        """
        self.isSavedFunc = parent.workbookSaved
        self.linkGroupFunc = parent.addEmptyLinkGroup
        self.parseFunc = parent.parseExpression
        self.clearFunc = parent.clear
        self.loadStorageFunc = parent.loadStorage
        """Mentioned in 'core.widgets.custom',
        because DimensionalSynthesis created after FileWidget.
        
        self.CollectDataFunc #Call to get collections data.
        self.TriangleDataFunc #Call to get triangle data.
        self.InputsDataFunc #Call to get inputs variables data.
        self.AlgorithmDataFunc #Call to get algorithm data.
        self.pathDataFunc #Call to get path data.
        self.loadCollectFunc #Call to load collections data.
        self.loadTriangleFunc #Call to load triangle data.
        self.loadInputsFunc #Call to load inputs variables data.
        self.loadAlgorithmFunc #Call after loaded algorithm results.
        self.loadPathFunc #Call after loaded paths.
        """
        #Close database when destroyed.
        self.destroyed.connect(self.closeDatabase)
        #Undo Stack
        self.CommandStack = parent.CommandStack
        #Reset
        self.reset()
    
    def reset(self):
        """Clear all the things that dependent on database."""
        #peewee Quary(CommitModel) type
        self.history_commit = None
        self.Script = ""
        self.file_name = QFileInfo("Untitled")
        self.lastTime = datetime.datetime.now()
        self.changed = False
        self.Stack = 0
        self.CommandStack.clear()
        for row in range(self.CommitTable.rowCount()):
            self.CommitTable.removeRow(0)
        self.BranchList.clear()
        self.AuthorList.clear()
        self.FileAuthor.clear()
        self.FileDescription.clear()
        self.branch_current.clear()
        self.commit_search_text.clear()
        self.commit_current_id.setValue(0)
    
    def __connectDatabase(self, file_name: str):
        """Connect database."""
        self.closeDatabase()
        _db.init(file_name)
        _db.connect()
        _db.create_tables([CommitModel, UserModel, BranchModel], safe=True)
    
    @pyqtSlot()
    def closeDatabase(self):
        if not _db.deferred:
            _db.close()
    
    def save(self, file_name: str, isBranch=False):
        """Save database.
        
        + Append to new branch function.
        """
        author_name = self.FileAuthor.text()
        if not author_name:
            author_name = self.FileAuthor.placeholderText()
        branch_name = '' if isBranch else self.branch_current.text()
        commit_text = self.FileDescription.text()
        while not author_name:
            author_name, ok = QInputDialog.getText(self, "Author",
                "Please enter author's name:",
                QLineEdit.Normal,
                "Anonymous"
            )
            if not ok:
                return
        while not branch_name.isidentifier():
            branch_name, ok = QInputDialog.getText(self, "Branch",
                "Please enter a branch name:",
                QLineEdit.Normal,
                "master"
            )
            if not ok:
                return
        while not commit_text:
            commit_text, ok = QInputDialog.getText(self, "Commit",
                "Please add a comment:",
                QLineEdit.Normal,
                "Update mechanism."
            )
            if not ok:
                return
        if (
            (file_name != self.file_name.absoluteFilePath()) and
            os.path.isfile(file_name)
        ):
            os.remove(file_name)
            print("The original file has been overwritten.")
        self.__connectDatabase(file_name)
        isError = False
        with _db.atomic():
            if author_name in (user.name for user in UserModel.select()):
                author_model = (
                    UserModel
                    .select()
                    .where(UserModel.name==author_name)
                    .get()
                )
            else:
                author_model = UserModel(name=author_name)
            if branch_name in (branch.name for branch in BranchModel.select()):
                branch_model = (
                    BranchModel
                    .select()
                    .where(BranchModel.name==branch_name)
                    .get()
                )
            else:
                branch_model = BranchModel(name=branch_name)
            pointData = self.pointDataFunc()
            linkcolor = {
                vlink.name: vlink.colorSTR
                for vlink in self.linkDataFunc()
            }
            args = {
                'author':author_model,
                'description':commit_text,
                'mechanism':_compress("M[{}]".format(", ".join(
                    vpoint.expr for vpoint in pointData
                ))),
                'linkcolor': _compress(linkcolor),
                'storage': _compress(self.storageDataFunc()),
                'pathdata': _compress(self.pathDataFunc()),
                'collectiondata': _compress(self.CollectDataFunc()),
                'triangledata': _compress(self.TriangleDataFunc()),
                'inputsdata': _compress(self.InputsDataFunc()),
                'algorithmdata': _compress(self.AlgorithmDataFunc()),
                'branch': branch_model
            }
            try:
                args['previous'] = (
                    CommitModel
                    .select()
                    .where(CommitModel.id == self.commit_current_id.value())
                    .get()
                )
            except CommitModel.DoesNotExist:
                args['previous'] = None
            new_commit = CommitModel(**args)
            try:
                author_model.save()
                branch_model.save()
                new_commit.save()
            except Exception as e:
                print(str(e))
                _db.rollback()
                isError = True
            else:
                self.history_commit = (
                    CommitModel
                    .select()
                    .order_by(CommitModel.id)
                )
        if isError:
            os.remove(file_name)
            print("The file was removed.")
            return
        self.read(file_name, showdlg = False)
        print("Saving \"{}\" successful.".format(file_name))
        size = QFileInfo(file_name).size()
        print("Size: {}".format(
            "{} MB".format(round(size/1024/1024, 2))
            if size / 1024 // 1024
            else "{} KB".format(round(size/1024, 2))
        ))
    
    def read(self, file_name: str, *, showdlg: bool = True):
        """Load database commit."""
        self.__connectDatabase(file_name)
        history_commit = CommitModel.select().order_by(CommitModel.id)
        commit_count = len(history_commit)
        if not commit_count:
            QMessageBox.warning(self,
                "Warning",
                "This file is a non-committed database."
            )
            return
        self.clearFunc()
        self.reset()
        self.history_commit = history_commit
        for commit in self.history_commit:
            self.__addCommit(commit)
        print("{} commit(s) was find in database.".format(commit_count))
        self.__loadCommit(
            self.history_commit.order_by(-CommitModel.id).get(),
            showdlg = showdlg
        )
        self.file_name = QFileInfo(file_name)
        self.isSavedFunc()
    
    def importMechanism(self, file_name: str):
        """Pick and import the latest mechanism from a branch."""
        self.__connectDatabase(file_name)
        commit_all = CommitModel.select().join(BranchModel)
        branch_all = BranchModel.select().order_by(BranchModel.name)
        if self.history_commit != None:
            self.__connectDatabase(self.file_name.absoluteFilePath())
        else:
            self.closeDatabase()
        branch_name, ok = QInputDialog.getItem(self,
            "Branch",
            "Select the latest commit in the branch to load.",
            [branch.name for branch in branch_all],
            0,
            False
        )
        if not ok:
            return
        try:
            commit = (
                commit_all
                .where(BranchModel.name==branch_name)
                .order_by(CommitModel.date)
                .get()
            )
        except CommitModel.DoesNotExist:
            QMessageBox.warning(self,
                "Warning",
                "This file is a non-committed database."
            )
        else:
            self.__importCommit(commit)
    
    def __addCommit(self, commit: CommitModel):
        """Add commit data to all widgets.
        
        + Commit ID
        + Date
        + Description
        + Author
        + Previous commit
        + Branch
        + Add to table widget.
        """
        row = self.CommitTable.rowCount()
        self.CommitTable.insertRow(row)
        
        self.commit_current_id.setValue(commit.id)
        button = LoadCommitButton(commit.id, self)
        button.loaded.connect(self.__loadCommitID)
        self.load_id.connect(button.isLoaded)
        self.CommitTable.setCellWidget(row, 0, button)
        
        date = (
            "{t.year:02d}-{t.month:02d}-{t.day:02d} " +
            "{t.hour:02d}:{t.minute:02d}:{t.second:02d}"
        ).format(t=commit.date)
        
        self.CommitTable.setItem(row, 2, QTableWidgetItem(commit.description))
        
        author_name = commit.author.name
        all_authors = [
            self.AuthorList.item(row).text()
            for row in range(self.AuthorList.count())
        ]
        if author_name not in all_authors:
            self.AuthorList.addItem(author_name)
        
        if commit.previous:
            previous_id = "#{}".format(commit.previous.id)
        else:
            previous_id = "None"
        
        branch_name = commit.branch.name
        all_branchs = [
            self.BranchList.item(row).text()
            for row in range(self.BranchList.count())
        ]
        if branch_name not in all_branchs:
            self.BranchList.addItem(branch_name)
        self.branch_current.setText(branch_name)
        
        for i, text in enumerate([
            date,
            commit.description,
            author_name,
            previous_id,
            branch_name
        ]):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.CommitTable.setItem(row, i+1, item)
    
    def __loadCommitID(self, id: int):
        """Check the id is correct."""
        try:
            commit = self.history_commit.where(CommitModel.id==id).get()
        except CommitModel.DoesNotExist:
            QMessageBox.warning(self, "Warning", "Commit ID is not exist.")
        except AttributeError:
            QMessageBox.warning(self, "Warning", "Nothing submitted.")
        else:
            self.__loadCommit(commit)
    
    def __loadCommit(self, commit: CommitModel, *, showdlg: bool = True):
        """Load the commit pointer."""
        if not self.__checkSaved():
            return
        #Reset the main window status.
        self.clearFunc()
        #Load the commit to widgets.
        print("Loading commit #{}.".format(commit.id))
        self.load_id.emit(commit.id)
        self.commit_current_id.setValue(commit.id)
        self.branch_current.setText(commit.branch.name)
        #Load the expression.
        self.linkGroupFunc(_decompress(commit.linkcolor))
        self.parseFunc(_decompress(commit.mechanism))
        #Load the storages.
        self.loadStorageFunc(_decompress(commit.storage))
        #Load pathdata.
        self.loadPathFunc(_decompress(commit.pathdata))
        #Load collectiondata.
        self.loadCollectFunc(_decompress(commit.collectiondata))
        #Load triangledata.
        self.loadTriangleFunc(_decompress(commit.triangledata))
        #Load inputsdata.
        self.loadInputsFunc(_decompress(commit.inputsdata))
        #Load algorithmdata.
        self.loadAlgorithmFunc(_decompress(commit.algorithmdata))
        #Workbook loaded.
        self.isSavedFunc()
        print("The specified phase has been loaded.")
        #Show overview dialog.
        dlg = WorkbookOverview(self, commit, _decompress)
        dlg.show()
        dlg.exec_()
    
    def __importCommit(self, commit: CommitModel):
        """Just load the expression. (No clear step!)"""
        self.parseFunc(_decompress(commit.mechanism))
        print("The specified phase has been merged.")
    
    @pyqtSlot()
    def on_commit_stash_clicked(self):
        """Reload the least commit ID."""
        self.__loadCommitID(self.commit_current_id.value())
    
    def loadExample(self, isImport: bool = False) -> bool:
        """Load example to new workbook."""
        if not self.__checkSaved():
            return False
        #load example by expression.
        example_name, ok = QInputDialog.getItem(self,
            "Examples",
            "Select a example to load:",
            sorted(example_list),
            0,
            False
        )
        if not ok:
            return False
        if not isImport:
            self.reset()
            self.clearFunc()
        expr, inputs = example_list[example_name]
        self.parseFunc(expr)
        self.loadInputsFunc(inputs)
        self.file_name = QFileInfo(example_name)
        self.isSavedFunc()
        print("Example \"{}\" has been loaded.".format(example_name))
        return True
    
    def __checkSaved(self) -> bool:
        """Check and warn if user is not saved yet."""
        if not self.changed:
            return True
        reply = QMessageBox.question(self,
            "Message",
            "Are you sure to load?\nAny changes won't be saved."
        )
        return reply == QMessageBox.Yes
    
    @pyqtSlot(str)
    def on_commit_search_text_textEdited(self, text: str):
        """Commit filter (by description and another)."""
        if not text:
            for row in range(self.CommitTable.rowCount()):
                self.CommitTable.setRowHidden(row, False)
            return
        for row in range(self.CommitTable.rowCount()):
            self.CommitTable.setRowHidden(row, not (
                (text in self.CommitTable.item(row, 2).text()) or
                (text in self.CommitTable.item(row, 3).text())
            ))
    
    @pyqtSlot(str)
    def on_AuthorList_currentTextChanged(self, text: str):
        """Change default author's name when select another author."""
        self.FileAuthor.setPlaceholderText(text)
    
    @pyqtSlot()
    def on_branch_checkout_clicked(self):
        """Switch to the last commit of branch."""
        if not self.BranchList.currentRow() > -1:
            return
        branch_name = self.BranchList.currentItem().text()
        if branch_name == self.branch_current.text():
            return
        leastCommit = (
            self.history_commit
            .join(BranchModel)
            .where(BranchModel.name == branch_name)
            .order_by(-CommitModel.date)
            .get()
        )
        self.__loadCommit(leastCommit)
    
    @pyqtSlot()
    def on_branch_delete_clicked(self):
        """Delete all commits in the branch."""
        if not self.BranchList.currentRow() > -1:
            return
        branch_name = self.BranchList.currentItem().text()
        if branch_name == self.branch_current.text():
            QMessageBox.warning(self,
                "Warning",
                "Cannot delete current branch."
            )
            return
        file_name = self.file_name.absoluteFilePath()
        #Connect on database to remove all the commit in this branch.
        with _db.atomic():
            branch_quary = (
                BranchModel
                .select()
                .where(BranchModel.name == branch_name)
            )
            (
                CommitModel
                .delete()
                .where(CommitModel.branch.in_(branch_quary))
                .execute()
            )
            (
                BranchModel
                .delete()
                .where(BranchModel.name == branch_name)
                .execute()
            )
        _db.close()
        print("Branch {} was deleted.".format(branch_name))
        #Reload database.
        self.read(file_name)
