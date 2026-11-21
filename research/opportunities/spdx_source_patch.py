"""Pinned MIT upstream source patch; never modifies the vendor repository.

This module obtains the *complete* original Python sources from an immutable
upstream commit, verifies their Git blob hashes, applies exactly two mechanical
source-level fixes, and imports the patched module in an isolated process.

License of upstream source: MIT, copyright (c) 2026 moriwaki.
https://github.com/MoriwakiYusuke/sbom-unifier/blob/main/LICENSE
"""
from __future__ import annotations
import hashlib
import importlib
import os
from pathlib import Path
import sys

import spdx_upstream_acceptance as pinned

ANNOTATION_FRAGMENT = (
    '    if spdx_element_id:\n'
    '        annotation["spdxElementId"] = spdx_element_id\n'
)
RELATION_START = "            # Add parent/child relationship to relationships\n"
RELATION_STOP = "    return new_packages_added, new_relationships_added\n"


def patch_merger_bytes(data: bytes) -> tuple[bytes, dict]:
    """Reject any unexpected source shape; remove only two known upstream defects."""
    text = data.decode('utf-8')
    if text.count(ANNOTATION_FRAGMENT) != 1:
        raise ValueError('upstream annotation marker mismatch')
    if text.count(RELATION_START) != 1 or text.count(RELATION_STOP) != 1:
        raise ValueError('upstream relationship marker mismatch')
    if text.count('def merge_transitive_relationships(') != 1:
        raise ValueError('safe package relationship translator missing')
    # Verify the full exact legacy block, not just a nearby comment.
    a = text.index(RELATION_START)
    b = text.index(RELATION_STOP, a)
    legacy = text[a:b]
    expected_tokens = (
        'if main_package_spdx_id and new_pkg_spdx_id:',
        '"spdxElementId": main_package_spdx_id',
        '"relatedSpdxElement": new_pkg_spdx_id',
        'new_relationships_added += 1',
    )
    if not all(x in legacy for x in expected_tokens):
        raise ValueError('upstream relationship body changed')
    if legacy.count('"spdxElementId": main_package_spdx_id') != 1:
        raise ValueError('unexpected relationship assignment count')
    # Nested annotations inherit their containing element identity.
    # SPDX JSON 2.3.1 schema forbids an additional nested spdxElementId.
    text = text.replace(
        ANNOTATION_FRAGMENT,
        '    # Nested annotations inherit their owner; SPDX 2.3.1 does not\n'
        '    # allow an extra spdxElementId property in this object.\n',
        1,
    )
    a = text.index(RELATION_START)
    b = text.index(RELATION_STOP, a)
    text = (
        text[:a]
        + "            # Do not invent base-main -> new-package edges here.\n"
          "            # merge_transitive_relationships below maps both source endpoints\n"
          "            # to the destination SPDXIDs using verified package PURLs.\n\n"
        + text[b:]
    )
    patched = text.encode('utf-8')
    assert patched != data
    return patched, {
        'upstream_sha256': hashlib.sha256(data).hexdigest(),
        'patched_sha256': hashlib.sha256(patched).hexdigest(),
        'annotation_target_field_removals': 1,
        'parent_rewrite_code_block_removals': 1,
    }


def load_patched(tmp: Path):
    """Download pinned modules, apply source fix before the first import."""
    blobs = {}
    vendor = Path(__file__).resolve().parent / 'vendor'
    offline = vendor.is_dir()
    if os.environ.get('CANO_OFFLINE_ONLY') == '1' and not offline:
        raise ValueError('verified offline vendor directory required')
    blobs['source_mode'] = 'offline_pinned_vendor' if offline else 'network_pinned'
    def source_bytes(relative: str, repo: str, ref: str, expected_blob: str) -> bytes:
        if offline:
            filename = vendor / relative
            if not filename.is_file():
                raise ValueError(f'missing pinned vendor file: {relative}')
            data = filename.read_bytes()
            actual = hashlib.sha1(
                f'blob {len(data)}\0'.encode() + data
            ).hexdigest()
            if actual != expected_blob:
                raise ValueError(f'pinned vendor blob mismatch: {relative}')
            return data
        uri = f'{pinned.SOURCE_BASE}{repo}/{ref}/{relative}'
        return pinned.get_pinned(uri, expected_blob)
    for path, expected_blob in pinned.FILES.items():
        data = source_bytes(path, pinned.UPSTREAM_REPO,
                            pinned.UPSTREAM_COMMIT, expected_blob)
        local = tmp / path.removeprefix('src/')
        local.parent.mkdir(parents=True, exist_ok=True)
        if path.endswith('/merge/merger.py'):
            data, report = patch_merger_bytes(data)
            blobs['source_level_patch'] = report
        local.write_bytes(data)
    for name in ('sbom_unifier/__init__.py','sbom_unifier/merge/__init__.py'):
        (tmp/name).touch()
    schema = source_bytes('schemas/spdx-schema.json', 'spdx/spdx-spec',
                          pinned.SPDX_REF, pinned.SCHEMA_BLOB)
    (tmp/'spdx-schema-v2.3.1.json').write_bytes(schema)
    # This helper is used in a fresh CI process. Never mix original and patched
    # imports under the same Python module name within one process.
    if any(name == 'sbom_unifier' or name.startswith('sbom_unifier.')
           for name in sys.modules):
        raise RuntimeError('module cache already contains an unpinned sbom_unifier')
    sys.path.insert(0,str(tmp))
    merger = importlib.import_module('sbom_unifier.merge.merger')
    return __import__('json').loads(schema), merger, blobs
