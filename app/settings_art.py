import tkinter as tk
from functools import lru_cache
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk


BG, CARD, INPUT = "#0b1120", "#141d32", "#0e1628"
INK, MUTED, EDGE = "#edf2ff", "#bbc8e0", "#344461"
CYAN, ACCENT = "#93edff", "#a4b6ff"
FONT = ("Segoe UI", 10)


@lru_cache(maxsize=16)
def rounded_surface(width, height, radius, fill, edge):
    scale = 3
    image = Image.new("RGBA", (width * scale, height * scale))
    painter = ImageDraw.Draw(image)
    painter.rounded_rectangle((1, 1, image.width - 2, image.height - 2),
                              radius=radius * scale, fill=fill, outline=edge, width=scale)
    return image.resize((width, height), Image.Resampling.LANCZOS)


@lru_cache(maxsize=16)
def frame_surface(width, height, radius, fill, edge):
    inset = radius + 2
    size = inset * 2 + 1
    if width < size or height < size:
        return rounded_surface(width, height, radius, fill, edge)
    tile = rounded_surface(size, size, radius, fill, edge)
    image = Image.new("RGBA", (width, height), fill)
    tile_edges = (0, inset, inset + 1, size)
    xs = (0, inset, width - inset, width)
    ys = (0, inset, height - inset, height)
    for row in range(3):
        for column in range(3):
            if row == column == 1:
                continue
            part = tile.crop((tile_edges[column], tile_edges[row],
                              tile_edges[column + 1], tile_edges[row + 1]))
            target = (xs[column + 1] - xs[column], ys[row + 1] - ys[row])
            if part.size != target:
                part = part.resize(target, Image.Resampling.NEAREST)
            image.paste(part, (xs[column], ys[row]))
    return image


class RoundedFrame(tk.Frame):
    def __init__(self, parent, *, outer, fill=CARD, edge=EDGE, radius=13):
        super().__init__(parent, bg=outer)
        self.fill = fill
        self.edge = edge
        self.radius = radius
        self.plate = tk.Label(self, bg=outer, borderwidth=0, highlightthickness=0)
        self.plate.place(x=0, y=0, relwidth=1, relheight=1, bordermode="ignore")
        self.plate.lower()
        self.image = None
        self.surface_key = None
        self.bind("<Configure>", self.draw)

    def draw(self, _event=None):
        width, height = self.winfo_width(), self.winfo_height()
        key = width, height, self.radius, self.fill, self.edge
        if width < 3 or height < 3 or key == self.surface_key:
            return
        self.image = ImageTk.PhotoImage(
            frame_surface(*key), master=self,
        )
        self.surface_key = key
        self.plate.configure(image=self.image)

    def focus_edge(self, active):
        self.edge = CYAN if active else EDGE
        self.draw()


class SettingsCombobox(ttk.Combobox):
    def __init__(self, parent, **options):
        super().__init__(parent, **options)
        self.bind("<Enter>", lambda _: self.state(["alternate"]), add="+")
        self.bind("<Leave>", lambda _: self.state(["!alternate"]), add="+")


def style_settings(window):
    root = window._root()
    if hasattr(root, "_settings_style_images"):
        return
    style = ttk.Style(root)
    style.theme_use("clam")
    images = root._settings_style_images = []

    def photo(image):
        result = ImageTk.PhotoImage(image, master=root)
        images.append(result)
        return result

    def element(name, base, states):
        # Tk tiles the center and edges on every repaint. Use a wide source to
        # cover each row in one pass while retaining the original minimum size.
        def image(colors):
            return photo(frame_surface(768, 40, 9, *colors))

        normal = image(base)
        variants = [(*state, image(colors)) for state, colors in states]
        style.element_create(name, "image", normal, *variants, border=9, padding=1,
                             width=29, height=29, sticky="nswe")

    def keep_corner_background(name, outer):
        # The transparent corners must blend with the parent in every state.
        style.map(name, background=[(state, outer) for state in ("disabled", "pressed", "active")])

    for label, outer, background, foreground, hover, outline in (
        ("Settings", BG, "#1c2a47", INK, "#273b61", "#455783"),
        ("Preview", CARD, "#1c2a47", INK, "#273b61", "#455783"),
        ("Accent", BG, ACCENT, "#0b1426", "#bfccff", "#b9c6ff"),
        ("Fold", BG, CARD, INK, "#233453", "#364669"),
        ("Navigation", CARD, CARD, INK, "#233453", "#364669"),
        ("OpenSection", CARD, CARD, INK, "#233453", CARD),
    ):
        name = f"{label}.TButton"
        plate = f"{label}.RoundedButton.border"
        element(plate, (background, outline), [
            (("disabled",), (INPUT, "#27344b")),
            (("pressed",), (hover, ACCENT)),
            (("focus",), (background, CYAN)),
            (("selected",), ("#293a62", "#7f8bc9")),
            (("active",), (hover, "#7288ba")),
        ])
        style.layout(name, [(plate, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"}),
            ]}),
        ]})])
        style.configure(name, font=("Segoe UI Semibold", 10), padding=(12, 7),
                        background=outer, foreground=foreground)
        keep_corner_background(name, outer)
        style.map(name, foreground=[("disabled", "#8e9bb4")])
    style.configure("Navigation.TButton", anchor="w")
    style.configure("Fold.TButton", anchor="w")
    style.configure("OpenSection.TButton", anchor="w", padding=(5, 5))

    plate = "Settings.RoundedCombobox.field"
    element(plate, (INPUT, EDGE), [
        (("focus",), (INPUT, CYAN)),
        (("alternate", "!disabled"), (INPUT, "#7181ad")),
        (("active",), (INPUT, "#7181ad")),
    ])
    arrow = Image.new("RGBA", (72, 54))
    ImageDraw.Draw(arrow).line([(20, 21), (35, 34), (50, 21)],
                              fill=ACCENT, width=5, joint="curve")
    arrow_name = "Settings.RoundedCombobox.downarrow"
    style.element_create(arrow_name, "image", photo(arrow.resize((24, 18), Image.Resampling.LANCZOS)),
                         sticky="")
    style.layout("Settings.TCombobox", [(plate, {"sticky": "nswe", "children": [
        (arrow_name, {"side": "right"}),
        ("Combobox.padding", {"sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"}),
        ]}),
    ]})])
    style.configure("Settings.TCombobox", padding=(10, 6, 2, 6), font=FONT, foreground=INK, background=CARD,
                    fieldbackground=INPUT, selectbackground="#3e4b81", selectforeground=INK,
                    insertcolor=INK)
    style.map("Settings.TCombobox", fieldbackground=[("readonly", INPUT)],
              foreground=[("readonly", INK)])
    style.configure("Chrome.Settings.TCombobox", background=BG)
    keep_corner_background("Settings.TCombobox", CARD)
    keep_corner_background("Chrome.Settings.TCombobox", BG)
    thumb = photo(rounded_surface(8, 21, 4, "#52668d", "#52668d"))
    style.element_create("Settings.Scrollbar.thumb", "image", thumb, border=4, sticky="nswe")
    style.layout("Settings.Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Settings.Scrollbar.thumb", {"sticky": "nswe"}),
        ]}),
    ])
    style.configure("Settings.Vertical.TScrollbar", troughcolor=BG, bordercolor=BG, background=BG)
    style.configure("Text.Settings.Vertical.TScrollbar", troughcolor=INPUT, bordercolor=INPUT, background=INPUT)
    empty_thumb = photo(Image.new("RGBA", (8, 21)))
    style.element_create("Quiet.Scrollbar.thumb", "image", empty_thumb, sticky="nswe")
    style.layout("Quiet.Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Quiet.Scrollbar.thumb", {"sticky": "nswe"}),
        ]}),
    ])
    style.configure("Quiet.Vertical.TScrollbar", troughcolor=BG, bordercolor=BG, background=BG)
    for name, value in {
        "background": INPUT, "foreground": INK, "selectBackground": "#3e4b81",
        "selectForeground": INK, "font": FONT, "borderWidth": 0, "highlightThickness": 0,
    }.items():
        root.option_add(f"*TCombobox*Listbox.{name}", value)
