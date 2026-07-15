## 2024-05-24 - Accessibility Keyboard Improvement
**Learning:** CustomTkinter modal dialogs (CTkToplevel) do not have a built-in binding for the Escape key to close the window.
**Action:** When creating modal dialogs, explicitly bind the `<Escape>` key to the close function.
