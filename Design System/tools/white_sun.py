"""Swap the white pip's central teardrop for a sun.

The medallion's interior is close to radially symmetric (starfield + rays around
a bright core), so the teardrop can be removed by replacing its pixels with the
art's own per-radius average colour. That leaves a clean glow to paint onto,
and the sun is drawn from the palette sampled out of the same art.
"""
from PIL import Image, ImageFilter
import numpy as np

# Overwritten by export_pips.py; standalone runs can point it at the source PNG.
SRC = "White Mana Pip.png"


def square(im):
    a = np.array(im)[:, :, 3]
    ys, xs = np.where(a > 24)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    half = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2 + 6
    return im.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))


def find_core(rgb, alpha):
    """Brightest blob inside the medallion = the existing central flare."""
    lum = rgb.mean(axis=2) * (alpha > 0.5)
    sm = np.array(Image.fromarray((lum * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius=max(3, lum.shape[0] // 60))))
    iy, ix = np.unravel_index(np.argmax(sm), sm.shape)
    return float(ix), float(iy)


def radial_profile(rgb, alpha, cx, cy, nbins):
    h, w = alpha.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    rmax = r.max()
    idx = np.clip((r / rmax * (nbins - 1)).astype(int), 0, nbins - 1)
    prof = np.zeros((nbins, 4), dtype=np.float64)
    for b in range(nbins):
        m = (idx == b) & (alpha > 0.02)
        if m.sum() > 4:
            prof[b, :3] = rgb[m].mean(axis=0)
            prof[b, 3] = alpha[m].mean()
        elif b > 0:
            prof[b] = prof[b - 1]
    return prof, r, rmax, idx


def smooth_prof(prof, k=5):
    out = prof.copy()
    for c in range(prof.shape[1]):
        out[:, c] = np.convolve(prof[:, c], np.ones(k) / k, mode="same")
        out[:k, c] = prof[:k, c]
        out[-k:, c] = prof[-k:, c]
    return out


def feather(mask, px):
    m = Image.fromarray((mask * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius=px))
    return np.array(m).astype(np.float32) / 255.0


def build(sun_rays=12, ray_len=0.80, ray_w=0.115, core=0.30, out_px=None,
          field_depth=0.80):
    im = square(Image.open(SRC).convert("RGBA"))
    S = im.size[0]
    arr = np.array(im).astype(np.float32) / 255.0
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]

    cx, cy = find_core(rgb, alpha)

    # ---- 1. erase the teardrop -------------------------------------------
    # ellipse covering the teardrop, measured off the art: it hangs below the
    # core and is narrower than it is tall.
    yy, xx = np.mgrid[0:S, 0:S]
    tw, th = 0.115 * S, 0.235 * S          # semi-axes
    tcx, tcy = cx, cy + 0.035 * S          # teardrop sits slightly low
    ell = (((xx - tcx) / tw) ** 2 + ((yy - tcy) / th) ** 2) <= 1.0
    m = feather(ell.astype(np.float32), px=max(2, S // 150))

    prof, r, rmax, idx = radial_profile(rgb, alpha, cx, cy, nbins=max(96, S // 6))
    prof = smooth_prof(prof)
    glow = prof[idx]                        # per-pixel radial average
    base_rgb = rgb * (1 - m[..., None]) + glow[:, :, :3] * m[..., None]
    base_a = alpha * (1 - m) + glow[:, :, 3] * m

    # The interior is near-white, so a warm sun painted on it has nothing to
    # read against. Deepen the field toward amber, strongest at the centre and
    # released before the ring so the metalwork keeps its own brightness.
    rr0 = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (0.5 * S)
    field = np.clip(1 - (rr0 / 0.62) ** 2.0, 0, 1)
    amber = np.array([0.62, 0.45, 0.17])
    base_rgb = base_rgb * (1 - field[..., None] * field_depth) \
        + amber[None, None, :] * field[..., None] * field_depth
    base_rgb = np.clip(base_rgb, 0, 1)

    # ---- 2. sun palette --------------------------------------------------
    # Fixed ramp rather than colours sampled from the art: the interior is
    # almost white, and sampling it washed the sun out entirely.
    c_hot = np.array([1.00, 0.995, 0.95])   # white-hot centre
    c_warm = np.array([1.00, 0.87, 0.46])   # warm gold body
    c_gold = np.array([0.95, 0.64, 0.14])   # saturated amber ray tips

    # ---- 3. paint the sun ------------------------------------------------
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (0.5 * S)
    th_ = np.arctan2(yy - cy, xx - cx)

    px = 1.0 / (0.5 * S)                   # one pixel in normalised units
    aa = 1.6 * px                          # antialias width

    disc_r = core * 0.5                    # in normalised radius units
    # hard-edged disc, antialiased: reads as a solid sun rather than a blur
    disc = np.clip((disc_r - rr) / aa, 0, 1)
    corona = np.exp(-((rr - disc_r) / (disc_r * 0.85)) ** 2) * (rr >= disc_r)

    # tapered rays: alternating long/short, straight-edged like a heraldic sun
    k = sun_rays
    long_ray = ray_len * 0.5
    short_len = long_ray * 0.60

    def wedge(phase, width, length):
        ang = ((th_ + phase) * k / (2 * np.pi)) % 1.0
        d = np.minimum(ang, 1 - ang) * 2.0          # 0 at centre, 1 between
        # width shrinks linearly with radius -> straight triangular edges
        grow = np.clip((length - rr) / (length - disc_r * 0.85), 0, 1)
        halfw = width * grow
        e = (halfw - d) / (aa / np.maximum(rr, 1e-3) * 0.9 + 1e-6)
        return np.clip(e, 0, 1) * (rr > disc_r * 0.92) * (rr < length)

    ray = wedge(0.0, ray_w, long_ray)
    ray = np.maximum(ray, wedge(np.pi / k, ray_w * 0.78, short_len) * 0.92)

    sun_i = np.clip(np.maximum(disc, ray) + corona * 0.42, 0, 1.35)

    # colour ramp: white-hot core -> warm gold body -> saturated amber tips
    t = np.clip((rr - disc_r * 0.35) / (long_ray * 0.95), 0, 1)[..., None]
    sun_rgb = np.clip(
        c_hot[None, None, :] * (1 - t) ** 2.1
        + c_warm[None, None, :] * 4 * t * (1 - t)
        + c_gold[None, None, :] * t ** 1.9, 0, 1)

    a_sun = np.clip(sun_i, 0, 1)
    # thin amber rim under the geometry so the sun separates from the field
    rim = np.clip((np.maximum(disc, ray) - 0.12) / 0.5, 0, 1)
    edge = np.clip(rim - np.clip((np.maximum(disc, ray) - 0.55) / 0.45, 0, 1), 0, 1)
    sun_rgb = np.clip(sun_rgb * (1 - edge[..., None] * 0.40)
                      + np.array([0.72, 0.42, 0.06])[None, None, :]
                      * edge[..., None] * 0.40, 0, 1)
    out_rgb = np.clip(base_rgb * (1 - a_sun[..., None]) + sun_rgb * a_sun[..., None]
                      + sun_rgb * np.clip(sun_i - 1, 0, 1)[..., None] * 0.5, 0, 1)
    out_a = np.clip(np.maximum(base_a, a_sun * (rr < long_ray * 1.15)), 0, 1)

    res = Image.fromarray((np.dstack([out_rgb, out_a]) * 255).round().astype(np.uint8), "RGBA")
    if out_px:
        res = downscale(res, out_px)
    return res


def downscale(im, out_px):
    a = np.array(im).astype(np.float32) / 255.0
    al = a[:, :, 3:4]
    pre = np.concatenate([a[:, :, :3] * al, al], axis=2)
    p = Image.fromarray((pre * 255).round().astype(np.uint8), "RGBA").resize(
        (out_px, out_px), Image.LANCZOS)
    q = np.array(p).astype(np.float32) / 255.0
    qa = q[:, :, 3:4]
    rgbq = np.where(qa > 1e-4, q[:, :, :3] / np.maximum(qa, 1e-4), 0.0)
    return Image.fromarray((np.dstack([np.clip(rgbq, 0, 1), qa]) * 255)
                           .round().astype(np.uint8), "RGBA")
