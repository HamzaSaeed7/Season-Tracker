from ui import App

app = App()
app.protocol("WM_DELETE_WINDOW", app.on_close)
app.mainloop()
