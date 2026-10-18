import customtkinter as ctk
from .ui import TradingApp


def main():
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    TradingApp().mainloop()


if __name__ == '__main__':
    main()
