#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数化外壳生成器（「路径 B：精确配合件」用）

给一个**圆形小物件**做一个能把它装进去的壳 —— 内腔、开孔、壁厚、卡扣全部
由数字算出来，改一个数就能重出模型。

适用于：录音豆 / 耳机充电仓 / 药盒 / 传感器 / 任何"要塞进去 + 要透气"的件。
**不适用于**：摆件、手办、造型件 —— 那些走「路径 A：文生图 → 图生3D」。

依赖（由 setup_env.py 一次性准备，用户不装任何东西）:
    trimesh  manifold3d  shapely  numpy

用法:
    <venv>/bin/python param_shell.py            # 出件，写到当前目录
    <venv>/bin/python param_shell.py --report   # 只打印尺寸自检，不写文件
    <venv>/bin/python param_shell.py --out DIR  # 指定输出目录

产出:
    body.stl  下盆（或叫底座）
    lid.stl   顶盖
    shell.3mf 两个零件合装，一次拖进拓竹 App
"""
import argparse
import os
import sys

try:
    import numpy as np
    import trimesh
    from shapely.geometry import box as shp_box
except ImportError as e:
    sys.stderr.write(
        '\n❌ 缺少依赖：%s\n'
        '请先运行同目录下的 setup_env.py 准备环境（用户不需要参与）：\n'
        '    python3 %s\n\n' % (e, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'setup_env.py'))
    )
    sys.exit(2)


# ═══════════════════════════════════════════════════════════════
#  参数区 —— 改这里就行
# ═══════════════════════════════════════════════════════════════

# ---- 1. 被装进去的东西（内腔尺寸由它推出来）----
OBJ_D = 23.2        # 物件直径 (mm)
OBJ_H = 13.45       # 物件厚度 / 高度 (mm)
FIT = 0.40          # 单边配合间隙 (mm)。FDM 打印建议 0.3~0.5，太大晃、太小塞不进
CLEAR_H = 1.50      # 物件上方的额外余量 (mm)。留出来给磁吸垫片、线材、公差

# ---- 2. 外壳外形 ----
SHELL_W = 62.0      # 宽 (X)
SHELL_D = 46.0      # 深 / 高 (Y)
CORNER_R = 4.0      # 四角圆角半径。想做成正圆壳：让 SHELL_W = SHELL_D = 直径，且 CORNER_R = 直径/2
PLATE = 2.0         # 顶板 / 底板厚度
WALL = 2.0          # 侧墙厚度
WALL_H = 8.0        # 侧墙高度（从内腔底面算起）。越低 → 侧面越敞开 → 越透气
POST_ON = True      # 四角是否加立柱（只保 4 个点撑住盖板，其余侧面全开）
POST = 8.0          # 立柱截面边长

# ---- 3. 开窗（透气 / 声学 / 观察）----
WIN_TOP = True      # 顶板开窗
WIN_BOTTOM = True   # 底板开窗
WIN_D = 19.0        # 窗口外径
CB_D = 1.2          # 内壁沉台深度。**有效孔长 = PLATE − CB_D**，这个数越小声音越透
CB_GROW = 2.0       # 沉台比窗口大多少（直径）

# ---- 4. 一体卡扣（无额外零件）----
SNAP_ON = True
SNAP_R = 0.70       # 卡钩半圆半径 = 凹槽深度
SNAP_Z = 6.0        # 凹槽中心高度
ARM_W = 12.0        # 弹性臂宽度
ARM_T = 1.4         # 弹性臂厚度
ARM_L = 12.0        # 弹性臂长度
CLA = 0.20          # 弹性臂与墙内壁的滑动间隙

# ---- 5. 挂绳 / 挂孔 ----
HOLE_ON = True
HOLE_D = 4.5        # 孔径
HOLE_XY = (-24.0, 18.0)   # 孔心坐标（底板平面内）

PRESS_ON = True     # 盖板内侧是否加"压环"轻压住物件
SEC = 256           # 圆柱分段数（越大越圆、面数越多）

# ═══════════════════════════════════════════════════════════════
#  派生量（自动算，别手改）
# ═══════════════════════════════════════════════════════════════
CAV_D = OBJ_D + 2 * FIT                 # 内腔直径
CAV_H = OBJ_H + CLEAR_H                 # 内腔净高
Z0 = PLATE                              # 内腔底面高度
ZT = PLATE + CAV_H                      # 内腔顶面高度 = 盖板下表面
SHELL_T = PLATE + CAV_H + PLATE         # 总高
IX = SHELL_W / 2 - WALL                 # 墙内壁 X 半宽
IY = SHELL_D / 2 - WALL                 # 墙内壁 Y 半宽
SIDE_OPEN = CAV_H - WALL_H              # 侧面敞开高度
SIDE_OPEN_PCT = SIDE_OPEN / CAV_H * 100 if CAV_H else 0
EFF_HOLE = PLATE - CB_D                 # 有效孔长


def check_params():
    """参数合法性检查 —— 在跑几何之前先拦下来，省得报看不懂的错。"""
    errs, warns = [], []
    if CORNER_R <= WALL:
        errs.append('CORNER_R(%.2f) 必须 > WALL(%.2f)，否则圆角处墙会被削穿' % (CORNER_R, WALL))
    if CORNER_R > min(SHELL_W, SHELL_D) / 2:
        errs.append('CORNER_R 不能大于 min(宽,深)/2')
    if CAV_D >= 2 * min(IX, IY):
        errs.append('内腔 Ø%.2f 装不进外形里（内壁只剩 %.1f 宽）' % (CAV_D, 2 * min(IX, IY)))
    if PLATE <= 0 or WALL <= 0:
        errs.append('PLATE / WALL 必须为正')
    if WALL_H > CAV_H:
        warns.append('WALL_H(%.1f) > 内腔净高(%.1f)：侧墙会顶到盖板' % (WALL_H, CAV_H))
    if SNAP_ON and ARM_L > CAV_H:
        warns.append('ARM_L(%.1f) > 内腔净高(%.1f)：弹性臂会顶到底板' % (ARM_L, CAV_H))
    if CB_D >= PLATE:
        errs.append('CB_D(%.2f) 必须 < PLATE(%.2f)，否则窗口被挖穿' % (CB_D, PLATE))
    if SNAP_ON and SNAP_R - CLA < 0.15:
        warns.append('卡钩需要内缩 %.2fmm，太小可能压不进或钩不住' % (SNAP_R - CLA))
    if POST_ON and CORNER_R > min(SHELL_W, SHELL_D) / 4:
        warns.append('圆角较大时四角立柱可能戳出外形，考虑 POST_ON = False')
    if EFF_HOLE < 0:
        errs.append('有效孔长为负')
    if EFF_HOLE > 1.2:
        warns.append('有效孔长 %.2fmm 偏长，做声学件时人声容易发闷（建议 ≤0.8mm）' % EFF_HOLE)

    for w in warns:
        print('  ⚠️  ' + w)
    for e in errs:
        print('  ❌ ' + e)
    return not errs


# ═══════════════════════════════════════════════════════════════
#  几何工具
# ═══════════════════════════════════════════════════════════════
def rrect_poly(w, d, r, seg=48):
    """圆角矩形轮廓。r 接近 min(w,d)/2 时就是圆。"""
    return (shp_box(-w / 2, -d / 2, w / 2, d / 2)
            .buffer(-r, join_style=1)
            .buffer(r, join_style=1, quad_segs=seg))


def rrect_solid(w, d, r, h, z=0.0):
    m = trimesh.creation.extrude_polygon(rrect_poly(w, d, r), height=h)
    m.apply_translation([0, 0, z])
    return m


def box_mm(x0, x1, y0, y1, z0, z1):
    m = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    m.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return m


def cyl_z(r, z0, z1, cx=0.0, cy=0.0, sec=SEC):
    """沿 Z 轴的圆柱（上下方向）"""
    m = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sec)
    m.apply_translation([cx, cy, (z0 + z1) / 2])
    return m


def cyl_y(r, x, z, y0, y1, sec=SEC):
    """沿 Y 轴的圆柱（做卡钩 / 凹槽用），再靠旋转摆到另外两边"""
    m = trimesh.creation.cylinder(radius=r, height=y1 - y0, sections=sec)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation([x, (y0 + y1) / 2, z])
    return m


def cyl_x(r, y, z, x0, x1, sec=SEC):
    """沿 X 轴的圆柱"""
    m = trimesh.creation.cylinder(radius=r, height=x1 - x0, sections=sec)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    m.apply_translation([(x0 + x1) / 2, y, z])
    return m


def u(*ms):
    """并集：把多个实体合成一个"""
    return trimesh.boolean.union(list(ms), engine='manifold')


def d(a, *ms):
    """差集：从 a 里挖掉后面的"""
    return trimesh.boolean.difference([a] + list(ms), engine='manifold')


def snap_units():
    """四条边的卡扣标记：('x', ±1) 是左右两边，('y', ±1) 是前后两边"""
    return (('x', 1), ('x', -1), ('y', 1), ('y', -1))


# ═══════════════════════════════════════════════════════════════
#  下盆（底座）
# ═══════════════════════════════════════════════════════════════
def build_body():
    parts = [rrect_solid(SHELL_W, SHELL_D, CORNER_R, PLATE, 0.0)]        # 底板

    # 侧墙：先做一整圈，再掏空内部
    parts.append(d(
        rrect_solid(SHELL_W, SHELL_D, CORNER_R, WALL_H, Z0),
        rrect_solid(SHELL_W - 2 * WALL, SHELL_D - 2 * WALL, CORNER_R - WALL, WALL_H + 2, Z0 - 1),
    ))

    # 四角立柱：撑住盖板，其余侧面敞开
    if POST_ON:
        posts = [box_mm(x0, x1, y0, y1, Z0, ZT)
                 for x0, x1 in ((IX - POST, IX), (-IX, -IX + POST))
                 for y0, y1 in ((IY - POST, IY), (-IY, -IY + POST))]
        parts.append(u(*posts))

    # 底面定位环：卡住物件不让它滑动
    parts.append(d(cyl_z(CAV_D / 2 + WALL, Z0, Z0 + 3.0),
                   cyl_z(CAV_D / 2, Z0 - 1, Z0 + 4.0)))

    body = u(*parts)

    cuts = []
    if WIN_BOTTOM:
        cuts.append(cyl_z(WIN_D / 2, -1, PLATE + 1))
        cuts.append(cyl_z(WIN_D / 2 + CB_GROW / 2, Z0 - 0.001, Z0 + CB_D))
    if HOLE_ON:
        cuts.append(cyl_z(HOLE_D / 2, -1, PLATE + 1, HOLE_XY[0], HOLE_XY[1]))
    if SNAP_ON:
        for axis, side in snap_units():
            if axis == 'x':
                cuts.append(cyl_y(SNAP_R, side * IX, SNAP_Z, -ARM_W / 2, ARM_W / 2))
            else:
                cuts.append(cyl_x(SNAP_R, side * IY, SNAP_Z, -ARM_W / 2, ARM_W / 2))

    return d(body, *cuts)


# ═══════════════════════════════════════════════════════════════
#  顶盖
# ═══════════════════════════════════════════════════════════════
def build_lid():
    parts = [rrect_solid(SHELL_W, SHELL_D, CORNER_R, PLATE, ZT)]          # 顶板

    if SNAP_ON:
        for axis, side in snap_units():
            if axis == 'x':
                xo = side * (IX - CLA)
                xi = xo - side * ARM_T
                parts.append(box_mm(min(xo, xi), max(xo, xi),
                                    -ARM_W / 2, ARM_W / 2, ZT - ARM_L, ZT))
                parts.append(cyl_y(SNAP_R, xo, SNAP_Z, -ARM_W / 2, ARM_W / 2))
            else:
                yo = side * (IY - CLA)
                yi = yo - side * ARM_T
                parts.append(box_mm(-ARM_W / 2, ARM_W / 2,
                                    min(yo, yi), max(yo, yi), ZT - ARM_L, ZT))
                parts.append(cyl_x(SNAP_R, yo, SNAP_Z, -ARM_W / 2, ARM_W / 2))

    if PRESS_ON:   # 中心压环：轻压住物件顶面，防晃
        parts.append(d(cyl_z(CAV_D / 2 + WALL, ZT - 1.4, ZT + 1),
                       cyl_z(CAV_D / 2, ZT - 3, ZT + 2)))

    lid = u(*parts)

    cuts = []
    if WIN_TOP:
        cuts.append(cyl_z(WIN_D / 2, ZT - 1, SHELL_T + 1))
        cuts.append(cyl_z(WIN_D / 2 + CB_GROW / 2, ZT - CB_D, ZT + 0.001))

    return d(lid, *cuts)


# ═══════════════════════════════════════════════════════════════
#  自检 + 导出
# ═══════════════════════════════════════════════════════════════
def describe(name, m):
    b = m.bounds
    size = b[1] - b[0]
    ok = m.is_watertight and m.volume > 0
    print('  %-4s 尺寸 %6.2f × %6.2f × %6.2f mm | 三角面 %6d | 体积 %6.2f cm³ | z %5.2f~%5.2f | 水密 %s'
          % (name, size[0], size[1], size[2], len(m.faces), m.volume / 1000,
             b[0][2], b[1][2], '✅' if m.is_watertight else '❌'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='.', help='输出目录')
    ap.add_argument('--report', action='store_true', help='只打印自检，不写文件')
    ap.add_argument('--prefix', default='', help='输出文件名前缀，例如 a-')
    a = ap.parse_args()

    print('=' * 74)
    print('参数化外壳生成器 · 物件 Ø%.2f × %.2fmm → 壳 %g × %g × %.2fmm'
          % (OBJ_D, OBJ_H, SHELL_W, SHELL_D, SHELL_T))
    print('=' * 74)

    print('\n[参数检查]')
    if not check_params():
        print('\n参数不合法，已中止。改上面【参数区】后重跑。')
        return 2
    print('  通过')

    body = build_body()
    lid = build_lid()

    print('\n[零件]')
    ok = describe('下盆', body)
    ok = describe('顶盖', lid) and ok

    print('\n[配合自检]')
    print('  内腔直径         : %6.2f mm   （物件 %.2f + 单边 %.2f）' % (CAV_D, OBJ_D, FIT))
    print('  内腔净高         : %6.2f mm   （物件 %.2f + 余量 %.2f）' % (CAV_H, OBJ_H, CLEAR_H))
    print('  侧面敞开         : %6.2f mm / 净高 %.2f mm → %.0f%%' % (SIDE_OPEN, CAV_H, SIDE_OPEN_PCT))
    if WIN_TOP or WIN_BOTTOM:
        print('  有效孔长         : %6.2f mm   （板厚 %.2f − 沉台 %.2f）' % (EFF_HOLE, PLATE, CB_D))
        print('  窗口面积 / 物件面: %6.0f%%' % ((WIN_D / OBJ_D) ** 2 * 100))
    if SNAP_ON:
        print('  卡钩突出 / 凹槽深: %6.2f / %.2f mm → 压入需内缩 %.2f mm' % (SNAP_R, SNAP_R, SNAP_R - CLA))
    print('  总高             : %6.2f mm' % SHELL_T)

    if not ok:
        print('\n❌ 有零件不水密或体积为负 —— 别交付，先查参数。')

    if a.report:
        print('\n（--report 模式，未写文件）')
        return 0 if ok else 1

    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    pb = os.path.join(out, a.prefix + 'body.stl')
    pl = os.path.join(out, a.prefix + 'lid.stl')
    pm = os.path.join(out, a.prefix + 'shell.3mf')
    body.export(pb)
    lid.export(pl)
    sc = trimesh.Scene()
    sc.add_geometry(body, node_name='body', geom_name='body')
    sc.add_geometry(lid, node_name='lid', geom_name='lid')
    sc.export(pm)

    print('\n[导出]')
    for p in (pb, pl, pm):
        print('  %-52s %6.0f KB' % (p, os.path.getsize(p) / 1024))
    print('\n下一步：把这几个文件交给用户看（🛑 节点 2），确认后再在拓竹 App 里打开。')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
