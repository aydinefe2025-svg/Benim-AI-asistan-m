"""Independently recompute held-out importance diagnostics from private D: artifacts."""
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

def summarize(logw, z):
    logw=np.asarray(logw,dtype=float); z=np.asarray(z,dtype=float)
    if len(logw)!=512 or z.shape!=(512,13) or not np.isfinite(logw).any():
        raise AssertionError("expected 512 weighted 13D samples")
    log_sum=logsumexp(logw); w=np.exp(logw-log_sum)
    phases=[]
    for positive in (False,True):
        mask=(z[:,2]>0)==positive
        if not mask.any() or not np.isfinite(logw[mask]).any(): ess=0.0
        else: ess=float(np.exp(2*logsumexp(logw[mask])-logsumexp(2*logw[mask])))
        phases.append(ess)
    return {"ESS":float(1/np.dot(w,w)),"max_weight_fraction":float(w.max()),
            "phase_ESS":phases,"log_conditional_integral":float(log_sum-math.log(len(logw)))}

def verify(root):
    root=Path(root); manifest=json.loads((root/"run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"]=="TAILCORR_HELDOUT_COMPLETE"
    assert len(manifest["heldout_points"])>=1 and len(manifest["runs"])==4*len(manifest["heldout_points"])
    rows=[]; sample_hashes=[]
    for run in manifest["runs"]:
        m,r=run["mass_radius"]; seed=run["seed"]
        stem=f"M{m:.3f}_R{r:.2f}_seed{seed}"
        npz=root/f"{stem}_512_local.npz"; ev=root/f"{stem}_evals.jsonl"
        data=np.load(npz); z=data["z"]; logw=data["logweights"]
        diag=summarize(logw,z)
        events=[json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(events)==512 and sorted(x["index"] for x in events)==list(range(512))
        assert all(x["model_sha256"]==manifest["model_sha256"] and x["mass_radius"]==[m,r] for x in events)
        assert np.array_equal(np.asarray([x["z"] for x in events]),z)
        for key in ("ESS","max_weight_fraction","log_conditional_integral"):
            assert math.isclose(diag[key],run["prefixes"][-1][key],rel_tol=1e-10,abs_tol=1e-10),(seed,key,diag[key],run["prefixes"][-1][key])
        assert np.allclose(diag["phase_ESS"],[p["ESS"] for p in run["prefixes"][-1]["phase_partitions"]],rtol=1e-10,atol=1e-10)
        rows.append({"mass_radius":run["mass_radius"],"seed":seed,"draws":len(events),**diag,
                     "drift_256_to_512":abs(run["prefixes"][-1]["log_conditional_integral"]-run["prefixes"][-2]["log_conditional_integral"]),
                     "finite_logL_events":sum(x["logL"] is not None for x in events),
                     "npz_bytes":npz.stat().st_size,"npz_sha256":hashlib.sha256(npz.read_bytes()).hexdigest()})
    grouped=[]
    for point in manifest["heldout_points"]:
        subset=[x for x in rows if x["mass_radius"]==point["mass_radius"]]
        assert len(subset)==4
        logs=[x["log_conditional_integral"] for x in subset]
        grouped.append({"mass_radius":point["mass_radius"],"seeds":[x["seed"] for x in subset],
          "ESS_min":min(x["ESS"] for x in subset),"max_weight_max":max(x["max_weight_fraction"] for x in subset),
          "phase_ESS_min":min(min(x["phase_ESS"]) for x in subset),
          "logI_spread":max(logs)-min(logs),
          "max_256_to_512_drift":max(x["drift_256_to_512"] for x in subset)})
    return {"status":"INDEPENDENT_RECOMPUTE_PASS","runs":rows,"groups":grouped,
            "manifest_sha256":hashlib.sha256((root/"run_manifest.json").read_bytes()).hexdigest(),
            "raw_evaluation_logs_kept_local":True}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run_dir",type=Path);ap.add_argument("--output",type=Path)
    args=ap.parse_args(); result=verify(args.run_dir); out=json.dumps(result,indent=2)+"\n"
    if args.output: args.output.write_text(out,encoding="utf-8")
    print(out)

