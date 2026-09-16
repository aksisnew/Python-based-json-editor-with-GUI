import sys
import tkinter as tk
from tkinter import messagebox


def main():
    """Entry point and initializer for the JSON Maker and Editor."""
    try:
        root = tk.Tk()
        root.title("JSON Maker & Editor")
        root.geometry("1100x650")
        root.minsize(800, 500)

        # Lazy import of GUI to ensure Tkinter root is instantiated first
        from gui import JSONEditorGUI
        
        # Initialize UI Application
        app = JSONEditorGUI(root)
        
        # Start Tkinter main loop
        root.mainloop()
    except Exception as e:
        print(f"Fatal Startup Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
