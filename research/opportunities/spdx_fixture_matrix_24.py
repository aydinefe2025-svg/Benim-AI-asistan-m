"""24 pinned historical fixtures checked by the *real* SPDX Draft201909 schema.
Unlike the prior JS reconstruction, this runs Python jsonschema on original schema bytes.
"""
from __future__ import annotations
import copy
import jsonschema

B={'SPDXID':'SPDXRef-DOCUMENT','spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0',
 'name':'fixture','documentNamespace':'https://example.org/spdxdocs/fixture-20261111',
 'creationInfo':{'created':'2026-11-11T20:00:00Z','creators':['Tool: CANO Fixture']}}
def package(pid,name,extras=None):return {'SPDXID':pid,'name':name,'downloadLocation':'NOASSERTION',**(extras or {})}
def case(doc, schema_valid, semantic_valid, name):return {'name':name,'doc':doc,'expect_schema_valid':schema_valid,'expect_semantic_valid':semantic_valid}
def mod(doc, **changes):d=copy.deepcopy(doc);d.update(changes);return d

def fixtures():
    P1=package('SPDXRef-A','A');P2=package('SPDXRef-B','B')
    D=mod(B,packages=[P1,P2],relationships=[{'spdxElementId':'SPDXRef-DOCUMENT','relatedSpdxElement':'SPDXRef-A','relationshipType':'DESCRIBES'}, {'spdxElementId':'SPDXRef-A','relatedSpdxElement':'SPDXRef-B','relationshipType':'DEPENDS_ON'}])
    R=D['relationships']
    items=[
    case(B,1,1,'valid_minimal'),case(D,1,1,'valid_packages_relations'),
    case(mod(D,packages=[P1,{**P2,'SPDXID':'SPDXRef-A'}]),1,0,'duplicate_spdxid'),
    case(mod(D,relationships=R+[{'spdxElementId':'SPDXRef-A','relatedSpdxElement':'SPDXRef-MISSING','relationshipType':'DEPENDS_ON'}]),1,0,'dangling_relation'),
    case({k:v for k,v in B.items() if k!='documentNamespace'},0,0,'missing_namespace'),
    case(mod(D,packages=[{**P1,'SPDXID':'INVALID'},P2]),0,0,'malformed_pkg_spdxid'),
    case(mod(B,creationInfo={**B['creationInfo'],'created':'bad-timestamp'}),0,1,'invalid_timestamp'),
    case(mod(B,newField=1),0,1,'unsupported_root_key'),
    case(mod(B,packages=[{'SPDXID':'SPDXRef-A','name':'pkg'}]),0,1,'missing_download_location'),
    case(mod(B,packages=[package('SPDXRef-A','pkg',{'primaryPackagePurpose':'OPERATING_SYSTEM'})]),0,1,'obsolete_purpose'),
    case(mod(B,packages=[package('SPDXRef-A','pkg',{'primaryPackagePurpose':'OPERATING-SYSTEM'})]),1,1,'current_purpose'),
    case(mod(B,spdxVersion='SPDX-6.6'),1,0,'invalid_spdx_version'),
    case(mod(D,relationships=[{'spdxElementId':'SPDXRef-A','relatedSpdxElement':'SPDXRef-B','relationshipType':'NOT_REAL'}]),0,1,'invalid_rel_type'),
    case(mod(B,files=[{'SPDXID':'SPDXRef-X','fileName':'file.c'}]),0,1,'file_no_checksums'),
    case(mod(B,creationInfo={**B['creationInfo'],'created':2026}),0,1,'created_wrong_type'),
    case(mod(B,packages=[package('SPDXRef-A','pkg',{'releaseDate':'2026-99-77'})]),0,1,'bad_release_date'),
    case(mod(B,packages=[package('SPDXRef-A','pkg',{'checksums':[{'algorithm':'SHA256','checksumValue':'x'}]})]),0,1,'invalid_sha256_format'),
    case(mod(B,packages=[]),1,1,'empty_package_list'),
    case(mod(B,relationships=[{'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES'}]),0,0,'rel_missing_target'),
    case(mod(B,files=[{'SPDXID':'SPDXRef-F','fileName':'./f.c','checksums':[],'unexpected':'value'}]),0,1,'file_unknown_key'),
    case(mod(B,packages=[package('SPDXRef-A','A',{'externalRefs':[{'referenceCategory':'PACKAGE-MANAGER','referenceType':'purl','referenceLocator':'pkg:pypi/x@1'}]}),package('SPDXRef-B','B',{'externalRefs':[{'referenceCategory':'PACKAGE-MANAGER','referenceType':'purl','referenceLocator':'pkg:pypi/x@1'}]})]),1,0,'duplicate_purl'),
    case(mod(B,dataLicense='MIT'),1,0,'wrong_datalicense'),
    case(mod(B,creationInfo={'created':'2026-11-11T20:00:00Z'}),0,1,'creators_missing'),
    case(mod(B,relationships=[{'spdxElementId':'SPDXRef-DOCUMENT','relatedSpdxElement':'DocumentRef-X:SPDXRef-A','relationshipType':'DEPENDS_ON'}]),1,0,'external_rel_undeclared'),
    ]
    assert len(items)==24
    return items

def verify(schema):
    jsonschema.Draft201909Validator.check_schema(schema)
    validator=jsonschema.Draft201909Validator(schema)
    rows=[]
    for f in fixtures():
        errors=sorted(e.message for e in validator.iter_errors(f['doc']))
        actual=len(errors)==0
        rows.append({'name':f['name'],'expected_schema_valid':bool(f['expect_schema_valid']),
                     'actual_schema_valid':actual,'passed':actual==bool(f['expect_schema_valid']),
                     'schema_errors':errors})
    return {'total':len(rows),'passed':sum(r['passed'] for r in rows),'cases':rows}
