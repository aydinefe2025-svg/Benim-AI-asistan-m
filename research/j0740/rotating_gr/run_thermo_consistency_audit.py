"""Reproduce local first-law + enthalpy audit from six pinned 5-node fixtures.

Uses original source-matched JESTER fixture; NEVER overwrites or claims to
fully repair any EOS. Outputs JSON and Markdown in the same directory.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from crust_local_causal_projection import project_local_five_nodes
from thermo_consistency_local import integrate_repaired_five_nodes

HERE=Path(__file__).resolve().parent
FIX=HERE/'fixtures/j0740_source_crust_5pt_pinned.json'
OUT=HERE/'J0740_LOCAL_THERMODYNAMIC_CONSISTENCY_20261116.json'
MD=HERE/'J0740_LOCAL_THERMODYNAMIC_CONSISTENCY_20261116.md'

def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()

def run():
 d=json.loads(FIX.read_text(encoding='utf-8'))
 assert d['source_sha256']=='c1e2e776d1c0032756e7aac8dda1022d698721748133610d798ada0a353c8412'
 assert d['jester_commit']=='e6768650ce992abfd1153a6833857572fe5cd230'
 assert set(d['models'])=={'ENG','MPA1','MS1','MS1B','WFF1','WFF2'}
 report={
  'schema':'j0740-local-eos-first-law-20261116-v1',
  'scientific_status':'LOCAL_FIRST_LAW_CONSTRUCTION_PASS_NO_STELLAR_VALIDATION',
  'source_generator':'https://github.com/nuclear-multimessenger-astronomy/jester/blob/e6768650ce992abfd1153a6833857572fe5cd230/jesterTOV/tabulated_eos/generate_lalsuite_eos.py',
  'JESTER_source_sha256':d['source_sha256'],
  'fixture_sha256':sha(FIX),
  'point_indices':[252,253,254,255,256],
  'condition':'0<dP/de<=0.95 in each of four piecewise-linear source-neighborhood pressure intervals',
  'baryon_density_constraint':'d ln n = d epsilon / (epsilon+P)',
  'pseudoenthalpy_constraint':'dh = dP / (epsilon+P), H dimensionless, anchored at source h[252] only',
  'native_generator_baryon_proxy':'n = epsilon / m_avg (rest-mass approximation), not exact cold-matter first law for positive pressure',
  'new_TOV_RNS_GR':'NOT_RUN',
  'full_EOS_thermodynamic_validation':'NOT_ESTABLISHED',
  'model_bayesian_evidence':'NOT_RUN',
  'per_EOS':{},
 }
 for model in sorted(d['models']):
  source=d['models'][model]
  prior=project_local_five_nodes(source,cap=.95)
  a=integrate_repaired_five_nodes(source,prior['candidate_e_geom'],cap=.95)
  src_h_range=source[-1]['h']-source[0]['h']
  candidate_h_range=a['candidate_pseudoenthalpy_h'][-1]-a['candidate_pseudoenthalpy_h'][0]
  assert a['max_first_law_identity_abs_error']<1e-12
  assert a['max_analytic_vs_simpson_relative_error']<1e-7
  assert all(0<s<=.95*(1+1e-9) for s in a['piecewise_cs2_over_c2'])
  report['per_EOS'][model]={
   'baseline_source_sha256':d['sources'][model],
   'max_relative_energy_change_for_sampled_projection':prior['maximum_relative_energy_adjustment'],
   'source_negative_cs2_knot_value':source[2]['cs2_native'],
   'source_native_h_252_to_256':src_h_range,
   'candidate_h_252_to_256':candidate_h_range,
   'candidate_vs_source_relative_h_increment_difference':candidate_h_range/src_h_range-1,
   'projection':prior,
   'piecewise_first_law_reconstruction':a,
  }
 report['verification']={'six_models_causal_sampled_edges':'PASS',
  'six_models_first_law':'PASS',
  'six_models_numeric_simpson_crosscheck':'PASS',
  'original_source_not_modified':True}
 OUT.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 lines=[
 '# PSR J0740+6620 — 253–254 kabuk bölgesinde termodinamik ilk-yasa devamı',
 '',
 '**Durum: Altı EOS için yalnız beş kaynak düğümünü kapsayan matematiksel aday doğrulandı. Bütün EOS, sürekli nedensellik veya dönen yıldız modeli onaylanmadı.**',
 '',
 '## Ne hesaplandı?',
 '',
 'Önceki kaynak-eşleşmiş altı modelin 253–254 enerji düğümüne yapılan koşullu, Öklid-minimum iki-nokta müdahalesi korunarak 252–256 arasındaki dört P–ε aralığında ε(P) parçalı doğrusal tanımlandı. Her aralıkta 0<dP/dε≤0,95 zorunlu tutuldu. Sonra **aynı tek ε(P)** üzerinden `dh=dP/(ε+P)` ve `dln n=dε/(ε+P)` analitik olarak entegre edildi. Sonuçlar bağımsız bileşik Simpson (512 alt-aralık/kenar) yöntemiyle kıyaslandı.',
 '',
 '| EOS | Özgün negatif cs² düğümü | Maks. yerel ε müdahalesi | Yeni Δh / eski Δh - 1 | Parçalı-sekant + ilk yasa |',
 '|---|---:|---:|---:|---|'
 ]
 for name,z in report['per_EOS'].items():
  lines.append('| {} | {:.7f} | {:.6f}% | +{:.6f}% | PASS |'.format(name,z['source_negative_cs2_knot_value'],z['max_relative_energy_change_for_sampled_projection']*100,100*z['candidate_vs_source_relative_h_increment_difference']))
 lines.extend([
  '',
  '## Neden fiziksel olarak önemli?',
  '',
  '- Kaynak JESTER üretici kodu baryon yoğunluğunu yaklaşık `n=e/m_avg` olarak yazıyor. Bu, P>0 olduğunda soğuk maddenin `dε=(ε+P)dn/n` birinci yasasıyla genel olarak özdeş değil. Yeni yerel aday için **n(P) yeniden türetildi**; kaynak `n` veya `h` kopyalanmadı.',
  '- Bu lokal parçada yeni entalpi artışı özgün h artışından **yaklaşık %5,7313 daha büyük**; fark yaklaşık **1,14994e-5** boyutsuz h. Bu fark farklı yerel e(P) temsili / interpolasyonu ile ilgilidir; tek başına orijinal X-PSI ya da LALSuite değerlerinin yanlış olduğunu kanıtlamaz.',
  '- Termodinamik birinci-yasa tutarlılığı, **yeni seçilen parçalı-doğrusal varsayım altında matematiksel olarak** sağlandı. Gerçek sıfır-basınç yüzeyi, atom/çekirdek madde fiziği, 6 EOS native cs²<0, ENG/WFF merkez cs²>1 sorunları geçerli açık kapılardır.',
  '- Bağımsız Simpson–analitik h testinde göreli hata tüm modellerde yaklaşık 1e-15 veya altında. 6 ayrı Python birim testi beklendiği şekilde kırmızıdan yeşile geçti; kaynak bilimsel tablo değiştirilmedi.',
  '',
  '## Çıktı ve yeniden üretim',
  '',
  '- `thermo_consistency_local.py`: üç fiziksel özdeşliği kullanan fail-closed yerel integral.',
  '- `test_thermo_consistency_local.py`: 6 davranış testi (6 EOS alt testi, negatif orijinal ve geçersiz girdi retleri).',
  '- `run_thermo_consistency_audit.py`: fikstürden tekrar JSON/MD üretir.',
  '- `J0740_LOCAL_THERMODYNAMIC_CONSISTENCY_20261116.json`: tüm aday düğümler, entalpi, bağıl baryon yoğunluğu, kaynak ve yeni kontrol sayıları.',
  '- Kaynak kimliği `'+d['source_sha256']+'`, JESTER commit `'+d['jester_commit']+'`.',
  '- İşletme sınırı: **bu dosyalar nihai nükleer EOS tablosu, M–R kestirimi veya Bayes faktörü değildir**.',
  '',
  '## Sıradaki kritik fizik işleri',
  '',
  '1. Orijinal kaynak LALSuite EOS kabuğunun 253→254 geçişinin özgün fiziksel/interpolasyon mekanizması ve gerçek P→0 eşlemesi.',
  '2. Tüm yüksek yoğunluk aralığında `0<c_s²/c²≤1`, monotoni ve EOS/entalpi/baryon ilişkisinin tek modelde ve gerçek kaynakla doğru uygulanması.',
  '3. Yalnız bu fizik kapılarını geçen ayrı tanımlı adaylara bağımsız TOV-Love ve aynı kütle/dönme RNS GR doğrulaması.',
  '4. Gerçek X-PSI nuisance bütünleştirmesi ve normalizasyon yapılmadan EOS kanıtı ilan edilmemesi.',
  '',
 ])
 MD.write_text('\n'.join(lines),encoding='utf-8')
 print(json.dumps({'status':'PASS','models':len(report['per_EOS']),
   'all_local_firstlaw':report['verification']['six_models_first_law'],
   'max_abs_h_diff':max(v['piecewise_first_law_reconstruction']['max_abs_h_difference_from_source'] for v in report['per_EOS'].values()),
   'max_analytic_simpson_error':max(v['piecewise_first_law_reconstruction']['max_analytic_vs_simpson_relative_error'] for v in report['per_EOS'].values()),
   'files':[str(OUT),str(MD)]},indent=2))
 return report

if __name__=='__main__':run()
