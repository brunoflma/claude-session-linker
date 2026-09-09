## 2024-05-24 - Explicit Loading States for Async Operations
**Learning:** For asynchronous or background I/O operations in the GUI, lacking explicit loading/disabled states on interactive selectors and cancel/close buttons can lead to user confusion, accidental double-clicks, and false expectations of cancellation while invisible threads are still running.
**Action:** Always implement explicit loading and disabled states for action buttons, dialog buttons, and interactive selectors when launching background threads, restoring their normal states once the background work completes.
