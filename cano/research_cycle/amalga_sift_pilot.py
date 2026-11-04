"""Offline SIFT baseline for two images; synthetic smoke test needs no downloads."""
import argparse, json
from pathlib import Path
import cv2
import numpy as np

def evaluate(a,b, known_h=None):
    sift=cv2.SIFT_create(nfeatures=1500)
    k1,d1=sift.detectAndCompute(a,None)
    k2,d2=sift.detectAndCompute(b,None)
    result={'keypoints_a':len(k1),'keypoints_b':len(k2),'ratio_matches':0,'ransac_inliers':0,'inlier_fraction':None,'median_reprojection_error_px':None}
    if d1 is None or d2 is None or len(d2)<2:return result
    knn=cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1,d2,k=2)
    good=[pair[0] for pair in knn if len(pair)==2 and pair[0].distance<0.75*pair[1].distance]
    result['ratio_matches']=len(good)
    if len(good)<4:return result
    src=np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst=np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    H,mask=cv2.findHomography(src,dst,cv2.RANSAC,5.0)
    if H is None or mask is None:return result
    inliers=mask.ravel().astype(bool)
    result['ransac_inliers']=int(inliers.sum())
    result['inlier_fraction']=float(inliers.mean())
    projected=cv2.perspectiveTransform(src,H).reshape(-1,2)
    result['median_reprojection_error_px']=float(np.median(np.linalg.norm(projected[inliers]-dst.reshape(-1,2)[inliers],axis=1))) if inliers.any() else None
    if known_h is not None:
        expected=cv2.perspectiveTransform(src,known_h).reshape(-1,2)
        result['median_ground_truth_error_px']=float(np.median(np.linalg.norm(expected-dst.reshape(-1,2),axis=1)))
    return result

def synthetic():
    rng=np.random.default_rng(20261101)
    a=np.zeros((600,800),np.uint8)
    for i in range(180):
        x,y=rng.integers(35,765),rng.integers(35,565)
        cv2.circle(a,(int(x),int(y)),int(rng.integers(3,11)),int(rng.integers(90,255)),-1)
    for i in range(30):
        x,y=rng.integers(30,700),rng.integers(30,500)
        cv2.line(a,(int(x),int(y)),(int(x+30),int(y+20)),200,2)
    H=cv2.getRotationMatrix2D((400,300),7,0.96)
    H[:,2]+=[14,-11]
    h=np.vstack([H,[0,0,1]]).astype(np.float64)
    b=cv2.warpPerspective(a,h,(800,600))
    return a,b,h

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image-a',type=Path)
    p.add_argument('--image-b',type=Path)
    args=p.parse_args()
    if bool(args.image_a)!=bool(args.image_b):p.error('Supply both images or neither (synthetic mode).')
    if args.image_a:
        a=cv2.imread(str(args.image_a),cv2.IMREAD_GRAYSCALE)
        b=cv2.imread(str(args.image_b),cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:p.error('Could not read one or both images.')
        h=None
    else:a,b,h=synthetic()
    print(json.dumps({'mode':'real_pair' if args.image_a else 'synthetic','opencv':cv2.__version__,**evaluate(a,b,h)},indent=2))
if __name__=='__main__':main()