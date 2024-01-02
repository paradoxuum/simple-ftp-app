from typing import Optional

import wx

from client.client import FileClient
from client.ui.main import MainFrame


class FileApp(wx.App):
    def __init__(self):
        super().__init__()

        self.frame: Optional[MainFrame] = None

        self.client = FileClient()
        self.client.start()

    def start(self) -> None:
        self.MainLoop()

    def OnInit(self):
        self.frame = MainFrame()
        self.frame.Show()

        self.SetTopWindow(self.frame)
        return True

    def OnExit(self):
        print(self.client)
        if self.client is not None:
            self.client.stop()
        return 0
