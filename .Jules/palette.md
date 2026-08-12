## 2025-02-13 - [Interactive Labels]
**Learning:** In Tkinter/CustomTkinter, standard Tkinter arguments like `cursor="hand2"` can be passed to text elements like `CTkLabel` to provide interactive hover affordances without needing a full button widget, making it ideal for micro-interactions like copy-to-clipboard on metadata labels.
**Action:** When adding small clickable interactions to text elements, use `CTkLabel` with `cursor="hand2"` and `.bind("<Button-1>", ...)` instead of replacing the layout with a `CTkButton`, avoiding unnecessary layout adjustments or button styling constraints.
