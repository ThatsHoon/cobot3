"""GP terrain path drawing tool — paste into Isaac Sim 5.1 Script Editor.

Controls (active immediately after running this script):
  Ctrl + Left Click   = add waypoint at mouse on terrain
  Backspace           = undo last waypoint
  Enter               = bake current waypoints to USD BasisCurves
  Escape              = cancel (clear current waypoints)
  _gp_path_tool['stop']()  = unsubscribe input hooks

Requires: terrain prim has PhysX collider (raycast targets it).
"""

import builtins
import carb
import carb.input
import omni.appwindow
import omni.kit.viewport.utility as vu
import omni.usd
from isaacsim.util.debug_draw import _debug_draw
from omni.physx import get_physx_scene_query_interface
from pxr import Gf, UsdGeom

CURVE_PARENT = "/World/Paths"
PREVIEW_COLOR = (1.0, 1.0, 0.0, 1.0)
PREVIEW_WIDTH = 4.0
POINT_COLOR = (1.0, 0.2, 0.2, 1.0)
POINT_SIZE = 12.0
SURFACE_OFFSET = 0.05
RAY_MAX_DIST = 1.0e6


class _State:
    points = []          # confirmed waypoints
    pending = None       # hover preview hit
    active = True


state = _State()
draw = _debug_draw.acquire_debug_draw_interface()


def _redraw():
    draw.clear_lines()
    draw.clear_points()
    pts = state.points + ([state.pending] if state.pending is not None else [])
    if len(pts) >= 2:
        starts, ends = pts[:-1], pts[1:]
        n = len(starts)
        draw.draw_lines(starts, ends, [PREVIEW_COLOR] * n, [PREVIEW_WIDTH] * n)
    if state.points:
        n = len(state.points)
        draw.draw_points(state.points, [POINT_COLOR] * n, [POINT_SIZE] * n)


def _mouse_to_ray(mx_screen, my_screen):
    vp_win = vu.get_active_viewport_window()
    if vp_win is None:
        return None
    try:
        wx = vp_win.position_x
        wy = vp_win.position_y
        ww = vp_win.width
        wh = vp_win.height
    except Exception:
        return None
    lx = mx_screen - wx
    ly = my_screen - wy
    if lx < 0 or ly < 0 or lx > ww or ly > wh:
        return None
    ndc_x = (lx / ww) * 2.0 - 1.0
    ndc_y = 1.0 - (ly / wh) * 2.0
    vp = vu.get_active_viewport()
    stage = omni.usd.get_context().get_stage()
    cam_prim = stage.GetPrimAtPath(vp.camera_path)
    if not cam_prim or not cam_prim.IsValid():
        return None
    gf_cam = UsdGeom.Camera(cam_prim).GetCamera(0.0)
    ray = gf_cam.frustum.ComputePickRay(Gf.Vec2d(ndc_x, ndc_y))
    return ray.startPoint, ray.direction


def _raycast(origin, direction):
    sqi = get_physx_scene_query_interface()
    hit = sqi.raycast_closest(
        carb.Float3(float(origin[0]), float(origin[1]), float(origin[2])),
        carb.Float3(float(direction[0]), float(direction[1]), float(direction[2])),
        RAY_MAX_DIST,
    )
    if hit and hit.get("hit"):
        p = hit["position"]
        return (p[0], p[1], p[2] + SURFACE_OFFSET)
    return None


def _pick_terrain(mx, my):
    ray = _mouse_to_ray(mx, my)
    if ray is None:
        return None
    return _raycast(ray[0], ray[1])


def _hover(mx, my):
    state.pending = _pick_terrain(mx, my)
    _redraw()


def _add(mx, my):
    hit = _pick_terrain(mx, my)
    if hit is not None:
        state.points.append(hit)
        carb.log_info(f"[GP-Path] +pt #{len(state.points)}: {hit}")
        _redraw()


def _undo():
    if state.points:
        p = state.points.pop()
        carb.log_info(f"[GP-Path] undo: {p}")
        _redraw()


def _cancel():
    state.points.clear()
    state.pending = None
    _redraw()
    carb.log_info("[GP-Path] cancelled")


def _bake():
    if len(state.points) < 2:
        carb.log_warn("[GP-Path] need >= 2 points to bake")
        return None
    stage = omni.usd.get_context().get_stage()
    if not stage.GetPrimAtPath(CURVE_PARENT).IsValid():
        UsdGeom.Xform.Define(stage, CURVE_PARENT)
    idx = 1
    while stage.GetPrimAtPath(f"{CURVE_PARENT}/Path_{idx:03d}").IsValid():
        idx += 1
    path = f"{CURVE_PARENT}/Path_{idx:03d}"
    curve = UsdGeom.BasisCurves.Define(stage, path)
    pts = [Gf.Vec3f(*p) for p in state.points]
    curve.CreatePointsAttr().Set(pts)
    curve.CreateCurveVertexCountsAttr().Set([len(pts)])
    curve.CreateTypeAttr().Set("linear")
    curve.CreateWidthsAttr().Set([0.15] * len(pts))
    curve.CreateDisplayColorAttr().Set([(1.0, 0.9, 0.0)])
    carb.log_info(f"[GP-Path] baked {len(pts)} pts -> {path}")
    _cancel()
    return path


_appwin = omni.appwindow.get_default_app_window()
_input = carb.input.acquire_input_interface()
_mouse = _appwin.get_mouse()
_keyboard = _appwin.get_keyboard()
_subs = []


def _on_mouse(event, *_a, **_k):
    if not state.active:
        return True
    if event.type == carb.input.MouseEventType.MOVE:
        pos = _input.get_mouse_coords_pixel(_mouse)
        _hover(pos.x, pos.y)
    elif event.type == carb.input.MouseEventType.LEFT_BUTTON_DOWN:
        mods = getattr(event, "modifiers", 0)
        if mods & carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL:
            pos = _input.get_mouse_coords_pixel(_mouse)
            _add(pos.x, pos.y)
    return True


def _on_key(event, *_a, **_k):
    if not state.active:
        return True
    if event.type != carb.input.KeyboardEventType.KEY_PRESS:
        return True
    if event.input == carb.input.KeyboardInput.ENTER:
        _bake()
    elif event.input == carb.input.KeyboardInput.ESCAPE:
        _cancel()
    elif event.input == carb.input.KeyboardInput.BACKSPACE:
        _undo()
    return True


def _stop():
    state.active = False
    for s in _subs:
        try:
            del s
        except Exception:
            pass
    _subs.clear()
    draw.clear_lines()
    draw.clear_points()
    print("[GP-Path] stopped")


_subs.append(_input.subscribe_to_mouse_events(_mouse, _on_mouse))
_subs.append(_input.subscribe_to_keyboard_events(_keyboard, _on_key))

builtins._gp_path_tool = {
    "state": state,
    "stop": _stop,
    "bake": _bake,
    "cancel": _cancel,
    "undo": _undo,
}

print("[GP-Path] active.")
print("  Ctrl+Left Click = add waypoint on terrain")
print("  Backspace       = undo last")
print("  Enter           = bake to /World/Paths/Path_NNN (BasisCurves)")
print("  Escape          = cancel")
print("  _gp_path_tool['stop']() to disable")
