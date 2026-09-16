import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Any, Dict, List, Optional, Tuple

import createFile
import readjson


class JSONEditorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("JSON Maker & Editor")
        self.root.geometry("1100x650")

        # Active state management
        self.active_rel_path: Optional[str] = None
        self.active_json_data: Any = {}
        self.primary_key_var = tk.StringVar(value="")
        self.current_view_mode = "wysiwyg"  # "wysiwyg" or "raw"
        self.clipboard_data: Optional[Tuple[str, str]] = None  # (source_rel_path, action)

        # Multi-threading Queue
        self.ui_queue: queue.Queue = queue.Queue()
        
        # Dynamic Widget Store for WYSIWYG Constructor
        self.form_entries: List[Dict[str, Any]] = []

        self._setup_ui()
        self._check_ui_queue()
        self.refresh_sidebar()

    # -------------------------------------------------------------------
    # Concurrency & Background Task Execution
    # -------------------------------------------------------------------

    def run_in_background(self, task_func, callback, *args):
        """Dispatches disk operations off the main thread."""
        def worker():
            try:
                result = task_func(*args)
                self.ui_queue.put((callback, result, None))
            except Exception as e:
                self.ui_queue.put((callback, None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _check_ui_queue(self):
        """Processes background thread callbacks on the main Tkinter thread."""
        while not self.ui_queue.empty():
            try:
                callback, result, err = self.ui_queue.get_nowait()
                if err:
                    messagebox.showerror("Error", str(err))
                else:
                    callback(result)
            except queue.Empty:
                break
        self.root.after(100, self._check_ui_queue)

    # -------------------------------------------------------------------
    # UI Layout Construction
    # -------------------------------------------------------------------

    def _setup_ui(self):
        # Main Window PanedLayout
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # 1. Left Sidebar (File/Folder Directory Tree)
        sidebar_frame = ttk.Frame(main_pane, width=250, padding=5)
        main_pane.add(sidebar_frame, weight=1)

        ttk.Label(sidebar_frame, text="Project Files", font=("Helvetica", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.file_tree = ttk.Treeview(sidebar_frame, selectmode="browse")
        self.file_tree.pack(fill=tk.BOTH, expand=True)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_tree_file_select)
        self.file_tree.bind("<Button-3>", self._show_context_menu)  # Right-click context menu

        # Sidebar Context Menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="New File", command=self._context_new_file)
        self.context_menu.add_command(label="New Folder", command=self._context_new_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Cut", command=self._context_cut)
        self.context_menu.add_command(label="Copy", command=self._context_copy)
        self.context_menu.add_command(label="Paste", command=self._context_paste)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Rename", command=self._context_rename)
        self.context_menu.add_command(label="Delete", command=self._context_delete)

        # 2. Right Content Area (Editor & Topbar)
        content_frame = ttk.Frame(main_pane, padding=10)
        main_pane.add(content_frame, weight=4)

        # Top Bar Controls
        top_bar = ttk.Frame(content_frame)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(top_bar, text="WYSIWYG View", command=lambda: self.switch_view("wysiwyg")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_bar, text="Raw View", command=lambda: self.switch_view("raw")).pack(side=tk.LEFT, padx=2)

        ttk.Label(top_bar, text="Primary Key:").pack(side=tk.LEFT, padx=(15, 5))
        self.pk_combobox = ttk.Combobox(top_bar, textvariable=self.primary_key_var, width=15)
        self.pk_combobox.pack(side=tk.LEFT, padx=2)

        ttk.Button(top_bar, text="Save JSON", command=self.save_active_file).pack(side=tk.RIGHT, padx=5)

        # Workspace Container (Swaps between WYSIWYG and Raw Text View)
        self.workspace_frame = ttk.Frame(content_frame)
        self.workspace_frame.pack(fill=tk.BOTH, expand=True)

        # Raw Text Editor Widget (Hidden by default)
        self.raw_text_area = tk.Text(self.workspace_frame, wrap=tk.NONE, font=("Consolas", 10))
        
        # Scrollable WYSIWYG Form Construction Area
        self.wysiwyg_canvas = tk.Canvas(self.workspace_frame)
        self.wysiwyg_scrollbar = ttk.Scrollbar(self.workspace_frame, orient=tk.VERTICAL, command=self.wysiwyg_canvas.yview)
        self.wysiwyg_inner_frame = ttk.Frame(self.wysiwyg_canvas)

        self.wysiwyg_inner_frame.bind(
            "<Configure>",
            lambda e: self.wysiwyg_canvas.configure(scrollregion=self.wysiwyg_canvas.bbox("all"))
        )
        self.wysiwyg_canvas.create_window((0, 0), window=self.wysiwyg_inner_frame, anchor="nw")
        self.wysiwyg_canvas.configure(yscrollcommand=self.wysiwyg_scrollbar.set)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(content_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, pady=(5, 0))

        self.switch_view("wysiwyg")

    # -------------------------------------------------------------------
    # Directory Tree Operations (createFile Integration)
    # -------------------------------------------------------------------

    def refresh_sidebar(self):
        """Loads project directory structure into the sidebar tree."""
        def task():
            return createFile.list_directory_contents("")

        def callback(tree_data):
            self.file_tree.delete(*self.file_tree.get_children())
            self._populate_sidebar_node("", tree_data)
            self.status_var.set("Directory refreshed.")

        self.run_in_background(task, callback)

    def _populate_sidebar_node(self, parent_id: str, nodes: List[Dict[str, Any]]):
        for node in nodes:
            item_id = self.file_tree.insert(
                parent_id,
                tk.END,
                text=node["name"],
                values=(node["rel_path"], node["type"]),
                open=False
            )
            if node["type"] == "folder" and "children" in node:
                self._populate_sidebar_node(item_id, node["children"])

    def _on_tree_file_select(self, event):
        selected_item = self.file_tree.selection()
        if not selected_item:
            return
        rel_path, item_type = self.file_tree.item(selected_item[0])["values"]
        if item_type == "file":
            self.load_json_to_editor(rel_path)

    # -------------------------------------------------------------------
    # Context Menu Actions (Sidebar Cut, Copy, Paste, Rename, Delete)
    # -------------------------------------------------------------------

    def _show_context_menu(self, event):
        item = self.file_tree.identify_row(event.y)
        if item:
            self.file_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _context_new_file(self):
        parent_rel = self._get_selected_folder_rel_path()
        name = simpledialog.askstring("New File", "Enter JSON file name:", parent=self.root)
        if name:
            self.run_in_background(createFile.create_file, lambda _: self.refresh_sidebar(), name, parent_rel)

    def _context_new_folder(self):
        parent_rel = self._get_selected_folder_rel_path()
        name = simpledialog.askstring("New Folder", "Enter folder name:", parent=self.root)
        if name:
            self.run_in_background(createFile.create_folder, lambda _: self.refresh_sidebar(), name, parent_rel)

    def _context_cut(self):
        selected = self.file_tree.selection()
        if selected:
            rel_path = self.file_tree.item(selected[0])["values"][0]
            self.clipboard_data = (rel_path, "cut")
            self.status_var.set(f"Cut: '{rel_path}'")

    def _context_copy(self):
        selected = self.file_tree.selection()
        if selected:
            rel_path = self.file_tree.item(selected[0])["values"][0]
            self.clipboard_data = (rel_path, "copy")
            self.status_var.set(f"Copied: '{rel_path}'")

    def _context_paste(self):
        if not self.clipboard_data:
            return
        src_path, action = self.clipboard_data
        target_folder = self._get_selected_folder_rel_path()

        def task():
            return createFile.clipboard_operation(src_path, target_folder, action)

        def callback(_):
            self.clipboard_data = None
            self.refresh_sidebar()

        self.run_in_background(task, callback)

    def _context_rename(self):
        selected = self.file_tree.selection()
        if not selected:
            return
        rel_path = self.file_tree.item(selected[0])["values"][0]
        new_name = simpledialog.askstring("Rename", "Enter new name:", parent=self.root)
        if new_name:
            self.run_in_background(createFile.rename_item, lambda _: self.refresh_sidebar(), rel_path, new_name)

    def _context_delete(self):
        selected = self.file_tree.selection()
        if not selected:
            return
        rel_path = self.file_tree.item(selected[0])["values"][0]
        if messagebox.askyesno("Confirm Delete", f"Delete '{rel_path}' permanently?"):
            self.run_in_background(createFile.delete_item, lambda _: self.refresh_sidebar(), rel_path)

    def _get_selected_folder_rel_path(self) -> str:
        selected = self.file_tree.selection()
        if not selected:
            return ""
        rel_path, item_type = self.file_tree.item(selected[0])["values"]
        return rel_path if item_type == "folder" else os.path.dirname(rel_path)

    # -------------------------------------------------------------------
    # JSON Loading & Parsing (readjson Integration)
    # -------------------------------------------------------------------

    def load_json_to_editor(self, rel_path: str):
        """Reads JSON using readjson off the main thread and populates GUI controls."""
        self.active_rel_path = rel_path
        self.status_var.set(f"Loading '{rel_path}'...")

        def task():
            return readjson.load_json_file(rel_path)

        def callback(payload):
            data, detected_pk = payload
            self.active_json_data = data
            self.primary_key_var.set(detected_pk or "")
            self._update_pk_combobox_options(data)
            
            # Sync Raw View Text
            self.raw_text_area.delete("1.0", tk.END)
            self.raw_text_area.insert("1.0", json.dumps(data, indent=2))
            
            # Sync WYSIWYG Form
            self._build_wysiwyg_form(data)
            self.status_var.set(f"Active File: '{rel_path}'")

        self.run_in_background(task, callback)

    # -------------------------------------------------------------------
    # WYSIWYG Form Builder (Custom Text-Box Based Editor)
    # -------------------------------------------------------------------

    def switch_view(self, mode: str):
        """Switches between WYSIWYG Form view and Raw Text View."""
        self.current_view_mode = mode
        if mode == "wysiwyg":
            self.raw_text_area.pack_forget()
            self.wysiwyg_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.wysiwyg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.wysiwyg_canvas.pack_forget()
            self.wysiwyg_scrollbar.pack_forget()
            self.raw_text_area.pack(fill=tk.BOTH, expand=True)

    def _build_wysiwyg_form(self, json_data: Any):
        """Dynamically constructs input text boxes based on JSON tree nodes."""
        for widget in self.wysiwyg_inner_frame.winfo_children():
            widget.destroy()

        self.form_entries.clear()
        tree_nodes = readjson.build_tree_nodes(json_data)

        # Header Control to add new root fields
        top_ctrl = ttk.Frame(self.wysiwyg_inner_frame)
        top_ctrl.pack(fill=tk.X, pady=5)
        ttk.Button(top_ctrl, text="+ Add Field", command=self._add_field_row).pack(side=tk.LEFT)

        for node in tree_nodes:
            self._render_node_row(self.wysiwyg_inner_frame, node)

    def _render_node_row(self, parent_widget, node: Dict[str, Any]):
        row_frame = ttk.Frame(parent_widget, padding=2)
        row_frame.pack(fill=tk.X, anchor=tk.W)

        key_entry = ttk.Entry(row_frame, width=20)
        key_entry.insert(0, str(node["key"]))
        key_entry.pack(side=tk.LEFT, padx=2)

        ttk.Label(row_frame, text=":").pack(side=tk.LEFT)

        type_var = tk.StringVar(value=node["type"])
        type_cb = ttk.Combobox(
            row_frame,
            textvariable=type_var,
            values=["string", "number", "boolean", "null", "object", "array"],
            state="readonly",
            width=10
        )
        type_cb.pack(side=tk.LEFT, padx=2)

        val_entry = ttk.Entry(row_frame, width=30)
        if node["value"] is not None:
            val_entry.insert(0, str(node["value"]))
        val_entry.pack(side=tk.LEFT, padx=2)

        self.form_entries.append({
            "key": key_entry,
            "type": type_var,
            "val": val_entry,
            "frame": row_frame
        })

    def _add_field_row(self):
        new_node = {"key": "new_key", "value": "", "type": "string", "children": []}
        self._render_node_row(self.wysiwyg_inner_frame, new_node)

    def _update_pk_combobox_options(self, data: Any):
        options = []
        if isinstance(data, dict):
            options = list(data.keys())
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            options = list(data[0].keys())
        self.pk_combobox["values"] = options

    # -------------------------------------------------------------------
    # Save & Serialization (Safe Type Coercion Handling)
    # -------------------------------------------------------------------

    def save_active_file(self):
        """Constructs JSON payload from active view and saves atomically to disk."""
        if not self.active_rel_path:
            messagebox.showwarning("Warning", "No active file selected to save.")
            return

        try:
            if self.current_view_mode == "raw":
                raw_content = self.raw_text_area.get("1.0", tk.END)
                payload = json.loads(raw_content)
            else:
                payload = {}
                for entry in self.form_entries:
                    k = entry["key"].get().strip()
                    if not k:
                        continue
                    t = entry["type"].get()
                    raw_v = entry["val"].get().strip()

                    # Safe type conversion with fallback to string
                    if t == "number":
                        try:
                            v = float(raw_v) if "." in raw_v else int(raw_v)
                        except ValueError:
                            v = raw_v  # Fallback to string if parsing as number fails
                    elif t == "boolean":
                        v = raw_v.lower() in ("true", "1", "yes")
                    elif t == "null":
                        v = None
                    elif t in ("object", "array"):
                        try:
                            v = json.loads(raw_v) if raw_v else ({} if t == "object" else [])
                        except json.JSONDecodeError:
                            v = raw_v  # Fallback to string if parsing fails
                    else:
                        v = raw_v

                    payload[k] = v

            # Save payload to disk via atomic write
            abs_path = createFile._resolve_safe_path(self.active_rel_path)

            def task():
                with open(abs_path, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2)

            def callback(_):
                self.status_var.set(f"Saved '{self.active_rel_path}' successfully.")

            self.run_in_background(task, callback)

        except Exception as e:
            messagebox.showerror("Save Error", f"Could not parse or save JSON: {e}")
