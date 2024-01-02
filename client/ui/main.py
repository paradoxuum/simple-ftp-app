from threading import Thread

import wx
import wx.lib.newevent

from client.ui.upload import UploadPanel

ResultEvent, EVT_RESULT_EVENT = wx.lib.newevent.NewEvent()


class NetworkThread(Thread):
    def __init__(self, window: wx.Frame) -> None:
        super().__init__()
        self._window = window
        self._running = True

    def run(self) -> None:
        while self._running:
            # wx.PostEvent(self._window, ResultEvent(message="Hello, World!"))
            pass

    def abort(self) -> None:
        self._running = False


class MainFrame(wx.Frame):
    def __init__(self) -> None:
        super().__init__(parent=None, title="Simple FTP App")
        self.panel = UploadPanel(self)
        self.SetSize((500, 300))

        # Begin network thread
        self.network_thread = NetworkThread(self)
        self.network_thread.start()

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(EVT_RESULT_EVENT, self.on_result)

    def on_close(self, event) -> None:
        self.network_thread.abort()
        self.network_thread.join()
        self.Destroy()

    def on_result(self, event) -> None:
        print(event.message)
