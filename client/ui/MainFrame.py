import time
from pathlib import Path
from threading import Thread
from typing import List, Optional

import wx
import wx.lib.newevent

from client.client import FileClient
from client.client_state import Upload, Login, Logout
from client.ui.AdminPanel import AdminPanel
from client.ui.FileBrowserPanel import FileBrowserPanel
from client.ui.LoginDialog import LoginDialog
from client.ui.UploadPanel import UploadPanel
from data import UserData, PrivilegeLevel, AdminData

StatusEvent, EVT_STATUS_EVENT = wx.lib.newevent.NewEvent()


class StatusCheckThread(Thread):
    def __init__(self, window: wx.Frame, client: FileClient) -> None:
        super().__init__()
        self._window = window
        self._client = client
        self._running = True

    def run(self) -> None:
        while self._running and not self._client.aborted:
            time.sleep(0.1)
        wx.PostEvent(self._window, StatusEvent())

    def stop(self) -> None:
        self._running = False


class MainFrame(wx.Frame):
    def __init__(self, client: FileClient) -> None:
        super().__init__(parent=None, title="Simple FTP App")
        self.client = client

        self.user: Optional[UserData] = None
        self.login_dialog: Optional[LoginDialog] = None

        # Create UI
        self.SetSize((500, 375))
        self.panel = wx.Panel(self)

        # Top bar buttons
        top_sizer = wx.BoxSizer()
        self.logged_in_status = wx.StaticText(self.panel, label="Not logged in")

        self.login_btn = wx.Button(self.panel, label="Login")
        self.login_btn.Bind(wx.EVT_BUTTON, self.on_login)

        top_sizer.Add(self.logged_in_status, 3, wx.ALL, 5)
        top_sizer.Add(self.login_btn, 1, wx.ALL, 5)

        # Initialize notebook
        self.note_book = wx.Notebook(self.panel)

        self.upload_page = UploadPanel(self.note_book, self.on_upload)
        self.files_page = FileBrowserPanel(self.note_book)
        self.admin_page = AdminPanel(self.note_book, client)
        self.admin_page.Hide()

        self.note_book.AddPage(self.upload_page, "Upload")
        self.note_book.AddPage(self.files_page, "Files")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top_sizer, 1, wx.EXPAND)
        sizer.Add(self.note_book, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)

        # Begin status check thread
        self.status_check_thread = StatusCheckThread(self, client)
        self.status_check_thread.start()

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(EVT_STATUS_EVENT, self.on_abort)

        self.client.data_manager.on_user_update(self.on_user_update)
        self.client.data_manager.on_files_update(self.on_files_update)
        self.client.data_manager.on_admin_data_update(self.on_admin_data_update)

    def on_upload(self, paths: List[str]) -> None:
        path_objs: List[Path] = []
        for p in paths:
            path = Path(p)
            if not path.exists():
                self.show_error(f"Path does not exist: {path}")
                return

            if not path.is_file():
                self.show_error(f"Path is not a file: {path}")
                return

            path_objs.append(path)

        self.client.enqueue_state(Upload(path_objs))

    @staticmethod
    def show_error(message: str) -> None:
        dialog = wx.MessageDialog(None, message, "Error", wx.OK | wx.ICON_ERROR)
        dialog.ShowModal()
        dialog.Destroy()

    def on_login(self, _) -> None:
        if self.user is not None:
            self.client.enqueue_state(Logout())
            return

        dialog = LoginDialog(self, self.on_login_entered)
        self.login_dialog = dialog

        dialog.ShowModal()
        self.login_dialog = None
        dialog.Destroy()

    def on_login_entered(self, register: bool, email: str, password: str) -> None:
        if email.strip() == "":
            self.show_error("No email given")
            return

        if password.strip() == "":
            self.show_error("No password given")
            return

        self.client.enqueue_state(Login(register, email, password))

    def on_user_update(self, user: Optional[UserData]) -> None:
        self.user = user

        # Close login dialog
        if self.login_dialog is not None:
            try:
                self.login_dialog.Close()
            except:
                pass
            self.login_dialog = None

        if user is None:
            self.logged_in_status.SetLabel("Not logged in")
            self.login_btn.SetLabel("Login")
            if self.note_book.GetPageCount() == 3:
                self.note_book.SetSelection(0)
                self.note_book.RemovePage(2)
                self.admin_page.Hide()

            return

        status = f"Logged in as: {user.email}"
        if user.privilege == PrivilegeLevel.Admin:
            status += " (Admin)"

        self.logged_in_status.SetLabel(status)
        self.login_btn.SetLabel("Logout")
        self.note_book.AddPage(self.admin_page, "Admin")

    def on_files_update(self, files: List[str]) -> None:
        self.files_page.update_files(files)

    def on_admin_data_update(self, data: Optional[AdminData]) -> None:
        self.admin_page.update_admin_data(data)

    def on_close(self, _) -> None:
        self.status_check_thread.stop()
        self.status_check_thread.join()
        if self.client.running:
            self.client.stop()

        self.Destroy()

    def on_abort(self, _) -> None:
        self.client.stop()
        self.Close()
