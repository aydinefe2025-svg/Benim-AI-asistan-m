#!/usr/bin/env python3
"""CANO privacy-conscious OFFLINE third-party witness-key receipt.

This checks possession of a previously pinned, independently controlled HMAC
key and binds it to a reverified blind-review/source snapshot. It CANNOT
verify institutional authority, real human identity, true independence,
chronological freshness, or scientific field acceptance. No key is generated
or copied by this tool. Data stay on local disk.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile

import blind_field_review as blind

REQUEST_SCHEMA = "cano.battery.witness-challenge.v1"
ENDORSEMENT_SCHEMA = "cano.battery.witness-hmac.v1"
RESULT_SCHEMA = "cano.battery.witness-integrity-report.v1"
DOMAIN = b"CANO:battery:external-witness:v1\x00"
FILE_KEYS = ("manifest", "audit", "cells", "pairs", "frame", "form_a", "form_b", "seal", "public_summary")
MAX_PRIVATE_REQUEST_BYTES = 8192
MAX_ENDORSEMENT_BYTES = 2048


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read_json(path, limit):
    path = Path(path)
    if not 0 < path.stat().st_size <= limit:
        raise ValueError("REVIEW_REQUIRED: unsupported/private proof size")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("REVIEW_REQUIRED: malformed proof JSON") from exc


def _load_key(path):
    p = Path(path)
    if p.is_symlink():
        raise ValueError("REVIEW_REQUIRED: linked witness key refused")
    metadata = p.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("REVIEW_REQUIRED: witness key must be a regular file")
    if os.name == 'posix' and metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("REVIEW_REQUIRED: witness key permissions too broad")
    key = p.read_bytes()
    if len(key) != 32:
        raise ValueError("REVIEW_REQUIRED: witness key must be exactly 32 bytes")
    return key


def _atomic_new(path, raw, protected=()):
    p = Path(path)
    resolved = p.resolve(strict=False)
    if p.is_symlink() or p.exists() or not p.parent.is_dir() or any(
        resolved == Path(x).resolve(strict=False) for x in protected
    ):
        raise ValueError("REVIEW_REQUIRED: output collides with existing/private input")
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        p.unlink(missing_ok=True)
        raise


def _evidence_files(files):
    if not isinstance(files, dict) or set(files) != set(FILE_KEYS):
        raise ValueError("REVIEW_REQUIRED: incomplete private evidence snapshot")
    return {k: Path(files[k]) for k in FILE_KEYS}


def reverify(files, *, root, operator_key, reviewer_a_id, reviewer_b_id):
    """Run the entire existing V6 source/selection/form gate on current bytes."""
    paths = _evidence_files(files)
    operator_key = Path(operator_key)
    with tempfile.TemporaryDirectory(prefix="cano-witness-reverify-") as tmp:
        independent_summary = Path(tmp) / "new-private-safe-summary.json"
        observed = blind.finalize(
            paths["manifest"], root, paths["audit"], paths["cells"],
            paths["pairs"], paths["frame"], paths["form_a"], paths["form_b"],
            paths["seal"], independent_summary,
            reviewer_a_id=reviewer_a_id, reviewer_b_id=reviewer_b_id,
            operator_key_path=operator_key,
        )
        if independent_summary.read_bytes() != paths["public_summary"].read_bytes():
            raise ValueError("REVIEW_REQUIRED: completed report not reproducible from sealed source")
    if observed.get("field_acceptance") != "NOT_ESTABLISHED":
        raise ValueError("REVIEW_REQUIRED: never infer field acceptance from a witness")
    return observed


def build_request(files, *, root, operator_key, reviewer_a_id, reviewer_b_id, nonce):
    paths = _evidence_files(files)
    if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce):
        raise ValueError("REVIEW_REQUIRED: invalid request nonce")
    observed = reverify(paths, root=root, operator_key=operator_key,
                        reviewer_a_id=reviewer_a_id, reviewer_b_id=reviewer_b_id)
    return {
        "schema": REQUEST_SCHEMA,
        "nonce": nonce,
        "evidence_sha256": {k: _digest(paths[k].read_bytes()) for k in FILE_KEYS},
        "reviewer_alias_commitment": _digest(
            bytes.fromhex(nonce) + b"\x00" + reviewer_a_id.encode("utf-8") +
            b"\x00" + reviewer_b_id.encode("utf-8")
        ),
        "source_decision": observed["source_screen_decision"],
        "combined_decision": observed["decision"],
        "field_acceptance": "NOT_ESTABLISHED",
        "witness_purpose": "record_integrity_not_real_site_authority",
    }


def endorse(request, witness_key):
    """Witness signs a private request *after external human review*, not identity."""
    if not isinstance(witness_key, bytes) or len(witness_key) != 32:
        raise ValueError("REVIEW_REQUIRED: witness HMAC key must be 32 secret bytes")
    if not isinstance(request, dict) or set(request) != {
        "schema", "nonce", "evidence_sha256", "reviewer_alias_commitment",
        "source_decision", "combined_decision", "field_acceptance", "witness_purpose"
    } or request.get("schema") != REQUEST_SCHEMA or request.get("field_acceptance") != "NOT_ESTABLISHED":
        raise ValueError("REVIEW_REQUIRED: unknown/untrusted challenge format")
    if set(request['evidence_sha256']) != set(FILE_KEYS):
        raise ValueError("REVIEW_REQUIRED: incomplete source bundle")
    for digest in list(request['evidence_sha256'].values()) + [request['reviewer_alias_commitment']]:
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError("REVIEW_REQUIRED: invalid evidence commitment")
    if len(request['nonce']) != 32 or any(c not in '0123456789abcdef' for c in request['nonce']):
        raise ValueError("REVIEW_REQUIRED: invalid challenge nonce")
    if request['witness_purpose'] != 'record_integrity_not_real_site_authority':
        raise ValueError("REVIEW_REQUIRED: scope cannot be broadened")
    blob = _canonical(request)
    return {"schema": ENDORSEMENT_SCHEMA,
            "request_sha256": _digest(blob),
            "mac": hmac.new(witness_key, DOMAIN + blob, hashlib.sha256).hexdigest()}


def verify(request, signed, witness_key, fingerprint, *, files, root, operator_key, reviewer_a_id, reviewer_b_id):
    if not isinstance(witness_key, bytes) or len(witness_key) != 32:
        raise ValueError("REVIEW_REQUIRED: witness HMAC key must be 32 secret bytes")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError("REVIEW_REQUIRED: trusted fingerprint missing/invalid")
    if not hmac.compare_digest(_digest(witness_key), fingerprint):
        raise ValueError("REVIEW_REQUIRED: witness trust anchor mismatch")
    if witness_key == Path(operator_key).read_bytes():
        raise ValueError("REVIEW_REQUIRED: witness and operator must not share secret")
    if not isinstance(signed, dict) or set(signed) != {'schema', 'request_sha256', 'mac'} or signed.get('schema') != ENDORSEMENT_SCHEMA:
        raise ValueError("REVIEW_REQUIRED: witness endorsement malformed")
    expected = endorse(request, witness_key)
    if not hmac.compare_digest(_canonical(expected), _canonical(signed)):
        raise ValueError("REVIEW_REQUIRED: witness endorsement invalid")
    fresh = build_request(files, root=root, operator_key=operator_key, reviewer_a_id=reviewer_a_id,
                          reviewer_b_id=reviewer_b_id, nonce=request.get('nonce'))
    if not hmac.compare_digest(_canonical(fresh), _canonical(request)):
        raise ValueError("REVIEW_REQUIRED: source/form/approval snapshot changed after witness")
    return {
        'schema': RESULT_SCHEMA,
        'decision': 'WITNESS_KEYED_INTEGRITY_MATCH_ONLY',
        'source_screen_decision': fresh['source_decision'],
        'combined_decision': fresh['combined_decision'],
        'source_and_blind_review_recomputed': True,
        'witness_key_fingerprint_pinned': True,
        'site_authorization_independently_verified': False,
        'distinct_reviewer_humans_authenticated': False,
        'freshness_or_replay_independently_verified': False,
        'field_acceptance': 'NOT_ESTABLISHED',
        'limits': [
          'A private shared HMAC key verifies possession, not an institutional digital signature.',
          'Fingerprint and secret must be provisioned and protected outside the operator evidence bundle.',
          'Key owner must independently check site authority; software cannot verify custody or identity.',
          'Replay, collusion, sample validity and human independence are not established.',
          'Never use this result to certify measurements or train/test independence.',
        ],
    }


def _arguments(p):
    for key in FILE_KEYS:
        p.add_argument('--'+key.replace('_','-'), type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--operator-key', type=Path, required=True)
    p.add_argument('--reviewer-a-id', required=True)
    p.add_argument('--reviewer-b-id', required=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare',help='Create private challenge after full source re-verification')
    _arguments(p)
    p.add_argument('--request',type=Path,required=True)
    a=sub.add_parser('endorse',help='Witness holds externally provisioned secret; NEVER export it')
    a.add_argument('--request',type=Path,required=True)
    a.add_argument('--witness-key',type=Path,required=True)
    a.add_argument('--endorsement',type=Path,required=True)
    v=sub.add_parser('verify',help='Recheck full source and independently pinned HMAC integrity')
    _arguments(v)
    v.add_argument('--request',type=Path,required=True)
    v.add_argument('--endorsement',type=Path,required=True)
    v.add_argument('--witness-key',type=Path,required=True)
    v.add_argument('--expected-witness-key-sha256',required=True)
    v.add_argument('--output',type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        if opts.command=='endorse':
            request=_read_json(opts.request,MAX_PRIVATE_REQUEST_BYTES)
            key=_load_key(opts.witness_key)
            receipt=endorse(request,key)
            _atomic_new(opts.endorsement, _canonical(receipt)+b'\n',protected=(opts.request,opts.witness_key))
            print('WITNESS_RECORD_SIGNED_ONLY: does NOT independently authenticate institution')
            return 0
        files={k:getattr(opts,k) for k in FILE_KEYS}
        protected=[*files.values(),opts.operator_key]
        if opts.command=='prepare':
            request=build_request(files,root=opts.root,operator_key=opts.operator_key,
                                  reviewer_a_id=opts.reviewer_a_id,reviewer_b_id=opts.reviewer_b_id,
                                  nonce=secrets.token_hex(16))
            _atomic_new(opts.request,_canonical(request)+b'\n',protected=protected)
            print('PREPARED: private witness request only; field acceptance NOT_ESTABLISHED')
            return 0
        key=_load_key(opts.witness_key)
        request=_read_json(opts.request,MAX_PRIVATE_REQUEST_BYTES)
        signed=_read_json(opts.endorsement,MAX_ENDORSEMENT_BYTES)
        result=verify(request,signed,key,opts.expected_witness_key_sha256,
                      files=files,root=opts.root,operator_key=opts.operator_key,
                      reviewer_a_id=opts.reviewer_a_id,reviewer_b_id=opts.reviewer_b_id)
        _atomic_new(opts.output,_canonical(result)+b'\n',protected=protected+[opts.request,opts.witness_key,opts.endorsement])
        print(result['decision']+': site/individual identity NOT_VERIFIED')
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
