import wx

from client.client import FileClient
from client.ui.MainFrame import MainFrame
from shared.state import EventMessage, EventMessageType


class FileApp(wx.App):
    def __init__(self, host: str = "127.0.0.1", port: int = 50_000):
        super().__init__()

        self.client = FileClient(host, port)
        self.client.set_event_handler(self.handle_event)
        self.frame = MainFrame(self.client)

        self.client.start()
        self.frame.Show()
        self.SetTopWindow(self.frame)

    def start(self) -> None:
        try:
            self.MainLoop()
        except KeyboardInterrupt:
            self.Destroy()
            self.client.stop()

    @staticmethod
    def handle_event(event: EventMessage) -> None:
        caption = "Info"
        style = wx.OK | wx.ICON_INFORMATION
        if event.message_type == EventMessageType.Success:
            caption = "Success"
        elif event.message_type == EventMessageType.Error:
            style = wx.OK | wx.ICON_ERROR

        dialog = wx.MessageDialog(None, event.message, caption, style)
        dialog.ShowModal()
        dialog.Destroy()
