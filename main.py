import pygame
import fitz  # PyMuPDF
import os
import shutil
import math
import time
import threading
import queue
import tkinter as tk
from tkinter import filedialog

# =============================================================================
# 1. CONFIG & CONSTANTS
# =============================================================================
pygame.init()

screen_info = pygame.display.Info()
MONITOR_W, MONITOR_H = screen_info.current_w, screen_info.current_h

WIDTH = MONITOR_W - 300
HEIGHT = MONITOR_H - 200

FPS = 60
BG_COLOR = (30, 30, 46)
CARD_BG = (49, 50, 68)
ACCENT_COLOR = (203, 166, 247)
TEXT_COLOR = (205, 214, 244)
GLASS_COLOR = (24, 24, 37, 200)
PDF_FOLDER = "pdf_files"
ASSETS_FOLDER = "assets"

CARD_WIDTH = 200
CARD_HEIGHT = 280
GAP = 30
ANIM_SPEED = 10
DOUBLE_CLICK_TIME = 0.3

# Initialize
pygame.font.init()

os.environ['SDL_VIDEO_CENTERED'] = '1'

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("DrawGen")
clock = pygame.time.Clock()

font_sm = pygame.font.SysFont("Segoe UI", 16)
font_md = pygame.font.SysFont("Segoe UI", 20, bold=True)
font_lg = pygame.font.SysFont("Segoe UI", 40, bold=True)
font_num = pygame.font.SysFont("Segoe UI", 30, bold=True)

if not os.path.exists(PDF_FOLDER):
    os.makedirs(PDF_FOLDER)
if not os.path.exists(ASSETS_FOLDER):
    os.makedirs(ASSETS_FOLDER)

# =============================================================================
# 2. UTILS & ENGINE
# =============================================================================

def load_icon(name, size=(30, 30)):
    path = os.path.join(ASSETS_FOLDER, name)
    if os.path.exists(path):
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(img, size)
        except:
            pass
    return None

def lerp(start, end, t):
    return start + (end - start) * t

def draw_rounded_rect(surface, rect, color, radius=10, border=0, border_color=None):
    rect = pygame.Rect(rect)
    color = pygame.Color(*color)
    pos = rect.topleft
    rect.topleft = 0,0
    rectangle = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(rectangle, color, rectangle.get_rect(), border_radius=radius)
    surface.blit(rectangle, pos)
    if border > 0 and border_color:
        pygame.draw.rect(surface, border_color, pygame.Rect(pos, rect.size), border, border_radius=radius)

def draw_spinner(surface, center, radius, color):
    t = time.time() * 10
    start_angle = t % (2 * math.pi)
    end_angle = (start_angle + math.pi / 1.5) % (2 * math.pi)
    rect = pygame.Rect(center[0]-radius, center[1]-radius, radius*2, radius*2)
    pygame.draw.arc(surface, color, rect, start_angle, end_angle, 4)
    pygame.draw.arc(surface, (*color[:3], 100), rect, end_angle, start_angle, 2)

class Tween:
    def __init__(self, value):
        self.val = value
        self.target = value

    def update(self, dt):
        diff = self.target - self.val
        factor = min(ANIM_SPEED * dt, 0.9)
        self.val += diff * factor
        return self.val

    def set(self, target):
        self.target = target

# =============================================================================
# 3. PDF BACKEND (OPTIMIZED)
# =============================================================================
class PDFManager:
    def __init__(self):
        self.doc = None
        self.filename = None
        self.page_count = 0

        # Grid/Thumbnails
        self.thumbnail_cache = {}
        self.thumbnail_queue = queue.Queue()
        self.loader_thread = None
        self.loading_active = False

        # Viewer Rendering
        self.render_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.render_thread = threading.Thread(target=self._render_worker, daemon=True)
        self.render_thread.start()

        # OPTIMIZATION: Base Cache (Low Res Full Page)
        # Structure: { page_num: Surface }
        self.base_images = {}

        # Page size info: { page_num: (width, height) } (PDF units)
        self.page_sizes = {}

    def get_files(self):
        return sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])

    def start_thumbnail_loader(self, file_list):
        if not self.loading_active:
            self.loading_active = True
            self.loader_thread = threading.Thread(target=self._loader_worker, args=(file_list,), daemon=True)
            self.loader_thread.start()

    def _loader_worker(self, file_list):
        for filename in file_list:
            if filename in self.thumbnail_cache:
                continue
            path = os.path.join(PDF_FOLDER, filename)
            try:
                doc = fitz.open(path)
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
                if pix.n != 3: pix = fitz.Pixmap(fitz.csRGB, pix)
                raw_data = bytes(pix.samples)
                size = (pix.width, pix.height)
                self.thumbnail_queue.put((filename, raw_data, size, "RGB"))
                doc.close()
            except Exception as e:
                pass
        self.loading_active = False

    def process_queue(self):
        # Thumbnails
        try:
            while True:
                filename, raw_data, size, mode = self.thumbnail_queue.get_nowait()
                img = pygame.image.frombytes(raw_data, size, mode)
                bg = pygame.Surface(img.get_size())
                bg.fill((255, 255, 255))
                bg.blit(img, (0, 0))
                scaled = pygame.transform.smoothscale(bg, (CARD_WIDTH - 20, int((CARD_WIDTH-20) * 1.414)))
                self.thumbnail_cache[filename] = scaled
        except queue.Empty:
            pass

    def get_thumbnail(self, filename):
        return self.thumbnail_cache.get(filename, None)

    def load_document(self, filename):
        self.filename = filename
        if self.doc: self.doc.close()

        path = os.path.join(PDF_FOLDER, filename)
        self.doc = fitz.open(path)
        self.page_count = self.doc.page_count

        self.base_images = {}
        self.page_sizes = {}

        # Pre-cache current page as low-res immediately
        self._create_base_cache(0)

        return self.page_count

    def _create_base_cache(self, page_num):
        if page_num in self.base_images: return
        try:
            page = self.doc.load_page(page_num)
            rect = page.rect
            self.page_sizes[page_num] = (rect.width, rect.height)

            # Low Res Render (e.g., zoom 0.5 or fixed width ~800px)
            # This is fast and small memory
            scale = 800 / rect.width
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            if pix.n != 3: pix = fitz.Pixmap(fitz.csRGB, pix)

            img = pygame.image.frombuffer(pix.samples, (pix.width, pix.height), "RGB")
            self.base_images[page_num] = img
        except:
            pass

    def get_base_image(self, page_num):
        if page_num not in self.base_images:
            self._create_base_cache(page_num)
        return self.base_images.get(page_num), self.page_sizes.get(page_num)

    def request_render(self, page_num, zoom, clip_rect=None):
        # Clear previous pending renders to avoid lag during fast zoom
        with self.render_queue.mutex:
            self.render_queue.queue.clear()

        self.render_queue.put((page_num, zoom, clip_rect))

    def _render_worker(self):
        while True:
            try:
                # Blocks until an item is available
                data = self.render_queue.get()
                p_num, zoom, clip_rect = data

                if self.doc and not self.doc.is_closed:
                    page = self.doc.load_page(p_num)

                    mat = fitz.Matrix(zoom, zoom)

                    # Optimization: Render ONLY the visible part (clip)
                    if clip_rect:
                        # clip_rect is in PDF coordinates (unscaled)
                        pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
                    else:
                        pix = page.get_pixmap(matrix=mat, alpha=False)

                    if pix.colorspace is None or pix.n != 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)

                    raw = pix.samples
                    size = (pix.width, pix.height)

                    # We pass back the clip_rect too so we know where to place it
                    self.result_queue.put((p_num, zoom, raw, size, clip_rect))

            except Exception as e:
                print(f"Render Error: {e}")

    def get_render_result(self):
        try:
            return self.result_queue.get_nowait()
        except queue.Empty:
            return None

# =============================================================================
# 4. DRAWING ENGINE
# =============================================================================
class DrawingLayer:
    def __init__(self):
        self.strokes = {}
        self.shapes = {}
        self.current_stroke = []

    def start_stroke(self):
        self.current_stroke = []

    def add_point(self, page_idx, point_pdf_space):
        self.current_stroke.append(point_pdf_space)

    def end_stroke(self, page_idx, color, width, tool_type='pen'):
        if len(self.current_stroke) > 0:
            if page_idx not in self.strokes:
                self.strokes[page_idx] = []

            self.strokes[page_idx].append({
                'points': list(self.current_stroke),
                'color': color,
                'width': width,
                'type': tool_type
            })
        self.current_stroke = []

    def add_shape(self, page_idx, shape_type, start_p, end_p, color, width):
        if page_idx not in self.shapes:
            self.shapes[page_idx] = []
        self.shapes[page_idx].append({
            'type': shape_type,
            'start': start_p,
            'end': end_p,
            'color': color,
            'width': width
        })

    def clear_page(self, page_idx):
        if page_idx in self.strokes: del self.strokes[page_idx]
        if page_idx in self.shapes: del self.shapes[page_idx]

    def erase_at(self, page_idx, pos_pdf_space, radius):
        if page_idx in self.strokes:
            px, py = pos_pdf_space
            remaining_strokes = []
            for stroke in self.strokes[page_idx]:
                hit = False
                for p in stroke['points']:
                    if math.hypot(p[0]-px, p[1]-py) < radius:
                        hit = True
                        break
                if not hit:
                    remaining_strokes.append(stroke)
            self.strokes[page_idx] = remaining_strokes

        if page_idx in self.shapes:
            px, py = pos_pdf_space
            remaining_shapes = []
            for shape in self.shapes[page_idx]:
                s = shape['start']
                e = shape['end']
                if math.hypot(s[0]-px, s[1]-py) < radius or math.hypot(e[0]-px, e[1]-py) < radius:
                    continue
                remaining_shapes.append(shape)
            self.shapes[page_idx] = remaining_shapes

    def draw(self, surface, page_idx, offset_x, offset_y, zoom):
        if page_idx in self.shapes:
            for s in self.shapes[page_idx]:
                self._draw_shape(surface, s['type'], s['start'], s['end'], s['color'], s['width'], zoom, offset_x, offset_y)

        if page_idx in self.strokes:
            for s in self.strokes[page_idx]:
                self._draw_stroke(surface, s['points'], s['color'], s['width'], zoom, offset_x, offset_y)

    def _draw_stroke(self, surface, points, color, width, zoom, off_x, off_y):
        if not points: return
        screen_width = max(1, width * zoom)
        radius = max(1, screen_width / 2.0)
        step_size = max(1.0, radius / 2.0)
        prev_p = points[0]

        sx = prev_p[0] * zoom + off_x
        sy = prev_p[1] * zoom + off_y

        # Optimization: Don't draw points outside screen
        # Simple bounding box check could be added here for stroke arrays

        pygame.draw.circle(surface, color, (int(sx), int(sy)), int(radius))

        for i in range(1, len(points)):
            curr_p = points[i]
            cx = curr_p[0] * zoom + off_x
            cy = curr_p[1] * zoom + off_y

            dx = (curr_p[0] - prev_p[0]) * zoom
            dy = (curr_p[1] - prev_p[1]) * zoom
            dist = math.hypot(dx, dy)
            if dist > 0:
                steps = int(dist / step_size)
                for j in range(1, steps + 1):
                    t = j / steps
                    inter_x = (prev_p[0] + (curr_p[0] - prev_p[0]) * t) * zoom + off_x
                    inter_y = (prev_p[1] + (curr_p[1] - prev_p[1]) * t) * zoom + off_y
                    pygame.draw.circle(surface, color, (int(inter_x), int(inter_y)), int(radius))

            pygame.draw.circle(surface, color, (int(cx), int(cy)), int(radius))
            prev_p = curr_p

    def _draw_shape(self, surface, shape_type, start, end, color, width, zoom, off_x, off_y):
        sx = start[0] * zoom + off_x
        sy = start[1] * zoom + off_y
        ex = end[0] * zoom + off_x
        ey = end[1] * zoom + off_y
        w = max(1, int(width * zoom))

        if shape_type == "LINE":
            pygame.draw.line(surface, color, (sx, sy), (ex, ey), w)

        elif shape_type == "RECT":
            left = min(sx, ex)
            top = min(sy, ey)
            rw = abs(ex - sx)
            rh = abs(ey - sy)
            pygame.draw.rect(surface, color, (left, top, rw, rh), w)

        elif shape_type == "CIRCLE":
            cx = (sx + ex) / 2
            cy = (sy + ey) / 2
            radius = math.hypot(ex - sx, ey - sy) / 2
            pygame.draw.circle(surface, color, (int(cx), int(cy)), int(radius), w)

        elif shape_type == "TRIANGLE_EQ":
            mid_x = (sx + ex) / 2
            points = [(mid_x, sy), (sx, ey), (ex, ey)]
            pygame.draw.polygon(surface, color, points, w)

        elif shape_type == "TRIANGLE_RIGHT":
            points = [(sx, sy), (sx, ey), (ex, ey)]
            pygame.draw.polygon(surface, color, points, w)

        elif shape_type == "ARROW":
            pygame.draw.line(surface, color, (sx, sy), (ex, ey), w)
            angle = math.atan2(ey - sy, ex - sx)
            arrow_len = 20 * (zoom if zoom > 0.5 else 0.5)
            arrow_angle = 0.5

            r_angle = angle + math.pi - arrow_angle
            rx = ex + arrow_len * math.cos(r_angle)
            ry = ey + arrow_len * math.sin(r_angle)

            l_angle = angle + math.pi + arrow_angle
            lx = ex + arrow_len * math.cos(l_angle)
            ly = ey + arrow_len * math.sin(l_angle)

            pygame.draw.line(surface, color, (ex, ey), (rx, ry), w)
            pygame.draw.line(surface, color, (ex, ey), (lx, ly), w)

# =============================================================================
# 5. UI WIDGETS
# =============================================================================

class ToolButton:
    def __init__(self, x, y, icon_name, label, w=30, h=30):
        self.rect = pygame.Rect(x, y, w, h)
        self.icon = load_icon(icon_name, size=(w-8, h-8))
        self.label = label
        self.active = False
        self.hovered = False

    def draw(self, surface, override_active_color=None):
        col = (70, 70, 90) if self.active else (50, 50, 70)
        if self.hovered: col = (80, 80, 110)

        draw_rounded_rect(surface, self.rect, col, radius=6)

        if self.active:
            border_col = override_active_color if override_active_color else ACCENT_COLOR
            pygame.draw.rect(surface, border_col, self.rect, 2, border_radius=6)

        if self.icon:
            r = self.icon.get_rect(center=self.rect.center)
            surface.blit(self.icon, r)
        else:
            txt = font_sm.render(self.label, True, TEXT_COLOR)
            surface.blit(txt, txt.get_rect(center=self.rect.center))

class FloatingToolbar:
    def __init__(self, app):
        self.app = app
        self.rect = pygame.Rect(20, 100, 50, 210)
        self.dragging = False
        self.drag_offset = (0, 0)

        self.tool_mode = "HAND" # HAND, PEN, ERASER, SHAPE
        self.pen_color = (200, 50, 50)
        self.pen_size = 3.0
        self.eraser_size = 20.0

        self.current_shape = "LINE"

        self.btn_hand = ToolButton(0, 0, "hand.png", "H", 34, 34)
        self.btn_pen = ToolButton(0, 0, "pen.png", "K", 34, 34)
        self.btn_shape = ToolButton(0, 0, "shape.png", "Ş", 34, 34)
        self.btn_eraser = ToolButton(0, 0, "eraser.png", "S", 34, 34)
        self.btn_clear = ToolButton(0, 0, "trash.png", "Temizle", 34, 34)

        self.show_settings = False
        self.settings_rect = pygame.Rect(0, 0, 160, 240)
        self.active_slider = None
        self.btn_hand.active = True

        self.shape_options = [
            ("LINE", "Çizgi"), ("ARROW", "Ok"),
            ("RECT", "Kare"), ("CIRCLE", "Daire"),
            ("TRIANGLE_EQ", "Eşk. Üçg"), ("TRIANGLE_RIGHT", "Dik Üçg")
        ]

    def update_layout(self):
        pad = 8
        x = self.rect.x + pad
        y = self.rect.y + 10

        self.btn_hand.rect.topleft = (x, y)
        self.btn_pen.rect.topleft = (x, y + 40)
        self.btn_shape.rect.topleft = (x, y + 80)
        self.btn_eraser.rect.topleft = (x, y + 120)
        self.btn_clear.rect.topleft = (x, y + 160)

        self.settings_rect.topleft = (self.rect.right + 10, self.rect.y)

    def handle_event(self, event):
        mx, my = pygame.mouse.get_pos()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.show_settings and self.settings_rect.collidepoint(mx, my):
                if self.handle_settings_press(mx, my): return True
                self.handle_settings_click(mx, my)
                return True

            if self.rect.collidepoint(mx, my):
                if not (self.btn_pen.rect.collidepoint(mx, my) or
                        self.btn_eraser.rect.collidepoint(mx, my) or
                        self.btn_hand.rect.collidepoint(mx, my) or
                        self.btn_shape.rect.collidepoint(mx, my) or
                        self.btn_clear.rect.collidepoint(mx, my)):
                    self.dragging = True
                    self.drag_offset = (mx - self.rect.x, my - self.rect.y)
                    return True

            if self.btn_clear.rect.collidepoint(mx, my):
                target_page = -1 if self.app.scene.show_whiteboard else self.app.scene.current_page
                self.app.scene.drawing_layer.clear_page(target_page)
                return True

            if self.btn_hand.rect.collidepoint(mx, my):
                self.set_tool("HAND")
                return True

            if self.btn_pen.rect.collidepoint(mx, my):
                if self.tool_mode == "PEN": self.show_settings = not self.show_settings
                else: self.set_tool("PEN")
                return True

            if self.btn_shape.rect.collidepoint(mx, my):
                if self.tool_mode == "SHAPE": self.show_settings = not self.show_settings
                else: self.set_tool("SHAPE")
                return True

            if self.btn_eraser.rect.collidepoint(mx, my):
                if self.tool_mode == "ERASER": self.show_settings = not self.show_settings
                else: self.set_tool("ERASER")
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
            self.active_slider = None

        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.rect.x = mx - self.drag_offset[0]
                self.rect.y = my - self.drag_offset[1]
                self.update_layout()

            if self.active_slider:
                sx = self.settings_rect.x
                w = 140
                rel_x = mx - (sx + 10)
                val = max(0.0, min(1.0, rel_x / w))
                if self.active_slider == "PEN_SIZE": self.pen_size = max(1.0, val * 20.0)
                elif self.active_slider == "ERASER_SIZE": self.eraser_size = max(5.0, val * 100.0)

            self.btn_hand.hovered = self.btn_hand.rect.collidepoint(mx, my)
            self.btn_pen.hovered = self.btn_pen.rect.collidepoint(mx, my)
            self.btn_shape.hovered = self.btn_shape.rect.collidepoint(mx, my)
            self.btn_eraser.hovered = self.btn_eraser.rect.collidepoint(mx, my)
            self.btn_clear.hovered = self.btn_clear.rect.collidepoint(mx, my)

        return False

    def set_tool(self, mode):
        self.tool_mode = mode
        self.show_settings = False
        self.update_active_states()

    def update_active_states(self):
        self.btn_hand.active = (self.tool_mode == "HAND")
        self.btn_pen.active = (self.tool_mode == "PEN")
        self.btn_shape.active = (self.tool_mode == "SHAPE")
        self.btn_eraser.active = (self.tool_mode == "ERASER")

    def handle_settings_press(self, mx, my):
        sx, sy = self.settings_rect.x, self.settings_rect.y
        if self.tool_mode == "PEN":
            slider_rect = pygame.Rect(sx + 10, sy + 130, 140, 30)
            if slider_rect.collidepoint(mx, my):
                self.active_slider = "PEN_SIZE"
                return True
        elif self.tool_mode == "ERASER":
            slider_rect = pygame.Rect(sx + 10, sy + 40, 140, 30)
            if slider_rect.collidepoint(mx, my):
                self.active_slider = "ERASER_SIZE"
                return True
        return False

    def handle_settings_click(self, mx, my):
        sx, sy = self.settings_rect.x, self.settings_rect.y

        if self.tool_mode in ["PEN", "SHAPE"]:
            colors = [(0,0,0), (200,50,50), (50,200,50), (50,50,200), (255,255,0), (255,100,255)]
            for i, c in enumerate(colors):
                r = pygame.Rect(sx + 10 + (i%3)*45, sy + 10 + (i//3)*45, 35, 35)
                if r.collidepoint(mx, my):
                    self.pen_color = c
                    return

            spec_rect = pygame.Rect(sx + 10, sy + 100, 140, 20)
            if spec_rect.collidepoint(mx, my):
                rel_x = (mx - spec_rect.x) / spec_rect.w
                self.pen_color = pygame.Color(0)
                self.pen_color.hsva = (rel_x * 360, 100, 100, 100)
                return

        if self.tool_mode == "SHAPE":
            start_y = sy + 140
            for i, (code, name) in enumerate(self.shape_options):
                r = pygame.Rect(sx + 10 + (i%2)*70, start_y + (i//2)*40, 65, 35)
                if r.collidepoint(mx, my):
                    self.current_shape = code
                    return

    def draw(self, surface):
        self.update_layout()
        draw_rounded_rect(surface, self.rect, (40, 40, 55, 220), radius=12, border=1, border_color=(100,100,120))
        for i in range(3):
            pygame.draw.circle(surface, (150,150,170), (self.rect.centerx - 6 + i*6, self.rect.y + 6), 1)

        self.btn_hand.draw(surface)
        self.btn_pen.draw(surface, override_active_color=self.pen_color)
        self.btn_shape.draw(surface, override_active_color=self.pen_color)
        self.btn_eraser.draw(surface)
        self.btn_clear.draw(surface)

        if self.show_settings:
            panel_h = 265 if self.tool_mode == "SHAPE" else 200
            self.settings_rect.height = panel_h

            draw_rounded_rect(surface, self.settings_rect, (35, 35, 50, 240), radius=10, border=1, border_color=ACCENT_COLOR)
            sx, sy = self.settings_rect.x, self.settings_rect.y

            if self.tool_mode == "PEN":
                colors = [(0,0,0), (200,50,50), (50,200,50), (50,50,200), (255,255,0), (255,100,255)]
                for i, c in enumerate(colors):
                    r = pygame.Rect(sx + 10 + (i%3)*45, sy + 10 + (i//3)*45, 35, 35)
                    pygame.draw.rect(surface, c, r, border_radius=5)
                    if c == self.pen_color: pygame.draw.rect(surface, (255,255,255), r, 2, border_radius=5)

                spec_rect = pygame.Rect(sx + 10, sy + 100, 140, 20)
                for i in range(spec_rect.w):
                    c = pygame.Color(0)
                    c.hsva = ((i/spec_rect.w)*360, 100, 100, 100)
                    pygame.draw.line(surface, c, (spec_rect.x+i, spec_rect.y), (spec_rect.x+i, spec_rect.bottom))

                sl_rect = pygame.Rect(sx + 10, sy + 140, 140, 6)
                pygame.draw.rect(surface, (80,80,90), sl_rect, border_radius=3)
                pygame.draw.rect(surface, ACCENT_COLOR, (sl_rect.x, sl_rect.y, (self.pen_size / 20.0)*140, 6), border_radius=3)
                knob_x = sx + 10 + (self.pen_size / 20.0) * 140
                pygame.draw.circle(surface, (255,255,255), (int(knob_x), sl_rect.centery), 8)
                pygame.draw.circle(surface, self.pen_color, (sx + 80, sy + 175), int(self.pen_size))

            elif self.tool_mode == "SHAPE":
                colors = [(0,0,0), (200,50,50), (50,200,50), (50,50,200), (255,255,0), (255,100,255)]
                for i, c in enumerate(colors):
                    r = pygame.Rect(sx + 10 + (i%3)*45, sy + 10 + (i//3)*45, 35, 35)
                    pygame.draw.rect(surface, c, r, border_radius=5)
                    if c == self.pen_color: pygame.draw.rect(surface, (255,255,255), r, 2, border_radius=5)

                spec_rect = pygame.Rect(sx + 10, sy + 100, 140, 20)
                for i in range(spec_rect.w):
                    c = pygame.Color(0)
                    c.hsva = ((i/spec_rect.w)*360, 100, 100, 100)
                    pygame.draw.line(surface, c, (spec_rect.x+i, spec_rect.y), (spec_rect.x+i, spec_rect.bottom))

                start_y = sy + 140
                for i, (code, name) in enumerate(self.shape_options):
                    r = pygame.Rect(sx + 10 + (i%2)*70, start_y + (i//2)*40, 65, 35)
                    bg = (80, 80, 100) if self.current_shape == code else (60, 60, 80)
                    draw_rounded_rect(surface, r, bg, radius=5)
                    if self.current_shape == code:
                        pygame.draw.rect(surface, ACCENT_COLOR, r, 2, border_radius=5)

                    cx, cy = r.center
                    if code == "LINE": pygame.draw.line(surface, TEXT_COLOR, (cx-10, cy), (cx+10, cy), 2)
                    elif code == "RECT": pygame.draw.rect(surface, TEXT_COLOR, (cx-10, cy-10, 20, 20), 2)
                    elif code == "CIRCLE": pygame.draw.circle(surface, TEXT_COLOR, (cx, cy), 10, 2)
                    elif code == "TRIANGLE_EQ": pygame.draw.polygon(surface, TEXT_COLOR, [(cx, cy-10), (cx-10, cy+10), (cx+10, cy+10)], 2)
                    elif code == "TRIANGLE_RIGHT": pygame.draw.polygon(surface, TEXT_COLOR, [(cx-10, cy-10), (cx-10, cy+10), (cx+10, cy+10)], 2)
                    elif code == "ARROW":
                        pygame.draw.line(surface, TEXT_COLOR, (cx-10, cy), (cx+10, cy), 2)
                        pygame.draw.line(surface, TEXT_COLOR, (cx+5, cy-5), (cx+10, cy), 2)
                        pygame.draw.line(surface, TEXT_COLOR, (cx+5, cy+5), (cx+10, cy), 2)

            elif self.tool_mode == "ERASER":
                txt = font_sm.render("Silgi Boyutu", True, TEXT_COLOR)
                surface.blit(txt, (sx + 10, sy + 10))
                sl_rect = pygame.Rect(sx + 10, sy + 50, 140, 6)
                pygame.draw.rect(surface, (80,80,90), sl_rect, border_radius=3)
                pygame.draw.rect(surface, ACCENT_COLOR, (sl_rect.x, sl_rect.y, (self.eraser_size / 100.0)*140, 6), border_radius=3)
                knob_x = sx + 10 + (self.eraser_size / 100.0) * 140
                pygame.draw.circle(surface, (255,255,255), (int(knob_x), sl_rect.centery), 8)
                pygame.draw.circle(surface, (200,200,200), (sx + 80, sy + 100), int(self.eraser_size), width=1)

class WhiteboardBtn:
    def __init__(self):
        self.rect = pygame.Rect(20, HEIGHT - 70, 50, 50)
        self.active = False
        self.hovered = False
        self.scale = Tween(1.0)

    def update(self, dt, mouse_pos):
        self.rect.y = HEIGHT - 70
        self.hovered = self.rect.collidepoint(mouse_pos)
        self.scale.set(1.15 if self.hovered else 1.0)
        self.scale.update(dt)

    def draw(self, surface):
        s = self.scale.val
        cx, cy = self.rect.center
        r = 22 * s

        bg_col = (200, 200, 220) if self.active else (50, 50, 70)
        if self.hovered and not self.active: bg_col = (70, 70, 90)

        pygame.draw.circle(surface, bg_col, (cx, cy), r)

        icon_col = (30, 30, 40) if self.active else TEXT_COLOR
        off = 8 * s
        tl = (cx - off, cy - off)
        pygame.draw.rect(surface, icon_col, (tl[0], tl[1], off*2 + 2, off*2 + 2), 2)
        pygame.draw.line(surface, icon_col, (cx, tl[1]), (cx, tl[1]+off*2), 2)
        pygame.draw.line(surface, icon_col, (tl[0], cy), (tl[0]+off*2, cy), 2)

class PDFCard:
    def __init__(self, filename, app):
        self.filename = filename
        self.app = app
        self.rect = pygame.Rect(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self.scale = Tween(1.0)
        self.shadow_opacity = Tween(0)
        self.border_alpha = Tween(0)
    def update(self, dt, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        self.scale.set(1.08 if hovered else 1.0)
        self.shadow_opacity.set(100 if hovered else 20)

        if hovered: self.border_alpha.set(255)
        else:
            self.border_alpha.target = 0
            self.border_alpha.val = 0

        self.scale.update(dt)
        self.shadow_opacity.update(dt)
        self.border_alpha.update(dt)
        return hovered
    def draw(self, surface):
        s_val = self.scale.val
        w, h = CARD_WIDTH * s_val, CARD_HEIGHT * s_val
        cx, cy = self.rect.center
        draw_rect = pygame.Rect(0, 0, w, h)
        draw_rect.center = (cx, cy)
        shadow_surf = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0,0,0, int(self.shadow_opacity.val)), shadow_surf.get_rect(), border_radius=15)
        surface.blit(shadow_surf, (draw_rect.x + 5, draw_rect.y + 10))
        draw_rounded_rect(surface, draw_rect, CARD_BG, radius=12)
        thumb = self.app.pdf_manager.get_thumbnail(self.filename)
        if thumb:
            thumb_scaled = pygame.transform.smoothscale(thumb, (int(w-20), int((w-20)*1.414)))
            thumb_rect = thumb_scaled.get_rect(center=draw_rect.center)
            thumb_rect.y -= 15
            surface.blit(thumb_scaled, thumb_rect)
        else:
            draw_spinner(surface, draw_rect.center, 30, ACCENT_COLOR)
        name = self.filename if len(self.filename) < 18 else self.filename[:15] + "..."
        txt = font_sm.render(name, True, TEXT_COLOR)
        txt_rect = txt.get_rect(midbottom=(cx, draw_rect.bottom - 10))
        surface.blit(txt, txt_rect)
        if self.border_alpha.val > 1:
            border_col = (*ACCENT_COLOR, int(self.border_alpha.val))
            draw_rounded_rect(surface, draw_rect, (0,0,0,0), radius=12, border=2, border_color=border_col)

class NavArrow:
    def __init__(self, direction):
        self.direction = direction
        self.rect = pygame.Rect(0, 0, 40, 60)
        self.visible = False
        self.hovered = False
    def update(self, mouse_pos, available):
        self.visible = available
        if not self.visible: return False
        if self.direction == 'left': self.rect.midleft = (0, HEIGHT // 2)
        else: self.rect.midright = (WIDTH, HEIGHT // 2)
        self.hovered = self.rect.collidepoint(mouse_pos)
        return self.hovered and pygame.mouse.get_pressed()[0]
    def draw(self, surface):
        if not self.visible: return
        bg_col = (0, 0, 0, 100 if self.hovered else 50)
        s = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, bg_col, s.get_rect(), border_radius=10)
        surface.blit(s, self.rect.topleft)
        cx, cy = self.rect.center
        off = 5 if self.direction == 'left' else -5
        p1 = (cx + off, cy - 10)
        p2 = (cx - off, cy)
        p3 = (cx + off, cy + 10)
        pygame.draw.lines(surface, TEXT_COLOR, False, [p1, p2, p3], 3)

class FullscreenBtn:
    def __init__(self):
        self.rect = pygame.Rect(WIDTH - 70, 20, 50, 50)
        self.is_fullscreen = False
        self.hovered = False
        self.scale = Tween(1.0)
        self.bg_alpha = Tween(50)
    def update(self, dt, mouse_pos):
        self.rect.x = WIDTH - 70
        self.hovered = self.rect.collidepoint(mouse_pos)
        self.scale.set(1.15 if self.hovered else 1.0)
        self.bg_alpha.set(200 if self.hovered else 80)
        self.scale.update(dt)
        self.bg_alpha.update(dt)
    def toggle(self):
        global WIDTH, HEIGHT, screen
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"
            screen = pygame.display.set_mode((0, 0), pygame.NOFRAME)
            w, h = screen.get_size()
            WIDTH, HEIGHT = w, h
        else:
            os.environ['SDL_VIDEO_CENTERED'] = '1'
            if 'SDL_VIDEO_WINDOW_POS' in os.environ: del os.environ['SDL_VIDEO_WINDOW_POS']
            w = MONITOR_W - 300
            h = MONITOR_H - 200
            screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            WIDTH, HEIGHT = w, h
    def draw(self, surface):
        s = self.scale.val
        cx, cy = self.rect.center
        radius = 22 * s
        bg_surf = pygame.Surface((int(radius*2.2), int(radius*2.2)), pygame.SRCALPHA)
        col = (*ACCENT_COLOR, int(self.bg_alpha.val))
        pygame.draw.circle(bg_surf, col, (int(radius*1.1), int(radius*1.1)), radius)
        surface.blit(bg_surf, (cx - radius*1.1, cy - radius*1.1))
        pygame.draw.rect(surface, TEXT_COLOR, (cx-10, cy-10, 18, 18), 2, 2)

class BackBtn:
    def __init__(self):
        self.rect = pygame.Rect(20, 20, 50, 50)
        self.hovered = False
        self.scale = Tween(1.0)
        self.bg_alpha = Tween(50)
    def update(self, dt, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)
        self.scale.set(1.15 if self.hovered else 1.0)
        self.bg_alpha.set(200 if self.hovered else 80)
        self.scale.update(dt)
        self.bg_alpha.update(dt)
    def draw(self, surface):
        s = self.scale.val
        cx, cy = self.rect.center
        radius = 22 * s
        bg_surf = pygame.Surface((int(radius*2.2), int(radius*2.2)), pygame.SRCALPHA)
        col = (*ACCENT_COLOR, int(self.bg_alpha.val))
        pygame.draw.circle(bg_surf, col, (int(radius*1.1), int(radius*1.1)), radius)
        surface.blit(bg_surf, (cx - radius*1.1, cy - radius*1.1))
        pygame.draw.line(surface, TEXT_COLOR, (cx+8, cy), (cx-7, cy), 3)
        pygame.draw.line(surface, TEXT_COLOR, (cx-8, cy), (cx, cy-7), 3)
        pygame.draw.line(surface, TEXT_COLOR, (cx-8, cy), (cx, cy+7), 3)

class Numpad:
    def __init__(self, app, max_page):
        self.app = app
        self.active = False
        self.value_str = ""
        self.max_page = max_page
        self.rect = pygame.Rect(0, 0, 220, 335)
        self.rect.center = (WIDTH // 2, HEIGHT // 2)
        self.buttons = []
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "<", "0", "GİT"]
        btn_w, btn_h = 55, 55
        self.btn_size = (btn_w, btn_h)
        for k in keys: self.buttons.append({"key": k, "rect": pygame.Rect(0,0,btn_w,btn_h)})
    def handle_event(self, event):
        if not self.active: return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if not self.rect.collidepoint(mx, my):
                self.active = False
                return True
            for b in self.buttons:
                if b["rect"].collidepoint(mx, my):
                    k = b["key"]
                    if k == "<": self.value_str = self.value_str[:-1]
                    elif k == "GİT":
                        if self.value_str:
                            p = int(self.value_str)
                            final_p = max(0, min(p - 1, self.max_page - 1))
                            self.app.scene.current_page = final_p
                            self.app.scene.center_view()
                        self.active = False
                    else:
                        if len(self.value_str) < 4: self.value_str += k
            return True
        return True
    def draw(self, surface):
        if not self.active: return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        self.rect.center = (WIDTH // 2, HEIGHT // 2)
        draw_rounded_rect(surface, self.rect, CARD_BG, radius=20, border=2, border_color=ACCENT_COLOR)
        display_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 20, 180, 40)
        draw_rounded_rect(surface, display_rect, (30, 30, 40), radius=10)
        txt = font_num.render(self.value_str, True, ACCENT_COLOR)
        surface.blit(txt, txt.get_rect(midright=(display_rect.right - 10, display_rect.centery)))
        mx, my = pygame.mouse.get_pos()
        btn_w, btn_h = self.btn_size
        start_x = self.rect.x + 20
        start_y = self.rect.y + 70
        for i, b in enumerate(self.buttons):
            r = i // 3
            c = i % 3
            rect = pygame.Rect(start_x + c*(btn_w+8), start_y + r*(btn_h+8), btn_w, btn_h)
            b["rect"] = rect
            hover = rect.collidepoint(mx, my)
            col = (60, 60, 80) if not hover else (80, 80, 100)
            if b["key"] == "GİT": col = (50, 100, 50) if not hover else (70, 150, 70)
            draw_rounded_rect(surface, rect, col, radius=10)
            t = font_num.render(b["key"], True, TEXT_COLOR)
            surface.blit(t, t.get_rect(center=rect.center))

class AddButton:
    def __init__(self):
        self.rect = pygame.Rect(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self.circle_radius = 40
        self.scale = Tween(1.0)
        self.glow = Tween(0)
    def update(self, dt, mouse_pos):
        cx, cy = self.rect.center
        dist = math.hypot(mouse_pos[0] - cx, mouse_pos[1] - cy)
        hovered = dist < self.circle_radius
        self.scale.set(1.2 if hovered else 1.0)
        self.glow.set(255 if hovered else 50)
        self.scale.update(dt)
        self.glow.update(dt)
        return hovered
    def draw(self, surface):
        cx, cy = self.rect.center
        s = self.scale.val
        r = self.circle_radius * s
        glow_surf = pygame.Surface((int(r*4), int(r*4)), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*ACCENT_COLOR, 50), (int(r*2), int(r*2)), r*1.2)
        surface.blit(glow_surf, (cx - r*2, cy - r*2))
        pygame.draw.circle(surface, (50, 50, 70), (cx, cy), r)
        pygame.draw.circle(surface, ACCENT_COLOR, (cx, cy), r, width=2)
        start = (cx - 15*s, cy)
        end = (cx + 15*s, cy)
        pygame.draw.line(surface, TEXT_COLOR, start, end, 3)
        start = (cx, cy - 15*s)
        end = (cx, cy + 15*s)
        pygame.draw.line(surface, TEXT_COLOR, start, end, 3)
        txt = font_md.render("PDF Ekle", True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(center=(cx, cy + r + 25)))

class GridScene:
    def __init__(self, app):
        self.app = app
        self.cards = []
        self.add_btn = AddButton()
        self.scroll_y = 0
        self.target_scroll_y = 0
        self.fullscreen_btn = FullscreenBtn()
        self.reload_pdfs()

        # --- TOUCH SCROLL VARS ---
        self.touch_last_y = None
        # -------------------------

    def reload_pdfs(self):
        self.cards = []
        files = self.app.pdf_manager.get_files()
        self.app.pdf_manager.start_thumbnail_loader(files)
        for f in files:
            self.cards.append(PDFCard(f, self.app))

    def handle_event(self, event):
        mx, my = pygame.mouse.get_pos()

        # --- TOUCH SCROLL LOGIC ---
        if event.type == pygame.FINGERDOWN:
            self.touch_last_y = event.y * HEIGHT
        elif event.type == pygame.FINGERMOTION:
            if self.touch_last_y is not None:
                current_y = event.y * HEIGHT
                dy = current_y - self.touch_last_y
                self.target_scroll_y += dy
                self.scroll_y += dy # Instant response
                self.touch_last_y = current_y
        elif event.type == pygame.FINGERUP:
            self.touch_last_y = None
        # ---------------------------

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.fullscreen_btn.rect.collidepoint(mx, my):
                self.fullscreen_btn.toggle()
                return
        if event.type == pygame.MOUSEWHEEL:
            self.target_scroll_y += event.y * 60
            self.target_scroll_y = min(0, self.target_scroll_y)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.add_btn.rect.collidepoint(mx, my - self.scroll_y):
                self.open_file_dialog()
                return
            for card in self.cards:
                if card.rect.collidepoint(mx, my - self.scroll_y):
                    self.app.open_viewer(card.filename)
                    return
    def open_file_dialog(self):
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        root.destroy()
        if path:
            filename = os.path.basename(path)
            dest = os.path.join(PDF_FOLDER, filename)
            shutil.copy(path, dest)
            self.reload_pdfs()
    def update(self, dt):
        self.app.pdf_manager.process_queue()
        self.scroll_y += (self.target_scroll_y - self.scroll_y) * 10 * dt
        mx, my = pygame.mouse.get_pos()
        adj_my = my - self.scroll_y
        for card in self.cards:
            card.update(dt, (mx, adj_my))
        self.add_btn.update(dt, (mx, adj_my))
        self.fullscreen_btn.update(dt, (mx, my))
    def draw(self, surface):
        surface.fill(BG_COLOR)
        cols = max(1, surface.get_width() // (CARD_WIDTH + GAP))
        start_x = (surface.get_width() - (cols * (CARD_WIDTH + GAP))) // 2
        title = font_lg.render("Kitaplık", True, TEXT_COLOR)
        surface.blit(title, (start_x, 30 + self.scroll_y))
        current_y = 100
        all_items = self.cards + [self.add_btn]
        for i, item in enumerate(all_items):
            row = i // cols
            col = i % cols
            x = start_x + col * (CARD_WIDTH + GAP)
            y = current_y + row * (CARD_HEIGHT + GAP)
            item.rect.topleft = (x, y)
            screen_y = y + self.scroll_y
            if screen_y + CARD_HEIGHT > 0 and screen_y < HEIGHT:
                saved_rect = item.rect.copy()
                item.rect.y += self.scroll_y
                item.draw(surface)
                item.rect = saved_rect
        total_rows = math.ceil(len(all_items) / cols)
        max_scroll = -(total_rows * (CARD_HEIGHT + GAP) + 150 - HEIGHT)
        if max_scroll > 0: max_scroll = 0
        if self.target_scroll_y < max_scroll: self.target_scroll_y = max_scroll
        self.fullscreen_btn.draw(surface)

class ViewerScene:
    def __init__(self, app, filename):
        self.app = app
        self.filename = filename
        self.page_count = app.pdf_manager.load_document(filename)

        self.current_page = 0
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self.target_zoom = 1.0
        self.target_offset_x = 0
        self.target_offset_y = 0

        # Rendering Optimizations
        self.last_interaction_time = time.time()
        self.render_debounce_time = 0.15  # Hareket bittikten ne kadar süre sonra render alınsın
        self.is_rendering = False

        # High Quality Fragment
        self.hq_surface = None
        self.hq_rect = None # PDF koordinatlarında (unscaled) fitz.Rect
        self.hq_zoom = 1.0

        self.drag_start = None
        self.last_click = 0
        self.toolbar_alpha = Tween(255)
        self.last_mouse_move = time.time()

        self.fullscreen_btn = FullscreenBtn()
        self.back_btn = BackBtn()
        self.nav_left = NavArrow('left')
        self.nav_right = NavArrow('right')
        self.numpad = Numpad(app, self.page_count)
        self.whiteboard_btn = WhiteboardBtn()

        self.drawing_layer = DrawingLayer()
        self.toolbar = FloatingToolbar(app)

        self.smooth_mx = 0
        self.smooth_my = 0
        self.is_drawing = False
        self.show_whiteboard = False
        self.shape_start_pos = None
        self.fingers = {}
        self.initial_pinch_dist = None
        self.initial_zoom = 1.0
        self.last_finger_tap_time = 0

        self.center_view()

    def center_view(self, maintain_zoom=False):
        if not maintain_zoom:
            self.zoom = 1.0
            self.target_zoom = 1.0

        base_img, size = self.app.pdf_manager.get_base_image(self.current_page)
        if size:
            page_w = size[0] * self.target_zoom
            self.target_offset_x = (WIDTH - page_w) // 2
            self.target_offset_y = 50

        self.hq_surface = None
        self.reset_render_timer()

    def reset_render_timer(self):
        self.last_interaction_time = time.time()

    def handle_event(self, event):
        self.last_mouse_move = time.time()
        self.toolbar_alpha.set(255)

        if self.toolbar.handle_event(event):
            self.drag_start = None
            return

        if self.numpad.active:
            if self.numpad.handle_event(event): return

        mx, my = pygame.mouse.get_pos()
        interaction_occured = False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.fullscreen_btn.rect.collidepoint(mx, my):
                self.fullscreen_btn.toggle()
                return

            if self.back_btn.rect.collidepoint(mx, my):
                self.app.scene = GridScene(self.app)
                return

            if self.whiteboard_btn.rect.collidepoint(mx, my):
                self.show_whiteboard = not self.show_whiteboard
                self.whiteboard_btn.active = self.show_whiteboard
                return

            if not self.show_whiteboard:
                if self.nav_left.visible and self.nav_left.rect.collidepoint(mx, my):
                    self.prev_page()
                    return
                if self.nav_right.visible and self.nav_right.rect.collidepoint(mx, my):
                    self.next_page()
                    return

            bar_rect = pygame.Rect(WIDTH//2 - 150, 10, 300, 50)
            if bar_rect.collidepoint(mx, my):
                self.numpad.active = True
                self.numpad.value_str = ""
                return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: self.app.scene = GridScene(self.app)
            elif event.key == pygame.K_f: self.fullscreen_btn.toggle()
            elif not self.show_whiteboard:
                if event.key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_PAGEDOWN): self.next_page()
                elif event.key in (pygame.K_LEFT, pygame.K_UP, pygame.K_PAGEUP): self.prev_page()

        # TOOL HANDLERS
        if self.toolbar.tool_mode in ["PEN", "ERASER", "SHAPE"]:
            target_page = -1 if self.show_whiteboard else self.current_page
            pdf_x = (self.smooth_mx - self.offset_x) / self.zoom
            pdf_y = (self.smooth_my - self.offset_y) / self.zoom

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.is_drawing = True
                if self.toolbar.tool_mode == "PEN":
                    self.drawing_layer.start_stroke()
                    self.drawing_layer.add_point(target_page, (pdf_x, pdf_y))
                elif self.toolbar.tool_mode == "SHAPE":
                    self.shape_start_pos = (pdf_x, pdf_y)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.is_drawing:
                    self.is_drawing = False
                    if self.toolbar.tool_mode == "PEN":
                        self.drawing_layer.end_stroke(target_page, self.toolbar.pen_color, self.toolbar.pen_size)
                    elif self.toolbar.tool_mode == "SHAPE" and self.shape_start_pos:
                        self.drawing_layer.add_shape(target_page, self.toolbar.current_shape, self.shape_start_pos, (pdf_x, pdf_y), self.toolbar.pen_color, self.toolbar.pen_size)
                        self.shape_start_pos = None

            elif event.type == pygame.MOUSEWHEEL:
                interaction_occured = True
                zoom_factor = 1.1 if event.y > 0 else 0.9
                new_zoom = self.target_zoom * zoom_factor
                new_zoom = max(0.2, min(new_zoom, 5.0))
                self.target_offset_x = mx - (mx - self.target_offset_x) * (new_zoom / self.target_zoom)
                self.target_offset_y = my - (my - self.target_offset_y) * (new_zoom / self.target_zoom)
                self.target_zoom = new_zoom

            if interaction_occured: self.reset_render_timer()
            return

        # --- MOUSE EVENTS ---
        if event.type == pygame.MOUSEWHEEL:
            interaction_occured = True
            zoom_factor = 1.1 if event.y > 0 else 0.9
            new_zoom = self.target_zoom * zoom_factor
            new_zoom = max(0.2, min(new_zoom, 5.0))
            self.target_offset_x = mx - (mx - self.target_offset_x) * (new_zoom / self.target_zoom)
            self.target_offset_y = my - (my - self.target_offset_y) * (new_zoom / self.target_zoom)
            self.target_zoom = new_zoom

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2:
                self.drag_start = pygame.mouse.get_pos()
            elif event.button == 1:
                if time.time() - self.last_click < DOUBLE_CLICK_TIME:
                    self.target_zoom = 1.0
                    self.center_view()
                    interaction_occured = True
                self.last_click = time.time()
                self.drag_start = pygame.mouse.get_pos()

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in (1, 2):
                self.drag_start = None
                self.fingers.clear()
                self.initial_pinch_dist = None

        elif event.type == pygame.MOUSEMOTION:
            if self.drag_start:
                interaction_occured = True
                dx = mx - self.drag_start[0]
                dy = my - self.drag_start[1]
                self.target_offset_x += dx
                self.target_offset_y += dy
                self.drag_start = (mx, my)

        # --- TOUCH EVENTS ---
        elif event.type == pygame.FINGERDOWN:
            now = time.time()
            if now - self.last_finger_tap_time < 0.3:
                if self.toolbar.tool_mode == "HAND":
                    self.target_zoom = 1.0
                    self.center_view()
                    interaction_occured = True
            self.last_finger_tap_time = now
            x = event.x * WIDTH
            y = event.y * HEIGHT
            self.fingers[event.finger_id] = (x, y)
            if len(self.fingers) == 2:
                f1 = list(self.fingers.values())[0]
                f2 = list(self.fingers.values())[1]
                self.initial_pinch_dist = math.hypot(f1[0]-f2[0], f1[1]-f2[1])
                self.initial_zoom = self.target_zoom
                self.drag_start = None

        elif event.type == pygame.FINGERUP:
            if event.finger_id in self.fingers: del self.fingers[event.finger_id]
            if len(self.fingers) < 2: self.initial_pinch_dist = None

        elif event.type == pygame.FINGERMOTION:
            interaction_occured = True
            x = event.x * WIDTH
            y = event.y * HEIGHT
            self.fingers[event.finger_id] = (x, y)
            if len(self.fingers) == 2 and self.initial_pinch_dist:
                f1 = list(self.fingers.values())[0]
                f2 = list(self.fingers.values())[1]
                current_dist = math.hypot(f1[0]-f2[0], f1[1]-f2[1])
                if self.initial_pinch_dist > 10:
                    scale = current_dist / self.initial_pinch_dist
                    self.target_zoom = max(0.2, min(self.initial_zoom * scale, 5.0))
            elif len(self.fingers) == 1 and self.toolbar.tool_mode == "HAND":
                dx = event.dx * WIDTH
                dy = event.dy * HEIGHT
                self.target_offset_x += dx
                self.target_offset_y += dy

        if interaction_occured:
            self.reset_render_timer()

    def next_page(self):
        if self.current_page < self.page_count - 1:
            self.current_page += 1
            self.center_view(maintain_zoom=True)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.center_view(maintain_zoom=True)

    def update(self, dt):
        # 1. Check for incoming renders
        result = self.app.pdf_manager.get_render_result()
        if result:
            p_num, z_level, raw, size, clip_rect = result
            if p_num == self.current_page:
                img = pygame.image.frombuffer(raw, size, "RGB")
                self.hq_surface = img
                self.hq_zoom = z_level
                # Fix: fitz.Rect created safely
                self.hq_rect = fitz.Rect(clip_rect) if clip_rect else None

        # 2. Check for Idle Render Trigger
        if not self.show_whiteboard:
            if time.time() - self.last_interaction_time > self.render_debounce_time:
                base_img, size = self.app.pdf_manager.get_base_image(self.current_page)
                if size:
                    pdf_w, pdf_h = size

                    # Screen coords to PDF coords
                    visible_x = -self.offset_x / self.zoom
                    visible_y = -self.offset_y / self.zoom
                    visible_w = WIDTH / self.zoom
                    visible_h = HEIGHT / self.zoom

                    visible_rect = fitz.Rect(visible_x, visible_y, visible_x + visible_w, visible_y + visible_h)
                    page_rect = fitz.Rect(0, 0, pdf_w, pdf_h)
                    final_clip = visible_rect & page_rect

                    if not final_clip.is_empty:
                        needs_render = False
                        if self.hq_surface is None or abs(self.hq_zoom - self.zoom) > 0.1:
                            needs_render = True
                        elif self.hq_rect and not (self.hq_rect.contains(final_clip)):
                            needs_render = True

                        if needs_render:
                            self.app.pdf_manager.request_render(self.current_page, self.zoom, final_clip)
                            self.last_interaction_time = time.time() + 1.0

                            # 3. Standard UI Update
        raw_mx, raw_my = pygame.mouse.get_pos()
        if not self.is_drawing:
            self.smooth_mx, self.smooth_my = raw_mx, raw_my
        else:
            self.smooth_mx = lerp(self.smooth_mx, raw_mx, 0.4)
            self.smooth_my = lerp(self.smooth_my, raw_my, 0.4)

        if self.is_drawing:
            pdf_x = (self.smooth_mx - self.offset_x) / self.zoom
            pdf_y = (self.smooth_my - self.offset_y) / self.zoom
            target_page = -1 if self.show_whiteboard else self.current_page
            if self.toolbar.tool_mode == "PEN":
                self.drawing_layer.add_point(target_page, (pdf_x, pdf_y))
            elif self.toolbar.tool_mode == "ERASER":
                self.drawing_layer.erase_at(target_page, (pdf_x, pdf_y), self.toolbar.eraser_size / self.zoom)

        smooth_factor = min(15 * dt, 0.8)
        self.zoom += (self.target_zoom - self.zoom) * smooth_factor
        self.offset_x += (self.target_offset_x - self.offset_x) * smooth_factor
        self.offset_y += (self.target_offset_y - self.offset_y) * smooth_factor

        mx, my = pygame.mouse.get_pos()
        if not self.show_whiteboard:
            self.nav_left.update((mx, my), self.current_page > 0)
            self.nav_right.update((mx, my), self.current_page < self.page_count - 1)
        else:
            self.nav_left.visible = False
            self.nav_right.visible = False

        self.fullscreen_btn.update(dt, (mx, my))
        self.back_btn.update(dt, (mx, my))
        self.whiteboard_btn.update(dt, (mx, my))

        if time.time() - self.last_mouse_move > 2.0:
            self.toolbar_alpha.set(0)
        self.toolbar_alpha.update(dt)

    def draw(self, surface):
        surface.fill(BG_COLOR)

        if self.show_whiteboard:
            grid_size = int(50 * self.zoom)
            if grid_size < 10: grid_size = 10
            start_x = int(self.offset_x % grid_size)
            start_y = int(self.offset_y % grid_size)
            surface.fill((240, 240, 245))
            for x in range(start_x, WIDTH, grid_size):
                pygame.draw.line(surface, (200, 200, 220), (x, 0), (x, HEIGHT))
            for y in range(start_y, HEIGHT, grid_size):
                pygame.draw.line(surface, (200, 200, 220), (0, y), (WIDTH, y))
            self.drawing_layer.draw(surface, -1, self.offset_x, self.offset_y, self.zoom)
        else:
            # OPTIMIZED DRAWING PIPELINE

            # 1. Base Layer (Low Res Cache) - Covers entire PDF area
            base_img, size = self.app.pdf_manager.get_base_image(self.current_page)
            if base_img and size:
                pdf_w, pdf_h = size

                # Where should the page be?
                dest_x = int(self.offset_x)
                dest_y = int(self.offset_y)
                dest_w = int(pdf_w * self.zoom)
                dest_h = int(pdf_h * self.zoom)

                # Only draw if onscreen
                screen_rect = pygame.Rect(0, 0, WIDTH, HEIGHT)
                dest_rect = pygame.Rect(dest_x, dest_y, dest_w, dest_h)

                if screen_rect.colliderect(dest_rect):
                    # Base image'i ekran boyutuna göre ölçekle
                    scaled_base = pygame.transform.scale(base_img, (dest_w, dest_h))
                    surface.blit(scaled_base, (dest_x, dest_y))

            # 2. High Quality Layer (Visible Clip) - Draws on top
            # FIX: Check both hq_surface AND hq_rect existence
            if self.hq_surface and self.hq_rect:
                # FIX: Use .x0 and .y0 (PyMuPDF Rect attributes)
                # Calculate screen position: Offset + (PDF_Local_X * Zoom)
                clip_dest_x = int(self.offset_x + (self.hq_rect.x0 * self.zoom))
                clip_dest_y = int(self.offset_y + (self.hq_rect.y0 * self.zoom))

                scale_ratio = self.zoom / self.hq_zoom

                if abs(scale_ratio - 1.0) > 0.001:
                    new_w = int(self.hq_surface.get_width() * scale_ratio)
                    new_h = int(self.hq_surface.get_height() * scale_ratio)
                    draw_surf = pygame.transform.scale(self.hq_surface, (new_w, new_h))
                else:
                    draw_surf = self.hq_surface

                surface.blit(draw_surf, (clip_dest_x, clip_dest_y))

            elif base_img is None:
                draw_spinner(surface, (WIDTH//2, HEIGHT//2), 40, ACCENT_COLOR)

            self.drawing_layer.draw(surface, self.current_page, self.offset_x, self.offset_y, self.zoom)

        if self.is_drawing:
            if self.toolbar.tool_mode == "PEN":
                points = self.drawing_layer.current_stroke
                self.drawing_layer._draw_stroke(surface, points, self.toolbar.pen_color, self.toolbar.pen_size, self.zoom, self.offset_x, self.offset_y)

            elif self.toolbar.tool_mode == "SHAPE" and self.shape_start_pos:
                pdf_mx = (self.smooth_mx - self.offset_x) / self.zoom
                pdf_my = (self.smooth_my - self.offset_y) / self.zoom
                self.drawing_layer._draw_shape(
                    surface,
                    self.toolbar.current_shape,
                    self.shape_start_pos,
                    (pdf_mx, pdf_my),
                    self.toolbar.pen_color,
                    self.toolbar.pen_size,
                    self.zoom,
                    self.offset_x,
                    self.offset_y
                )

        if self.toolbar.tool_mode == "ERASER":
            pygame.draw.circle(surface, (150, 150, 150), (int(self.smooth_mx), int(self.smooth_my)), int(self.toolbar.eraser_size), 1)

        alpha = int(self.toolbar_alpha.val)
        self.nav_left.draw(surface)
        self.nav_right.draw(surface)
        self.fullscreen_btn.draw(surface)
        self.back_btn.draw(surface)
        self.whiteboard_btn.draw(surface)

        if alpha > 0 or self.numpad.active:
            bar_alpha = 255 if self.numpad.active else alpha
            bar_rect = pygame.Rect(WIDTH//2 - 150, 10, 300, 50)
            overlay = pygame.Surface(bar_rect.size, pygame.SRCALPHA)
            overlay.fill(GLASS_COLOR)
            overlay.set_alpha(bar_alpha)
            surface.blit(overlay, bar_rect.topleft)

            info_text = f"Tahta Modu" if self.show_whiteboard else f"Sayfa {self.current_page + 1} / {self.page_count}"
            info = f"{info_text}  |  {(self.zoom*100):.0f}%"
            txt = font_md.render(info, True, TEXT_COLOR)
            txt.set_alpha(bar_alpha)
            surface.blit(txt, txt.get_rect(center=bar_rect.center))

        self.numpad.draw(surface)
        self.toolbar.draw(surface)

class App:
    def __init__(self):
        self.pdf_manager = PDFManager()
        self.scene = GridScene(self)
        self.running = True

    def open_viewer(self, filename):
        self.scene = ViewerScene(self, filename)

    def run(self):
        while self.running:
            dt = clock.tick(FPS) / 1000.0
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    global WIDTH, HEIGHT
                    WIDTH, HEIGHT = event.w, event.h
                self.scene.handle_event(event)
            self.scene.update(dt)
            self.scene.draw(screen)
            pygame.display.flip()
        pygame.quit()

if __name__ == "__main__":
    app = App()
    app.run()