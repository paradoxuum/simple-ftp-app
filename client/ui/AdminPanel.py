from datetime import datetime
from typing import List, Optional, Dict, Tuple

import wx
import wx.lib.newevent

from client.client import FileClient
from client.client_state import ViewFiles
from shared.data import UserView, AdminData, Interaction, PrivilegeLevel

FileUpdateEvent, EVT_FILE_UPDATE_EVENT = wx.lib.newevent.NewEvent()


class ViewFilesDialog(wx.Dialog):
    def __init__(self, parent, client: FileClient, user: UserView, files: List[str]):
        super().__init__(parent)

        self.client = client
        self.user = user

        self.SetSize((350, 250))
        self.SetTitle(f"{user.email}'s files")

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, 150), style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.InsertColumn(0, "File", width=wx.EXPAND)
        for i, path in enumerate(files):
            self.list_ctrl.InsertItem(i, path)

        sizer.Add(self.list_ctrl, flag=wx.ALL | wx.EXPAND, border=5)
        self.SetSizer(sizer)


class UserPanel(wx.Panel):
    def __init__(self, parent, client: FileClient) -> None:
        super().__init__(parent)

        self.client = client
        self.client.data_manager.on_viewed_files_update(self.on_viewed_files_update)

        self.user_map: Dict[int, UserView] = {}
        self.selected_user: Optional[UserView] = None
        self.view_files_dialog: Optional[ViewFilesDialog] = None

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, -1), style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self._insert_columns()

        self.view_files_btn = wx.Button(self, label="View Files")
        self.view_files_btn.Bind(wx.EVT_BUTTON, self.on_view_files)

        sizer.Add(self.list_ctrl, flag=wx.ALL | wx.EXPAND, border=5)
        sizer.Add(self.view_files_btn, flag=wx.ALL | wx.EXPAND, border=5)
        self.SetSizer(sizer)

        self.Bind(EVT_FILE_UPDATE_EVENT, self.show_file_dialog)

    def _insert_columns(self) -> None:
        self.list_ctrl.InsertColumn(0, "Email", width=150)
        self.list_ctrl.InsertColumn(1, "Privilege Level", width=wx.EXPAND)

    def set_users(self, users: List[UserView]) -> None:
        self.user_map.clear()
        self.list_ctrl.ClearAll()
        self._insert_columns()
        for i, user in enumerate(users):
            self.user_map[i] = user
            self.list_ctrl.InsertItem(i, user.email)

            privilege_name: str
            if user.privilege == PrivilegeLevel.Admin:
                privilege_name = "Admin"
            else:
                privilege_name = "User"

            self.list_ctrl.SetItem(i, 1, privilege_name)

    def on_view_files(self, _) -> None:
        selected_item: int = self.list_ctrl.GetFirstSelected()
        if selected_item == -1 or selected_item not in self.user_map:
            return

        self.selected_user = self.user_map[selected_item]
        self.client.enqueue_state(ViewFiles(email=self.selected_user.email, admin_view=True))

    def show_file_dialog(self, event) -> None:
        if len(event.files) == 0 or self.view_files_dialog is not None:
            return

        if self.selected_user is None:
            return

        if self.selected_user.email != event.email:
            return

        dialog = ViewFilesDialog(self, self.client, self.selected_user, event.files)
        self.view_files_dialog = dialog

        dialog.ShowModal()
        dialog.Destroy()
        self.client.data_manager.clear_viewed_files()
        self.view_files_dialog = None

    def on_viewed_files_update(self, data: Optional[Tuple[str, List[str]]]) -> None:
        if data is None:
            return
        wx.PostEvent(self, FileUpdateEvent(email=data[0], files=data[1]))


class InteractionsPanel(wx.Panel):
    def __init__(self, parent) -> None:
        super().__init__(parent)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, -1), style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self._insert_columns()

        sizer.Add(self.list_ctrl, flag=wx.ALL | wx.EXPAND, border=5)
        self.SetSizer(sizer)

    def _insert_columns(self) -> None:
        self.list_ctrl.InsertColumn(0, "Time", width=50)
        self.list_ctrl.InsertColumn(1, "User", width=150)
        self.list_ctrl.InsertColumn(2, "Message", width=wx.EXPAND)

    def set_interactions(self, interactions: List[Interaction]) -> None:
        self.list_ctrl.ClearAll()
        self._insert_columns()

        for i, interaction in enumerate(interactions):
            time = datetime.fromtimestamp(interaction.timestamp)
            formatted_date = time.strftime("%Y/%m/%d, %H:%M:%S")
            self.list_ctrl.InsertItem(i, formatted_date)
            self.list_ctrl.SetItem(i, 1, interaction.user_email)
            self.list_ctrl.SetItem(i, 2, interaction.message)


class AdminPanel(wx.Panel):
    def __init__(self, parent, client: FileClient) -> None:
        super().__init__(parent)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Initialize notebook
        self.note_book = wx.Notebook(self)

        self.user_page = UserPanel(self.note_book, client)
        self.interactions_page = InteractionsPanel(self.note_book)

        self.note_book.AddPage(self.user_page, "Users")
        self.note_book.AddPage(self.interactions_page, "Interactions")

        sizer.Add(self.note_book, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def update_admin_data(self, data: Optional[AdminData]) -> None:
        if data is None:
            self.user_page.set_users([])
            self.interactions_page.set_interactions([])
            return

        self.user_page.set_users(data.users)
        self.interactions_page.set_interactions(data.interactions)
