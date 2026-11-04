"""Offline reproducibility and failure-mode suite for the SIFT baseline."""
import argparse, json
from pathlib import Path
import numpy as np
import cv2
from amalga_sift_pilot import evaluate


def make_pair(seed, angle, scale):
    rng=np.random.default_rng(seed)
    a=np.zeros((480,640),np.uint8)
    for _ in range(150):
        x=int(rng.integers(25,615)); y=int(rng.integers(25,455))
        cv2.circle(a,(x,y),int(rng.integers(3,9)),int(rng.integers(90,255)),-1)
    for _ in range(25):
        x=int(rng.integers(20,570));y=int(rng.integers(20,410))
        cv2.line(a,(x,y),(x+25,y+16),int(rng.integers(120,255)),2)
    H=cv2.getRotationMatrix2D((320,240),angle,scale)
    H[:,2]+=[11,-7]
    H=np.vstack([H,[0,0,1]]).astype(np.float64)
    b=cv2.warpPerspective(a,H,(640,480))
    return a,b,H


def run():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent / 'amalga_robustness_results.json')
    args=p.parse_args()
    rows=[]
    for seed in [11,22,33,44]:
        for angle,scale in [(0,1),(7,.96),(15,.9)]:
            a,b,h=make_pair(seed,angle,scale)
            result=evaluate(a,b,h)
            rows.append({'seed':seed,'angle_deg':angle,'scale':scale,**result})
    blank=evaluate(np.zeros((100,100),np.uint8),np.zeros((100,100),np.uint8))
    assert blank['ratio_matches']==0 and blank['ransac_inliers']==0
    assert len(rows)==12 and all(r['ransac_inliers']>0 for r in rows)
    # The known transform gives an independent error metric; the estimated H is not ground truth.
    stats={'runs':len(rows),'inlier_fraction_min':float(min(r['inlier_fraction'] for r in rows)),
        'inlier_fraction_median':float(np.median([r['inlier_fraction'] for r in rows])),
        'median_ground_truth_error_px_median':float(np.median([r['median_ground_truth_error_px'] for r in rows])),
        'median_ground_truth_error_px_max':float(max(r['median_ground_truth_error_px'] for r in rows)),
        'blank_image_test':'passed'}
    output={'protocol':'4 seeds x 3 rotation/scale settings, deterministic synthetic textures','opencv':cv2.__version__,'summary':stats,'runs':rows}
    args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(stats,indent=2))
if __name__=='__main__':run()
