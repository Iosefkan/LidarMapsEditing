import json
import os
from .schemas import CleanRequest
from .clearing_algorithm import process as process_pcd


def run_clean_process(in_path: str, out_path: str, params: CleanRequest, delta_out_path: str | None = None) -> dict:
    """
    Call clearing_algorithm.process directly and return the summary dict it returns.
    """
    summary = process_pcd(
        in_path,
        out_path,
        grid=params.grid,
        q_low=params.q_low,
        q_high=params.q_high,
        smooth_cells=params.smooth_cells,
        h_min=params.h_min,
        h_max=params.h_max,
        min_len=params.min_len,
        min_width=params.min_width,
        max_width=params.max_width,
        min_elong=params.min_elong,
        density_min=params.density_min,
        use_hough=params.use_hough,
        hough_theta_step=params.hough_theta_step,
        hough_rho_bin=params.hough_rho_bin,
        hough_topk=params.hough_topk,
        hough_min_len=params.hough_min_len,
        hough_min_w=params.hough_min_w,
        hough_max_w=params.hough_max_w,
        hough_dilate=params.hough_dilate,
        debug_dump=params.debug_dump,
        delta_out_path=delta_out_path,
    )
    # Ensure summary.json exists for parity
    summary_path = os.path.splitext(out_path)[0] + "_summary.json"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary or {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return summary or {}


