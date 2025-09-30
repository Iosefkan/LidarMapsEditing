from __future__ import annotations
import argparse, os, sys, math, json
from dataclasses import dataclass
from typing import Tuple, List
import numpy as np
import open3d as o3d

np.random.seed(42)
def log(m): print(m, file=sys.stderr)
def to_np(pcd): return np.asarray(pcd.points, dtype=np.float64)
def from_np(xyz):
    p=o3d.geometry.PointCloud()
    p.points=o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return p

# ---------- 2.5D квантильная сетка ----------
@dataclass
class Grid2p5D:
    grid: float; origin: Tuple[float,float]; W:int; H:int
    z_low: np.ndarray; z_high: np.ndarray; count: np.ndarray

def build_grid(points: np.ndarray, grid: float, q_low=0.02, q_high=0.90) -> Grid2p5D:
    xy=points[:,:2]; z=points[:,2]
    mn=xy.min(axis=0); mx=xy.max(axis=0); origin=mn
    W=int(math.ceil((mx[0]-mn[0])/grid))+1
    H=int(math.ceil((mx[1]-mn[1])/grid))+1
    ix=np.floor((xy[:,0]-origin[0])/grid).astype(np.int64); ix=np.clip(ix,0,W-1)
    iy=np.floor((xy[:,1]-origin[1])/grid).astype(np.int64); iy=np.clip(iy,0,H-1)
    gid=iy*W+ix
    order=np.argsort(gid); gid_s=gid[order]; z_s=z[order]
    uniq, start, cnt=np.unique(gid_s, return_index=True, return_counts=True)

    z_low=np.full((H,W), np.nan, dtype=np.float32)
    z_high=np.full((H,W), np.nan, dtype=np.float32)
    count=np.zeros((H,W), dtype=np.int32)
    for u,s,c in zip(uniq,start,cnt):
        seg=z_s[s:s+c]
        low=np.quantile(seg, q_low)
        high=np.quantile(seg, q_high)
        iyc=int(u//W); ixc=int(u%W)
        z_low[iyc,ixc]=low; z_high[iyc,ixc]=high; count[iyc,ixc]=c
    return Grid2p5D(grid,(origin[0],origin[1]),W,H,z_low,z_high,count)

# ---------- фильтр по окну (без SciPy) ----------
def nanmean_filter(A: np.ndarray, radius: int) -> np.ndarray:
    if radius<=0: return A.copy()
    H,W=A.shape
    acc=np.zeros((H,W), dtype=np.float64)
    cnt=np.zeros((H,W), dtype=np.float64)
    for dy in range(-radius, radius+1):
        y0=max(0,-dy); y1=min(H,H-dy)
        for dx in range(-radius, radius+1):
            x0=max(0,-dx); x1=min(W,W-dx)
            src=A[y0:y1, x0:x1]
            tgt=acc[y0+dy:y1+dy, x0+dx:x1+dx]
            tcnt=cnt[y0+dy:y1+dy, x0+dx:x1+dx]
            m=~np.isnan(src)
            tgt[m]+=src[m]; tcnt[m]+=1.0
    out=np.full_like(A, np.nan, dtype=np.float64)
    m=cnt>0; out[m]=acc[m]/cnt[m]
    return out

# ---------- связные компоненты ----------
def connected_components(mask: np.ndarray) -> List[np.ndarray]:
    H,W=mask.shape
    seen=np.zeros_like(mask, dtype=bool)
    comps=[]
    neigh=[(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    for y in range(H):
        xs=np.where(mask[y] & (~seen[y]))[0]
        for x in xs:
            if seen[y,x]: continue
            q=[(y,x)]; seen[y,x]=True; comp=[]
            while q:
                cy,cx=q.pop(); comp.append(cy*W+cx)
                for dy,dx in neigh:
                    ny=cy+dy; nx=cx+dx
                    if ny<0 or nx<0 or ny>=H or nx>=W: continue
                    if mask[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx]=True; q.append((ny,nx))
            comps.append(np.array(comp, dtype=np.int64))
    return comps

def xy_to_cell(xy: np.ndarray, origin: Tuple[float,float], grid: float, W:int, H:int):
    ix=np.floor((xy[:,0]-origin[0])/grid).astype(np.int64)
    iy=np.floor((xy[:,1]-origin[1])/grid).astype(np.int64)
    valid=(ix>=0)&(iy>=0)&(ix<W)&(iy<H)
    return ix,iy,valid

# ---------- НОВОЕ: Hough-полосы ----------
def detect_hough_bands(G: Grid2p5D, cand: np.ndarray,
                       theta_step_deg: float = 5.0,
                       rho_bin_m: float = 0.5,
                       topk: int = 8,
                       min_len_m: float = 8.0,
                       min_width_m: float = 1.0,
                       max_width_m: float = 4.5,
                       dilate_cells: int = 1) -> np.ndarray:
    """
    Ищем длинные полосы в бинарной карте cand (без требования связности).
    Возвращает маску клеток-банд, которые надо удалить.
    """
    ys, xs = np.where(cand)
    if ys.size < 40:
        return np.zeros_like(cand, dtype=bool)

    # центры клеток в метрах
    C = np.column_stack([G.origin[0] + (xs + 0.5)*G.grid,
                         G.origin[1] + (ys + 0.5)*G.grid])

    thetas = np.deg2rad(np.arange(0.0, 180.0, theta_step_deg))
    nT = len(thetas)

    # диапазон rho
    x_all = C[:,0]; y_all = C[:,1]
    rho_min = +np.inf; rho_max = -np.inf
    # оценим по всем углам сразу (консервативно по bbox)
    bbox = np.array([[x_all.min(), y_all.min()],
                     [x_all.min(), y_all.max()],
                     [x_all.max(), y_all.min()],
                     [x_all.max(), y_all.max()]])
    for th in thetas:
        c, s = math.cos(th), math.sin(th)
        rhos = bbox @ np.array([c, s])
        rho_min = min(rho_min, float(rhos.min()))
        rho_max = max(rho_max, float(rhos.max()))
    Nrho = max(1, int(math.ceil((rho_max - rho_min) / rho_bin_m)) + 1)

    A = np.zeros((nT, Nrho), dtype=np.int32)  # аккумулятор
    # накидываем голоса
    for ti, th in enumerate(thetas):
        c, s = math.cos(th), math.sin(th)
        rho = C @ np.array([c, s])
        ridx = np.floor((rho - rho_min) / rho_bin_m).astype(np.int32)
        ridx = np.clip(ridx, 0, Nrho-1)
        # каждый центр дает один голос
        np.add.at(A[ti], ridx, 1)

    # выбираем top-K пиков (без близких дублей)
    peaks = []
    flat_idx = np.argsort(A.ravel())[::-1]
    used = np.zeros_like(A, dtype=bool)
    for idx in flat_idx:
        if len(peaks) >= topk:
            break
        ti = int(idx // Nrho); ri = int(idx % Nrho)
        if used[ti, ri]: 
            continue
        if A[ti, ri] < max(20, int(0.25 * A.max())):
            break
        peaks.append((ti, ri))
        # глушим окрестность, чтобы не брать почти те же линии
        t0 = max(0, ti-1); t1 = min(nT, ti+2)
        r0 = max(0, ri-3); r1 = min(Nrho, ri+4)
        used[t0:t1, r0:r1] = True

    band_mask = np.zeros_like(cand, dtype=bool)
    if not peaks:
        return band_mask

    # для каждой линии собираем клетки в полосу нужной ширины и длины
    for ti, ri in peaks:
        th = float(thetas[ti]); c, s = math.cos(th), math.sin(th)
        rho = rho_min + ri * rho_bin_m
        n = np.array([c, s])                   # нормаль
        u = np.array([-s, c])                  # вдоль линии
        # расстояние от центров до линии
        d = np.abs(C @ n - rho)
        in_band = d <= (max_width_m/2.0)
        if in_band.sum() < 30:
            continue
        t = C @ u
        L = t[in_band].max() - t[in_band].min()
        if L < min_len_m:
            continue
        # оценим фактическую ширину по 90-му процентилю
        w_est = 2.0 * np.quantile(d[in_band], 0.9)
        if not (min_width_m <= w_est <= max_width_m):
            continue
        # отметим клетки
        idx_lin = ys*G.W + xs
        band_mask.reshape(-1)[idx_lin[in_band]] = True

    if dilate_cells > 0:
        band_mask = binary_dilate(band_mask, dilate_cells)

    return band_mask

# ---------- простая морфология для склейки/расширения ----------
def binary_dilate(mask, r):
    if r<=0: return mask.copy()
    H,W=mask.shape; out=np.zeros_like(mask)
    for dy in range(-r,r+1):
        y0=max(0,-dy); y1=min(H,H-dy)
        for dx in range(-r,r+1):
            x0=max(0,-dx); x1=min(W,W-dx)
            out[y0+dy:y1+dy, x0+dx:x1+dx] |= mask[y0:y1, x0:x1]
    return out

# ---------- основной процесс ----------
def process(in_path: str, out_path: str,
            grid: float=0.35, q_low: float=0.02, q_high: float=0.90,
            smooth_cells: int=7,
            h_min: float=0.20, h_max: float=3.0,
            min_len: float=3.0, min_width: float=1.4, max_width: float=3.5,
            min_elong: float=2.2, density_min: int=5,
            use_hough: bool=False,
            hough_theta_step: float=5.0, hough_rho_bin: float=0.5, hough_topk: int=8,
            hough_min_len: float=8.0, hough_min_w: float=1.0, hough_max_w: float=4.5,
            hough_dilate: int=1,
            debug_dump: bool=False,
            delta_out_path: str | None = None):

    log(f"Чтение: {in_path}")
    pcd=o3d.io.read_point_cloud(in_path)
    if len(pcd.points)==0: raise RuntimeError("Пустое облако")
    if os.path.isdir(out_path): out_path=os.path.join(out_path,"cleaned.pcd")
    if not out_path.lower().endswith(".pcd"): out_path=out_path+".pcd"
    P=to_np(pcd)

    # 1) карта низов/верхов и dh
    log("Строим 2.5D сетку…")
    G=build_grid(P, grid=grid, q_low=q_low, q_high=q_high)
    z_ground = nanmean_filter(G.z_low, radius=smooth_cells)
    dh = G.z_high - z_ground

    valid = (~np.isnan(dh)) & (G.count >= density_min)
    cand = valid & (dh >= h_min) & (dh <= h_max)

    # 2) компонентная логика (как была)
    comps = connected_components(cand)
    keep = np.zeros_like(cand, dtype=bool)
    sel = 0
    for comp in comps:
        if comp.size < 4:
            continue
        ys = comp // G.W; xs = comp % G.W
        X = np.column_stack([G.origin[0] + (xs + 0.5)*G.grid,
                             G.origin[1] + (ys + 0.5)*G.grid])
        mu = X.mean(axis=0)
        C = np.cov((X - mu).T)
        evals, _ = np.linalg.eigh(C)           # λ1<=λ2
        lam1, lam2 = float(evals[0]), float(evals[1])
        length = 2.0 * math.sqrt(max(lam2, 1e-12))
        width  = 2.0 * math.sqrt(max(lam1, 1e-12))
        if length < min_len:            continue
        if width  < min_width:          continue
        if width  > max_width:          continue
        if (length / max(width,1e-6)) < min_elong: continue
        keep.reshape(-1)[comp] = True
        sel += 1
    log(f"Компонент после фильтров (PCA): {sel}")

    # 3) НОВОЕ: Hough-полосы (добавляем к keep)
    if use_hough:
        band_mask = detect_hough_bands(
            G, cand,
            theta_step_deg=hough_theta_step,
            rho_bin_m=hough_rho_bin,
            topk=hough_topk,
            min_len_m=hough_min_len,
            min_width_m=hough_min_w,
            max_width_m=hough_max_w,
            dilate_cells=hough_dilate
        )
        log(f"Hough-полосы: клеток в маске = {int(band_mask.sum())}")
        keep |= band_mask

    # 4) перенос на точки и удаление
    ix,iy,valid_pts = xy_to_cell(P[:,:2], G.origin, G.grid, G.W, G.H)
    inside_cells = np.zeros(P.shape[0], dtype=bool)
    m = valid_pts & keep[iy, ix]
    inside_cells[m] = True

    z_ground_pt = np.full(P.shape[0], np.nan, dtype=np.float64)
    z_ground_pt[valid_pts] = z_ground[iy[valid_pts], ix[valid_pts]]
    h_pt = P[:,2] - z_ground_pt
    h_ok = (~np.isnan(h_pt)) & (h_pt >= h_min) & (h_pt <= h_max)

    del_mask = inside_cells & h_ok
    removed = int(del_mask.sum())
    log(f"К удалению намечено точек: {removed}")

    static_pts = P[~del_mask]
    removed_pts = P[del_mask]
    # безопасное сохранение: фильтруем NaN/Inf; PLY-фолбэк при необходимости
    finite = np.isfinite(static_pts).all(axis=1)
    if not finite.all():
        log(f"Предупреждение: удаляем не-финитные точки: {(~finite).sum()}")
        static_pts = static_pts[finite]
    # Write binary (optionally compressed) PCD to reduce file size
    ok = o3d.io.write_point_cloud(out_path, from_np(static_pts), write_ascii=False, compressed=True)
    if not ok:
        alt = os.path.splitext(out_path)[0]+".ply"
        log("PCD не записался, сохраняю как PLY…")
        o3d.io.write_point_cloud(alt, from_np(static_pts), write_ascii=True)
        log(f"Сохранено: {alt}")
    else:
        log(f"Сохранение: {out_path}")

    # Always write delta if requested
    if delta_out_path is not None:
        try:
            if removed_pts.size > 0:
                o3d.io.write_point_cloud(delta_out_path, from_np(removed_pts), write_ascii=False, compressed=True)
        except Exception as e:
            log(f"Не удалось записать delta: {e}")

    if debug_dump:
        base=os.path.splitext(out_path)[0]
        try: o3d.io.write_point_cloud(base+"_removed.pcd", from_np(P[del_mask]))
        except: pass
        ys, xs = np.where(keep)
        if ys.size>0:
            centers = np.column_stack([G.origin[0] + (xs + 0.5)*G.grid,
                                       G.origin[1] + (ys + 0.5)*G.grid,
                                       np.full(xs.shape[0], float(np.nanmean(z_ground)))])
            try: o3d.io.write_point_cloud(base+"_keepcells_centers.pcd", from_np(centers))
            except: pass

    summary = {
        "input_points": int(P.shape[0]),
        "removed_points": removed,
        "grid": grid, "q_low": q_low, "q_high": q_high,
        "smooth_cells": smooth_cells,
        "h_min": h_min, "h_max": h_max,
        "min_len": min_len, "min_width": min_width, "max_width": max_width,
        "min_elong": min_elong, "density_min": density_min,
        "hough_used": bool(use_hough),
        "hough_theta_step": hough_theta_step,
        "hough_rho_bin": hough_rho_bin,
        "hough_topk": hough_topk,
        "hough_min_len": hough_min_len,
        "hough_min_w": hough_min_w,
        "hough_max_w": hough_max_w
    }
    with open(os.path.splitext(out_path)[0]+"_summary.json","w",encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary

def main():
    ap=argparse.ArgumentParser(description="2.5D + Hough-полосы для удаления длинных лент")
    ap.add_argument("--in",  required=True, dest="in_path")
    ap.add_argument("--out", required=True, dest="out_path")
    ap.add_argument("--grid", type=float, default=0.35)
    ap.add_argument("--q_low", type=float, default=0.02)
    ap.add_argument("--q_high", type=float, default=0.90)
    ap.add_argument("--smooth_cells", type=int, default=7)
    ap.add_argument("--h_min", type=float, default=0.20)
    ap.add_argument("--h_max", type=float, default=3.0)
    ap.add_argument("--min_len", type=float, default=3.0)
    ap.add_argument("--min_width", type=float, default=1.4)
    ap.add_argument("--max_width", type=float, default=3.5)
    ap.add_argument("--min_elong", type=float, default=2.2)
    ap.add_argument("--density_min", type=int, default=5)
    ap.add_argument("--use_hough", action="store_true")
    ap.add_argument("--hough_theta_step", type=float, default=5.0)
    ap.add_argument("--hough_rho_bin", type=float, default=0.5)
    ap.add_argument("--hough_topk", type=int, default=8)
    ap.add_argument("--hough_min_len", type=float, default=8.0)
    ap.add_argument("--hough_min_w", type=float, default=1.0)
    ap.add_argument("--hough_max_w", type=float, default=4.5)
    ap.add_argument("--hough_dilate", type=int, default=1)
    ap.add_argument("--debug_dump", action="store_true")
    args=ap.parse_args()

    process(args.in_path, args.out_path,
            grid=args.grid, q_low=args.q_low, q_high=args.q_high,
            smooth_cells=args.smooth_cells,
            h_min=args.h_min, h_max=args.h_max,
            min_len=args.min_len, min_width=args.min_width, max_width=args.max_width,
            min_elong=args.min_elong, density_min=args.density_min,
            use_hough=args.use_hough,
            hough_theta_step=args.hough_theta_step,
            hough_rho_bin=args.hough_rho_bin,
            hough_topk=args.hough_topk,
            hough_min_len=args.hough_min_len,
            hough_min_w=args.hough_min_w,
            hough_max_w=args.hough_max_w,
            hough_dilate=args.hough_dilate,
            debug_dump=args.debug_dump)

if __name__=="__main__":
    main()