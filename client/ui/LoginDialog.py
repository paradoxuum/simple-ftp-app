from typing import Callable

import wx


class TextField(wx.Panel):
    def __init__(self, parent, label: str, style: int = 0):
        super().__init__(parent)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label_text = wx.StaticText(self, -1, label)
        self.input = wx.TextCtrl(self, style=style)

        sizer.Add(self.label_text, 1, wx.EXPAND | wx.ALIGN_LEFT | wx.ALL, 5)
        sizer.Add(self.input, 1, wx.EXPAND | wx.ALIGN_LEFT | wx.ALL, 5)
        self.SetSizer(sizer)


class LoginPanel(wx.Panel):
    def __init__(self, parent, callback: Callable[[bool, str, str], None]) -> None:
        super().__init__(parent)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.email_field = TextField(self, label="Email Address")
        self.password_field = TextField(self, label="Password", style=wx.TE_PASSWORD)

        btn_sizer = wx.BoxSizer()
        self.login_btn = wx.Button(self, label="Login")
        self.register_btn = wx.Button(self, label="Register")

        self.login_btn.Bind(wx.EVT_BUTTON,
                            lambda _: callback(False, self.email_field.input.GetValue(),
                                               self.password_field.input.GetValue()))
        self.register_btn.Bind(wx.EVT_BUTTON,
                               lambda _: callback(True, self.email_field.input.GetValue(),
                                                  self.password_field.input.GetValue()))

        btn_sizer.Add(self.login_btn, 1, wx.ALL, 5)
        btn_sizer.Add(self.register_btn, 1, wx.ALL, 5)

        sizer.Add(self.email_field, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(self.password_field, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(sizer)


class LoginDialog(wx.Dialog):
    def __init__(self, parent, callback: Callable[[bool, str, str], None]) -> None:
        super().__init__(parent)

        self.callback = callback

        self.SetSize((350, 200))
        self.SetTitle("Login")

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.login_panel = LoginPanel(self, self.callback)

        sizer.Add(self.login_panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
