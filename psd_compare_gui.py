import customtkinter as ctk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
import argparse
import json
from psd_tools import PSDImage

# UI/UX Pro Max Settings
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def extract_layers(layer, path="", counter=None, depth=0, parent_id=None):
    """Extract metadata using stable layer path hierarchy as key."""
    if counter is None:
        counter = [0]
        
    layers_dict = {}
    current_path = f"{path}/{layer.name}" if path else layer.name
    
    # Use path as primary key to avoid layer_id collision (-1 in Live2D exports)
    key = current_path
    
    props = {
        "id": key,
        "name": layer.name,
        "path": current_path,
        "depth": depth,
        "tree_index": counter[0],
        "parent_id": parent_id,
        "visible": getattr(layer, 'visible', True),
        "kind": getattr(layer, 'kind', 'unknown'),
        "opacity": getattr(layer, 'opacity', 255),
        "blend_mode": str(getattr(layer, 'blend_mode', 'normal')).replace('BlendMode.', ''),
        "offset": getattr(layer, 'offset', (0,0)),
        "text": "",
        "layer_ref": layer
    }
    
    if props["kind"] == "type":
        try:
            if hasattr(layer, 'text') and layer.text:
                props["text"] = str(layer.text).strip()
        except Exception:
            props["text"] = "[Unreadable]"
            
    layers_dict[key] = props
    counter[0] += 1
    
    # Recurse if group
    is_group = layer.is_group() if callable(getattr(layer, 'is_group', None)) else getattr(layer, 'is_group', False)
    if is_group:
        for child in layer:
            layers_dict.update(extract_layers(child, current_path, counter, depth + 1, key))
            
    return layers_dict

from PIL import Image

def get_thumb(layer):
    try:
        is_group = layer.is_group() if callable(getattr(layer, 'is_group', None)) else getattr(layer, 'is_group', False)
        if is_group:
            return None
        has_pixels = getattr(layer, 'has_pixels', None)
        if callable(has_pixels) and not has_pixels():
            return None
            
        img = layer.topil()
        if img:
            img.thumbnail((60, 60), Image.Resampling.BOX)
            return img
    except Exception:
        pass
    return None

def compare_psd_data(dict1, dict2, load_thumbnails=False):
    """Compare two extracted dictionaries and return structured stats and changes."""
    all_keys = set(dict1.keys()).union(set(dict2.keys()))
    stats = {"added": 0, "removed": 0, "modified": 0}
    
    temp_results = {}
    
    for key in all_keys:
        if key not in dict1:
            l2 = dict2[key]
            temp_results[key] = {
                "status": "🟢 Added", "path": l2["path"], "name": l2["name"], "visible": l2["visible"], "depth": l2["depth"], "kind": l2.get("kind", "unknown"),
                "details": "New Layer Created", "tag": "added",
                "thumb_before": None, "thumb_after": get_thumb(l2["layer_ref"]) if load_thumbnails else None
            }
            stats["added"] += 1
        elif key not in dict2:
            l1 = dict1[key]
            temp_results[key] = {
                "status": "🔴 Removed", "path": l1["path"], "name": l1["name"], "visible": l1["visible"], "depth": l1["depth"], "kind": l1.get("kind", "unknown"),
                "details": "Layer Deleted", "tag": "removed",
                "thumb_before": get_thumb(l1["layer_ref"]) if load_thumbnails else None, "thumb_after": None
            }
            stats["removed"] += 1
        else:
            l1 = dict1[key]
            l2 = dict2[key]
            changes = []
            
            if l1["name"] != l2["name"]:
                changes.append(f"Renamed: '{l1['name']}' -> '{l2['name']}'")
            if l1["path"] != l2["path"] and l1["name"] == l2["name"]:
                changes.append("Moved to different group")
            if l1["visible"] != l2["visible"]:
                changes.append(f"Visibility: {'Visible' if l2['visible'] else 'Hidden'}")
            if l1["opacity"] != l2["opacity"]:
                changes.append(f"Opacity: {int(l2['opacity']/255*100)}%")
            if l1["blend_mode"] != l2["blend_mode"]:
                changes.append(f"Blend: {l2['blend_mode']}")
            if l1["offset"] != l2["offset"]:
                dx = l2["offset"][0] - l1["offset"][0]
                dy = l2["offset"][1] - l1["offset"][1]
                changes.append(f"Move: X{'+' if dx>0 else ''}{dx}, Y{'+' if dy>0 else ''}{dy}")
            if l1["kind"] == "type" and l1["text"] != l2["text"]:
                changes.append("Text Edited")
                
            if changes:
                temp_results[key] = {
                    "status": "🔵 Modified", "path": l2["path"], "name": l2["name"], "visible": l2["visible"], "depth": l2["depth"], "kind": l2.get("kind", "unknown"),
                    "details": " | ".join(changes), "tag": "modified",
                    "thumb_before": get_thumb(l1["layer_ref"]) if load_thumbnails else None, 
                    "thumb_after": get_thumb(l2["layer_ref"]) if load_thumbnails else None
                }
                stats["modified"] += 1
                
    # Build tree context with cycle protection
    keys_to_show = set(temp_results.keys())
    for key in list(keys_to_show):
        for d in (dict2, dict1):
            curr = d.get(key)
            visited = {key}
            while curr and curr.get("parent_id"):
                p_id = curr["parent_id"]
                if p_id in visited:
                    break
                visited.add(p_id)
                keys_to_show.add(p_id)
                curr = d.get(p_id)

    results = []
    def get_sort_key(k):
        if k in dict2: return dict2[k]["tree_index"]
        if k in dict1: return dict1[k]["tree_index"]
        return 0
        
    for key in sorted(keys_to_show, key=get_sort_key):
        if key in temp_results:
            results.append(temp_results[key])
        else:
            l = dict2.get(key) or dict1.get(key)
            results.append({
                "status": "⚪ Context", "path": l["path"], "name": l["name"], "visible": l["visible"], "depth": l["depth"], "kind": l.get("kind", "unknown"),
                "details": "", "tag": "unchanged",
                "thumb_before": None, "thumb_after": None
            })
            
    return stats, results

class PSDCompareProMax(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PSD Compare | Pro Max (System Edition)")
        self.geometry("1100x800")
        self.minsize(900, 600)
        
        try:
            import os
            import sys
            def resource_path(relative_path):
                if hasattr(sys, '_MEIPASS'):
                    return os.path.join(sys._MEIPASS, relative_path)
                return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
            self.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass
        
        self.file1_path = ctk.StringVar()
        self.file2_path = ctk.StringVar()
        self.last_stats = None
        self.last_results = None
        
        self.setup_ui()
        
        # Bind Drag and Drop
        try:
            import windnd
            windnd.hook_dropfiles(self.winfo_id(), self.on_drop)
        except Exception as e:
            print(f"Drag and drop disabled: {e}")
            
    def on_drop(self, files):
        paths = []
        for f in files:
            try:
                paths.append(f.decode('utf-8'))
            except:
                try:
                    paths.append(f.decode('mbcs'))
                except:
                    paths.append(str(f))
        
        if len(paths) == 1:
            if not self.file1_path.get():
                self.file1_path.set(paths[0])
            elif not self.file2_path.get():
                self.file2_path.set(paths[0])
            else:
                self.file1_path.set(paths[0])
        elif len(paths) >= 2:
            self.file1_path.set(paths[0])
            self.file2_path.set(paths[1])
            
    def setup_ui(self):
        # Apply strict Pro Max UI Colors
        bg_color = "#18181B" # Zinc 900
        card_color = "#27272A" # Zinc 800
        border_color = "#3F3F46" # Zinc 700
        text_muted = "#A1A1AA" # Zinc 400
        
        self.configure(fg_color=bg_color)
        
        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(40, 20))
        
        ctk.CTkLabel(header, text="🎨 PSD Compare Pro", font=("Segoe UI", 32, "bold"), text_color="#FFFFFF").pack(anchor="w")
        ctk.CTkLabel(header, text="Deep Metadata Analysis • Structural Tree Diff • Native PDF Export", 
                     font=("Segoe UI", 14), text_color=text_muted).pack(anchor="w", pady=(5, 0))
                     
        # --- Input Section (Drop Zone) ---
        input_frame = ctk.CTkFrame(self, fg_color=card_color, border_width=1, border_color=border_color, corner_radius=12)
        input_frame.pack(fill="x", padx=40, pady=10)
        
        self.create_file_row(input_frame, "Original PSD (Old)", self.file1_path, 0)
        
        # Divider
        divider = ctk.CTkFrame(input_frame, height=1, fg_color=border_color)
        divider.pack(fill="x", padx=20)
        
        self.create_file_row(input_frame, "Modified PSD (New)", self.file2_path, 1)
        
        # --- Action Toolbar ---
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=40, pady=20)
        
        # Primary Action (Right aligned)
        self.btn_compare = ctk.CTkButton(action_frame, text="✨ Analyze Differences", 
                                         font=("Segoe UI", 14, "bold"), height=40, width=190,
                                         fg_color="#2563EB", hover_color="#1D4ED8", corner_radius=8,
                                         command=self.start_compare)
        self.btn_compare.pack(side="right")
        
        self.load_thumbs_var = ctk.BooleanVar(value=False)
        self.chk_thumbs = ctk.CTkCheckBox(action_frame, text="Layer Thumbnails", 
                                          variable=self.load_thumbs_var,
                                          font=("Segoe UI", 12), text_color=text_muted,
                                          fg_color="#2563EB", hover_color="#1D4ED8")
        self.chk_thumbs.pack(side="right", padx=15)
        
        self.progress = ctk.CTkProgressBar(action_frame, mode="indeterminate", width=120, fg_color=card_color, progress_color="#2563EB")
        self.progress.set(0)
        
        # Secondary Actions (Left aligned)
        self.btn_visual = ctk.CTkButton(action_frame, text="👁️ Web Slider", 
                                         font=("Segoe UI", 13, "bold"), height=40, width=140,
                                         fg_color=card_color, hover_color=border_color, text_color="#FFFFFF", border_width=1, border_color=border_color, corner_radius=8,
                                         command=self.start_visual_compare)
        self.btn_visual.pack(side="left", padx=(0, 10))
        
        self.btn_export = ctk.CTkButton(action_frame, text="📄 Export PDF", 
                                         font=("Segoe UI", 13, "bold"), height=40, width=140,
                                         fg_color=card_color, hover_color=border_color, text_color="#FFFFFF", border_width=1, border_color=border_color, corner_radius=8,
                                         command=self.export_report)
        self.btn_export.pack(side="left", padx=10)
        
        self.btn_save_diff = ctk.CTkButton(action_frame, text="💾 Save Diff PSD", 
                                         font=("Segoe UI", 13, "bold"), height=40, width=140,
                                         fg_color=card_color, hover_color=border_color, text_color="#FFFFFF", border_width=1, border_color=border_color, corner_radius=8,
                                         command=self.save_diff_psd)
        self.btn_save_diff.pack(side="left", padx=10)
        
        self.summary_label = ctk.CTkLabel(action_frame, text="", font=("Segoe UI", 14, "bold"))
        self.summary_label.pack(side="right", padx=20)
        
        # --- Table Section ---
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=40, pady=(0, 40))
        self.setup_table(table_frame)
        
    def create_file_row(self, parent, label_text, str_var, row):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(row_frame, text=label_text, font=("Segoe UI", 13, "bold"), text_color="#E4E4E7", width=140, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row_frame, textvariable=str_var, height=36, font=("Segoe UI", 13), 
                             fg_color="#18181B", border_color="#3F3F46", corner_radius=6, placeholder_text="Drag & Drop PSD here or Browse...")
        entry.pack(side="left", fill="x", expand=True, padx=15)
        ctk.CTkButton(row_frame, text="Browse", width=80, height=36, fg_color="#3F3F46", hover_color="#52525B", corner_radius=6,
                      font=("Segoe UI", 12, "bold"), command=lambda: self.browse_file(str_var)).pack(side="right")
                      
    def setup_table(self, parent):
        # Quick Filter Bar
        self.filter_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.filter_frame.pack(fill="x", pady=(0, 10))
        self.filter_buttons = {}
        
        self.scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="#27272A", border_width=1, border_color="#3F3F46", corner_radius=12)
        self.scroll_frame.pack(fill="both", expand=True)
        
        self.image_refs = []
        
        # Header Row (Muted, sleek)
        self.header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(10, 10), padx=10)
        
        text_muted = "#A1A1AA"
        ctk.CTkLabel(self.header_frame, text="👁️", font=("Segoe UI", 12), width=30, text_color=text_muted).pack(side="left", padx=5)
        self.hdr_before = ctk.CTkLabel(self.header_frame, text="BEFORE", font=("Segoe UI", 11, "bold"), width=50, text_color=text_muted)
        self.hdr_before.pack(side="left", padx=5)
        self.hdr_after = ctk.CTkLabel(self.header_frame, text="AFTER", font=("Segoe UI", 11, "bold"), width=50, text_color=text_muted)
        self.hdr_after.pack(side="left", padx=5)
        ctk.CTkLabel(self.header_frame, text="LAYER STRUCTURE", font=("Segoe UI", 11, "bold"), anchor="w", text_color=text_muted).pack(side="left", padx=15, fill="x", expand=True)
        ctk.CTkLabel(self.header_frame, text="STATUS", font=("Segoe UI", 11, "bold"), width=90, text_color=text_muted).pack(side="right", padx=15)
        
        # Divider below header
        ctk.CTkFrame(self.scroll_frame, height=1, fg_color="#3F3F46").pack(fill="x", padx=15, pady=(0, 5))
        
        self.rows_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.rows_container.pack(fill="both", expand=True)
        
        self.empty_label = ctk.CTkLabel(self.rows_container, text="Drop PSDs and click Analyze to begin", font=("Segoe UI", 14), text_color="#71717A")
        self.empty_label.pack(pady=80)
        
    def browse_file(self, str_var):
        path = filedialog.askopenfilename(filetypes=[("PSD Files", "*.psd")])
        if path:
            str_var.set(path)
            
    def start_compare(self):
        f1 = self.file1_path.get().strip().strip('"').strip("'")
        f2 = self.file2_path.get().strip().strip('"').strip("'")
        self.file1_path.set(f1)
        self.file2_path.set(f2)
        
        if not f1 or not f2:
            messagebox.showwarning("Incomplete", "Please select both PSD files.")
            return
            
        self.btn_compare.configure(state="disabled", text="Analyzing...")
        self.progress.pack(side="left", padx=20)
        self.progress.start()
        self.summary_label.configure(text="Analyzing structure...")
        
        # Fast container reset
        self.image_refs.clear()
        if hasattr(self, 'rows_container') and self.rows_container.winfo_exists():
            self.rows_container.destroy()
        self.rows_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.rows_container.pack(fill="both", expand=True)
        
        load_thumbs = self.load_thumbs_var.get()
        threading.Thread(target=self.process_worker, args=(f1, f2, load_thumbs), daemon=True).start()
        
    def process_worker(self, f1, f2, load_thumbs=False):
        try:
            psd1 = PSDImage.open(f1)
            dict1 = {}
            for layer in psd1: dict1.update(extract_layers(layer))
            
            psd2 = PSDImage.open(f2)
            dict2 = {}
            for layer in psd2: dict2.update(extract_layers(layer))
            
            stats, results = compare_psd_data(dict1, dict2, load_thumbnails=load_thumbs)
            
            # Send back to Main UI Thread
            self.after(0, self.show_results, stats, results)
        except Exception as e:
            self.after(0, self.show_error, str(e))
            
    def show_error(self, err):
        self.reset_ui()
        self.summary_label.configure(text="Analysis Failed", text_color="#F87171")
        messagebox.showerror("Error", f"Failed to parse PSD:\n{err}")
        
    def reset_ui(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_compare.configure(state="normal", text="🔍 Analyze Differences")
        
    def start_visual_compare(self):
        f1 = self.file1_path.get().strip().strip('"').strip("'")
        f2 = self.file2_path.get().strip().strip('"').strip("'")
        if not f1 or not f2:
            messagebox.showwarning("Incomplete", "Please select both PSD files.")
            return
            
        self.btn_visual.configure(state="disabled", text="Generating...")
        
        # Run in thread so GUI doesn't freeze
        threading.Thread(target=self.generate_visual_worker, args=(f1, f2), daemon=True).start()
        
    def save_diff_psd(self):
        try:
            f1 = self.file1_path.get().strip().strip('"').strip("'")
            f2 = self.file2_path.get().strip().strip('"').strip("'")
            
            if not f1 or not f2:
                self.summary_label.configure(text="⚠️ Please select both PSD files first!", text_color="#EF4444")
                messagebox.showwarning("Incomplete", "Please select or drop both PSD files first.")
                return
                
            if not os.path.exists(f2):
                self.summary_label.configure(text="⚠️ Modified PSD file not found!", text_color="#EF4444")
                messagebox.showerror("Error", f"Modified PSD file not found:\n{f2}")
                return
                
            # If user hasn't clicked Analyze yet, auto-analyze on the fly!
            if not self.last_results:
                self.summary_label.configure(text="Analyzing structure for diff...", text_color="#93C5FD")
                self.update_idletasks()
                try:
                    psd1 = PSDImage.open(f1)
                    dict1 = {}
                    for l in psd1: dict1.update(extract_layers(l))
                    psd2 = PSDImage.open(f2)
                    dict2 = {}
                    for l in psd2: dict2.update(extract_layers(l))
                    stats, results = compare_psd_data(dict1, dict2, load_thumbnails=False)
                    self.last_stats = stats
                    self.last_results = results
                    self.show_results(stats, results)
                except Exception as e:
                    self.summary_label.configure(text=f"⚠️ Analysis failed: {e}", text_color="#EF4444")
                    messagebox.showerror("Error", f"Failed to analyze PSDs:\n{e}")
                    return
                
            init_dir = os.path.dirname(f2) if os.path.exists(f2) else ""
            out_path = filedialog.asksaveasfilename(
                title="Save Diff PSD (Added/Modified Layers Only)",
                initialdir=init_dir,
                defaultextension=".psd",
                initialfile="Modified_Diff_Only.psd",
                filetypes=[("PSD Files", "*.psd")]
            )
            if not out_path:
                return
                
            self.btn_save_diff.configure(state="disabled", text="Saving...")
            self.summary_label.configure(text="Saving Diff PSD...", text_color="#93C5FD")
            threading.Thread(target=self.save_diff_worker, args=(f2, out_path), daemon=True).start()
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            with open(r"D:\Ai\PSD-Compare-ProMax\save_diff_log.txt", "a", encoding="utf-8") as f:
                f.write(f"UI Error:\n{err}\n")
            messagebox.showerror("Error", f"Save action failed:\n{e}")
        
    def save_diff_worker(self, f2, out_path):
        try:
            changed_paths = set()
            for r in self.last_results:
                if r.get("tag") in ("added", "modified"):
                    changed_paths.add(r["path"])
                    
            from psd_tools import PSDImage
            psd = PSDImage.open(f2)
            
            def prune_layer(parent_group, current_path=""):
                for child in reversed(list(parent_group)):
                    child_path = f"{current_path}/{child.name}" if current_path else child.name
                    is_group = child.is_group() if callable(getattr(child, 'is_group', None)) else getattr(child, 'is_group', False)
                    
                    if is_group:
                        prune_layer(child, child_path)
                        if len(child) == 0:
                            parent_group.remove(child)
                    else:
                        if child_path not in changed_paths:
                            parent_group.remove(child)
                            
            prune_layer(psd)
            # Write record directly to avoid slow 6000x6000 software composite rendering in Python
            with open(out_path, "wb") as f:
                psd._record.write(f)
                
            def on_success():
                self.summary_label.configure(text="✅ Diff PSD Saved!", text_color="#10B981")
                # Open folder and select file in Windows Explorer
                try:
                    import subprocess
                    subprocess.Popen(f'explorer /select,"{os.path.normpath(out_path)}"')
                except Exception:
                    pass
                messagebox.showinfo("Success", f"Saved Diff PSD to:\n{out_path}")
                
            self.after(0, on_success)
            
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            with open(r"D:\Ai\_automation\error_log.txt", "a") as f:
                f.write("Save Diff Error:\n" + err_msg + "\n")
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to save Diff PSD:\n{str(e)}"))
        finally:
            self.after(0, lambda: self.btn_save_diff.configure(state="normal", text="💾 Save Diff PSD"))
            
    def generate_visual_worker(self, f1, f2):
        try:
            import os
            import webbrowser
            output_dir = os.path.dirname(os.path.abspath(__file__))
            
            psd1 = PSDImage.open(f1)
            img1 = psd1.topil()
            img1_path = os.path.join(output_dir, "old.png")
            img1.save(img1_path)
            
            psd2 = PSDImage.open(f2)
            img2 = psd2.topil()
            img2_path = os.path.join(output_dir, "new.png")
            img2.save(img2_path)
            
            html_content = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <title>PSD Visual Compare</title>
                <style>
                    body { margin: 0; padding: 20px; font-family: sans-serif; background: #1a1a1a; color: white; display: flex; flex-direction: column; align-items: center; }
                    .compare-container {
                        position: relative;
                        width: 100%;
                        max-width: 1200px;
                        overflow: hidden;
                        border: 2px solid #333;
                        border-radius: 8px;
                    }
                    .compare-container img { display: block; width: 100%; height: auto; }
                    .img-background { display: block; }
                    .img-foreground {
                        position: absolute; top: 0; left: 0; width: 50%; height: 100%;
                        overflow: hidden; border-right: 2px solid #fff;
                    }
                    .img-foreground div { width: 100%; }
                    .img-foreground img { width: 100%; height: auto; }
                    .slider { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: ew-resize; }
                    .slider-button {
                        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                        width: 40px; height: 40px; background: white; border-radius: 50%;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.3); pointer-events: none;
                        display: flex; justify-content: center; align-items: center;
                    }
                    .slider-button::before, .slider-button::after { content: ''; border-top: 6px solid transparent; border-bottom: 6px solid transparent; }
                    .slider-button::before { border-right: 8px solid #333; margin-right: 4px; }
                    .slider-button::after { border-left: 8px solid #333; margin-left: 4px; }
                </style>
            </head>
            <body>
                <h1>👁️ Visual Diff (Before & After)</h1>
                <p>Drag the slider to compare. <b>Left side: New PSD | Right side: Old PSD</b></p>
                
                <div class="compare-container">
                    <img class="img-background" src="old.png" alt="Original (Old)">
                    <div class="img-foreground" id="foreground">
                        <div id="innerWrapper"><img src="new.png" alt="Modified (New)" id="innerImg"></div>
                    </div>
                    <input type="range" min="0" max="100" value="50" class="slider" id="slider">
                    <div class="slider-button" id="slider-button"></div>
                </div>

                <script>
                    const slider = document.getElementById('slider');
                    const foreground = document.getElementById('foreground');
                    const sliderBtn = document.getElementById('slider-button');
                    const container = document.querySelector('.compare-container');
                    const innerWrapper = document.getElementById('innerWrapper');
                    const innerImg = document.getElementById('innerImg');
                    
                    function updateWidths() {
                        const w = container.getBoundingClientRect().width;
                        innerWrapper.style.width = w + 'px';
                        innerImg.style.width = w + 'px';
                    }
                    window.addEventListener('resize', updateWidths);
                    document.querySelector('.img-background').onload = updateWidths;
                    updateWidths();

                    slider.addEventListener('input', (e) => {
                        const val = e.target.value;
                        foreground.style.width = val + '%';
                        sliderBtn.style.left = val + '%';
                    });
                </script>
            </body>
            </html>
            """
            html_path = os.path.join(output_dir, "compare.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            webbrowser.open(html_path)
            self.after(0, lambda: self.btn_visual.configure(state="normal", text="👁️ Visual Compare (Slider)"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Visual compare failed:\n{e}"))
            self.after(0, lambda: self.btn_visual.configure(state="normal", text="👁️ Visual Compare (Slider)"))

    def export_report(self):
        try:
            if not self.last_results and not self.last_stats:
                messagebox.showwarning("Empty", "Please run Analysis first before exporting.", parent=self)
                return
                
            from fpdf import FPDF
            import os
            
            report_path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".pdf",
                initialfile="PSD_Compare_Report.pdf",
                filetypes=[("PDF Report", "*.pdf")]
            )
            if not report_path:
                return
                
            self.btn_export.configure(state="disabled", text="Generating PDF...")
            
            def build_pdf():
                try:
                    pdf = FPDF()
                    pdf.add_page()
                    
                    font_path = r"C:\Windows\Fonts\tahoma.ttf"
                    font_bold = r"C:\Windows\Fonts\tahomabd.ttf"
                    
                    if os.path.exists(font_path):
                        pdf.add_font("Tahoma", "", font_path, uni=True)
                        pdf.add_font("Tahoma", "B", font_bold if os.path.exists(font_bold) else font_path, uni=True)
                        pdf.set_font("Tahoma", "", 12)
                    else:
                        pdf.set_font("Arial", "", 12)
                        
                    pdf.set_font(pdf.font_family, "B", 16)
                    pdf.cell(0, 10, "PSD Compare Report", ln=True, align="C")
                    pdf.ln(5)
                    
                    total = sum(self.last_stats.values())
                    pdf.set_font(pdf.font_family, "", 12)
                    pdf.cell(0, 10, f"Changes Found: {total} (+{self.last_stats['added']}  -{self.last_stats['removed']}  ~{self.last_stats['modified']})", ln=True)
                    pdf.ln(5)
                    
                    # Keep images in memory for fpdf
                    for r in self.last_results:
                        tag = r["tag"]
                        status = r["status"].split(" ")[1] if " " in r["status"] else r["status"]
                        if status == "Context": status = "Folder"
                        
                        pdf.set_font(pdf.font_family, "B", 10)
                        prefix = "  " * r.get("depth", 0) + ("-> " if r.get("depth", 0) > 0 else "")
                        pdf.cell(0, 8, f"[{status}] {prefix}{r['name']}", ln=True)
                        
                        pdf.set_font(pdf.font_family, "", 9)
                        pdf.set_text_color(100, 100, 100)
                        pdf.cell(0, 6, f"Path: {r['path']}", ln=True)
                        if r["details"]:
                            pdf.cell(0, 6, f"Details: {r['details']}", ln=True)
                        pdf.set_text_color(0, 0, 0)
                        
                        # Thumbnails
                        t_before = r.get("thumb_before")
                        t_after = r.get("thumb_after")
                        
                        y_before_img = pdf.get_y()
                        if t_before or t_after:
                            if t_before:
                                try:
                                    pdf.image(t_before, x=pdf.get_x() + 10, y=y_before_img, w=15, h=15)
                                except: pass
                            if t_after:
                                try:
                                    pdf.image(t_after, x=pdf.get_x() + 40, y=y_before_img, w=15, h=15)
                                except: pass
                            pdf.ln(16)
                        else:
                            pdf.ln(2)
                            
                        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
                        pdf.ln(2)
                        
                    pdf.output(report_path)
                    
                    import webbrowser
                    webbrowser.open(f"file:///{report_path.replace(chr(92), '/')}")
                except Exception as e:
                    import traceback
                    with open(r"D:\Ai\_automation\error_log.txt", "a") as f:
                        f.write("PDF Export Error:\n" + traceback.format_exc() + "\n")
                    self.after(0, lambda e=e: messagebox.showerror("PDF Error", f"Failed to build PDF:\n{str(e)}", parent=self))
                finally:
                    self.after(0, lambda: self.btn_export.configure(state="normal", text="📄 Export PDF"))
                    
            import threading
            threading.Thread(target=build_pdf, daemon=True).start()
            
        except Exception as e:
            import traceback
            with open(r"D:\Ai\_automation\error_log.txt", "a") as f:
                f.write(traceback.format_exc() + "\n")
            messagebox.showerror("Export Failed", f"An error occurred:\n{str(e)}", parent=self)
        
    def show_results(self, stats, results):
        self.reset_ui()
        self.last_stats = stats
        self.last_results = results
        
        self.setup_filter_tabs(stats, results)
        self.display_items(results)
        
    def setup_filter_tabs(self, stats, results):
        for widget in self.filter_frame.winfo_children():
            widget.destroy()
            
        total_changes = stats["added"] + stats["removed"] + stats["modified"]
        
        filters = [
            ("all", f"All ({len(results)})", None),
            ("changes", f"⚡ Changes Only ({total_changes})", "#2563EB"),
            ("added", f"🟢 Added ({stats['added']})", "#10B981"),
            ("removed", f"🔴 Removed ({stats['removed']})", "#EF4444"),
            ("modified", f"🔵 Modified ({stats['modified']})", "#3B82F6"),
        ]
        
        self.active_filter = "all"
        for fid, text, color in filters:
            btn = ctk.CTkButton(
                self.filter_frame, text=text, height=32,
                fg_color="#2563EB" if fid == "all" else "#27272A",
                hover_color="#3F3F46", text_color="#FFFFFF",
                font=("Segoe UI", 12, "bold"),
                command=lambda f=fid: self.apply_filter(f)
            )
            btn.pack(side="left", padx=(0, 8))
            self.filter_buttons[fid] = btn
            
    def apply_filter(self, fid):
        self.active_filter = fid
        for k, btn in self.filter_buttons.items():
            btn.configure(fg_color="#2563EB" if k == fid else "#27272A")
            
        if fid == "all":
            items = self.last_results
        elif fid == "changes":
            items = [r for r in self.last_results if r["tag"] in ("added", "removed", "modified")]
        else:
            items = [r for r in self.last_results if r["tag"] == fid]
            
        self.display_items(items)

    def display_items(self, items):
        if hasattr(self, 'rows_container') and self.rows_container.winfo_exists():
            self.rows_container.destroy()
        self.rows_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.rows_container.pack(fill="both", expand=True)
        self.image_refs.clear()
        
        if not items:
            lbl = ctk.CTkLabel(self.rows_container, text="No layers match this filter", font=("Segoe UI", 14), text_color="#71717A")
            lbl.pack(pady=60)
            return
            
        self._current_render_items = items
        self._render_batch(0)
        
    def _render_batch(self, start_idx):
        if not hasattr(self, 'rows_container') or not self.rows_container.winfo_exists():
            return
            
        batch_size = 35
        items = self._current_render_items
        end_idx = min(start_idx + batch_size, len(items))
        
        has_thumbs = self.load_thumbs_var.get()
        
        for i in range(start_idx, end_idx):
            self.render_single_row(self.rows_container, items[i], has_thumbs)
            
        if end_idx < len(items):
            self.summary_label.configure(text=f"Loaded {end_idx}/{len(items)} layers...")
            self.after(2, self._render_batch, end_idx)
        else:
            total = sum(self.last_stats.values()) if self.last_stats else 0
            if total == 0:
                self.summary_label.configure(text="✅ Files are structurally identical", text_color="#10B981")
            else:
                self.summary_label.configure(
                    text=f"{total} Changes (+{self.last_stats['added']} -{self.last_stats['removed']} ~{self.last_stats['modified']})",
                    text_color="#F8FAFC"
                )

    def render_single_row(self, parent, r, has_thumbs=False):
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", pady=1, padx=5)
        
        ctk.CTkFrame(row, height=1, fg_color="#333333").pack(side="bottom", fill="x", padx=5)
        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(fill="x", pady=3)
        
        # Eye icon
        eye_text = "👁️" if r["visible"] else "⬛"
        ctk.CTkLabel(content, text=eye_text, font=("Segoe UI", 13), width=25).pack(side="left", padx=2)
        
        # Thumbnails if enabled
        if has_thumbs:
            def add_thumb(p, img_pil):
                if img_pil:
                    ctk_img = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(img_pil.width, img_pil.height))
                    self.image_refs.append(ctk_img)
                    ctk.CTkLabel(p, image=ctk_img, text="", width=45, height=45, fg_color="#18181B", corner_radius=4).pack(side="left", padx=3)
                else:
                    ctk.CTkLabel(p, text="--", text_color="#52525B", width=45, height=45, fg_color="#18181B", corner_radius=4).pack(side="left", padx=3)
            add_thumb(content, r.get("thumb_before"))
            if r["tag"] == "modified":
                ctk.CTkLabel(content, text="➡️", text_color="#71717A", font=("Segoe UI", 11), width=16).pack(side="left")
            add_thumb(content, r.get("thumb_after"))
            
        # Info
        info_frame = ctk.CTkFrame(content, fg_color="transparent")
        padding_x = 10 + (r.get("depth", 0) * 18)
        info_frame.pack(side="left", padx=(padding_x, 10), fill="y", pady=2)
        
        kind_icons = {
            "group": "📁", "type": "T", "shape": "⬛", "pixel": "🖼️", "smartobject": "🔗"
        }
        icon = kind_icons.get(r.get("kind", "unknown"), "📄")
        name_prefix = "↳ " if r.get("depth", 0) > 0 else ""
        name_text = f"{name_prefix}{icon} {r['name']}"
        
        ctk.CTkLabel(info_frame, text=name_text, font=("Segoe UI", 13, "bold"), text_color="#F4F4F5", anchor="w").pack(fill="x")
        ctk.CTkLabel(info_frame, text=f"Path: {r['path']}", font=("Segoe UI", 10), text_color="#71717A", anchor="w").pack(fill="x")
        if r.get("details"):
            ctk.CTkLabel(info_frame, text=r["details"], font=("Segoe UI", 10), text_color="#93C5FD", anchor="w").pack(fill="x")
            
        # Status Badge
        color_map = {"added": "#10B981", "removed": "#EF4444", "modified": "#3B82F6", "unchanged": "#3F3F46"}
        badge_color = color_map.get(r["tag"], "#333")
        badge = ctk.CTkFrame(content, fg_color=badge_color, corner_radius=6)
        badge.pack(side="right", padx=10)
        
        status_text = r["status"].split(" ")[1] if " " in r["status"] else r["status"]
        if status_text == "Context": status_text = "Folder"
        ctk.CTkLabel(badge, text=status_text.upper(), font=("Segoe UI", 10, "bold"), text_color="#FFFFFF", width=65, height=22).pack(padx=8, pady=2)

# --- CLI Headless Mode (Automation API) ---
def run_cli_mode(f1, f2, output_json):
    try:
        psd1 = PSDImage.open(f1)
        dict1 = {}
        for layer in psd1: dict1.update(extract_layers(layer))
        
        psd2 = PSDImage.open(f2)
        dict2 = {}
        for layer in psd2: dict2.update(extract_layers(layer))
        
        stats, results = compare_psd_data(dict1, dict2)
        
        final_output = {
            "status": "success",
            "stats": stats,
            "changes": results
        }
        
        with open(output_json, 'w', encoding='utf-8') as f:
            # Drop the heavy PIL objects before JSON dump
            for r in results:
                r.pop("thumb_before", None)
                r.pop("thumb_after", None)
            json.dump(final_output, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Success! Report exported to {output_json}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if run as CLI
    parser = argparse.ArgumentParser(description="PSD Systems Analyzer (Pro Max)")
    parser.add_argument("--file1", help="Path to original PSD")
    parser.add_argument("--file2", help="Path to modified PSD")
    parser.add_argument("--json", help="Path to export JSON output")
    parser.add_argument("--diff-psd", help="Path to export Diff PSD output directly")
    
    args = parser.parse_args()
    
    if args.file1 and args.file2 and (args.json or args.diff_psd):
        print("🚀 Running in Headless CLI Mode...")
        if args.json:
            run_cli_mode(args.file1, args.file2, args.json)
        if args.diff_psd:
            print("🚀 Generating Diff PSD via CLI...")
            f1, f2, out_path = args.file1, args.file2, args.diff_psd
            psd1 = PSDImage.open(f1)
            dict1 = {}
            for l in psd1: dict1.update(extract_layers(l))
            psd2 = PSDImage.open(f2)
            dict2 = {}
            for l in psd2: dict2.update(extract_layers(l))
            stats, results = compare_psd_data(dict1, dict2, load_thumbnails=False)
            
            changed_paths = set()
            for r in results:
                if r.get("tag") in ("added", "modified"):
                    changed_paths.add(r["path"])
                    
            psd = PSDImage.open(f2)
            def prune_layer(parent_group, current_path=""):
                for child in reversed(list(parent_group)):
                    child_path = f"{current_path}/{child.name}" if current_path else child.name
                    is_group = child.is_group() if callable(getattr(child, 'is_group', None)) else getattr(child, 'is_group', False)
                    if is_group:
                        prune_layer(child, child_path)
                        if len(child) == 0:
                            parent_group.remove(child)
                    else:
                        if child_path not in changed_paths:
                            parent_group.remove(child)
            prune_layer(psd)
            with open(out_path, "wb") as f:
                psd._record.write(f)
            print(f"✅ Diff PSD exported successfully to {out_path} ({os.path.getsize(out_path)/1024/1024:.2f} MB)")
    else:
        # Run GUI Mode
        app = PSDCompareProMax()
        app.mainloop()

