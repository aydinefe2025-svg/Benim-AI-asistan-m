"""F62 transparent output-only precision patch for pinned RNS C source.

Preserves equations, model and solver; only prints full double-precision diagnostics
instead of RNS default e_c %g, mass 0.001 Msun, radius 0.01 km, spin 0.1 Hz.
Fail closed if upstream rns.c formatting no longer matches pinned commit.
"""
from pathlib import Path
import argparse
import hashlib

OLD=r'printf("%g \t %4.3f \t %4.2f \t %4.1f \n",'
NEW=r'printf("%.10g \t %.9f \t %.9f \t %.9f \n",'

def precision_patch(source):
    if source.count(OLD)!=1 or source.count(NEW):
        raise ValueError('F62_PINNED_RNS_PRINTF_SIGNATURE_DRIFT')
    result=source.replace(OLD,NEW)
    if result.count(NEW)!=1 or result.count(OLD):
        raise ValueError('F62_PRECISION_PATCH_NOT_UNIQUE')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('rns_c',type=Path);a=p.parse_args()
    old=a.rns_c.read_bytes()
    new=precision_patch(old.decode('utf-8')).encode('utf-8')
    a.rns_c.write_bytes(new)
    print({'source_only_output_format_changed':True,
           'source_rns_c_before_sha256':hashlib.sha256(old).hexdigest(),
           'source_rns_c_after_sha256':hashlib.sha256(new).hexdigest(),
           'physics_equations_changed':False})

if __name__=='__main__':main()