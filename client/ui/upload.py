from pathlib import Path
from typing import List, Dict

import wx


def create_list_columns(list_ctrl: wx.ListCtrl, name_column_width: int) -> None:
    list_ctrl.InsertColumn(0, "File Name", width=name_column_width)
    list_ctrl.InsertColumn(1, "File Path", width=wx.EXPAND)


class RemoveFilesDialog(wx.Dialog):
    def __init__(self, parent, paths: List[str], *args, **kw) -> None:
        super().__init__(parent=parent, *args, **kw)

        self.SetSize((350, 250))
        self.SetTitle("Remove files")

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, 150), style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.EnableCheckBoxes(True)
        create_list_columns(self.list_ctrl, 100)

        for i, path in enumerate(paths):
            path_obj = Path(path)
            self.list_ctrl.InsertItem(i, path_obj.name)
            self.list_ctrl.SetItem(i, 1, path)

        vbox.Add(self.list_ctrl, flag=wx.ALL | wx.EXPAND, border=5)

        dialog_btn_hbox = wx.BoxSizer(wx.HORIZONTAL)

        ok_button = wx.Button(self, label="Ok")
        ok_button.Bind(wx.EVT_BUTTON, self.on_ok)

        close_button = wx.Button(self, label="Cancel")
        close_button.Bind(wx.EVT_BUTTON, self.on_close)

        dialog_btn_hbox.Add(ok_button)
        dialog_btn_hbox.Add(close_button, flag=wx.LEFT, border=5)

        vbox.Add(panel, proportion=1, flag=wx.ALL | wx.EXPAND, border=5)
        vbox.Add(dialog_btn_hbox, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=10)

        self.SetSizer(vbox)

    def get_checked(self) -> List[int]:
        checked: List[int] = []
        for i in range(0, self.list_ctrl.GetItemCount()):
            if not self.list_ctrl.IsItemChecked(i):
                continue
            checked.append(i)

        return checked

    def on_ok(self, _) -> None:
        self.Destroy()

    def on_close(self, _) -> None:
        self.Destroy()


class UploadPanel(wx.Panel):
    def __init__(self, parent) -> None:
        super().__init__(parent)

        self.path_map: Dict[str, int] = {}
        self.paths: List[str] = []

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, 150), style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        create_list_columns(self.list_ctrl, 200)
        main_sizer.Add(self.list_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        add_files_btn = wx.Button(self, label="Add file(s)")
        add_files_btn.Bind(wx.EVT_BUTTON, self.on_add_files)

        remove_files_btn = wx.Button(self, label="Remove file(s)")
        remove_files_btn.Bind(wx.EVT_BUTTON, self.on_remove_files)

        upload_btn = wx.Button(self, label="Upload")
        upload_btn.Bind(wx.EVT_BUTTON, self.on_upload)

        main_sizer.Add(add_files_btn, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(remove_files_btn, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(upload_btn, 0, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(main_sizer)

    def update_list(self) -> None:
        self.list_ctrl.ClearAll()
        create_list_columns(self.list_ctrl, 200)

        for i, path in enumerate(self.paths):
            path_obj = Path(path)
            self.list_ctrl.InsertItem(i, path_obj.name)
            self.list_ctrl.SetItem(i, 1, path)

    def add_path(self, path: str) -> None:
        if path in self.path_map:
            return

        self.path_map[path] = len(self.paths)
        self.paths.append(path)

    def remove_path(self, index: int) -> None:
        if index > len(self.paths) - 1:
            return

        path = self.paths.pop(index)
        del self.path_map[path]

    def on_add_files(self, _) -> None:
        with wx.FileDialog(
            self, "Add files", style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                # User cancelled the dialog, so return early
                return

            for path in dialog.GetPaths():
                self.add_path(path)
            self.update_list()

    def on_remove_files(self, _) -> None:
        with RemoveFilesDialog(self, self.paths) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return

            for i in dialog.get_checked():
                self.remove_path(i)
            self.update_list()

    def on_upload(self, event) -> None:
        pass

