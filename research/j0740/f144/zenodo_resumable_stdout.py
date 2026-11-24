#!/usr/bin/env python3
"""Stream an immutable public file to stdout, resuming at exact HTTP byte offsets.

Never accepts a resumed 200 response or mismatching Content-Range. The consumer
must verify the complete published checksum before accepting any data.
"""
import argparse
import re
import sys
import time
from urllib.request import Request, urlopen

DEFAULT_URL = ('https://zenodo.org/records/10519473/files/'
               'psr_J0740%2B6620_with_3p6_Years_of_NICER_Data.tar.gz?download=1')
EXPECTED_SIZE = 12879907825


def connect(url, offset, expected_size, timeout):
    headers={'User-Agent':'J0740-scientific-source-audit/1.0'}
    if offset:
        headers['Range']=f'bytes={offset}-'
    response=urlopen(Request(url,headers=headers),timeout=timeout)
    status=response.status
    if offset:
        if status != 206:
            response.close()
            raise ValueError(f'Range resume rejected: HTTP {status}, offset {offset}')
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
        if not match or int(match.group(1))!=offset or int(match.group(3))!=expected_size:
            response.close()
            raise ValueError('Content-Range source identity or byte offset mismatch')
    elif status != 200:
        response.close()
        raise ValueError(f'Unexpected initial HTTP {status}')
    return response


def stream(url=DEFAULT_URL, expected_size=EXPECTED_SIZE, timeout=120, max_attempts=40):
    offset=0;attempts=0;last_note=0
    while offset < expected_size:
        try:
            with connect(url,offset,expected_size,timeout) as response:
                while offset < expected_size:
                    chunk=response.read1(min(1024*1024,expected_size-offset))
                    if not chunk:
                        raise ConnectionError(f'Early EOF at {offset}/{expected_size}')
                    sys.stdout.buffer.write(chunk)
                    offset+=len(chunk)
                    if offset-last_note>=256*1024*1024:
                        print(f'F144_PUBLIC_STREAM {offset}/{expected_size} bytes',file=sys.stderr,flush=True)
                        last_note=offset
            attempts=0
        except (ValueError, BrokenPipeError):
            raise
        except Exception as exc:
            partial=getattr(exc,'partial',b'')
            if partial:
                sys.stdout.buffer.write(partial)
                offset+=len(partial)
            attempts+=1
            if attempts>max_attempts:
                raise RuntimeError(f'HTTP range resume exhausted at offset {offset}') from exc
            delay=min(attempts*2,20)
            print(f'F144_RESUME offset={offset} attempt={attempts} reason={type(exc).__name__}',file=sys.stderr,flush=True)
            time.sleep(delay)
    sys.stdout.buffer.flush()
    print(f'F144_PUBLIC_STREAM_COMPLETE {offset} bytes',file=sys.stderr,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--url',default=DEFAULT_URL)
    p.add_argument('--expected-size',type=int,default=EXPECTED_SIZE)
    p.add_argument('--probe-range',action='store_true')
    a=p.parse_args()
    if a.probe_range:
        # A one-byte bounded request proves the server supports exact resumes.
        req=Request(a.url,headers={'Range':'bytes=1-1','User-Agent':'J0740-scientific-source-audit/1.0'})
        with urlopen(req,timeout=30) as r:
            if r.status!=206 or r.headers.get('Content-Range')!=f'bytes 1-1/{a.expected_size}' or len(r.read(2))!=1:
                raise ValueError('Original source lacks exact one-byte HTTP range support')
        print('F144_EXACT_HTTP_RANGE_PASS',file=sys.stderr)
    else:
        stream(a.url,a.expected_size)
