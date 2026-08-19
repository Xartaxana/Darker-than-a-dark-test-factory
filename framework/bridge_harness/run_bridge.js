'use strict';

/*
 * ao3-bridge-harness entrypoint (spec-p2-pyramid-bridge N5, docs/tasks/p2-pyramid-bridge.md Р3).
 *
 * Invoked as a subprocess by framework/tests/bridge/conftest.py — NOT a standalone
 * CLI tool, no `npm test` runner behind it (единственная прод-зависимость — jsdom).
 *
 * Subprocess protocol (AT-BUG-079 class — node UTF-8 stdout vs cp1251-locale python
 * subprocess, docs/tasks/p2-pyramid-bridge.md факт 6): list-argv, shell=False,
 * АБСОЛЮТНЫЕ пути, payload — через ФАЙЛЫ (не argv):
 *   argv[2] = путь к request.json  (UTF-8, читается ЭТИМ процессом)
 *   argv[3] = путь к response.json (UTF-8, пишется ЭТИМ процессом, всегда —
 *             happy path и ошибка одинаково несут {"ok": bool, ...})
 * Вызывающий Python ОБЯЗАН читать/декодировать эти файлы с encoding="utf-8" —
 * иначе тихая порча кириллицы на happy path, при этом json.loads не падает
 * (тот же класс, что закрывает AT-BUG-079 для adb-подпроцессов).
 *
 * jsdom-механика (docs/tasks/p2-pyramid-bridge.md, факт 1, Р3):
 *   - runScripts: "outside-only" — фикстурный HTML НЕ исполняет inline <script>
 *     сам; ao3_bridge.js выполняется ЯВНО через `window.eval(bridgeText)` ПОСЛЕ
 *     настройки моков/стабов — тот же порядок, что реальный Android WebView
 *     (onPageFinished -> evaluateJavascript), не автозагрузка.
 *   - pretendToBeVisual: true — даёт window.innerWidth/innerHeight и
 *     requestAnimationFrame; getBoundingClientRect()/scrollHeight у ЛЮБОГО узла
 *     остаются 0 (jsdom не считает layout) — ИМЕННО это и есть fail-open граница
 *     (B4), не баг этого харнесса: layout-гейтированные ветки (infinite-scroll
 *     append-триггер, auto-READ по scrollY/rect) остаются L3, харнесс их не
 *     ассертит (см. framework/tests/bridge/test_layout_fail_open_canary.py).
 *   - jsdom НЕ реализует navigator.clipboard/document.execCommand/fetch — стабы
 *     объявленным контрактом ниже (Р3): управляемые resolve/reject/bool/ответы.
 */

const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

function makeQuietVirtualConsole() {
  // jsdom печатает СОБСТВЕННЫЕ "Not implemented: ..." предупреждения (например
  // навигация формы при submit-событии без preventDefault — реальный AO3-HTML
  // sort_filter_form.mitm несёт такую форму, N5 main-pairing persistence pilot)
  // в Node-консоль по умолчанию — это шум харнесса, не сигнал о падении теста
  // (`omitJSDOMErrors: true` НЕ глушит console.error/warn, вызванный САМИМ
  // ao3_bridge.js/тестовым eval-кодом — те по-прежнему видны при локальном
  // ручном запуске node напрямую).
  const vc = new VirtualConsole();
  vc.forwardTo(console, { omitJSDOMErrors: true });
  return vc;
}

function makeAndroidMock(androidCalls, peekScrollRestoreValue) {
  // Proxy-рекордер (Р3): ЛЮБОЙ Android.<method>(...args) записывается по имени
  // метода — новый вызов, добавленный в ao3_bridge.js, автоматически попадает
  // в androidCalls без правки харнесса. Единственное специальное значение —
  // peekScrollRestore (используется bridge синхронно при init, должно быть
  // числом, не undefined) — управляемо через request.peekScrollRestore,
  // дефолт 0 (Р3: "peekScrollRestore -> 0 по умолчанию").
  return new Proxy({}, {
    get(_target, prop) {
      if (typeof prop === 'symbol') return undefined;
      return function (...args) {
        androidCalls.push({ method: String(prop), args: args });
        if (prop === 'peekScrollRestore') return peekScrollRestoreValue;
        return undefined;
      };
    },
  });
}

function installClipboardStub(window, mode) {
  // Оговорка нормы (Р3, класс BUG-071): этот стаб проверяет JS-ФОЛБЭК бриджа
  // (какую ветку ao3_bridge.js выбирает и что она пишет), а НЕ реальное
  // поведение WebView/системного clipboard-провайдера Android — тот остаётся
  // L3/L4 (device-покрытие BUG-071 не снимается этим харнессом).
  const writeText = function (text) {
    if (mode === 'reject') {
      return Promise.reject(new Error('bridge-harness clipboard stub: rejected (mode=reject)'));
    }
    window.__ao3HarnessClipboardWritten = text;
    return Promise.resolve();
  };
  try {
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText: writeText },
      configurable: true,
    });
  } catch (e) {
    window.navigator.clipboard = { writeText: writeText };
  }
}

function installExecCommandStub(window, result) {
  window.document.execCommand = function () {
    window.__ao3HarnessExecCommandCalled = true;
    return !!result;
  };
}

function installFetchStub(window, fetchResponses) {
  // Управляемые ответы для пагинации (Р3) — карта url -> {status, body}.
  // Непокрытый URL -> reject (не тихий undefined) — тот же принцип честного
  // отказа, что и остальной протокол харнесса.
  window.fetch = function (url) {
    const responses = fetchResponses || {};
    const entry = responses[url];
    if (!entry) {
      return Promise.reject(new Error('bridge-harness fetch stub: no response configured for ' + url));
    }
    const status = entry.status === undefined ? 200 : entry.status;
    const body = entry.body === undefined ? '' : entry.body;
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status: status,
      text: function () { return Promise.resolve(body); },
      json: function () { return Promise.resolve(JSON.parse(body)); },
    });
  };
}

function seedLocalStorage(window, seed) {
  Object.keys(seed || {}).forEach(function (key) {
    window.localStorage.setItem(key, seed[key]);
  });
}

function normalizeEvalResult(raw) {
  // Значение из window.eval() живёт в РЕАЛМЕ jsdom (свои Array/Object) — этот
  // ПРОЦЕСС (Node) сериализует его в план JSON здесь же, ДО записи в
  // response.json, чтобы Python-стороне не приходилось иметь дело с
  // кросс-реалменными объектами. IsArray/JSON.stringify спецификационно
  // кросс-реалм-безопасны, но несериализуемое (функция/DOM-узел/undefined)
  // не должно ронять весь прогон — фолбэк на String(raw).
  if (raw === undefined) return null;
  try {
    return JSON.parse(JSON.stringify(raw));
  } catch (e) {
    return String(raw);
  }
}

function flushMicrotasksAndTimers() {
  // Клик по DEBUG copy-URL кнопке (и вообще любой Promise-based путь бриджа —
  // navigator.clipboard.writeText().then(...)/execCommandFallback) заводит
  // асинхронную цепочку; без явного тика event loop `main()` пишет
  // response.json и завершает процесс ДО того, как её .then/.catch успевают
  // выполниться (наблюдалось эмпирически при разработке — clipboard-стаб в
  // режиме reject молча НЕ доходил до execCommand-фолбэка). setTimeout(0)
  // гарантированно выполняется ПОСЛЕ полного дренажа очереди микрозадач
  // (спецификационное поведение event loop — макрозадача ждёт ВСЕ уже
  // поставленные микрозадачи, включая цепочки .then), поэтому одного тика
  // достаточно для цепочки любой глубины, поставленной синхронно ДО него.
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function runRequest(request) {
  const html = request.html || '<!DOCTYPE html><html><head></head><body></body></html>';
  const url = request.url || 'https://archiveofourown.org/works';
  const bridgeJsPath = request.bridgeJsPath;
  if (!bridgeJsPath || !path.isAbsolute(bridgeJsPath)) {
    throw new Error(
      'request.bridgeJsPath обязателен и должен быть АБСОЛЮТНЫМ путём (получено: ' + bridgeJsPath + ')'
    );
  }
  // Побайтовая идентичность с реально поставляемым скриптом (тот же приём, что
  // framework/steps/bridge_harness_steps.py::_read_bridge_js_text, AT-BUG-067) —
  // без ручного копирования/пересказа логики в этот харнесс.
  const bridgeText = fs.readFileSync(bridgeJsPath, 'utf8');

  const dom = new JSDOM(html, {
    url: url,
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    virtualConsole: makeQuietVirtualConsole(),
  });
  const window = dom.window;

  const androidCalls = [];
  const consoleErrors = [];
  window.addEventListener('error', function (e) {
    consoleErrors.push(e && e.message ? String(e.message) : String(e));
  });

  // window.__ao3* флаги — ДО исполнения bridge-скрипта: читаются один раз при
  // ao3BridgeInit (isDark/isEink/infiniteScroll и т.д. — переменные IIFE,
  // не переопределяемые извне ПОСЛЕ первого исполнения).
  const flags = request.flags || {};
  Object.keys(flags).forEach(function (name) {
    window['__' + name] = flags[name];
  });
  if (flags.ao3AppDark === undefined) window.__ao3AppDark = false;
  if (flags.ao3AppEink === undefined) window.__ao3AppEink = false;

  window.Android = makeAndroidMock(
    androidCalls,
    request.peekScrollRestore === undefined ? 0 : request.peekScrollRestore
  );

  installClipboardStub(window, (request.clipboard || {}).mode || 'resolve');
  installExecCommandStub(window, request.execCommandResult !== false);
  installFetchStub(window, request.fetchResponses);
  seedLocalStorage(window, request.localStorage);

  window.eval(bridgeText);
  await flushMicrotasksAndTimers(); // init (peekScrollRestore/onWorksFound/onWorkPageInfo) тоже может завести промисы

  const results = {};
  for (const action of (request.actions || [])) {
    if (!action || action.type !== 'eval') {
      throw new Error('unknown/missing action.type (only "eval" supported): ' + JSON.stringify(action));
    }
    if (!action.id) {
      throw new Error('action.id обязателен (ключ, под которым результат вернётся в response.results)');
    }
    // eslint-disable-next-line no-eval
    const raw = window.eval(action.code);
    await flushMicrotasksAndTimers();
    results[action.id] = normalizeEvalResult(raw);
  }

  return {
    ok: true,
    androidCalls: androidCalls,
    results: results,
    consoleErrors: consoleErrors,
    clipboardWritten:
      window.__ao3HarnessClipboardWritten === undefined ? null : window.__ao3HarnessClipboardWritten,
    execCommandCalled: window.__ao3HarnessExecCommandCalled === true,
    // Кириллическая канарейка протокола (факт 6, AT-BUG-079 класс) — эхо ровно
    // того, что прислал Python, доказывает целостность round-trip кодировки, а
    // не только "json.loads не упал".
    canaryEcho: request.canary === undefined ? null : request.canary,
  };
}

async function main() {
  const requestPath = process.argv[2];
  const responsePath = process.argv[3];
  if (!requestPath || !responsePath) {
    process.stderr.write('usage: node run_bridge.js <request.json> <response.json>\n');
    process.exit(2);
  }

  // `request` объявлена ВНЕ try (не const внутри блока) — чтобы ветка catch
  // могла эхо-ить request.canary даже когда runRequest() бросает ПОСЛЕ
  // успешного парсинга request.json (Б1, критик-раунд 2, task_id
  // "p2-n5-bridge-harness" accepted 2026-08-19T11:42:52): без canaryEcho на
  // ошибочном ответе Python-сторона (conftest.py::_bridge_call) не могла бы
  // заметить порчу кириллицы round-trip НА пути ошибки, а не только на happy path.
  let request = null;
  let response;
  try {
    const requestText = fs.readFileSync(requestPath, 'utf8');
    request = JSON.parse(requestText);
    response = await runRequest(request);
  } catch (e) {
    response = {
      ok: false,
      error: e && e.message ? String(e.message) : String(e),
      stack: e && e.stack ? String(e.stack) : null,
      canaryEcho: request && request.canary !== undefined ? request.canary : null,
    };
  }

  fs.writeFileSync(responsePath, JSON.stringify(response), 'utf8');
  process.exit(response.ok ? 0 : 1);
}

main();
