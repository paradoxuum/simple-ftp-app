from typing import List, Optional

import wx
from wx import TreeItemId


class FileBrowserPanel(wx.Panel):
    def __init__(self, parent) -> None:
        super().__init__(parent)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.tree = wx.TreeCtrl(self, wx.ID_ANY, wx.DefaultPosition, (-1, 200),
                                wx.TR_HIDE_ROOT | wx.TR_HAS_BUTTONS)
        self.root = self.tree.AddRoot("Files")

        sizer.Add(self.tree, 0, wx.ALL | wx.EXPAND)

        self.SetSizer(sizer)

    def clear_files(self) -> None:
        self.tree.DeleteAllItems()

    def update_files(self, files: List[str]) -> None:
        self.clear_files()
        for f in files:
            parts = f.split("/")

            prev_item: Optional[TreeItemId] = None
            for part in parts:
                if prev_item is None:
                    prev_item = self.tree.AppendItem(self.root, part)
                else:
                    prev_item = self.tree.AppendItem(prev_item, part)

        self.tree.ExpandAll()
