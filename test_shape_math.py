import sys
import math

# Test math for each shape
def get_rectangle(cx, cy, width, height, steps=54):
    w_val = float(width)
    h_val = float(height)
    hx = w_val / 2.0
    hy = h_val / 2.0
    corners = [
        (cx - hx, cy - hy),
        (cx + hx, cy - hy),
        (cx + hx, cy + hy),
        (cx - hx, cy + hy),
        (cx - hx, cy - hy),
    ]
    stroke = []
    sub = max(4, steps // 4)
    for k in range(len(corners) - 1):
        c1, c2 = corners[k], corners[k + 1]
        for s in range(sub):
            t = s / float(sub)
            stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
    stroke.append(corners[-1])
    return stroke

def get_circle(cx, cy, width, height, steps=54):
    r_val = min(float(width), float(height)) / 2.0
    stroke = []
    for i in range(steps + 1):
        angle = 2.0 * math.pi * (i / float(steps))
        stroke.append((cx + r_val * math.cos(angle), cy + r_val * math.sin(angle)))
    return stroke

def get_square(cx, cy, width, height, steps=54):
    side = min(float(width), float(height))
    hx = side / 2.0
    hy = side / 2.0
    corners = [
        (cx - hx, cy - hy),
        (cx + hx, cy - hy),
        (cx + hx, cy + hy),
        (cx - hx, cy + hy),
        (cx - hx, cy - hy),
    ]
    stroke = []
    sub = max(4, steps // 4)
    for k in range(len(corners) - 1):
        c1, c2 = corners[k], corners[k + 1]
        for s in range(sub):
            t = s / float(sub)
            stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
    stroke.append(corners[-1])
    return stroke

def get_parallelogram(cx, cy, width, height, steps=54):
    w_val = float(width)
    h_val = float(height)
    hx = w_val / 2.0
    hy = h_val / 2.0
    slant = w_val * 0.25
    corners = [
        (cx - hx + slant / 2.0, cy - hy),      # Top-left
        (cx + hx + slant / 2.0, cy - hy),      # Top-right
        (cx + hx - slant / 2.0, cy + hy),      # Bottom-right
        (cx - hx - slant / 2.0, cy + hy),      # Bottom-left
        (cx - hx + slant / 2.0, cy - hy),      # Close back to Top-left
    ]
    stroke = []
    sub = max(4, steps // 4)
    for k in range(len(corners) - 1):
        c1, c2 = corners[k], corners[k + 1]
        for s in range(sub):
            t = s / float(sub)
            stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
    stroke.append(corners[-1])
    return stroke

def get_trapezium(cx, cy, width, height, steps=54):
    w_val = float(width)
    h_val = float(height)
    w_top = w_val * 0.55
    w_bot = w_val
    hy = h_val / 2.0
    h_top = w_top / 2.0
    h_bot = w_bot / 2.0
    corners = [
        (cx - h_top, cy - hy),      # Top-left
        (cx + h_top, cy - hy),      # Top-right
        (cx + h_bot, cy + hy),      # Bottom-right
        (cx - h_bot, cy + hy),      # Bottom-left
        (cx - h_top, cy - hy),      # Close back to Top-left
    ]
    stroke = []
    sub = max(4, steps // 4)
    for k in range(len(corners) - 1):
        c1, c2 = corners[k], corners[k + 1]
        for s in range(sub):
            t = s / float(sub)
            stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
    stroke.append(corners[-1])
    return stroke

shapes = {
    "rectangle": get_rectangle(450, 350, 200, 110),
    "circle": get_circle(960, 350, 120, 120),
    "square": get_square(1450, 350, 120, 120),
    "parallelogram": get_parallelogram(680, 670, 200, 110),
    "trapezium": get_trapezium(1240, 670, 200, 110),
}

for name, s in shapes.items():
    print(f"{name}: {len(s)} pts, start={s[0]}, end={s[-1]}")
    # Verify closed loop
    dx = abs(s[0][0] - s[-1][0])
    dy = abs(s[0][1] - s[-1][1])
    assert dx < 1e-3 and dy < 1e-3, f"{name} is not closed: dx={dx}, dy={dy}"

print("All 5 shapes pass closed-loop geometric tests!")
