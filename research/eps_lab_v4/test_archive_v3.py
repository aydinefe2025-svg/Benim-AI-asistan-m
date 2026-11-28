import json, pathlib, threading, http.server, functools
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).parent
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/CANO_EPS_operating_simulator_V3.html'
with sync_playwright() as p:
 b=p.chromium.launch(args=['--no-sandbox']); ctx=b.new_context(accept_downloads=True); page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url)
 page.wait_for_function("document.getElementById('journal').textContent.includes('HAZIR')")
 page.evaluate('async()=>{for(let i=0;i<2050;i++) await document.getElementById("step").onclick()}')
 assert '2050' in page.locator('#info').inner_text()
 page.reload();page.wait_for_function("document.getElementById('info').textContent.includes('2050')")
 page.locator('#fault').select_option('open');page.evaluate('async()=>{for(let i=0;i<5;i++)await document.getElementById("step").onclick()}');assert page.locator('#state').inner_text()=='ALARM'
 for seg,expected in [('1',list(range(1,2049))),('2',list(range(2049,2056)))]:
  page.locator('#segment').fill(seg)
  with page.expect_download() as d: page.locator('#save').click()
  j=json.loads(d.value.path().read_text());assert [x['position'] for x in j['events']]==expected;assert j['segment']==int(seg);assert all(x['control']=='DISABLED' for x in j['events'])
 other=ctx.new_page();other.goto(url);other.wait_for_function("document.getElementById('info').textContent.includes('2055')")
 other.locator('#step').click();other.wait_for_function("document.getElementById('info').textContent.includes('2056')")
 page.locator('#step').click();page.wait_for_function("document.getElementById('journal').textContent.includes('HATA')");assert '2055' in page.locator('#info').inner_text()
 page.reload();page.wait_for_function("document.getElementById('info').textContent.includes('2056')");assert not errors,errors
 old=page.locator('#runid').input_value();page.locator('#reset').click();page.wait_for_function("document.getElementById('info').textContent.includes('Ölçüm 0')")
 page.locator('#runid').fill(old);page.locator('#segment').fill('2')
 with page.expect_download() as d: page.locator('#save').click()
 assert [x['position'] for x in json.loads(d.value.path().read_text())['events']]==list(range(2049,2057))
 print('PASS real Chromium IndexedDB rollover, reload, concurrent tab fail-closed, old session retained')
 b.close()
server.shutdown()
