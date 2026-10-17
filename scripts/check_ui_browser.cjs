/* Requiere Playwright de desarrollo y navegador instalado; nunca dependencia de producción.
   ECOGUARD_URL=http://127.0.0.1:7860 node scripts/check_ui_browser.cjs
   Opcionales: PLAYWRIGHT_MODULE, CHROMIUM_EXECUTABLE. Usa una cámara sintética. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const out = path.resolve(__dirname, '../docs/evidencias/ui-refinement');
(async () => {
  fs.mkdirSync(out,{recursive:true});
  const report = {status:'pending', physical_mobile:'pending', checks:[]};
  let browser;
  try {
    const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
    browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE || undefined,
      args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    let streamRequests = 0;
    let streamIndex;
    // Gradio envía los siguientes fotogramas por /stream (HTTP o WebSocket).
    page.on('websocket', socket => {
      if (socket.url().includes('/stream/')) socket.on('framesent', () => streamRequests++);
    });
    page.on('request', request => {
      if (request.method() === 'POST' && /\/stream\/[^/]+$/.test(new URL(request.url()).pathname)) streamRequests++;
      if (request.method() !== 'POST' || !request.url().includes('/queue/join')) return;
      try { if (request.postDataJSON()?.fn_index === streamIndex) streamRequests++; } catch {}
    });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(process.env.ECOGUARD_URL || 'http://127.0.0.1:7860');
    const config = await (await page.request.get((process.env.ECOGUARD_URL || 'http://127.0.0.1:7860') + '/config')).json();
    streamIndex = config.dependencies.find(d=>d.api_name==='fotograma').id;
    for (const [name, viewport] of [['desktop',{width:1440,height:1000}],['phone-emulated',{width:390,height:844}]]) {
      await page.setViewportSize(viewport);
      await page.getByRole('tab',{name:'Fotografía',exact:true}).click();
      await page.screenshot({path:path.join(out,`${name}-empty.png`),fullPage:true});
      await page.locator('input[type="file"]').first().setInputFiles(path.resolve(__dirname,'../artifacts/test-original/aire_contaminado/ECO-019.png'));
      await page.getByText('Fotografía lista.',{exact:false}).waitFor();
      await page.getByRole('button',{name:'Analizar imagen',exact:true}).click();
      await page.getByText('Análisis completado.',{exact:false}).waitFor();
      assert.equal(await page.getByRole('meter').count(),3);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+2));
      await page.screenshot({path:path.join(out,`${name}.png`),fullPage:true});
      report.checks.push(`${name}: carga, inferencia, barras, ancho responsive`);
      await page.getByRole('button',{name:'Limpiar',exact:true}).click();
    }
    await page.getByRole('tab',{name:'Cámara',exact:true}).click();
    await page.getByRole('button',{name:'Iniciar análisis',exact:true}).click();
    await page.locator('#live-camera [title="grant webcam access"]').click();
    await page.locator('#live-camera button[aria-label="capture photo"]').click();
    await page.getByText('Resultado actualizado',{exact:false}).waitFor({timeout:20000});
    await page.screenshot({path:path.join(out,'camera-synthetic.png'),fullPage:true});
    const firstRequests = streamRequests;
    // Una segunda actualización verifica el bucle periódico sin exigir una latencia fija.
    const deadline = Date.now() + 20000;
    while (streamRequests <= firstRequests && Date.now() < deadline) await page.waitForTimeout(500);
    assert(streamRequests > firstRequests, 'No llegaron nuevas solicitudes periódicas de fotogramas');
    assert.equal(await page.getByRole('meter').count(),3);
    await page.getByRole('button',{name:'Detener análisis y cámara',exact:true}).click();
    await page.getByText('Análisis detenido.',{exact:false}).waitFor();
    assert(await page.locator('#live-camera video').evaluateAll(videos=>videos.every(v=>!v.srcObject || v.srcObject.getTracks().every(t=>t.readyState==='ended'))));
    report.checks.push('cámara sintética: iniciar, clasificación periódica, detener y liberar tracks');
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({width, height:844});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+2));
      await page.screenshot({path:path.join(out,`camera-${width}.png`),fullPage:true});
    }
    await page.getByRole('tab',{name:'Fotografía',exact:true}).click();
    await page.getByRole('button',{name:'Limpiar',exact:true}).click();
    await page.locator('#eco-photo-empty').waitFor({state:'visible'});
    assert.equal(await page.locator('#eco-preview').isVisible(),false);
    assert.equal(await page.locator('#eco-upload').getByText('Elige un archivo',{exact:false}).count(),1);
    await page.getByText('Resultados guardados',{exact:true}).click();
    await page.getByRole('button',{name:'Actualizar resultados',exact:true}).click();
    await page.getByText('El guardado no está habilitado.',{exact:false}).waitFor();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+2));
    await page.screenshot({path:path.join(out,'history-unavailable.png'),fullPage:true});
    report.checks.push('cámara a 320/390/768 px; limpiar, estado vacío, carga en español e historial no disponible');
    assert.deepEqual(errors,[]);
    report.status='passed';
  } catch(error) {
    report.status='blocked_or_failed'; report.error=error.message;
    process.exitCode=1;
  } finally {
    await browser?.close();
    fs.mkdirSync(out,{recursive:true});
    fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  }
})();
